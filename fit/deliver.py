#!/usr/bin/env python3
"""Stage 6 -- deliver: run the promoted blueprint as agents over files with no labels.

    python3 fit/deliver.py
    python3 fit/deliver.py --step 0 --parallel 3   # the trial's step, 3 runs at once (the free trial's default)

One bundle on fit/test.py's promoted blueprint, which already holds the detector
and every value the trial pinned. The bundle adds only `step_size: 1` (one score
per sample; bundle values override a promoted blueprint's), `output_score` and
checkpointing off. `--step 0` delivers at the trial's own step (8) instead: an
eighth of the windows, which a free-trial run (CPU, stopped after 2 hours) can
finish; Stages 7 and 8 follow the delivery's step. On the free trial
(ATAI_API_ENDPOINT on try.archetypeai.app) that, and 3 runs at once, are the defaults. It runs over the delivery chunks and val_normal, all five at
once. The inputs are data/roles/delivery/, which carry no label column: the labels
stay in data/roles/labels/ until Stage 7 reads them.

val_normal (ten fault-free runs from the validation role) is delivered too:
Stage 7 sets the 1%-false-alarm threshold from its scores.

Writes eval_out/delivery/ad-output-*.csv and fit/out/deliver_state.json (resume:
finished outputs are skipped, started agents are polled, not started again).
"""
from __future__ import annotations

import argparse
import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from atai import REPO, free_trial, load_dotenv, load_state, log, manifest, request, save_state, state_path
from ad_api import CHECKPOINTING_OFF, bundles_url, download_results, poll_agent, upload_file

OUT = REPO / "eval_out" / "delivery"
TIMEOUT_S = 3 * 3600
NETWORK_WAIT_S, NETWORK_RETRIES = 60, 60   # ride out an outage of up to an hour
lock = threading.Lock()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parallel", type=int, help="runs at once (default 5; 3 on the free trial)")
    ap.add_argument("--step", type=int, help="step_size: 1 = a score per sample (default); 0 = the trial's "
                                              "(the free trial's default)")
    args = ap.parse_args()
    load_dotenv()
    trial = free_trial()
    if args.step is None:
        args.step = 0 if trial else 1
        if trial:
            log("free trial (try.archetypeai.app): each run stops after 2 hours, so delivering at the "
                "trial's step, a score every 8 samples (--step 0; --step 1 for every sample)")
    if args.parallel is None:
        args.parallel = 3 if trial else 5
    m = manifest()
    test = load_state(state_path("test"))
    if "blueprint" not in test:
        raise SystemExit("no promoted blueprint: run fit/test.py first")
    bp = test["blueprint"]
    STATE = state_path("deliver")
    state = load_state(STATE)
    if state.get("blueprint", bp["key"]) != bp["key"]:
        raise SystemExit(f"{STATE} is for {state['blueprint']}: move it aside to deliver {bp['key']}")
    state["blueprint"] = bp["key"]
    step = args.step or bp["values"]["step_size"]
    if "bundle" in state and state.get("step", 1) != step:
        raise SystemExit(f"{STATE} delivered at step {state['step']}: move it and eval_out/delivery/ aside "
                         f"to deliver at step {step}")
    state["step"] = step

    def save():
        with lock:
            save_state(STATE, state)

    if "bundle" not in state:
        b = request("POST", bundles_url(), body={
            "blueprint": bp["key"], "name": f"AD TEP quickstart delivery, stride {step}",
            "values": {"step_size": step, "output_score": True, "runner_config": CHECKPOINTING_OFF}})
        state["bundle"] = b["id"]
        save()
        log(f"bundle {b['id']} ({b.get('status')}) on {bp['key']}, step {step}")

    files = [REPO / "data" / "roles" / f["file"] for f in m["delivery"]]
    if not files:
        raise SystemExit("no delivery files in the manifest: run prep/build_roles.py")
    OUT.mkdir(parents=True, exist_ok=True)

    def one(src: Path) -> Path | None:
        dst = OUT / f"ad-output-{src.stem.removeprefix('tep_')}.csv"
        if dst.exists() and dst.stat().st_size:
            return dst
        runs = state.setdefault("agents", {})
        if src.stem not in runs:
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            fid = upload_file(str(src), rename=f"ad-tep-qs-{src.stem}-{stamp}.csv")["file_id"]
            agent = request("POST", f"{bundles_url(state['bundle'])}/run", body={
                "connectors": {"source": [{"type": "file", "id": fid, "format": "csv"}]}})
            with lock:
                runs[src.stem] = agent["id"]
            save()
            log(f"{src.name}: agent {agent['id']}")
        if poll_agent(runs[src.stem], TIMEOUT_S, interval_s=30) != "completed":
            log(f"{src.name}: agent did not report completed; trying /results anyway")
        if download_results(runs[src.stem], str(dst), source_csv=str(src)):
            return dst
        with lock:
            runs.pop(src.stem)
        save()
        return None

    def offline(e: BaseException) -> bool:
        text = f"{type(e).__name__} {e}"
        return any(k in text for k in ("URLError", "urlopen error", "nodename", "timed out",
                                       "Connection", "RemoteDisconnected", "IncompleteRead"))

    def safe(src: Path) -> Path | None:
        for attempt in range(NETWORK_RETRIES + 1):
            try:
                return one(src)
            except (Exception, SystemExit) as e:  # one flaky run must not stop the others
                if offline(e) and attempt < NETWORK_RETRIES:
                    # the network, not the run: wait for it instead of failing every file
                    log(f"{src.name}: network error ({e}); retrying in {NETWORK_WAIT_S} s")
                    time.sleep(NETWORK_WAIT_S)
                    continue
                log(f"{src.name}: {type(e).__name__}: {e}; rerun to retry")
                return None

    with ThreadPoolExecutor(args.parallel) as pool:
        got = list(pool.map(safe, files))
    missing = [s.name for s, g in zip(files, got) if not g]
    if missing:
        log(f"{len(missing)} of {len(got)} outputs missing ({', '.join(missing)}); rerun to resume")
        return 1
    log(f"{len(got)} outputs in {OUT.relative_to(REPO)}; next: python3 fit/score_delivery.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
