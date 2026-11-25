#!/usr/bin/env python3
"""Stage 7 — score downloaded AD outputs against the TEP labels. Offline.

    python3 fit/evaluate_detection.py \
        --platform-output eval_out/ad-output-eval_slice_02.csv \
                          eval_out/ad-output-eval_slice_03.csv \
                          eval_out/ad-output-eval_slice_04.csv \
        --val-output eval_out/ad-output-val_normal.csv --threshold 1.5

No API key, no network. Reads the platform's per-window rows
(`finish_timestamp, start_timestamp, predicted_label, invalid, anomaly_score`),
drops INVALID windows (seams), joins each window to the label of its END row,
and reports — per IDV, pooled over slices —

    detection rate    fraction of post-onset windows over the threshold
    sims detected     runs with a sustained crossing (`--sustain` consecutive)
    delay             hours from fault onset to that first sustained crossing
    AUROC             fault windows vs every normal window, threshold-free

plus the false-alarm rate on normal windows (fault-free sims + pre-onset rows).

Two thresholds are reported when `--val-output` is given: the detector's own
(`--threshold`, the value baked into the artifact) and one CALIBRATED on the
held-out normal run to a target false-alarm rate (`--far`). The second is the
literature's convention and is what makes the PCA side-by-side fair — both
detectors are then read at the same FAR.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tep_common import (REPO, calibrate_threshold, format_table, jsonable, load_baseline,
                        load_labels, pool, series_metrics)

NAME_RE = re.compile(r"(eval_slice_\d\d|val_normal|full_chunk_\d+)")


def read_output(path: Path):
    """(finish_timestamps, scores, n_invalid) from a platform output CSV."""
    ts, score, invalid = [], [], 0
    with open(path) as fh:
        for row in csv.DictReader(fh):
            if str(row.get("invalid", "false")).lower() == "true" \
                    or row.get("predicted_label") == "INVALID_STATE":
                invalid += 1
                continue
            t = row.get("finish_timestamp") or row.get("timestamp")
            ts.append(int(float(t)))
            score.append(float(row["anomaly_score"]))
    return np.array(ts, dtype=np.int64), np.array(score), invalid


def target_of(path: Path) -> str:
    m = NAME_RE.search(path.stem)
    if not m:
        raise SystemExit(f"cannot infer the slice from '{path.name}' — name outputs "
                         f"like ad-output-eval_slice_02.csv")
    return m.group(1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--platform-output", nargs="+", type=Path, required=True)
    ap.add_argument("--val-output", type=Path, default=None,
                    help="AD output for tep_val_normal.csv — calibrates the FAR threshold")
    ap.add_argument("--threshold", type=float, default=None,
                    help="the detector's own threshold (from the artifact / fit record)")
    ap.add_argument("--far", type=float, default=0.01)
    ap.add_argument("--sustain", type=int, default=3)
    ap.add_argument("--baseline", type=Path, default=None,
                    help="fit/out/baseline_pca.json (default) for the side-by-side")
    ap.add_argument("--out", type=Path, default=None,
                    help="JSON report (default eval_out/evaluation.json)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.threshold is None:
        rec = REPO / "fit" / "out" / "fit_record.json"
        if rec.exists():
            args.threshold = float(json.loads(rec.read_text())["values"]["threshold"])
        else:
            args.threshold = 1.5
    baseline = load_baseline(args.baseline)

    loaded = []
    for path in args.platform_output:
        ts, score, invalid = read_output(path)
        loaded.append((target_of(path), ts, score, invalid))
        if not args.quiet:
            print(f"{path.name}: {len(ts):,} windows, {invalid} invalid  "
                  f"score median {np.median(score):.3f}  p99 {np.quantile(score, .99):.3f}  "
                  f"max {score.max():.3f}")

    runs = {"artifact": args.threshold}
    if args.val_output:
        vts, vscore, vinv = read_output(args.val_output)
        val_far = float((vscore > args.threshold).mean())
        cal = calibrate_threshold(vscore, args.far)
        if not args.quiet:
            print(f"{args.val_output.name}: {len(vscore):,} windows, {vinv} invalid; FAR at "
                  f"threshold {args.threshold} = {val_far*100:.2f}%; threshold for "
                  f"{args.far:.0%} FAR = {cal:.3f}")
        # A detector whose baked-in threshold IS the calibrated one (Stage 5) would print
        # the same table twice; report the second only when it differs.
        if abs(cal - args.threshold) > 1e-3:
            runs["calibrated"] = cal
        elif not args.quiet:
            print(f"(artifact threshold equals the {args.far:.0%}-FAR calibration — one table)")

    report = {"sustain": args.sustain, "far_target": args.far,
              "inputs": [str(p) for p in args.platform_output]}
    for label, thr in runs.items():
        files = [series_metrics(load_labels(name), ts, score, thr, args.sustain)
                 for name, ts, score, _ in loaded if name != "val_normal"]
        if not files:
            continue
        pooled = pool(files)
        report[label] = {"threshold": thr, **jsonable(pooled)}
        base = baseline.get("calibrated") if baseline else None
        if not args.quiet:
            print()
            print(format_table(pooled, baseline=base,
                               title=f"=== AD agent — {label} threshold {thr:.3f}, "
                                     f"sustain {args.sustain}"
                                     + ("  |  PCA bar at its calibrated threshold" if base else "") + " ==="))

    out = args.out or REPO / "eval_out" / "evaluation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    if not args.quiet:
        print(f"\nwrote {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
