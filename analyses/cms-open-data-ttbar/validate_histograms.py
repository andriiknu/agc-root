# Compare the content of histograms produced by ttbar_analysis_pipeline with a reference file.
# A reference file for N_FILES_MAX_PER_SAMPLE=1 is available in directory `reference/`.

from __future__ import annotations
import argparse
from collections import defaultdict
import json
import numpy as np
import sys
import uproot

order = 3
rtol=float(f'1e-{order}')
atol=1e-3

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--histos", help="ROOT file containing the output histograms. Defaults to './histograms.root'.", default="histograms.root")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--reference", help="JSON reference against which histogram contents should be compared")
    group.add_argument("--dump-json", help="Print JSON representation of histogram contents to screen", action='store_true')
    return parser.parse_args()

# convert uproot file containing only TH1Ds to a corresponding JSON-compatible dict with structure:
# { "histo1": { "edges": [...], "contents": [...] }, "histo2": { ... }, ... }
# Only the highest namecycle for every histogram is considered, and cycles are stripped from the histogram names.
def as_dict(f: uproot.ReadOnlyDirectory) -> dict[str, dict]:
    histos = defaultdict(dict)
    # this assumes that the rightmost ";" (if any) comes before a namecycle
    names = set(k.rsplit(";", 1)[0] for k in f)
    for name in names:
        h = f[name]
        assert isinstance(h, uproot.behaviors.TH1.Histogram)
        histos[name]["edges"] = h.axis().edges().tolist()
        histos[name]["contents"] = h.counts(flow=True).tolist()
    return histos

def validate(histos: dict, reference: dict) -> dict[str, list[str]]:
    errors = defaultdict(list)
    discreps = {}
    for name, ref_h in reference.items():
        if 'pseudodata' in name: continue
        if name not in histos:
            if name+'_nominal' not in histos:
                errors[name].append("Histogram not found.")
                continue
            else:
                name+='_nominal'

        h = histos[name]
        if not np.allclose(h['edges'], ref_h['edges']):
            errors[name].append(f"Edges do not match:\n\tgot      {h['edges']}\n\texpected {ref_h['edges']}")
        contents_depend_on_rng = "pt_res_up" in name # skip checking the contents of these histograms as they are not stable
        if not contents_depend_on_rng and not np.allclose(h['contents'], ref_h['contents'], rtol=rtol,atol=atol):
            errors[name].append(f"Contents do not match:\n\tgot      {h['contents']}\n\texpected {ref_h['contents']}")
            discreps[name]=abs(np.array(ref_h['contents'])-np.array(h['contents']))#/np.array(ref_h['contents'])

    return errors,discreps

if __name__ == "__main__":
    args = parse_args()
    with uproot.open(args.histos) as f:
        histos = as_dict(f)

    if args.dump_json:
        print(json.dumps(histos, indent=2, sort_keys=True))
        sys.exit(0)

    with open(args.reference) as reference:
        ref_histos = json.load(reference)

    print(f"Validating '{args.histos}' against reference '{args.reference}'...")
    errs,discreps = validate(histos=histos, reference=ref_histos)
    if len(errs) == 0:
        print("All good!")
    else:
        for hist_name, errors in errs.items():
            errors = '\n\t'.join(errors)
            print(f"{hist_name}\n\t{errors}")
        print(f'Summary for tolerance {rtol*100}%')
        summary = {k:np.max(v) for k,v in discreps.items()}
        for name, err in summary.items():
            print("{:<50} {:<5}".format(name,err))
            # print(err)
        sys.exit(1)
