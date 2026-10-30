#!/usr/bin/env python3
"""Stage 5 -- promote the best trial and test it once with the Evals API.

    python3 fit/test.py                  # best trial across fit/optimize.py's runs, on slices 02-04
    python3 fit/test.py --trial otr_...  # a specific trial of the best run

The promoted blueprint carries the detector Optimize fitted on the library and
pins the trial's values. One eval scores it on the test role (eval slices 02-04,
never used for a choice) against the `label` column, at the trial's own
threshold and stride, with predictions.

With the predictions downloaded, this script pairs each one with its window's
last row in the slice (windows tile each file from row 0 at `step_size`;
`row_index` counts across the whole eval, so a window's position in its file is
its rank within its example) and:
  * checks every prediction's gold label against the sidecar, and the offline
    confusion matrix against the platform's;
  * reports window detection per fault type (IDV) and the false-alarm rate on
    normal windows, the fault-free run and the faulty runs' first 8 h apart.

Writes fit/out/test_state.json (resume), fit/out/test.json and
fit/out/test-predictions.ndjson.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json

from atai import (COLUMN, OUT, REPO, ROLES, agents_base, aggregate, api_base, example, load_dotenv,
                  load_state, log, manifest, request, save_state, state_path, upload_all, wait)


def best_run(opt_state: dict) -> str:
    """The optimization whose best trial scores highest, across fit/optimize.py's runs."""
    best = None
    for r in opt_state.get("runs", []):
        opt = request("GET", f"{agents_base()}/optimizations/{r['optimization']}")
        value = (opt.get("best_trial") or {}).get("objective_value")
        log(f"{opt['id']}: {opt['status']}, best {value}")
        if opt["status"] == "completed" and value is not None and (best is None or value > best[1]):
            best = (opt["id"], value)
    if not best:
        raise SystemExit("no completed optimization with a scored trial: run fit/optimize.py")
    return best[0]


def promote(opt_id: str, trial_id: str | None) -> dict:
    opt = request("GET", f"{agents_base()}/optimizations/{opt_id}")
    trials = request("GET", f"{agents_base()}/optimizations/{opt_id}/trials?limit=1000")["data"]
    tid = trial_id or opt.get("best_trial_id")
    trial = next((t for t in trials if t["id"] == tid), None)
    if not trial or trial["status"] != "completed":
        raise SystemExit(f"trial {tid} of {opt_id} is not a completed trial")
    vals = {**opt["overrides"]["values"], **trial["trial_values"]["values"]}
    if trial.get("promoted_blueprint"):
        bp = trial["promoted_blueprint"]
        log(f"{tid} already promoted -> {bp['blueprint_key']} ({bp['id']})")
        return {"id": bp["id"], "key": bp["blueprint_key"], "trial": tid, "values": vals}
    # No `blueprint_key`: choosing one takes the admin role. The default,
    # <base key>-<trial id>, is ad-tep-qs-otr_... (fit/atai.py's BASE_KEY).
    bp = request("POST", f"{agents_base()}/optimizations/{opt_id}/trials/{tid}/promote", body={
        "name": f"AD TEP quickstart (w {vals['window_size']}, step {vals['step_size']}, k {vals['n_neighbors']}, "
                f"{vals['metric']}, PCA {vals['pca_components']}, threshold {vals['threshold']:.3f})",
        "description": f"Promoted from {opt_id}; detector fitted on the 40 fault-free reference sims."})
    log(f"promoted {tid} -> {bp['blueprint_key']} ({bp['id']})")
    return {"id": bp["id"], "key": bp["blueprint_key"], "trial": tid, "values": vals}


def windows(sidecar, window: int, step: int) -> list:
    """The sidecar row each window ends on, tiling from row 0."""
    with open(sidecar) as fh:
        rows = list(csv.DictReader(fh))
    return [rows[i + window - 1] for i in range(0, len(rows) - window + 1, step)]


def gold(row: dict) -> str:
    return "normal" if row["label"] == "normal" else "anomaly"


def score(files: list, ev: dict, preds: list, window: int, step: int) -> dict:
    by_ex = {}
    for p in preds:
        by_ex.setdefault(p["example"], []).append(p)
    paired, abstained = [], 0
    for f in files:
        name = (ROLES / f["file"]).stem
        # The manifest names the labels sidecar directly; deriving it from a
        # "source" key does not work, because build_roles.py has never written
        # one -- each test entry carries file / labels / normal / anomaly.
        ws = windows(ROLES / f["labels"], window, step)
        # Order by the window's own time interval. The platform emits `input`
        # as 0 for every record, so it cannot order anything; `key.predicted`
        # is [start, end] in epoch seconds and is unique per window.
        got = sorted(by_ex.get(name, []), key=lambda p: p["key"]["predicted"][0])
        if len(got) != len(ws):
            raise SystemExit(f"{name}: {len(got)} predictions for {len(ws)} windows at "
                             f"window {window}, step {step}")
        for i, (row, p) in enumerate(zip(ws, got)):
            if p["expected"] != gold(row):
                raise SystemExit(f"{name} window {i}: platform gold {p['expected']}, sidecar says "
                                 f"{gold(row)} -- predictions are misaligned")
            # `outcome: missed` carries a null `predicted`: the detector
            # abstained on that window.
            if p["outcome"] == "missed" or p["predicted"] is None:
                abstained += 1
            else:
                paired.append((row, p["predicted"]))
    a = aggregate(ev["metrics_report"])
    idx = {n: i for i, n in enumerate(a["class_names"])}
    cm, ai, ni = a["confusion_matrix"], idx["anomaly"], idx["normal"]
    platform = {"tp": cm[ai][ai], "fn": cm[ai][ni], "fp": cm[ni][ai], "tn": cm[ni][ni]}
    offline = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
    for row, p in paired:
        g = gold(row)
        offline[("t" if g == p else "f") + ("p" if p == "anomaly" else "n")] += 1
    if offline != platform:
        raise SystemExit(f"offline confusion {offline} != platform {platform}")
    per_idv, normal = {}, {"fault-free run": [0, 0], "faulty runs, first 8 h": [0, 0]}
    for row, p in paired:
        if gold(row) == "anomaly":
            d = per_idv.setdefault(row["fault_id"], [0, 0])
            d[0] += p == "anomaly"
            d[1] += 1
        else:
            d = normal["fault-free run" if row["fault_id"] == "idv_00" else "faulty runs, first 8 h"]
            d[0] += p == "anomaly"
            d[1] += 1
    return {"platform": {k: v for k, v in a.items() if k not in ("confusion_matrix", "class_names")},
            "confusion": platform, "abstained": abstained,
            "detection_by_idv": {k: {"flagged": v[0], "windows": v[1]} for k, v in sorted(per_idv.items())},
            "false_alarms": {k: {"flagged": v[0], "windows": v[1]} for k, v in normal.items()}}


def report(r: dict) -> None:
    p, v = r["platform"], r["blueprint"]["values"]
    print(f"\neval {r['eval']}  blueprint {r['blueprint']['key']}  "
          f"(window {v['window_size']}, step {v['step_size']}, threshold {v['threshold']:.3f}; "
          f"{r['abstained']} abstained)")
    print(f"  platform: macro-F1 {p['macro_f1']:.4f}  anomaly F1 {p['foreground_macro_f1']:.4f}  "
          f"recall {p['detection_recall']:.4f}  precision {p['detection_precision']:.4f}")
    for k, d in r["false_alarms"].items():
        print(f"  false alarms, {k:<22} {d['flagged']:>5,} / {d['windows']:>6,}  {d['flagged'] / max(d['windows'], 1):.4f}")
    rates = [d["flagged"] / d["windows"] for d in r["detection_by_idv"].values()]
    print(f"  window detection per IDV (mean {sum(rates) / len(rates):.3f}):")
    for k, d in r["detection_by_idv"].items():
        print(f"    {k}  {d['flagged']:>5,} / {d['windows']:>5,}  {d['flagged'] / d['windows']:.3f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--optimization", help="default: the best of fit/out/optimize_state.json's runs")
    ap.add_argument("--trial", help="default: the optimization's best trial")
    args = ap.parse_args()
    load_dotenv()
    m = manifest()
    STATE = state_path("test")
    state = load_state(STATE)
    save = lambda: save_state(STATE, state)  # noqa: E731
    if "blueprint" not in state:
        opt_id = args.optimization or best_run(load_state(state_path("optimize")))
        state["optimization"] = opt_id
        state["blueprint"] = promote(opt_id, args.trial)
        save()

    files = m["test"]
    paths = [ROLES / f["file"] for f in files]
    ids = upload_all(paths, jobs=3)
    if "eval" not in state:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ev = request("POST", f"{agents_base()}/evals", body={
            "blueprint_id": state["blueprint"]["id"], "emit_predictions": True,
            "name": f"ad-tep test slices 02-04 {stamp}",
            "examples": [example(p.stem, ids[p], COLUMN) for p in paths]})
        state["eval"] = ev["id"]
        save()
        log(f"eval {ev['id']}: {len(paths)} test files")
    ev = wait("evals", state["eval"], every_s=30)
    if ev["status"] != "completed" or not ev.get("metrics_report"):
        raise SystemExit(f"eval {state['eval']} ended {ev['status']}: {ev.get('error')}")
    pred = next(x["id"] for x in ev["output_artifacts"]
                if x.get("metadata", {}).get("kind") == "predictions")
    raw = request("GET", f"{api_base()}/files/download/{pred}", raw=True)
    (OUT / "test-predictions.ndjson").write_bytes(raw)
    v = state["blueprint"]["values"]
    r = score(files, ev, [json.loads(x) for x in raw.decode().splitlines()],
              v["window_size"], v["step_size"])
    r = {"eval": state["eval"], "blueprint": state["blueprint"],
         "optimization": state["optimization"], **r}
    (OUT / "test.json").write_text(json.dumps(r, indent=1))
    report(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
