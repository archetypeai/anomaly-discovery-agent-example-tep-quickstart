#!/usr/bin/env python3
"""Stage 8 -- serve: the promoted detector answering over /query, checked against Stage 6.

    python3 fit/serve.py                          # delivery file 1's fault-free run and IDV 5 (~3 min)
    python3 fit/serve.py --faults idv_01 idv_19   # other runs of the file
    python3 fit/serve.py --file full_chunk_002    # another delivery file
    python3 fit/serve.py --faults all             # all 21 runs of the file (~30 min)

Stage 6 delivered the detector in batch: a session per file, the output read
when the session is done. Serving keeps an agent loaded and answers a window in one
round trip, as a plant historian would ask it every 24 minutes (8 samples) for
the latest 48 samples. This replays delivery runs that way and checks every answer against
Stage 6's batch output for the same window:

  1. a package of fit/test.py's promoted blueprint, as it is. A package carries
     no values, so the agent runs at the blueprint's own step;
  2. that package deployed as `serving` (the agent placed on a worker and
     loaded), and a session opened on the deployment to query it;
  3. each run replayed at the blueprint's step, the one Optimize chose and
     Stage 6 delivered at: a query every `step_size` samples holding the latest
     `window_size` (`--windows-per-query N` sends N windows at once);
  4. every answer against Stage 6: `predicted_label`, and `anomaly_score` to
     within 1e-4 relative (served and batch differ by ~1e-5, float32 noise);
     the first sustained alarm (3 consecutive anomaly windows) of each run,
     served and batch;
  5. the session cancelled, the deployment stopped, and all three deleted, however it went
     (Ctrl-C, SIGTERM and SIGHUP included; a second Ctrl-C waits for it).
     Their ids are kept in fit/out/serve_state.json until then, so if the
     replay is killed before it can clean up, fit/cleanup.py finds them.

Each query is answered on its own: a served agent keeps no window between
queries, so a query must carry the whole window. Writes eval_out/serving/.
"""
from __future__ import annotations

import argparse
import json
import signal
import statistics
import sys
import time

import pandas as pd

from atai import REPO, load_dotenv, load_state, log, request, save_state, state_path
from ad_api import create_package, deploy, end_deployment, end_session, open_session, packages_url, sessions_url, wait_running

MODEL = "tep-ad"                 # the name a query gives in `model`
ONSET = 160                      # TEP's 48-hour runs: the fault starts after sample 160 (8 h)
SAMPLE_H = 3 / 60
SUSTAIN = 3
OUT = REPO / "eval_out" / "serving"


def first_alarm(labels: list[str]) -> int | None:
    """Index of the window that completes the first run of SUSTAIN anomaly windows."""
    run = 0
    for i, lab in enumerate(labels):
        run = run + 1 if lab == "anomaly" else 0
        if run == SUSTAIN:
            return i
    return None


def stop(signum, _frame):
    sys.exit(f"stopped by signal {signum}")       # so `finally` ends the session and deployment


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
    bp = load_state(state_path("test")).get("blueprint") or sys.exit("no promoted blueprint: run fit/test.py")
    channels, window = bp["values"]["data_columns"], bp["values"]["window_size"]
    step = int(bp["values"]["step_size"])
    data = pd.read_csv(REPO / "data" / "prepared" / "full" / f"tep_{args.file}.csv")
    labels = pd.read_csv(REPO / "data" / "prepared" / "full" / f"tep_{args.file}_labels.csv")
    batch = pd.read_csv(REPO / "eval_out" / "delivery" / f"ad-output-{args.file}.csv")
    if len(batch) != (len(data) - window) // step + 1:
        sys.exit(f"{args.file}: Stage 6's output has {len(batch)} windows, "
                 f"expected {(len(data) - window) // step + 1} at step {step}")

    # Batch windows start at rows 0, step, 2*step, ... of the file; a run replays the ones inside it.
    runs = []                                   # (fault id, sim, run's first row, first window's row, windows)
    for (fault, sim), rows in labels.groupby(["fault_id", "simulationrun"], sort=False):
        if args.faults == ["all"] or fault in args.faults:
            start, end = rows.index[0], rows.index[-1] + 1
            lo = -(-start // step) * step
            n = max(0, (end - window - lo) // step + 1)
            runs.append((fault, int(sim), start, lo, min(n, args.max_windows or n)))
    if not runs:
        sys.exit(f"none of {args.faults} in {args.file}")
    wpq = max(1, min(args.windows_per_query, 16))
    X = data[channels].to_numpy(dtype=float)
    log(f"{args.file}: {len(runs)} run(s), {sum(r[4] for r in runs):,} windows at step {step}, "
        f"{wpq} per query; model {bp['key']}")

    live = state_path("serve")
    state = load_state(live)
    if state.get("package"):
        sys.exit(f"{live} holds an earlier replay's session, deployment and package: run fit/cleanup.py first")
    served, latency = {}, []
    t_start = time.time()
    try:
        state["package"] = create_package(bp["id"], "TEP Stage 8")["id"]
        save_state(live, state)
        state["deployment"] = deploy(state["package"], "serving")["id"]
        save_state(live, state)
        state["session"] = open_session(state["deployment"])["id"]
        save_state(live, state)
        log(f"package {state['package']} · serving deployment {state['deployment']} · session {state['session']}")
        wait_running(state["session"])
        for fault, sim, _, first, n in runs:
            got = served[(fault, sim)] = []
            for k in range(0, n, wpq):
                count = min(wpq, n - k)
                lo = first + k * step
                chunk = X[lo:lo + window + (count - 1) * step]
                body = {"model": MODEL, "query": "", "events": [{"type": "data.numeric_array",
                        "event_data": {"contents": [chunk[:, c].tolist() for c in range(len(channels))]}}]}
                t = time.time()
                answer = request("POST", f"{sessions_url(state['session'])}/query", body=body)
                latency.append(time.time() - t)
                records = (answer.get("response") or {}).get("data")
                if not isinstance(records, list) or len(records) != count:
                    sys.exit(f"{fault} window {k}: expected {count} records, got {str(answer)[:300]}")
                got.extend(records)
            log(f"  {fault} (sim {sim}): {n} windows, {time.time() - t_start:.0f} s so far")
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)     # a second Ctrl-C mustn't cut the cleanup short
        if state.get("session"):
            end_session(state["session"])
        if state.get("deployment"):
            end_deployment(state["deployment"])
        if state.get("package"):
            request("DELETE", packages_url(state["package"]), raw=True)
        live.unlink(missing_ok=True)
        log(f"ended and deleted {', '.join(state[k] for k in ('session', 'deployment', 'package') if k in state)}")
    elapsed = time.time() - t_start

    rows, per_run = [], []
    for fault, sim, start, first, n in runs:
        ref = batch.iloc[first // step:first // step + n]
        offset = first - start                  # the run's first window starts this many rows in
        got = served[(fault, sim)]
        for k, (s, (_, b)) in enumerate(zip(got, ref.iterrows())):
            rows.append({"fault_id": fault, "sim": sim, "window": k, "end_sample": offset + k * step + window,
                         "batch_label": b.predicted_label, "served_label": s["predicted_label"],
                         "batch_score": b.anomaly_score, "served_score": s["anomaly_score"],
                         "served_invalid": s["invalid"],
                         "same_label": s["predicted_label"] == b.predicted_label,
                         "same_score": abs(float(s["anomaly_score"]) / float(b.anomaly_score) - 1) < 1e-4})
        alarms = {}
        for who, labs in (("served", [s["predicted_label"] for s in got]), ("batch", ref.predicted_label.tolist())):
            i = first_alarm(labs)
            # window i ends on sample offset + i * step + window: hours into the run
            alarms[who] = None if i is None else round((offset + i * step + window) * SAMPLE_H, 2)
        per_run.append({"fault_id": fault, "sim": sim, "windows": n, "first_alarm_h": alarms,
                        "onset_h": None if fault == "idv_00" else ONSET * SAMPLE_H})

    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    label = "all" if args.faults == ["all"] else "_".join(r[0] for r in runs)
    stem = OUT / f"serve_{args.file}_{label}_wpq{wpq}"
    df.to_csv(stem.with_suffix(".csv"), index=False)
    ms = sorted(x * 1000 for x in latency)
    summary = {"blueprint": bp["key"], "file": args.file, "step_size": step, "runs": per_run,
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
