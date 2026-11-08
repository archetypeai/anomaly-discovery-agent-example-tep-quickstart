#!/usr/bin/env python3
"""Stage 2 -- build the (mini) role files the Optimizations and Evals APIs take.

    python3 prep/build_roles.py
    python3 prep/preflight_roles.py      # then check them

A deliberately small version of the TEP scenario, so a first run on Newton takes
minutes, not hours, and every run in it can be named. All 33 sensors are kept;
what shrinks is the number of runs, the faults and the run length.

  library/      tep_library.csv: 5 fault-free training runs (496 rows, 24.8 h
                each), joined with a 1-day gap like the files below. The platform invalidates the
                windows that straddle a gap (fit/atai.py), so no window mixes two
                runs. Optimize `training_examples`, constant `normal`.
  validation/   tep_validation.csv: 4 runs, 24 h each, joined with a 1-day gap:
                2 normal, IDV 1 (feed ratio step: easy), IDV 10 (random feed
                temperature: hard). A `label` column marks `anomaly` from the
                fault's start at hour 8. Optimize `validation_examples`.
  test/         tep_test.csv: 4 different runs of the same kinds. Evals, once.
  delivery/     tep_delivery.csv: 4 more runs of the same kinds, no label column.
  labels/       every validation, test and delivery file's `_labels.csv` sidecar.

No simulation run is in two roles. Values are already z-scored by Stage 1
(prep/prepare_tep.py) with fault-free training statistics, so nothing here
rescales them. Reads data/prepared/, writes data/roles/ and data/roles/manifest.json.
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
PREPARED = REPO / "data" / "prepared"
ROLES = REPO / "data" / "roles"
LABEL = {"normal": "normal", "fault": "anomaly"}

LIBRARY_RUNS = 5              # first N fault-free training runs
LIBRARY_RUN_ROWS = 496        # of each run's 500: a multiple of the step (8), so each run's
                              # windows line up exactly as they would in a file of its own
RUN_SAMPLES = 480             # 24 h at one sample every 3 minutes
SEAM_GAP_S = 86_400           # 1 day between joined runs, as in Stage 1

# (source file under data/prepared/, fault_id, simulation run) for each role.
# IDV 1 is easy to see; IDV 10 swings in and out of the normal band.
ROLE_RUNS = {
    "validation": [("tep_val_normal", "idv_00", 41), ("tep_val_normal", "idv_00", 42),
                   ("tep_eval_slice_01", "idv_01", 1), ("tep_eval_slice_01", "idv_10", 1)],
    "test": [("tep_eval_slice_02", "idv_00", 52), ("tep_eval_slice_03", "idv_00", 53),
             ("tep_eval_slice_02", "idv_01", 2), ("tep_eval_slice_02", "idv_10", 2)],
    "delivery": [("full/tep_full_chunk_001", "idv_00", 96), ("full/tep_full_chunk_002", "idv_00", 344),
                 ("full/tep_full_chunk_001", "idv_01", 26), ("full/tep_full_chunk_001", "idv_10", 26)],
}


def join(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Runs one after another, re-timed so each starts SEAM_GAP_S after the last ends."""
    out, t = [], 0
    for f in frames:
        f = f.copy()
        step = int(f.timestamp.iloc[1] - f.timestamp.iloc[0])
        f["timestamp"] = (t + (f.timestamp - f.timestamp.iloc[0])).astype(int).to_numpy()
        out.append(f)
        t = int(f.timestamp.iloc[-1]) + step + SEAM_GAP_S
    return pd.concat(out, ignore_index=True)


def take(runs: list[tuple[str, str, int]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The first RUN_SAMPLES of each run, re-timed so runs follow each other with a seam gap."""
    data, labels, t = [], [], 0
    cache: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for src, fault, sim in runs:
        if src not in cache:
            cache[src] = (pd.read_csv(PREPARED / f"{src}.csv"), pd.read_csv(PREPARED / f"{src}_labels.csv"))
        d, lab = cache[src]
        pick = ((lab.fault_id == fault) & (lab.simulationrun == sim)).to_numpy()
        dd, ll = d[pick].head(RUN_SAMPLES).copy(), lab[pick].head(RUN_SAMPLES).copy()
        if len(dd) != RUN_SAMPLES:
            raise SystemExit(f"{src}: {fault} sim {sim} has {len(dd)} rows, need {RUN_SAMPLES}")
        step = int(dd.timestamp.iloc[1] - dd.timestamp.iloc[0])
        new_ts = t + (dd.timestamp - dd.timestamp.iloc[0]).astype(int)
        dd["timestamp"], ll["timestamp"] = new_ts.to_numpy(), new_ts.to_numpy()
        data.append(dd)
        labels.append(ll)
        t = int(new_ts.iloc[-1]) + step + SEAM_GAP_S
    return pd.concat(data, ignore_index=True), pd.concat(labels, ignore_index=True)


def main() -> int:
    report = PREPARED / "prep_report.json"
    if not report.exists():
        raise SystemExit(f"{report} not found -- run Stage 1 first (prep/prepare_tep.py)")
    rep = json.loads(report.read_text())

    if ROLES.exists():
        shutil.rmtree(ROLES)     # a clean rebuild: no file from an earlier layout survives
    m = {"label_column": "label", "labels": ["normal", "anomaly"],
         "onset_sample": rep["onset_sample_testing"], "channels": rep["channels"],
         "run_samples": RUN_SAMPLES,
         "library": [], "validation": [], "test": [], "delivery": []}

    (ROLES / "library").mkdir(parents=True)
    refs = rep["reference_files"][:LIBRARY_RUNS]
    lib = join([pd.read_csv(REPO / f["path"]).head(LIBRARY_RUN_ROWS) for f in refs])
    dst = ROLES / "library" / "tep_library.csv"
    lib.to_csv(dst, index=False)
    m["library"].append({"file": str(dst.relative_to(ROLES)), "rows": len(lib),
                         "sims": [s for f in refs for s in f["sims"]],
                         "runs_rows": [LIBRARY_RUN_ROWS] * len(refs)})
    print(f"library: {dst.name} {len(lib):,} rows from {len(refs)} runs, all normal")

    (ROLES / "labels").mkdir()
    for role, runs in ROLE_RUNS.items():
        (ROLES / role).mkdir()
        d, lab = take(runs)
        dst, side = ROLES / role / f"tep_{role}.csv", ROLES / "labels" / f"tep_{role}_labels.csv"
        lab.to_csv(side, index=False)
        entry = {"file": str(dst.relative_to(ROLES)), "labels": str(side.relative_to(ROLES)),
                 "runs": [{"fault_id": f, "simulationrun": s} for _, f, s in runs]}
        if role == "delivery":
            d.to_csv(dst, index=False)     # labels held back in the sidecar
        else:
            d["label"] = lab.label.map(LABEL).to_numpy()
            d.to_csv(dst, index=False, quoting=csv.QUOTE_MINIMAL)
            entry.update(d.label.value_counts().reindex(["normal", "anomaly"], fill_value=0).astype(int).to_dict())
        m[role].append(entry)
        runs_txt = ", ".join(f"{f} sim {s}" for _, f, s in runs)
        print(f"{role}: {dst.name} {len(d):,} rows ({runs_txt})")

    (ROLES / "manifest.json").write_text(json.dumps(m, indent=1) + "\n")
    print(f"wrote {ROLES / 'manifest.json'}; next: python3 prep/preflight_roles.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
