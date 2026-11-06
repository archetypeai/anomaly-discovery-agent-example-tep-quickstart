#!/usr/bin/env python3
"""Step 3 (Newton): promote the winning trial, make one bundle with scores and embeddings on,
and run it as batch agents over one normal run, one faulty run and the first N library files.

    .venv/bin/python .claude/skills/tep-walkthrough/scripts/step3_run.py [--library 10]

No evaluation is run (that is fit/test.py's job). The trial is promoted once; if it was
promoted before, that blueprint is reused. The two test runs come from
data/roles/test/tep_eval_slice_02.csv with the label column removed.

Blocks until every run is downloaded, printing "k/N done, ~M min left" as runs finish.
Resumable: ids are kept in walkthrough_out/step3/state.json, finished outputs are skipped.
Expect about 12 minutes for 12 runs on the free trial (3 at a time), less on production.
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
from atai import api_base, free_trial, load_dotenv, load_state, log, manifest, request, state_path, upload_all  # noqa: E402
from test import promote  # noqa: E402  (fit/test.py's promote: reuses an already-promoted trial)

DIR = OUT / "step3"
STATE = DIR / "state.json"
TEST_RUNS = {"normal_run": "idv_00", "fault_run": "idv_01"}   # from test slice 02
FIRST_GUESS_MIN = 2.5        # one run on the free trial; replaced by the measured average
lock = threading.Lock()


def save(st):
    with lock:
        STATE.write_text(dump(st))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", type=int, default=10, help="library files to embed for the PCA map (default 10)")
    args = ap.parse_args()
    load_dotenv()
    DIR.mkdir(parents=True, exist_ok=True)
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    console = console_base(api_base())

    # 1. promote the best trial of the latest optimization (no evaluation)
    if "blueprint" not in st:
        opt = load_state(state_path("optimize")).get("runs", [{}])[-1].get("optimization")
        if not opt:
            sys.exit("no optimization yet: run step2_optimize.py first")
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
    log(f"bundle {st['bundle']}  {console}/agents/{st['bundle']}")

    # 3. inputs: the two test runs without labels, plus library files 1..N
    d = pd.read_csv(ROLES / "test" / "tep_eval_slice_02.csv")
    lab = pd.read_csv(ROLES / "labels" / "tep_eval_slice_02_labels.csv")
    sources = {}
    for name, fault in TEST_RUNS.items():
        p = DIR / f"input_{name}.csv"
        if not p.exists():
            d[(lab.fault_id == fault).values].drop(columns=["label"]).to_csv(p, index=False)
            lab[lab.fault_id == fault].to_csv(DIR / f"input_{name}_labels.csv", index=False)
        sources[name] = p
    lib = [ROLES / f["file"] for f in manifest()["library"][: args.library]]
    ids = {p.stem: fid for p, fid in upload_all(lib).items()}
    files = st.setdefault("files", {})
    for name, p in sources.items():
        if name not in files:
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            files[name] = upload_file(str(p), rename=f"ad-tep-walkthrough-{name}-{stamp}.csv")["file_id"]
            save(st)
    ids.update(files)
    srcs = {**sources, **{p.stem: p for p in lib}}
    order = list(sources) + [p.stem for p in lib]

    # 4. one batch agent per file, as many at once as the deployment allows
    parallel = 3 if free_trial() else 4
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
