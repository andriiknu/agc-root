import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union
from urllib.request import urlretrieve

import ROOT
from tqdm import tqdm

# Declare a Slice helper C++ function
ROOT.gInterpreter.Declare(
    """
TH1D Slice(TH1D &h, double low_edge, double high_edge)
{
   int xfirst = h.FindBin(low_edge);
   int xlast = h.FindBin(high_edge);

   // do slice in xfirst:xlast including xfirst and xlast
   TH1D res(h.GetName(), h.GetTitle(), xlast - xfirst,
            h.GetXaxis()->GetBinLowEdge(xfirst), h.GetXaxis()->GetBinUpEdge(xlast - 1));
   // note that histogram arrays are : [ undeflow, bin1, bin2,....., binN, overflow]
   std::copy(h.GetArray() + xfirst, h.GetArray() + xlast, res.GetArray() + 1);
   // set correct underflow/overflows
   res.SetBinContent(0, h.Integral(0, xfirst - 1));                              // set underflow value
   res.SetBinContent(res.GetNbinsX() + 1, h.Integral(xlast, h.GetNbinsX() + 1)); // set overflow value

   return res;
}
"""
)


@dataclass
class AGCInput:
    paths: list[str]  # paths, http urls or xrootd urls of the input files
    process: str
    variation: str
    nevents: int  # total number of events for the sample


@dataclass
class AGCResult:
    histo: Union[
        ROOT.TH1D, ROOT.RDF.RResultPtr[ROOT.TH1D], ROOT.RDF.Experimental.RResultMap[ROOT.TH1D]
    ]
    region: str
    process: str
    variation: str


def _tqdm_urlretrieve_hook(t: tqdm):
    """From https://github.com/tqdm/tqdm/blob/master/examples/tqdm_wget.py ."""
    last_b = [0]

    def update_to(b=1, bsize=1, tsize=None):
        """
        b  : int, optional
            Number of blocks transferred so far [default: 1].
        bsize  : int, optional
            Size of each block (in tqdm units) [default: 1].
        tsize  : int, optional
            Total size (in tqdm units). If [default: None] or -1,
            remains unchanged.
        """
        if tsize not in (None, -1):
            t.total = tsize
        displayed = t.update((b - last_b[0]) * bsize)
        last_b[0] = b
        return displayed

    return update_to


def _cache_files(file_paths: list, cache_dir: str, remote_prefix: str):
    for url in file_paths:
        out_path = Path(cache_dir) / url.removeprefix(remote_prefix).lstrip("/")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if not out_path.exists():
            with tqdm(
                unit="B", unit_scale=True, unit_divisor=1024, miniters=1, desc=out_path.name
            ) as t:
                urlretrieve(url, out_path.absolute(), reporthook=_tqdm_urlretrieve_hook(t))


def retrieve_inputs(
    max_files_per_sample: Optional[int],
    remote_data_prefix: Optional[str],
    data_cache: Optional[str],
    input_json: Path = Path("ntuples.json"),
) -> list[AGCInput]:
    """Return a dictionary of file paths and a corresponding dictionary of event counts.
    Both are 2-level dictionaries: there is a dictionary per process per variation.
    Each files[process][variation] corresponds to a list of input files.
    nevts[process][variation] is the total number of events for that sample.
    """
    with open(input_json) as f:
        input_spec = json.load(f)

    input_files: list[AGCInput] = []

    for process, process_spec in input_spec.items():
        if process == "data":
            continue  # skip data

        for variation, sample_info in process_spec.items():
            sample_info = sample_info["files"]  # this is now a list of (filename, nevents) tuples

            if max_files_per_sample is not None:
                sample_info = sample_info[:max_files_per_sample]

            file_paths = [f["path"] for f in sample_info]
            prefix = "https://xrootd-local.unl.edu:1094//store/user/AGC"
            assert all(f.startswith(prefix) for f in file_paths)

            if remote_data_prefix is not None:
                old_prefix, prefix = prefix, remote_data_prefix
                file_paths = [f.replace(old_prefix, prefix) for f in file_paths]

            if data_cache is not None:
                _cache_files(file_paths, data_cache, prefix)
                old_prefix, prefix = prefix, str(Path(data_cache).absolute())
                file_paths = [f.replace(old_prefix, prefix) for f in file_paths]

            nevents = sum(f["nevts"] for f in sample_info)
            input_files.append(AGCInput(file_paths, process, variation, nevents))

    return input_files


def postprocess_results(results: list[AGCResult]):
    """Extract TH1D objects from list of RDF's ResultPtrs and RResultMaps.
    The function also gives appropriate names to each varied histogram and slices them and rebins them as needed.
    """

    # Substitute RResultPtrs and RResultMaps of histograms to actual histograms
    new_results = []
    for res in results:
        if isinstance(res.histo, ROOT.RDF.RResultPtr[ROOT.TH1D]):
            # just extract the histogram from the RResultPtr
            h = res.histo.GetValue()
            new_results.append(AGCResult(h, res.region, res.process, res.variation))
        else:
            resmap = res.histo
            assert isinstance(resmap, ROOT.RDF.Experimental.RResultMap[ROOT.TH1D])
            # extract each histogram in the map
            for variation in resmap.GetKeys():
                h = resmap[variation]
                # strip the varied variable name: it's always 'weights'
                variation_name = str(variation).split(":")[-1]
                new_name = h.GetName().replace("nominal", variation_name)
                h.SetName(new_name)
                new_results.append(AGCResult(h, res.region, res.process, variation_name))

    return new_results


# Apply slicing and rebinning similar to the reference implementation
def slice_and_rebin(h: ROOT.TH1D) -> ROOT.TH1D:
    return ROOT.Slice(h, 120.0, 550.0).Rebin(2)


def save_histos(results: list[ROOT.TH1D], output_fname: str):
    with ROOT.TFile.Open(output_fname, "recreate") as out_file:
        for result in results:
            out_file.WriteObject(slice_and_rebin(result), result.GetName())