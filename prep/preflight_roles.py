#!/usr/bin/env python3
"""Stage 3 -- check the role files against what the platform will do with them.

    python3 prep/preflight_roles.py

Fails on anything that would make an optimization or an eval wrong rather than
merely slow:
  * one label per row, matching the sidecar; labels only `normal` / `anomaly`
  * both classes in validation and in test (macro-F1 scores a missing class 0)
  * no simulation run in two roles, delivery included
  * no label column in the delivery files, and every delivery sidecar present
  * the manifest matches the disk
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PREPARED = REPO / "data" / "prepared"
ROLES = REPO / "data" / "roles"
LABEL = {"normal": "normal", "fault": "anomaly"}

checks = failures = 0


def check(ok: bool, what: str) -> None:
    global checks, failures
    checks += 1
    if not ok:
        failures += 1
        print(f"  FAIL  {what}")


def sims_in(sidecar: Path) -> set:
    with open(sidecar) as fh:
        return {(r["fault_id"], int(r["simulationrun"])) for r in csv.DictReader(fh)}


def main() -> int:
    m = json.loads((ROLES / "manifest.json").read_text())
    owner = {}

    def claim(role: str, sims: set) -> None:
        for s in sims:
            check(owner.setdefault(s, role) == role, f"{s} is in {owner.get(s)} and {role}")

    # library: Stage 2's reference files, fault-free training sims (their own id space)
    for f in m["library"]:
        p = ROLES / f["file"]
        check(p.exists(), f"{p} missing")
        with open(p) as fh:
            header = next(csv.reader(fh))
            rows = sum(1 for _ in fh)
        check("label" not in header, f"{p.name}: library files carry no label")
        check(rows == f["rows"], f"{p.name}: {rows} rows, manifest says {f['rows']}")
    claim("library", {("ff_train", s[1]) for f in m["library"] for s in f["sims"]})

    for role in ("validation", "test"):
        seen = {"normal": 0, "anomaly": 0}
        for f in m[role]:
            p = ROLES / f["file"]
            sidecar = ROLES / f["labels"]
            with open(p) as fr, open(sidecar) as fl:
                for r, lab in zip(csv.DictReader(fr), csv.DictReader(fl), strict=True):
                    check(r["label"] in seen, f"{p.name}: label {r['label']!r}")
                    check(r["label"] == LABEL[lab["label"]] and r["timestamp"] == lab["timestamp"],
                          f"{p.name} row {r['timestamp']}: label disagrees with the sidecar")
                    seen[r["label"]] = seen.get(r["label"], 0) + 1
            claim(role, {("ff_test" if s[0] == "idv_00" else s[0], s[1]) for s in sims_in(sidecar)})
        check(seen["normal"] > 0 and seen["anomaly"] > 0, f"{role}: both classes present {seen}")
        print(f"  {role}: {len(m[role])} files, {seen['normal']:,} normal / {seen['anomaly']:,} anomaly rows")

    validation = {(ROLES / f["file"]).name for f in m["validation"]}
    for f in m["delivery"]:
        p, sidecar = ROLES / f["file"], ROLES / f["labels"]
        check(sidecar.exists(), f"{sidecar} missing")
        with open(p) as fh:
            header = next(csv.reader(fh))
        check("label" not in header, f"{p.name}: delivery files carry no label")
        check(header[1:] == m["channels"], f"{p.name}: channels differ from the manifest")
        if p.name in validation:
            continue  # val_normal: run to set the threshold, never scored as delivery
        claim("delivery", {("ff_test" if s[0] == "idv_00" else s[0], s[1]) for s in sims_in(sidecar)})
    print(f"  delivery: {len(m['delivery'])} files, labels held back")
    print(f"  {len(owner):,} simulation runs, each in one role")
    print(f"\n{checks - failures:,} checks passed" if not failures else f"\n{failures} of {checks:,} checks FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
