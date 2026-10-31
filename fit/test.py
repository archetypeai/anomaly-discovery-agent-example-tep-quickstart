#!/usr/bin/env python3
"""Stage 5 -- promote the best trial and test it once with the Evals API.

    python3 fit/test.py                  # best trial across fit/optimize.py's runs, on slices 02-04
    python3 fit/test.py --trial otr_...  # a specific trial of the best run
    python3 fit/test.py --pieces 2       # 6 evals of half a slice, 3 at a time, pooled (the free trial's default)

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

On the free trial an eval is stopped after 2 hours and runs on CPU, slower than
the 3 slices allow, so there (ATAI_API_ENDPOINT on try.archetypeai.app) the default
is `--pieces 2`. `--pieces K` cuts each slice at run boundaries into K pieces
(fit/out/test-pieces/), runs an eval per piece, `--parallel` at a time, and pools
them: the confusion matrices add up, and the metrics are recomputed from the
pooled counts the way the platform computes them (checked against every eval's
own report). Only the windows that straddle a cut are lost, and those span two
runs, so the detector abstains on them anyway.

Writes fit/out/test_state.json (resume), fit/out/test.json and
fit/out/test-predictions.ndjson.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from atai import (COLUMN, OUT, REPO, ROLES, agents_base, aggregate, api_base, example, free_trial, load_dotenv,
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
    url = f"{agents_base()}/optimizations/{opt_id}/trials/{tid}/promote"
    body = {
        "name": f"AD TEP quickstart (w {vals['window_size']}, step {vals['step_size']}, k {vals['n_neighbors']}, "
                f"{vals['metric']}, PCA {vals['pca_components']}, threshold {vals['threshold']:.3f})",
        "description": f"Promoted from {opt_id}; detector fitted on the 40 fault-free reference sims."}
    try:
        bp = request("POST", url, body={"blueprint_key": f"ad-tep-qs-{tid}", **body})
    except SystemExit as e:
        # choosing the key needs the admin role (a free-trial org has none): let the platform choose it
        if "(403)" not in str(e) or "blueprint_key" not in str(e):
            raise
        bp = request("POST", url, body=body)
    log(f"promoted {tid} -> {bp['blueprint_key']} ({bp['id']})")
    return {"id": bp["id"], "key": bp["blueprint_key"], "trial": tid, "values": vals}


def windows(sidecar, window: int, step: int) -> list:
    """The sidecar row each window ends on, tiling from row 0."""
    with open(sidecar) as fh:
        rows = list(csv.DictReader(fh))
    return [rows[i + window - 1] for i in range(0, len(rows) - window + 1, step)]


def gold(row: dict) -> str:
    return "normal" if row["label"] == "normal" else "anomaly"


def split(files: list, pieces: int, step: int) -> list:
    """Each test file cut at run boundaries into `pieces` parts, written to fit/out/test-pieces/."""
    out = []
    (OUT / "test-pieces").mkdir(parents=True, exist_ok=True)
    for f in files:
        data, side = ROLES / f["file"], ROLES / f["labels"]
        lines, sides = data.read_text().splitlines(True), side.read_text().splitlines(True)
        rows = list(csv.DictReader(sides))
        starts = [i for i in range(1, len(rows)) if (rows[i]["fault_id"], rows[i]["simulationrun"])
                  != (rows[i - 1]["fault_id"], rows[i - 1]["simulationrun"])]
        cuts = [0] + [min(starts, key=lambda b: abs(b - k * len(rows) / pieces)) for k in range(1, pieces)] + [len(rows)]
        if any(c % step for c in cuts) or sorted(set(cuts)) != cuts:
            raise SystemExit(f"{data.name}: cannot cut into {pieces} pieces at run boundaries on a multiple of {step}")
        for j, (a, b) in enumerate(zip(cuts, cuts[1:]), 1):
            piece = OUT / "test-pieces" / f"{data.stem}_part{j}of{pieces}.csv"
            labels = piece.with_name(piece.stem + "_labels.csv")
            if not piece.exists():
                piece.write_text(lines[0] + "".join(lines[1 + a:1 + b]))
                labels.write_text(sides[0] + "".join(sides[1 + a:1 + b]))
            out.append({"file": piece, "labels": labels})
    return out


def metrics(c: dict) -> dict:
    """The platform's aggregate from counts: an abstention counts against its gold class's recall."""
    gold_a, gold_n = c["tp"] + c["fn"] + c["abstained_anomaly"], c["fp"] + c["tn"] + c["abstained_normal"]
    f1 = lambda p, r: 2 * p * r / (p + r) if p + r else 0.0  # noqa: E731
    pa, ra = c["tp"] / max(c["tp"] + c["fp"], 1), c["tp"] / max(gold_a, 1)
    pn, rn = c["tn"] / max(c["tn"] + c["fn"], 1), c["tn"] / max(gold_n, 1)
    return {"accuracy": (c["tp"] + c["tn"]) / max(gold_a + gold_n, 1), "detection_precision": pa,
            "detection_recall": ra, "foreground_macro_f1": f1(pa, ra), "macro_f1": (f1(pa, ra) + f1(pn, rn)) / 2}


def score(files: list, evals: list, preds: list, window: int, step: int) -> dict:
    """Pair predictions with sidecar rows; check each eval's confusion and metrics; pool them."""
    by_ex = {}
    for p in preds:
        by_ex.setdefault(p["example"], []).append(p)
    paired, abstained, counts = [], 0, {}
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
        c = counts[name] = dict.fromkeys(("tp", "fn", "fp", "tn", "abstained_anomaly", "abstained_normal"), 0)
        for i, (row, p) in enumerate(zip(ws, got)):
            if p["expected"] != gold(row):
                raise SystemExit(f"{name} window {i}: platform gold {p['expected']}, sidecar says "
                                 f"{gold(row)} -- predictions are misaligned")
            # `outcome: missed` carries a null `predicted`: the detector
            # abstained on that window.
            if p["outcome"] == "missed" or p["predicted"] is None:
                abstained += 1
                c[f"abstained_{gold(row)}"] += 1
            else:
                paired.append((row, p["predicted"]))
                g, pr = gold(row), p["predicted"]
                c[("t" if g == pr else "f") + ("p" if pr == "anomaly" else "n")] += 1
    total = dict.fromkeys(next(iter(counts.values())), 0)
    for ev, names in evals:
        a = aggregate(ev["metrics_report"])
        idx = {n: i for i, n in enumerate(a["class_names"])}
        cm, ai, ni = a["confusion_matrix"], idx["anomaly"], idx["normal"]
        platform = {"tp": cm[ai][ai], "fn": cm[ai][ni], "fp": cm[ni][ai], "tn": cm[ni][ni]}
        offline = {k: sum(counts[n][k] for n in names) for k in total}
        if {k: offline[k] for k in platform} != platform:
            raise SystemExit(f"{ev['id']}: offline confusion {offline} != platform {platform}")
        ours = metrics(offline)
        if any(abs(ours[k] - a[k]) > 1e-9 for k in ours):
            raise SystemExit(f"{ev['id']}: metrics from its counts {ours} != the platform's {a}")
        for k in total:
            total[k] += offline[k]
    platform = {k: total[k] for k in ("tp", "fn", "fp", "tn")}
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
    return {"platform": metrics(total), "confusion": platform, "abstained": abstained,
            "detection_by_idv": {k: {"flagged": v[0], "windows": v[1]} for k, v in sorted(per_idv.items())},
            "false_alarms": {k: {"flagged": v[0], "windows": v[1]} for k, v in normal.items()}}


def report(r: dict) -> None:
    p, v = r["platform"], r["blueprint"]["values"]
    print(f"\neval {', '.join(r['evals'])}  blueprint {r['blueprint']['key']}  "
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
    ap.add_argument("--pieces", type=int, help="cut each test slice into K evals (default 1; 2 on the free trial)")
    ap.add_argument("--parallel", type=int, default=3, help="evals at once with --pieces (the free trial runs 3)")
    args = ap.parse_args()
    load_dotenv()
    if args.pieces is None:
        args.pieces = 2 if free_trial() else 1
        if args.pieces > 1:
            log("free trial (try.archetypeai.app): each job stops after 2 hours, so the test runs as "
                "6 evals of half a slice, 3 at a time, pooled (--pieces 2; --pieces 1 for one eval)")
    m = manifest()
    STATE = state_path("test")
    state = load_state(STATE)
    save = lambda: save_state(STATE, state)  # noqa: E731
    if "blueprint" not in state:
        opt_id = args.optimization or best_run(load_state(state_path("optimize")))
        state["optimization"] = opt_id
        state["blueprint"] = promote(opt_id, args.trial)
        save()

    v = state["blueprint"]["values"]
    files = [{"file": ROLES / f["file"], "labels": ROLES / f["labels"]} for f in m["test"]]
    if args.pieces > 1:
        files = split(files, args.pieces, v["step_size"])
    paths = [f["file"] for f in files]
    ids = upload_all(paths, jobs=3)
    groups = [paths] if args.pieces == 1 else [[p] for p in paths]
    if args.pieces == 1 and "eval" in state:               # this script's single-eval state, before --pieces
        state.setdefault("evals", [state["eval"]])
    state.setdefault("evals", [])
    if len(state["evals"]) not in (0, len(groups)):
        raise SystemExit(f"{STATE} holds {len(state['evals'])} eval(s), not {len(groups)}: "
                         f"rerun with the same --pieces, or move it aside")

    def one(i: int) -> dict:
        if i >= len(state["evals"]) or not state["evals"][i]:
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            what = "slices 02-04" if args.pieces == 1 else groups[i][0].stem.removeprefix("tep_")
            ev = request("POST", f"{agents_base()}/evals", body={
                "blueprint_id": state["blueprint"]["id"], "emit_predictions": True,
                "name": f"ad-tep test {what} {stamp}",
                "examples": [example(p.stem, ids[p], COLUMN) for p in groups[i]]})
            with lock:
                state["evals"] += [None] * (i + 1 - len(state["evals"]))
                state["evals"][i] = ev["id"]
                save()
            log(f"eval {ev['id']}: {len(groups[i])} test file(s)")
        ev = wait("evals", state["evals"][i], every_s=30)
        if ev["status"] != "completed" or not ev.get("metrics_report"):
            with lock:                                      # a rerun starts a new eval for it
                state["evals"][i] = None
                save()
            raise SystemExit(f"eval {ev['id']} ended {ev['status']}: {ev.get('error')}; rerun to retry it")
        return ev

    lock = threading.Lock()
    with ThreadPoolExecutor(args.parallel if args.pieces > 1 else 1) as pool:
        evs = list(pool.map(one, range(len(groups))))
    raw = b""
    for ev in evs:
        pred = next(x["id"] for x in ev["output_artifacts"]
                    if x.get("metadata", {}).get("kind") == "predictions")
        raw += request("GET", f"{api_base()}/files/download/{pred}", raw=True).rstrip(b"\n") + b"\n"
    (OUT / "test-predictions.ndjson").write_bytes(raw)
    r = score(files, [(ev, [p.stem for p in g]) for ev, g in zip(evs, groups)],
              [json.loads(x) for x in raw.decode().splitlines() if x.strip()], v["window_size"], v["step_size"])
    r = {"evals": state["evals"], "pieces": args.pieces, "blueprint": state["blueprint"],
         "optimization": state["optimization"], **r}
    (OUT / "test.json").write_text(json.dumps(r, indent=1))
    report(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
