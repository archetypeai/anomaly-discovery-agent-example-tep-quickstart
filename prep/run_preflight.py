#!/usr/bin/env python3
"""Stages 1a and 1c — preflight the raw TEP files, then the prepared datasets.

    python3 prep/run_preflight.py --raw                       # Stage 1 (before prep)
    python3 prep/run_preflight.py --window-size 64 --step-size 8   # Stage 3 (after prep)

Stage 1 runs the vendored omega-1-4-preflight static checks against the raw
data so every prep decision downstream answers a finding rather than a guess.
The raw files have no timestamp column — the first finding — so one fault-free
simulation is materialised as a CSV view with the 3-minute cadence made
explicit, and the checks run on that.

Stage 1c reads the FILES Stage 1b wrote (never its in-memory state) and refuses
to let Stage 4 spend API budget on data that would fit a detector on nothing:
seam accounting, role separation, per-slice coverage, normalisation, the
filename→label contract, and reference coverage for the LOF/PCA head.

Exit status is non-zero only on FAIL. Every WARN should be accounted for in the
README.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight_static as ps
import preflight_tep as pt
from preflight_static import PASS, WARN, FAIL, INFO

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
PREPARED = REPO / "data" / "prepared"
SAMPLE_S = 180
LEVEL_ORDER = {FAIL: 0, WARN: 1, INFO: 2, PASS: 3}
RAW_FILES = ["TEP_FaultFree_Training", "TEP_FaultFree_Testing",
             "TEP_Faulty_Training", "TEP_Faulty_Testing"]
CONTINUOUS = [f"xmeas_{i}" for i in range(1, 23)]
ANALYSERS = [f"xmeas_{i}" for i in range(23, 42)]


def emit(results: list, notes: list = (), alias: tuple | None = None) -> int:
    for n in notes:
        print(f"  note  {n}")
    if notes:
        print()
    for r in sorted(results, key=lambda r: LEVEL_ORDER[r.level]):
        msg = r.message.replace(alias[0], alias[1]) if alias else r.message
        print(f"  {r.level:<4}  {r.name}: {msg}")
    counts = {lvl: sum(1 for r in results if r.level == lvl) for lvl in LEVEL_ORDER}
    print(f"\n  {counts[PASS]} PASS, {counts[WARN]} WARN, {counts[FAIL]} FAIL"
          + (f", {counts[INFO]} INFO" if counts[INFO] else ""))
    return counts[FAIL]


# --------------------------------------------------------------------------- Stage 1

def survey_raw(path: Path, max_rows: int | None = None) -> dict:
    """One streaming pass: sims per fault, rows per sim, repeat fractions."""
    sims = defaultdict(set)
    rows_per_sim = defaultdict(int)
    repeats = defaultdict(int)
    n = faulty_rows = 0
    prev = None
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames
        for row in reader:
            f, s = int(float(row["faultnumber"])), int(float(row["simulationrun"]))
            sims[f].add(s)
            rows_per_sim[(f, s)] += 1
            faulty_rows += f != 0
            if prev is not None and prev[0] == (f, s):
                for c in CONTINUOUS + ANALYSERS:
                    if row[c] == prev[1][c]:
                        repeats[c] += 1
            prev = ((f, s), row)
            n += 1
            if max_rows and n >= max_rows:
                break
    return {"header": header, "rows": n, "faulty_rows": faulty_rows, "sims": {f: len(s) for f, s in sorted(sims.items())},
            "rows_per_sim": sorted(set(rows_per_sim.values())),
            "repeat_fraction": {c: repeats[c] / max(n - 1, 1) for c in CONTINUOUS + ANALYSERS}}


def materialise_view(path: Path, out: Path, sim: int = 1) -> int:
    """One fault-free simulation as a CSV with synthesised 180 s timestamps."""
    n = 0
    with open(path, newline="") as fh, open(out, "w", newline="") as oh:
        reader = csv.DictReader(fh)
        cols = [c for c in reader.fieldnames if c.startswith(("xmeas_", "xmv_"))]
        w = csv.writer(oh)
        w.writerow(["timestamp"] + cols)
        for row in reader:
            if int(float(row["simulationrun"])) != sim:
                if n:
                    break
                continue
            w.writerow([SAMPLE_S * (int(row["sample"]) - 1)] + [row[c] for c in cols])
            n += 1
    return n


def stage1(window_size: int, full: bool) -> int:
    print("=" * 78)
    print(" Stage 1 — preflight the raw TEP files")
    print("=" * 78)
    missing = [f for f in RAW_FILES if not (RAW / f"{f}.csv").exists()]
    if missing:
        print(f"\n  missing in data/raw/: {missing} — run prep/download.py first")
        return 1

    fails = 0
    cap = None if full else 600_000
    for name in RAW_FILES:
        path = RAW / f"{name}.csv"
        print("\n" + "-" * 78 + f"\n {name}.csv" + ("" if full else f"  (first {cap:,} rows; --full for all)")
              + "\n" + "-" * 78)
        sv = survey_raw(path, cap)
        notes, results = [], []
        notes.append(f"{len(sv['header'])} columns: faultnumber, simulationrun, sample + "
                     f"{len(sv['header']) - 3} variables. No timestamp column — prep "
                     f"synthesises one at {SAMPLE_S} s/sample.")
        notes.append(f"faults seen: {list(sv['sims'])[:6]}{'…' if len(sv['sims']) > 6 else ''}; "
                     f"sims per fault: {sorted(set(sv['sims'].values()))}; rows per sim: "
                     f"{sv['rows_per_sim']}")
        fault_free = "FaultFree" in name
        if fault_free:
            results.append(pt.check_reference_purity(sv["faulty_rows"], sv["rows"], name))
        results.append(pt.check_analyser_staircase(sv["repeat_fraction"], CONTINUOUS, ANALYSERS))

        if name == "TEP_FaultFree_Training":
            with tempfile.TemporaryDirectory() as tmp:
                view = Path(tmp) / "view.csv"
                n = materialise_view(path, view)
                notes.append(f"vendored checks run on simulation 1 ({n} rows, 52 variables) "
                             f"materialised with {SAMPLE_S} s timestamps.")
                s = ps.summarize_shot_file(str(view))
                for check in (ps.check_schema, ps.check_timestamp, ps.check_missing,
                              ps.check_constant_cols, ps.check_feature_scale):
                    results.append(check(s))
                results.append(ps.check_nshot_support(s, window_size))
                results.append(ps.check_window_vs_sampling(s, s, window_size, "seconds"))
                results.append(ps.check_window_size_range(window_size))
                alias = (str(view), "sim 1 view")
            fails += emit(results, notes, alias)
        else:
            fails += emit(results, notes)
    print("\n  Prep decisions these prescribe: synthesise timestamps; z-score per channel "
          "(feature_scale); stitch many 500-row sims into the library (nshot_support); "
          "default to the 33 continuous channels (analyser_staircase).")
    return fails


# --------------------------------------------------------------------------- Stage 3

def read_csv(path: Path):
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames, list(reader)


def stage3(window_size: int, step_size: int, n_neighbors: int, pca: int) -> int:
    print("=" * 78)
    print(" Stage 3 — preflight the prepared datasets")
    print("=" * 78)
    report_path = PREPARED / "prep_report.json"
    if not report_path.exists():
        print("\n  no prep_report.json — run prep/prepare_tep.py first")
        return 1
    report = json.loads(report_path.read_text())
    stats = json.loads((PREPARED / "zscore_stats.json").read_text())
    channels = report["channels"]
    seam_gap = report["seam_gap_seconds"]
    fails = 0

    # -- reference files: vendored checks on every file, summarised ----------------
    print("\n" + "-" * 78 + f"\n reference library ({len(report['reference_files'])} files)\n" + "-" * 78)
    by_check: dict[str, list] = defaultdict(list)
    per_sim_rms, total_windows = {}, 0
    sums = {c: 0.0 for c in channels}
    sumsq = {c: 0.0 for c in channels}
    n_rows = 0
    for f in report["reference_files"]:
        path = REPO / f["path"]
        s = ps.summarize_shot_file(str(path))
        for check in (ps.check_schema, ps.check_timestamp, ps.check_missing,
                      ps.check_constant_cols, ps.check_feature_scale):
            by_check[check.__name__].append(check(s))
        by_check["check_nshot_support"].append(ps.check_nshot_support(s, window_size))
        total_windows += max(0, (s.n_rows - window_size) // step_size + 1)
        _, body = read_csv(path)
        acc = 0.0
        for row in body:
            for c in channels:
                v = float(row[c])
                sums[c] += v
                sumsq[c] += v * v
                acc += v * v
        n_rows += len(body)
        per_sim_rms[path.stem[-6:]] = math.sqrt(acc / (len(body) * len(channels)))
    results, notes = [], []
    for name, rs in by_check.items():
        worst = min(rs, key=lambda r: LEVEL_ORDER[r.level])
        n_non_pass = sum(1 for r in rs if r.level != PASS)
        results.append(ps.CheckResult(
            worst.name, worst.level,
            (f"all {len(rs)} files PASS" if n_non_pass == 0 else
             f"{n_non_pass}/{len(rs)} files non-PASS; worst: "
             + worst.message.replace(str(REPO) + "/", ""))))
    notes.append("nshot_support is per FILE (500 rows each); the library is the union of "
                 f"all files — {total_windows:,} windows at window {window_size}, step {step_size}.")
    notes.append("AD is one-class: check_schema_match, check_class_balance and "
                 "check_expected_accuracy_prior are not applicable and are not run.")
    means = {c: sums[c] / n_rows for c in channels}
    stds = {c: math.sqrt(max(sumsq[c] / n_rows - means[c] ** 2, 0.0)) for c in channels}
    results.append(pt.check_normalisation(max(abs(m) for m in means.values()),
                                          min(stds.values()), max(stds.values()),
                                          stats.get("fitted_on", "?")))
    results.append(pt.check_reference_agreement(per_sim_rms))
    results.append(pt.check_reference_coverage(total_windows, n_neighbors, pca))
    results.append(pt.check_filename_labels([Path(f["path"]).name for f in report["reference_files"]]))
    results.append(pt.check_window_span(window_size, step_size, SAMPLE_S,
                                        report["reference_files"][0]["rows"]))
    results.append(ps.check_window_size_range(window_size))
    fails += emit(results, notes)

    # -- validation + eval slices ------------------------------------------------
    # Key every segment by (source file, fault, sim): training and testing sims are
    # separate runs even when their ids coincide, and prep keeps ids disjoint anyway.
    def keyed(info):
        return {tuple(s) if len(s) == 3 else (info["source"], *s) for s in info["sims"]}
    roles = {"reference": set().union(*(keyed(f) for f in report["reference_files"])),
             "val_normal": keyed(report["val_normal"])}
    for info in [report["val_normal"]] + report["eval_slices"]:
        path = REPO / info["path"]
        name = path.stem
        print("\n" + "-" * 78 + f"\n {path.name}\n" + "-" * 78)
        results = []
        header, body = read_csv(path)
        s = ps.summarize_shot_file(str(path))
        results.append(ps.check_schema(s))
        results.append(ps.check_missing(s))
        if header[1:] != channels:
            results.append(ps.CheckResult("channels", FAIL, f"{name}: header differs from prep_report channels"))
        else:
            results.append(ps.CheckResult("channels", PASS, f"{name}: {len(channels)} channels in report order"))
        ts = [float(r["timestamp"]) for r in body]
        results.append(pt.check_seams(name, ts, seam_gap, SAMPLE_S, len(info["seams"]), window_size))
        _, labels = read_csv(PREPARED / f"{name}_labels.csv")
        if len(labels) != len(body) or any(float(a["timestamp"]) != b for a, b in zip(labels, ts)):
            results.append(ps.CheckResult("labels", FAIL, f"{name}: labels sidecar does not align row-for-row"))
        else:
            results.append(ps.CheckResult("labels", PASS, f"{name}: sidecar aligns on all {len(labels):,} timestamps"))
        if "eval_slice" in name:
            results.append(pt.check_slice_coverage(name, labels, 20, 960, report["onset_sample_testing"]))
            roles[name] = keyed(info)
        fails += emit(results, alias=(str(path), path.name))

    print("\n" + "-" * 78 + "\n cross-file\n" + "-" * 78)
    fails += emit([pt.check_role_separation(roles)])

    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", action="store_true", help="Stage 1: check the raw CSVs")
    ap.add_argument("--full", action="store_true", help="Stage 1: scan whole files (slow on the 3.6 GB one)")
    ap.add_argument("--window-size", type=int, default=64)
    ap.add_argument("--step-size", type=int, default=None, help="default window_size // 8")
    ap.add_argument("--n-neighbors", type=int, default=20)
    ap.add_argument("--pca-components", type=int, default=20)
    args = ap.parse_args()
    step = args.step_size or max(1, args.window_size // 8)
    fails = stage1(args.window_size, args.full) if args.raw else \
        stage3(args.window_size, step, args.n_neighbors, args.pca_components)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
