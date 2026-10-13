#!/usr/bin/env python3
"""Stage 2 -- build the role files the Optimizations and Evals APIs take.

    python3 prep/build_roles.py
    python3 prep/preflight_roles.py      # then check them

The OSM scenario on TEP. One plant, simulated many times: the simulation run is
the independence unit, and no run appears in two roles (Stage 2 already keeps
them apart; this only assigns the roles).

  library/      the 40 fault-free training sims (Stage 2's reference files,
                hard-linked). Optimize `training_examples`, constant `normal`.
  validation/   eval slice 01 and val_normal, each with a `label` column
                (`anomaly` from a faulty sim's onset, `normal` everywhere else).
                Optimize `validation_examples`: what chooses the settings.
  test/         eval slices 02-04, same format. Evals, once.
  delivery/     the delivery chunks and val_normal, with no label column: the
                files Stage 6 runs as agents.
  labels/       every validation, test and delivery file's `_labels.csv`
                sidecar: Stage 3 checks against them, Stage 7 scores with them.

Everything Stages 3-7 read is under data/roles/, which the repo ships, so a
clone can start at Stage 3 without the raw data. Writes data/roles/ and
data/roles/manifest.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PREPARED = REPO / "data" / "prepared"
ROLES = REPO / "data" / "roles"
LABEL = {"normal": "normal", "fault": "anomaly"}


def with_label(src: Path, sidecar: Path, dst: Path) -> dict:
    """src plus a `label` column from sidecar, row for row. Returns label counts."""
    counts = {"normal": 0, "anomaly": 0}
    with open(src) as fs, open(sidecar) as fl, open(dst, "w", newline="") as fo:
        rows, labels = csv.reader(fs), csv.DictReader(fl)
        w = csv.writer(fo)
        w.writerow(next(rows) + ["label"])
        for row, lab in zip(rows, labels, strict=True):
            if row[0] != lab["timestamp"]:
                sys.exit(f"{src.name}: timestamp {row[0]} != sidecar {lab['timestamp']}")
            label = LABEL[lab["label"]]
            counts[label] += 1
            w.writerow(row + [label])
    return counts


def link(src: Path, dst: Path) -> None:
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        dst.write_bytes(src.read_bytes())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--validation", default="eval_slice_01,val_normal")
    ap.add_argument("--test", default="eval_slice_02,eval_slice_03,eval_slice_04")
    args = ap.parse_args()
    report = PREPARED / "prep_report.json"
    if not report.exists():
        sys.exit(f"{report} not found -- run Stage 2 first (prep/prepare_tep.py)")
    rep = json.loads(report.read_text())

    m = {"label_column": "label", "labels": ["normal", "anomaly"],
         "onset_sample": rep["onset_sample_testing"], "channels": rep["channels"],
         "library": [], "validation": [], "test": [], "delivery": []}
    (ROLES / "library").mkdir(parents=True, exist_ok=True)
    for f in rep["reference_files"]:
        src = REPO / f["path"]
        dst = ROLES / "library" / src.name
        link(src, dst)
        m["library"].append({"file": str(dst.relative_to(ROLES)), "rows": f["rows"],
                             "sims": f["sims"]})
    print(f"library: {len(m['library'])} files, {sum(f['rows'] for f in m['library']):,} rows, all normal")

    (ROLES / "labels").mkdir(parents=True, exist_ok=True)
    for role, names in (("validation", args.validation), ("test", args.test)):
        (ROLES / role).mkdir(parents=True, exist_ok=True)
        for name in names.split(","):
            src = PREPARED / f"tep_{name}.csv"
            dst = ROLES / role / src.name
            lab = ROLES / "labels" / f"tep_{name}_labels.csv"
            link(PREPARED / lab.name, lab)
            counts = with_label(src, lab, dst)
            m[role].append({"file": str(dst.relative_to(ROLES)), "labels": str(lab.relative_to(ROLES)),
                            **counts})
            print(f"{role}: {dst.name} {counts['normal']:,} normal / {counts['anomaly']:,} anomaly rows")

    # Delivery: the files Stage 6 runs, with no label column. val_normal goes too,
    # so Stage 7 can set the 1%-false-alarm threshold from its scores.
    (ROLES / "delivery").mkdir(parents=True, exist_ok=True)
    full = PREPARED / "full"
    chunks = [p for p in sorted(full.glob("tep_full_chunk_*.csv")) if not p.stem.endswith("_labels")]
    if not chunks:
        sys.exit(f"no delivery chunks in {full.relative_to(REPO)} -- run prep/prepare_full_eval.py first")
    for src in [PREPARED / "tep_val_normal.csv"] + chunks:
        dst = ROLES / "delivery" / src.name
        lab = ROLES / "labels" / f"{src.stem}_labels.csv"
        link(src, dst)
        link(src.with_name(src.stem + "_labels.csv"), lab)
        m["delivery"].append({"file": str(dst.relative_to(ROLES)), "labels": str(lab.relative_to(ROLES))})
    print(f"delivery: {len(chunks)} chunks + val_normal under data/roles/delivery, labels held back "
          f"in data/roles/labels")

    (ROLES / "manifest.json").write_text(json.dumps(m, indent=1) + "\n")
    print(f"wrote {ROLES / 'manifest.json'}; next: python3 prep/preflight_roles.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
