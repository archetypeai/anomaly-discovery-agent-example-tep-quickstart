#!/usr/bin/env python3
"""Stage 8 -- serve: the promoted detector answering over /query, checked against Stage 6.

    python3 fit/serve.py                          # delivery file 1's fault-free run and IDV 5 (~25 min)
    python3 fit/serve.py --faults idv_01 idv_19   # other runs of the file
    python3 fit/serve.py --file full_chunk_002    # another delivery file
    python3 fit/serve.py --faults all             # all 21 runs of the file (~4 h)

Stage 6 delivered the detector in batch: an agent run per file, the output read
when the run is done. Serving keeps an agent loaded and answers a window in one
round trip, as a plant historian would ask it every 3 minutes for the latest
48 samples. This replays delivery runs that way and checks every answer against
Stage 6's batch output for the same window:

  1. the served variant of fit/test.py's promoted blueprint, made once and reused
     (`<key>-served-records`): the same detector, encoder and values, step 1,
     with the CSV source and sink swapped for an `atai-records` serving endpoint;
  2. a bundle of it, run in serving mode;
  3. each run replayed one sample at a time: every query holds the latest
     `window_size` samples (`--windows-per-query N` sends N windows at once);
  4. every answer against Stage 6: `predicted_label`, and `anomaly_score` to
     within 1e-4 relative (served and batch differ by ~1e-5, float32 noise);
     the first sustained alarm (3 consecutive anomaly windows) of each run,
     served and batch;
  5. the agent cancelled and deleted, and the bundle deleted, however it went
     (Ctrl-C, SIGTERM and SIGHUP included; a second Ctrl-C waits for it).
     Their ids are kept in fit/out/serve_state.json until then, so if the
     replay is killed before it can clean up, fit/cleanup.py finds them.

Dev only, like serving (https://github.com/archetypeai/agent-serving-example).
Each query is answered on its own: a served agent keeps no window between
queries, so a query must carry the whole window. Writes eval_out/serving/.
"""
from __future__ import annotations

import argparse
import copy
import json
import signal
import statistics
import sys
import time

import pandas as pd

from atai import REPO, agents_base, load_dotenv, load_state, log, request, save_state, state_path

MODEL = "tep-ad"                 # the name a query gives in `model`
ONSET = 160                      # TEP's 48-hour runs: the fault starts after sample 160 (8 h)
SAMPLE_H = 3 / 60
SUSTAIN = 3
OUT = REPO / "eval_out" / "serving"


def get_or_none(url: str):
    try:
        return request("GET", url)
    except SystemExit as e:
        if "(404)" in str(e):
            return None
        raise


def served_blueprint(promoted: str) -> str:
    """The atai-records served variant of `promoted`, created once."""
    key = f"{promoted}-served-records"
    if get_or_none(f"{agents_base()}/blueprints/{key}"):
        return key
    src = request("GET", f"{agents_base()}/blueprints/{promoted}")
    doc = copy.deepcopy(src["document"])
    doc.pop("blueprint_id", None)
    doc["values"]["step_size"] = 1
    # The platform fills in protocols and models for a served blueprint and
    # rejects the document outright if we set them ourselves.
    endpoint = {"format": "serving", "kind": "http"}
    doc["connectors"] = {
        "source": {"key": "RecordsSource", "config": {
            **endpoint,
            "data_columns": [{"dtype": "f32", "names": doc["values"]["data_columns"]}],
            "timestamp_column": doc["values"]["timestamp_column"]}},
        "sink": {"key": "RecordsSink", "config": dict(endpoint)},
    }
    doc["name"] = f"{src['name']} (served, records)"
    bp = request("POST", f"{agents_base()}/blueprints", body={
        "blueprint_key": key, "name": doc["name"], "document": doc,
        "description": f"Stage 8: {promoted} served with atai-records, step 1."})
    log(f"created served blueprint {key} ({bp['id']})")
    return key


def first_alarm(labels: list[str]) -> int | None:
    """Index of the window that completes the first run of SUSTAIN anomaly windows."""
    run = 0
    for i, lab in enumerate(labels):
        run = run + 1 if lab == "anomaly" else 0
        if run == SUSTAIN:
            return i
    return None


def stop(signum, _frame):
    sys.exit(f"stopped by signal {signum}")       # so `finally` deletes the agent and bundle


def main() -> int:
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", default="full_chunk_001", help="a delivery file Stage 6 delivered")
    ap.add_argument("--faults", nargs="+", default=["idv_00", "idv_05"],
                    help="the file's runs to replay, by fault id (idv_00 = fault-free); `all` for every run")
    ap.add_argument("--windows-per-query", type=int, default=1, help="1 = live, one window per sample (default); up to 16")
    ap.add_argument("--max-windows", type=int, help="replay only the first N windows of each run")
    args = ap.parse_args()

    load_dotenv()
    # Match the deployment generation, not one host: dev is api.dev.* and platform.dev.*
    if ".dev." not in agents_base():
        sys.exit("agent serving is on dev only for now (e.g. https://platform.dev.u1.archetypeai.app)")
    bp = load_state(state_path("test")).get("blueprint") or sys.exit("no promoted blueprint: run fit/test.py")
    channels, window = bp["values"]["data_columns"], bp["values"]["window_size"]
    data = pd.read_csv(REPO / "data" / "prepared" / "full" / f"tep_{args.file}.csv")
    labels = pd.read_csv(REPO / "data" / "prepared" / "full" / f"tep_{args.file}_labels.csv")
    batch = pd.read_csv(REPO / "eval_out" / "delivery" / f"ad-output-{args.file}.csv")
    if len(batch) != len(data) - window + 1:
        sys.exit(f"{args.file}: Stage 6's output has {len(batch)} windows, expected {len(data) - window + 1}")

    runs = []                                   # (fault id, sim, first row, windows to replay)
    for (fault, sim), rows in labels.groupby(["fault_id", "simulationrun"], sort=False):
        if args.faults == ["all"] or fault in args.faults:
            n = len(rows) - window + 1
            runs.append((fault, int(sim), rows.index[0], min(n, args.max_windows or n)))
    if not runs:
        sys.exit(f"none of {args.faults} in {args.file}")
    wpq = max(1, min(args.windows_per_query, 16))
    X = data[channels].to_numpy(dtype=float)
    log(f"{args.file}: {len(runs)} run(s), {sum(r[3] for r in runs):,} windows, {wpq} per query; model {bp['key']}")

    key = served_blueprint(bp["key"])
    live = state_path("serve")
    state = load_state(live)
    if state.get("bundle"):
        sys.exit(f"{live} holds an earlier replay's agent and bundle: run fit/cleanup.py first")
    state["bundle"] = request("POST", f"{agents_base()}/bundles", body={"blueprint": key, "name": "TEP Stage 8"})["id"]
    save_state(live, state)
    state["agent"] = request("POST", f"{agents_base()}/bundles/{state['bundle']}/run", body={"mode": "serving"})["id"]
    save_state(live, state)
    bundle, agent = state["bundle"], state["agent"]
    log(f"bundle {bundle} · agent {agent}")
    served, latency = {}, []
    t_start = time.time()
    try:
        while (status := request("GET", f"{agents_base()}/instances/{agent}").get("status")) != "running":
            if status in ("failed", "completed", "cancelled", "canceled") or time.time() - t_start > 600:
                sys.exit(f"agent {agent} is {status}, not running")
            time.sleep(3)
        for fault, sim, first, n in runs:
            got = served[(fault, sim)] = []
            for k in range(0, n, wpq):
                count = min(wpq, n - k)
                lo = first + k
                chunk = X[lo:lo + window + count - 1]
                body = {"model": MODEL, "query": "", "events": [{"type": "data.numeric_array",
                        "event_data": {"contents": [chunk[:, c].tolist() for c in range(len(channels))]}}]}
                t = time.time()
                answer = request("POST", f"{agents_base()}/instances/{agent}/query", body=body)
                latency.append(time.time() - t)
                records = (answer.get("response") or {}).get("data")
                if not isinstance(records, list) or len(records) != count:
                    sys.exit(f"{fault} window {k}: expected {count} records, got {str(answer)[:300]}")
                got.extend(records)
            log(f"  {fault} (sim {sim}): {n} windows, {time.time() - t_start:.0f} s so far")
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)     # a second Ctrl-C mustn't cut the cleanup short
        request("POST", f"{agents_base()}/instances/{agent}/cancel", body={})
        request("DELETE", f"{agents_base()}/instances/{agent}", raw=True)
        request("DELETE", f"{agents_base()}/bundles/{bundle}", raw=True)
        live.unlink()
        log(f"cancelled and deleted {agent}, deleted {bundle}")
    elapsed = time.time() - t_start

    rows, per_run = [], []
    for fault, sim, first, n in runs:
        ref = batch.iloc[first:first + n]
        got = served[(fault, sim)]
        for k, (s, (_, b)) in enumerate(zip(got, ref.iterrows())):
            rows.append({"fault_id": fault, "sim": sim, "window": k, "end_sample": k + window,
                         "batch_label": b.predicted_label, "served_label": s["predicted_label"],
                         "batch_score": b.anomaly_score, "served_score": s["anomaly_score"],
                         "served_invalid": s["invalid"],
                         "same_label": s["predicted_label"] == b.predicted_label,
                         "same_score": abs(float(s["anomaly_score"]) / float(b.anomaly_score) - 1) < 1e-4})
        alarms = {}
        for who, labs in (("served", [s["predicted_label"] for s in got]), ("batch", ref.predicted_label.tolist())):
            i = first_alarm(labs)
            # window i ends on sample i + window: hours into the run
            alarms[who] = None if i is None else round((i + window) * SAMPLE_H, 2)
        per_run.append({"fault_id": fault, "sim": sim, "windows": n, "first_alarm_h": alarms,
                        "onset_h": None if fault == "idv_00" else ONSET * SAMPLE_H})

    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    label = "all" if args.faults == ["all"] else "_".join(r[0] for r in runs)
    stem = OUT / f"serve_{args.file}_{label}_wpq{wpq}"
    df.to_csv(stem.with_suffix(".csv"), index=False)
    ms = sorted(x * 1000 for x in latency)
    summary = {"blueprint": bp["key"], "served_blueprint": key, "file": args.file, "runs": per_run,
               "windows": len(df), "windows_per_query": wpq, "queries": len(latency),
               "same_label": int(df.same_label.sum()), "same_score": int(df.same_score.sum()),
               "max_score_rel_diff": float((df.served_score.astype(float) / df.batch_score - 1).abs().max()),
               "invalid": int((df.served_invalid.astype(str).str.lower() == "true").sum()),
               "latency_ms": {"median": round(statistics.median(ms)), "p95": round(ms[int(0.95 * (len(ms) - 1))]),
                              "max": round(ms[-1])},
               "replay_seconds": round(elapsed, 1)}
    stem.with_suffix(".json").write_text(json.dumps(summary, indent=1))

    print(f"\nStage 8: {len(df):,} windows of {len(runs)} run(s) served in {len(latency):,} queries, {elapsed:.0f} s")
    print(f"  against Stage 6 (batch): predicted_label identical in {summary['same_label']:,}/{len(df):,}, "
          f"anomaly_score within 1e-4 in {summary['same_score']:,}/{len(df):,} "
          f"(max relative difference {summary['max_score_rel_diff']:.1e}); invalid {summary['invalid']}")
    print(f"  latency per query: median {summary['latency_ms']['median']} ms, "
          f"p95 {summary['latency_ms']['p95']} ms, max {summary['latency_ms']['max']} ms")
    for r in per_run:
        def fmt(h):
            if h is None:
                return "none"
            if r["onset_h"] is None or h < r["onset_h"]:
                return f"{h:.2f} h into the run (a false alarm)"
            return f"{h - r['onset_h']:.2f} h after onset"
        a = r["first_alarm_h"]
        print(f"  {r['fault_id']} sim {r['sim']}: first sustained alarm, served {fmt(a['served'])}; batch {fmt(a['batch'])}")
    print(f"  -> {stem.relative_to(REPO)}.csv / .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
