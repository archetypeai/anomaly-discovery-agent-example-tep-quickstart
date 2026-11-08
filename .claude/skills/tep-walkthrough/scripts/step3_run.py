#!/usr/bin/env python3
"""Step 3 (Newton): promote the winning trial, make one bundle with scores and embeddings on,
and run it as batch agents over one normal run and one faulty run it has never seen.

    .venv/bin/python .claude/skills/tep-walkthrough/scripts/step3_run.py

No evaluation is run (that is fit/test.py's job). The trial is promoted once; if it was
promoted before, that blueprint is reused. The two test runs (the first normal run and
the IDV 1 run) come from data/roles/test/tep_test.csv with the label column removed.

Blocks until every run is downloaded, printing "k/N done, ~M min left" as runs finish.
Resumable: ids are kept in walkthrough_out/step3/state.json, finished outputs are skipped.
2 runs (the 2 test runs), both at once.
"""
import argparse
import datetime
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from common import OUT, ROLES, console_base, dump

from ad_api import CHECKPOINTING_OFF, bundles_url, download_results, poll_agent, upload_file  # noqa: E402
from atai import api_base, free_trial, load_dotenv, load_state, log, request, state_path  # noqa: E402
from test import promote  # noqa: E402  (fit/test.py's promote: reuses an already-promoted trial)

DIR = OUT / "step3"
STATE = DIR / "state.json"
TEST_RUNS = {"normal_run": "idv_00", "fault_run": "idv_01"}   # the first run of each kind in tep_test.csv
FIRST_GUESS_MIN = 1          # one run on the free trial (0.8 min, 2026-11-07); replaced by the measured average
lock = threading.Lock()


def save(st):
    with lock:
        STATE.write_text(dump(st))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    load_dotenv()
    opt = load_state(state_path("optimize")).get("runs", [{}])[-1].get("optimization")
    if not opt:
        sys.exit("no optimization yet: run step2_optimize.py first")
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    if st and st.get("optimization") != opt:
        # an earlier Step 3 built on another optimization: keep it aside, start over on this one
        old = OUT / f"step3_{st.get('optimization', 'old')}"
        DIR.rename(old)
        log(f"Step 2 has a new optimization: earlier Step 3 outputs moved to {old.relative_to(OUT.parent)}")
        st = {}
    DIR.mkdir(parents=True, exist_ok=True)
    console = console_base(api_base())

    # 1. promote the best trial of the latest optimization (no evaluation)
    if "blueprint" not in st:
        st["optimization"], st["blueprint"] = opt, promote(opt, None)
        save(st)
    bp = st["blueprint"]
    log(f"blueprint {bp['key']} ({bp['id']}) from trial {bp['trial']}")

    # 2. one bundle at the trial's step, with per-window scores and Omega embeddings in the output
    if "bundle" not in st:
        b = request("POST", bundles_url(), body={
            "blueprint": bp["key"], "name": "AD TEP walkthrough: score + embeddings",
            "values": {"step_size": bp["values"]["step_size"], "output_score": True,
                       "output_embeddings": True, "runner_config": CHECKPOINTING_OFF}})
        st["bundle"] = b["id"]
        save(st)
    log(f"bundle {st['bundle']}")
    print(f"console: {console}/agents/{st['bundle']}", flush=True)

    # 3. inputs: the two test runs without labels
    d = pd.read_csv(ROLES / "test" / "tep_test.csv")
    lab = pd.read_csv(ROLES / "labels" / "tep_test_labels.csv")
    sources = {}
    for name, fault in TEST_RUNS.items():
        p = DIR / f"input_{name}.csv"
        if not p.exists():
            sim = lab.simulationrun[lab.fault_id == fault].iloc[0]
            pick = ((lab.fault_id == fault) & (lab.simulationrun == sim)).values
            d[pick].drop(columns=["label"]).to_csv(p, index=False)
            lab[pick].to_csv(DIR / f"input_{name}_labels.csv", index=False)
        sources[name] = p
    files = st.setdefault("files", {})
    for name, p in sources.items():
        if name not in files:
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            files[name] = upload_file(str(p), rename=f"ad-tep-walkthrough-{name}-{stamp}.csv")["file_id"]
            save(st)
    ids, srcs, order = files, sources, list(sources)

    # 4. one batch agent per file, as many at once as the deployment allows
    parallel = min(3 if free_trial() else 4, len(order))
    done, durations, t0 = [], [], time.time()

    def progress():
        left = len(order) - len(done)
        per = (sum(durations) / len(durations) if durations else FIRST_GUESS_MIN * 60) / 60
        log(f"{len(done)}/{len(order)} runs done, ~{max(1, round(per * -(-left // parallel)))} min left"
            if left else f"{len(order)}/{len(order)} runs done in {(time.time() - t0) / 60:.1f} min")

    def one(name):
        dst = DIR / f"{name}.csv"
        if not (dst.exists() and dst.stat().st_size):
            started = time.time()
            agents = st.setdefault("agents", {})
            if name not in agents:
                a = request("POST", f"{bundles_url(st['bundle'])}/run", body={
                    "connectors": {"source": [{"type": "file", "id": ids[name], "format": "csv"}]}})
                with lock:
                    agents[name] = a["id"]
                save(st)
                log(f"{name}: agent {a['id']}  {console}/agents/{st['bundle']}/runs/{a['id']}")
            poll_agent(agents[name], 3600, interval_s=20)
            if not download_results(agents[name], str(dst), source_csv=str(srcs[name])):
                with lock:
                    agents.pop(name)
                save(st)
                log(f"{name}: no complete output; rerun to retry")
                return None
            with lock:
                durations.append(time.time() - started)
        with lock:
            done.append(name)
            progress()
        return dst

    log(f"{len(order)} runs, {parallel} at a time: ~{round(FIRST_GUESS_MIN * -(-len(order) // parallel))} min expected")
    with ThreadPoolExecutor(parallel) as pool:
        got = list(pool.map(one, order))
    missing = [n for n, g in zip(order, got) if not g]
    links = {"bundle": f"{console}/agents/{st['bundle']}",
             **{n: f"{console}/agents/{st['bundle']}/runs/{a}" for n, a in st.get("agents", {}).items()}}
    (DIR / "links.json").write_text(dump(links))
    if missing:
        log(f"missing outputs: {missing}; rerun to resume")
        return 1
    log(f"all outputs in {DIR}; console links in {DIR / 'links.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
