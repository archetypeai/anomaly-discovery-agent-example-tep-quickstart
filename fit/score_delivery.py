#!/usr/bin/env python3
"""Stage 7 -- score the delivery against the held-back labels. Offline.

    python3 fit/score_delivery.py

No API key, no network. Scores the delivery chunks' outputs per fault type
(detection rate, runs detected, delay, AUROC) and the false-alarm rate, at two
thresholds: the trial's own (what the agent's labels used) and one set to a 1%
false-alarm rate on val_normal's scores.

Writes eval_out/delivery/evaluation.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "eval_out" / "delivery"


def main() -> int:
    state = REPO / "fit" / "out" / "test_state.json"
    if not state.exists():
        raise SystemExit("no promoted blueprint: run fit/test.py first")
    threshold = json.loads(state.read_text())["blueprint"]["values"]["threshold"]
    outputs = sorted(OUT.glob("ad-output-full_chunk_*.csv"))
    val = OUT / "ad-output-val_normal.csv"
    if not outputs or not val.exists():
        raise SystemExit("no delivery outputs: run fit/deliver.py first")
    rel = lambda p: str(p.relative_to(REPO))  # noqa: E731  (no home directory in the results)
    return subprocess.run([sys.executable, "fit/evaluate_detection.py",
                           "--platform-output", *map(rel, outputs), "--val-output", rel(val),
                           "--threshold", str(threshold),
                           "--out", rel(OUT / "evaluation.json")], cwd=REPO).returncode


if __name__ == "__main__":
    raise SystemExit(main())
