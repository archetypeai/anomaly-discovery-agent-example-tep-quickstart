#!/usr/bin/env python3
"""Stage 1b — cut the delivery: a few more 48-hour runs, in slice-shaped chunks.

    python3 prep/prepare_full_eval.py                          # budget B: all fault-free + 25 runs/IDV
    python3 prep/prepare_full_eval.py --runs-per-idv 5         # budget A-ish, quick
    python3 prep/prepare_full_eval.py --runs-per-idv all       # budget C: every remaining simulation

THE POOL is every 48-hour-set simulation that has no role yet — read from
prep_report.json, never hard-coded:

    TEP_FaultFree_Testing   500 sims minus validation (41–50) and eval (51–54)  -> 486
    TEP_Faulty_Testing      500 runs per IDV minus the eval slices' runs 1–4     -> 496 per IDV

Nothing from the reference file (`FaultFree_Training`) or the 25-hour faulty set
is touched: the former is what the detector was fitted on, the latter has a
1-hour normal prefix that would mix onset conventions.

CHUNKS have the same shape as the eval slices so every downstream script runs
unchanged: 21 simulations per file — one fault-free run followed by one run of
each IDV 1–20 (160 normal -> 800 fault rows) — with the same 86,400 s seams and
the same `_labels.csv` sidecar. Fault-free sims left over after pairing are
packed into normal-only chunks of 21. Run ids are drawn with a seed so the draw
is reproducible; the SAME run ids are used for every IDV in a chunk.

Writes data/prepared/full/tep_full_chunk_NNN.csv (+ _labels.csv) and
data/prepared/full/full_report.json.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd

from prepare_tep import N_FAULTS, OUT as PREPARED, REPO, load_sims, segment, write_file

FULL = PREPARED / "full"
SIMS_PER_FILE = 21


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs-per-idv", default="4",
                    help="faulty runs per IDV to include, or 'all' (496)")
    ap.add_argument("--ff-sims", default="4",
                    help="fault-free sims to include, or 'all' (486)")
    ap.add_argument("--seed", type=int, default=20260916)
    ap.add_argument("--batch", type=int, default=25,
                    help="faulty runs streamed from the 3.6 GB file per pass")
    args = ap.parse_args()

    report = json.loads((PREPARED / "prep_report.json").read_text())
    stats = json.loads((PREPARED / "zscore_stats.json").read_text())
    channels = report["channels"]
    mean = pd.Series(stats["mean"])
    std = pd.Series(stats["std"])

    # -- the pool: everything in the 48-hour set without a role --------------------
    used_ff = {s[-1] for s in report["val_normal"]["sims"]}
    used_faulty_runs = set()
    for sl in report["eval_slices"]:
        for s in sl["sims"]:
            src, fault, run = s
            (used_ff if fault == 0 else used_faulty_runs).add(run)
    pool_ff = sorted(set(range(1, 501)) - used_ff)
    pool_runs = sorted(set(range(1, 501)) - used_faulty_runs)
    print(f"pool: {len(pool_ff)} fault-free sims (excl. {sorted(used_ff)}), "
          f"{len(pool_runs)} runs per IDV (excl. runs {sorted(used_faulty_runs)})")

    rng = random.Random(args.seed)
    n_runs = len(pool_runs) if args.runs_per_idv == "all" else int(args.runs_per_idv)
    n_ff = len(pool_ff) if args.ff_sims == "all" else int(args.ff_sims)
    runs = sorted(rng.sample(pool_runs, n_runs))
    ff = sorted(rng.sample(pool_ff, n_ff))
    if n_ff < n_runs:
        print(f"note: {n_runs} faulty chunks but {n_ff} fault-free sims — the last "
              f"{n_runs - n_ff} faulty chunks carry no fault-free sim (their 160-row "
              f"normal prefixes still feed the false-alarm denominator)")

    FULL.mkdir(parents=True, exist_ok=True)
    ff_df = load_sims("ff_test", set(ff))
    chunks = []
    ff_iter = iter(ff)

    # -- faulty chunks: 1 fault-free + run r of every IDV ---------------------------
    for b in range(0, len(runs), args.batch):
        batch = runs[b:b + args.batch]
        print(f"streaming faulty runs {batch[0]}..{batch[-1]} ({len(batch)} runs x {N_FAULTS} IDVs)...")
        faulty = load_sims("f_test", set(batch), faults=set(range(1, N_FAULTS + 1)))
        for r in batch:
            ff_sim = next(ff_iter, None)
            segs = [segment(ff_df, 0, ff_sim)] if ff_sim is not None else []
            segs += [segment(faulty, f, r) for f in range(1, N_FAULTS + 1)]
            idx = len(chunks) + 1
            info = write_file(FULL / f"tep_full_chunk_{idx:03d}.csv", segs, channels, mean, std,
                              FULL / f"tep_full_chunk_{idx:03d}_labels.csv", source="ff_test + f_test")
            info["sims"] = [["ff_test" if f == 0 else "f_test", f, s] for f, s in info["sims"]]
            chunks.append(info)
        del faulty

    # -- normal-only chunks from the remaining fault-free sims -------------------------
    rest = list(ff_iter)
    for i in range(0, len(rest), SIMS_PER_FILE):
        group = rest[i:i + SIMS_PER_FILE]
        idx = len(chunks) + 1
        info = write_file(FULL / f"tep_full_chunk_{idx:03d}.csv",
                          [segment(ff_df, 0, s) for s in group], channels, mean, std,
                          FULL / f"tep_full_chunk_{idx:03d}_labels.csv", source="ff_test")
        info["sims"] = [["ff_test", f, s] for f, s in info["sims"]]
        chunks.append(info)

    rows = sum(c["rows"] for c in chunks)
    out = {"seed": args.seed, "runs_per_idv": n_runs, "fault_free_sims": n_ff,
           "faulty_runs": runs, "fault_free_ids": ff, "excluded_fault_free": sorted(used_ff),
           "excluded_runs": sorted(used_faulty_runs), "chunks": chunks, "rows": rows}
    (FULL / "full_report.json").write_text(json.dumps(out, indent=1))
    print(f"\nwrote {len(chunks)} chunks ({n_runs} faulty + {len(chunks) - n_runs} normal-only), "
          f"{rows:,} rows, to {FULL.relative_to(REPO)}/  — at ~56 rows/s that is "
          f"~{rows / 56 / 3600:.1f} h of platform time at step 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
