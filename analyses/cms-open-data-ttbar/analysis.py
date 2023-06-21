import argparse
import os
from pathlib import Path
from time import time
from typing import Optional

import ROOT
from distributed import Client, LocalCluster, SSHCluster, get_worker
from plotting import save_plots
from utils import (
    AGCInput,
    AGCResult,
    postprocess_results,
    retrieve_inputs,
    save_histos,
)

# Using https://atlas-groupdata.web.cern.ch/atlas-groupdata/dev/AnalysisTop/TopDataPreparation/XSection-MC15-13TeV.data
# as a reference. Values are in pb.
XSEC_INFO = {
    "ttbar": 396.87 + 332.97,  # nonallhad + allhad, keep same x-sec for all
    "single_top_s_chan": 2.0268 + 1.2676,
    "single_top_t_chan": (36.993 + 22.175) / 0.252,  # scale from lepton filter to inclusive
    "single_top_tW": 37.936 + 37.906,
    "wjets": 61457 * 0.252,  # e/mu+nu final states
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--n-max-files-per-sample",
        "-n",
        help="How many files per sample will be processed (if absent, all files for all samples).",
        type=int,
    )
    p.add_argument(
        "--data-cache",
        "-d",
        help="Use the specified directory as a local data cache: required input datasets will be downloaded here and the analysis will read this local copy of the data.",
    )
    p.add_argument(
        "--remote-data-prefix",
        help="""The original data is stored at 'https://xrootd-local.unl.edu:1094//store/user/AGC'.
                If this option is passed, that prefix is replaced with the argument to this option when accessing
                remote data. For example for the version of the input datasets stored on EOS use
                `--remote-data-prefix='root://eoscms.cern.ch//eos/cms/store/test/agc'`.""",
    )
    p.add_argument(
        "--output",
        "-o",
        help="Name of the file where analysis results will be stored. If it already exists, contents are overwritten.",
        default="histograms.root",
    )
    p.add_argument(
        "--scheduler",
        "-s",
        help="""The scheduler for RDataFrame parallelization. Will honor the --ncores flag.
                The default is `mt`, i.e. multi-thread execution.
                If dask-ssh, a list of worker node hostnames to connect to should be provided via the --nodes option.""",
        default="mt",
        choices=["mt", "dask-local", "dask-ssh"],
    )
    p.add_argument(
        "--ncores",
        "-c",
        help=(
            "Number of cores to use. In case of distributed execution this is the amount of cores per node."
        ),
        default=len(os.sched_getaffinity(0)),
        type=int,
    )
    p.add_argument(
        "--npartitions",
        help="Number of data partitions. Only used in case of distributed execution. By default it follows RDataFrame defaults.",
        type=int,
    )
    p.add_argument(
        "--hosts",
        help="A comma-separated list of worker node hostnames. Only required if --scheduler=dask-ssh, ignored otherwise.",
    )
    p.add_argument("-v", "--verbose", help="Turn on verbose execution logs.", action="store_true")

    return p.parse_args()


def create_dask_client(scheduler: str, ncores: int, hosts: str) -> Client:
    """Create a Dask distributed client."""
    if scheduler == "dask-local":
        lc = LocalCluster(n_workers=ncores, threads_per_worker=1, processes=True)
        return Client(lc)

    if scheduler == "dask-ssh":
        workers = hosts.split(",")
        print(f"Using worker nodes: {workers=}")
        # The creation of the SSHCluster object might need to be further configured to fit specific use cases.
        # For example, in some clusters the "local_directory" key must be supplied in the worker_options dictionary.
        sshc = SSHCluster(
            workers,
            connect_options={"known_hosts": None},
            worker_options={"nprocs": ncores, "nthreads": 1, "memory_limit": "32GB"},
        )
        return Client(sshc)

    raise ValueError(
        f"Unexpected scheduling mode '{scheduler}'. Valid modes are ['dask-local', 'dask-ssh']."
    )


def make_rdf(
    files: list[str], client: Optional[Client], npartitions: Optional[int]
) -> ROOT.RDataFrame:
    """Construct and return a dataframe or, if a dask client is present, a distributed dataframe."""
    if client is not None:
        d = ROOT.RDF.Experimental.Distributed.Dask.RDataFrame(
            "Events", files, daskclient=client, npartitions=npartitions
        )
        d._headnode.backend.distribute_unique_paths(
            [
                "helpers.cpp",
            ]
        )
        return d

    return ROOT.RDataFrame("Events", files)


def define_trijet_mass(df: ROOT.RDataFrame) -> ROOT.RDataFrame:
    """Add the trijet_mass observable to the dataframe after applying the appropriate selections."""

    # First, select events with at least 2 b-tagged jets
    df = df.Filter("Sum(Jet_btagCSVV2[Jet_pt_mask]>=0.5)>1")

    # Build four-momentum vectors for each jet
    df = (  
        df.Define(
        "Jet_p4",
        """
        "ROOT::VecOps::Construct<ROOT::Math::PxPyPzMVector>(
            ROOT::VecOps::Construct<ROOT::Math::PtEtaPhiMVector>(
                Jet_pt[Jet_pt_mask], Jet_eta[Jet_pt_mask], Jet_phi[Jet_pt_mask], Jet_mass[Jet_pt_mask]
            )
        )"
        """,
        )
    )

    # Build trijet combinations
    df = df.Define("Trijet", "ROOT::VecOps::Combinations(Jet_pt[Jet_pt_mask],3)")
    df = df.Define("nTrijet", "Trijet[0].size()")

    # Assign four-momentums to each trijet combination
    df = df.Define(
        "Trijet_p4",
        """
        ROOT::RVec<ROOT::Math::PxPyPzMVector> Trijet_p4(ntrijet);
        for (int i = 0; i < nTrijet; ++i)
        {
            int j1 = Trijet[0][i];
            int j2 = Trijet[1][i];
            int j3 = Trijet[2][i];
            Trijet_p4[i] = Jet_p4[j1] + Jet_p4[j2] + Jet_p4[j3];
        }
        return Trijet_p4;
        """,
    )

    # Get trijet transverse momentum values from four-momentum vectors
    df = df.Define(
        "Trijet_pt",
        "return ROOT::VecOps::Map(Trijet_p4, [](ROOT::Math::PxPyPzMVector v) { return v.Pt(); })",
    )

    # trijet_btag is a helpful array of bool values indicating whether or not the maximum btag value in trijet is larger than 0.5 threshold
    df = df.Define(
        "Trijet_btag",
        """
        ROOT::RVecB btag(nTrijet);
        for (int i = 0; i < nTrijet; ++i)
        {
            int j1 = Trijet[0][i];
            int j2 = Trijet[1][i];
            int j3 = Trijet[2][i];
            btag[i] = std::max({Jet_btagCSVV2[j1], Jet_btagCSVV2[j2], Jet_btagCSVV2[j3]}) > 0.5;
        }
        return btag;
        """,
    )

    # Evaluate mass of trijet with maximum pt and btag higher than threshold
    df = df.Define(
        "Trijet_mass",
        """
        double mass{};
        double Pt{};
        double indx{};
        for (int i = 0; i < nTrijet; ++i) {
            if ((Pt < Trijet_pt[i]) && (Trijet_btag[i])) {
                Pt = Trijet_pt[i];
                indx = i;
            }
        }
        mass = Trijet_p4[indx].M();
        return mass;
        """,
    )

    return df


def book_histos(
    df: ROOT.RDataFrame,
    process: str,
    variation: str,
    nevents: int,
) -> list[AGCResult]:
    """Return the RDataFrame results pertaining to the desired process and variation."""
    # Calculate normalization for MC
    x_sec = XSEC_INFO[process]
    lumi = 3378  # /pb
    xsec_weight = x_sec * lumi / nevents
    df = df.Define("weights", str(xsec_weight))  # default weights

    if variation == "nominal":
        # Jet_pt variations definition
        # pt_scale_up() and pt_res_up(jet_pt) return scaling factors applying to jet_pt
        # pt_scale_up() - jet energy scaly systematic
        # pt_res_up(jet_pt) - jet resolution systematic
        df = df.Vary(
            "Jet_pt",
            "ROOT::RVec<ROOT::RVecF>{Jet_pt*pt_scale_up(), Jet_pt*jet_pt_resolution(Jet_pt.size())}",
            ["pt_scale_up", "pt_res_up"],
        )

        if process == "wjets":
            # Flat weight variation definition
            df = df.Vary(
                "Weights",
                "Weights*flat_variation()",
                [f"scale_var_{direction}" for direction in ["up", "down"]],
            )

    # Event selection - the core part of the algorithm applied for both regions
    # Selecting events containing at least one lepton and four jets with pT > 25 GeV
    # Applying requirement at least one of them must be b-tagged jet (see details in the specification)
    df = (
        df.Define("Electron_pt_mask", "Electron_pt>25")
        .Define("Muon_pt_mask", "Muon_pt>25")
        .Define("Jet_pt_mask", "Jet_pt>25")
        .Filter("Sum(Electron_pt_mask) + Sum(Muon_pt_mask) == 1")
        .Filter("Sum(Jet_pt_mask) >= 4")
        .Filter("Sum(Jet_btagCSVV2[Jet_pt_mask]>=0.5)>=1")
    )

    # b-tagging variations for nominal samples
    if variation == "nominal":
        df = df.Vary(
            "Weights",
            "ROOT::RVecD{Weights*btag_weight_variation(Jet_pt[Jet_pt_mask])}",
            [
                f"{weight_name}_{direction}"
                for weight_name in [f"btag_var_{i}" for i in range(4)]
                for direction in ["up", "down"]
            ],
        )

    # Define HT observable for the 4j1b region
    # Only one b-tagged region required
    # The observable is the total transvesre momentum
    # fmt: off
    df4j1b = df.Filter("Sum(Jet_btagCSVV2[Jet_pt_mask]>=0.5)==1")\
               .Define("HT", "Sum(Jet_pt[Jet_pt_mask])")
    # fmt: on

    # Define trijet_mass observable for the 4j2b region (this one is more complicated)
    df4j2b = define_trijet_mass(df)

    # Book histograms and, if needed, their systematic variations
    results = []
    for df, observable, region in zip([df4j1b, df4j2b], ["HT", "Trijet_mass"], ["4j1b", "4j2b"]):
        histo_model = ROOT.RDF.TH1DModel(
            name=f"{region}_{process}_{variation}", title=process, nbinsx=25, xlow=50, xup=550
        )
        histo = df.Histo1D(histo_model, observable, "Weights")
        print(f"Booked histogram {histo_model.fName}")
        if variation == "nominal":
            if type(histo).__name__ == "ActionProxy":
                result = ROOT.RDF.Experimental.Distributed.VariationsFor(histo)
            else:
                result = ROOT.RDF.Experimental.VariationsFor(histo)
            results.append(AGCResult(result, region, process, variation))
        else:
            results.append(AGCResult(histo, region, process, variation))

    # Return the booked results
    # Note that no event loop has run yet at this point (RDataFrame is lazy)
    return results


def load_cpp():
    """Load C++ helper functions. Works for both local and distributed execution."""
    try:
        localdir = get_worker().local_directory
        cpp_source = Path(localdir) / "helpers.cpp"
    except ValueError:
        # must be local execution
        cpp_source = "helpers.cpp"

    ROOT.gSystem.CompileMacro(cpp_source, "kO")


def main() -> None:
    program_start = time()
    args = parse_args()

    # Do not add histograms to TDirectories automatically: we'll do it ourselves as needed.
    ROOT.TH1.AddDirectory(False)

    if args.verbose:
        # Set higher RDF verbosity for the rest of the program.
        # To only change the verbosity in a given scope, use ROOT.Experimental.RLogScopedVerbosity.
        ROOT.Detail.RDF.RDFLogChannel.SetVerbosity(ROOT.Experimental.ELogLevel.kInfo)

    if args.scheduler == "mt":
        # Setup for local, multi-thread RDataFrame
        ROOT.EnableImplicitMT(args.ncores)
        print(f"Number of threads: {ROOT.GetThreadPoolSize()}")
        client = None
        load_cpp()
    else:
        # Setup for distributed RDataFrame
        client = create_dask_client(args.scheduler, args.ncores, args.hosts)
        ROOT.RDF.Experimental.Distributed.initialize(load_cpp)

    # Book RDataFrame results
    inputs: list[AGCInput] = retrieve_inputs(
        args.n_max_files_per_sample, args.remote_data_prefix, args.data_cache
    )
    results: list[AGCResult] = []
    for input in inputs:
        df = make_rdf(input.paths, client, args.npartitions)
        results += book_histos(df, input.process, input.variation, input.nevents)
    print(f"Building the computation graphs took {time() - program_start:.2f} seconds")

    # Run the event loops for all processes and variations here
    run_graphs_start = time()
    # FIXME isinstance(h, RResultPtr) does not work for distRDF
    handles = [r.histo for r in results if isinstance(r.histo, ROOT.RDF.RResultPtr[ROOT.TH1D])]
    ROOT.RDF.RunGraphs(handles)
    print(f"Executing the computation graphs took {time() - run_graphs_start:.2f} seconds")
    if client is not None:
        client.close()

    results = postprocess_results(results)
    save_plots(results)
    save_histos([r.histo for r in results], output_fname=args.output)
    print(f"Result histograms saved in file {args.output}")


if __name__ == "__main__":
    main()
