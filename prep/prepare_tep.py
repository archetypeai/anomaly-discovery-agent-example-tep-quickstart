#!/usr/bin/env python3
"""Stage 1b — cut the Tennessee Eastman Process into AD-shaped datasets.

    python3 prep/prepare_tep.py                       # defaults below
    python3 prep/prepare_tep.py --channels all        # 52 variables instead of 33
    python3 prep/prepare_tep.py --reference-sims 60

Reads the four Rieth et al. (2017) CSVs (Kaggle `afrniomelo/tep-csv`) from
data/raw/ and writes data/prepared/:

    tep_ref_normal_simNNN.csv     reference library, ONE FILE PER SIMULATION —
                                  fault-free training sims, the only thing the
                                  detector is fitted on. The filename carries
                                  `normal`: the fitting runner labels files by
                                  name, so the token has to be there.
    tep_val_normal.csv            held-out fault-free TESTING sims, for the
                                  false-alarm rate and threshold calibration
    tep_eval_slice_0N.csv         one fault-free testing sim + one testing sim per
                                  IDV (160 normal rows -> 800 fault rows each), so
                                  detection delay after onset is measurable
    *_labels.csv                  sidecars: timestamp,label,fault_id,sim,sample
    zscore_stats.json             per-channel mean/std, fitted on REFERENCE ONLY
    prep_report.json              sim assignments, channels, seams, row counts

THE SIMULATION RUN IS THE INDEPENDENCE UNIT. Every run is an independent
realisation (its own noise + disturbance seeds), so no run appears in more than
one role — the analogue of "the bearing" in the Paderborn OSM example.

TIMESTAMPS ARE SYNTHESISED. The CSVs carry only `sample` (1..500 / 1..960) at a
3-minute cadence, so rows get `t = 180 * (sample-1)` seconds within a segment,
and consecutive segments in one file are separated by a SEAM_GAP far larger
than 180 s. The platform's default `sample_rate_interval_tolerance: 0.05` then
marks any window straddling a seam INVALID_STATE instead of splicing two
simulations together — the bearings pattern. Reference files hold one sim each,
so no reference window is ever lost to a seam.

CHANNELS. Default is the standard 33-variable set of the TEP literature:
xmeas_1..22 (continuous process measurements) + xmv_1..11 (manipulated
variables). xmeas_23..41 are composition analysers with 6- and 15-minute
sampling delays — 2- and 5-step staircases at a 3-minute cadence. Channels that
are constant in the reference data are dropped (and reported): a constant
series embeds to a constant and contributes nothing but dimensions.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
OUT = REPO / "data" / "prepared"

FILES = {
    "ff_train": "TEP_FaultFree_Training.csv",
    "ff_test": "TEP_FaultFree_Testing.csv",
    "f_test": "TEP_Faulty_Testing.csv",
}
SAMPLE_S = 180                 # 3-minute cadence
SEAM_GAP_S = 86_400            # one day between concatenated simulations
ONSET_TEST = 160               # fault introduced at sample 160 in testing sims
N_FAULTS = 20
CHANNELS_33 = [f"xmeas_{i}" for i in range(1, 23)] + [f"xmv_{i}" for i in range(1, 12)]
CHANNELS_52 = [f"xmeas_{i}" for i in range(1, 42)] + [f"xmv_{i}" for i in range(1, 12)]
META = ["faultnumber", "simulationrun", "sample"]


def load_sims(name: str, sims: set[int], faults: set[int] | None = None,
              chunksize: int = 500_000) -> pd.DataFrame:
    """Stream one raw CSV, keeping only the requested (fault, sim) rows.

    The faulty testing file is 3.6 GB; a full read is neither needed nor kind.
    """
    path = RAW / FILES[name]
    if not path.exists():
        sys.exit(f"{path} not found — download the Kaggle CSVs into data/raw/")
    keep = []
    for chunk in pd.read_csv(path, chunksize=chunksize):
        m = chunk["simulationrun"].astype(int).isin(sims)
        if faults is not None:
            m &= chunk["faultnumber"].astype(int).isin(faults)
        if m.any():
            keep.append(chunk.loc[m])
    if not keep:
        sys.exit(f"no rows matched in {path.name}")
    df = pd.concat(keep, ignore_index=True)
    df[META] = df[META].astype(int)
    return df.sort_values(META).reset_index(drop=True)


def segment(df: pd.DataFrame, fault: int, sim: int) -> pd.DataFrame:
    seg = df[(df.faultnumber == fault) & (df.simulationrun == sim)]
    if seg.empty:
        sys.exit(f"missing segment fault={fault} sim={sim}")
    return seg.sort_values("sample")


def write_file(path: Path, segments: list[pd.DataFrame], channels: list[str],
               mean: pd.Series, std: pd.Series, labels_path: Path | None,
               source: str) -> dict:
    """Concatenate segments with seam gaps, z-score, write the CSV (+ sidecar)."""
    frames, sidecars, seams = [], [], []
    t0 = 0
    for seg in segments:
        n = len(seg)
        ts = t0 + SAMPLE_S * (seg["sample"].to_numpy() - 1)
        z = (seg[channels] - mean[channels]) / std[channels]
        frame = pd.DataFrame({"timestamp": ts})
        frame = pd.concat([frame, z.reset_index(drop=True)], axis=1)
        frames.append(frame)
        fault = int(seg.faultnumber.iloc[0])
        is_fault = (fault > 0) & (seg["sample"].to_numpy() > ONSET_TEST)
        sidecars.append(pd.DataFrame({
            "timestamp": ts,
            "label": np.where(is_fault, "fault", "normal"),
            "fault_id": f"idv_{fault:02d}",
            "simulationrun": int(seg.simulationrun.iloc[0]),
            "sample": seg["sample"].to_numpy(),
        }))
        end = int(ts[-1])
        seams.append(end)
        t0 = end + SEAM_GAP_S
    seams.pop()  # the last segment end is the file end, not a seam
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(path, index=False, float_format="%.6f")
    if labels_path is not None:
        pd.concat(sidecars, ignore_index=True).to_csv(labels_path, index=False)
    return {"path": str(path.relative_to(REPO)), "rows": len(out),
            "segments": len(segments), "seams": seams,
            "source": source,
            "sims": [[int(s.faultnumber.iloc[0]), int(s.simulationrun.iloc[0])]
                     for s in segments]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--channels", default="33", choices=["33", "all"])
    ap.add_argument("--reference-sims", type=int, default=40,
                    help="fault-free TRAINING sims 1..N fitted on (500 rows each)")
    ap.add_argument("--val-sims", type=int, default=10,
                    help="N fault-free TESTING sims for FAR / threshold, ids starting "
                         "after the reference ids so no role shares a sim id")
    ap.add_argument("--slices", type=int, default=4,
                    help="eval slices; slice s uses testing sim s of every IDV and the "
                         "next fault-free testing sim after the validation ids")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    channels = CHANNELS_33 if args.channels == "33" else CHANNELS_52
    ref_sims = set(range(1, args.reference_sims + 1))
    # Training and testing sims are separate runs (different seeds) even when they
    # share a simulationrun id, but ids are kept disjoint across roles anyway so
    # the separation is unambiguous: reference 1..R (training), validation
    # R+1..R+V (testing), eval fault-free R+V+s (testing).
    val_sims = set(range(args.reference_sims + 1, args.reference_sims + args.val_sims + 1))
    slice_ids = list(range(1, args.slices + 1))
    ff_eval_sims = {s: args.reference_sims + args.val_sims + s for s in slice_ids}

    print(f"reference: fault-free training sims {min(ref_sims)}..{max(ref_sims)}")
    ref = load_sims("ff_train", ref_sims)
    print(f"  {len(ref):,} rows")

    # Z-score on the reference only (fit on train, transform everything).
    mean, std = ref[channels].mean(), ref[channels].std(ddof=0)
    constant = [c for c in channels if std[c] < 1e-9]
    if constant:
        print(f"  dropping {len(constant)} constant channel(s): {constant}")
        channels = [c for c in channels if c not in constant]
    stats = {"fitted_on": f"fault-free training sims 1..{args.reference_sims}",
             "n_rows": int(len(ref)), "channels": channels,
             "mean": {c: float(mean[c]) for c in channels},
             "std": {c: float(std[c]) for c in channels}}
    (OUT / "zscore_stats.json").write_text(json.dumps(stats, indent=2))

    report = {"sample_seconds": SAMPLE_S, "seam_gap_seconds": SEAM_GAP_S,
              "onset_sample_testing": ONSET_TEST, "channels": channels,
              "dropped_constant_channels": constant,
              "reference_files": [], "val_normal": None, "eval_slices": []}

    print("writing reference files (one per sim)...")
    for sim in sorted(ref_sims):
        seg = segment(ref, 0, sim)
        info = write_file(OUT / f"tep_ref_normal_sim{sim:03d}.csv", [seg],
                          channels, mean, std, labels_path=None, source="ff_train")
        report["reference_files"].append(info)
    del ref

    print(f"val_normal: fault-free testing sims {min(val_sims)}..{max(val_sims)}; "
          f"eval fault-free sims {sorted(ff_eval_sims.values())}")
    ff_test = load_sims("ff_test", val_sims | set(ff_eval_sims.values()))
    report["val_normal"] = write_file(
        OUT / "tep_val_normal.csv", [segment(ff_test, 0, s) for s in sorted(val_sims)],
        channels, mean, std, OUT / "tep_val_normal_labels.csv", source="ff_test")
    print(f"  {report['val_normal']['rows']:,} rows, {len(val_sims)} sims")

    print(f"faulty testing sims {slice_ids} for IDV 1..{N_FAULTS} (streaming 3.6 GB)...")
    faulty = load_sims("f_test", set(slice_ids), faults=set(range(1, N_FAULTS + 1)))
    print(f"  {len(faulty):,} rows")
    for s in slice_ids:
        segs = [segment(ff_test, 0, ff_eval_sims[s])]
        segs += [segment(faulty, f, s) for f in range(1, N_FAULTS + 1)]
        info = write_file(OUT / f"tep_eval_slice_{s:02d}.csv", segs, channels,
                          mean, std, OUT / f"tep_eval_slice_{s:02d}_labels.csv",
                          source="ff_test + f_test")
        info["sims"] = [["ff_test" if f == 0 else "f_test", f, sim] for f, sim in info["sims"]]
        report["eval_slices"].append(info)
        print(f"  slice_{s:02d}: {info['rows']:,} rows, {info['segments']} sims, "
              f"{len(info['seams'])} seams")

    (OUT / "prep_report.json").write_text(json.dumps(report, indent=2))
    print(f"\nchannels: {len(channels)}   wrote {OUT.relative_to(REPO)}/"
          f"{{{len(report['reference_files'])} reference files, tep_val_normal, "
          f"{len(slice_ids)} eval slices, zscore_stats.json, prep_report.json}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
