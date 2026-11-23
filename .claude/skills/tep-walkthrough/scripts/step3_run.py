#!/usr/bin/env python3
"""Step 3 (Newton): promote the winning trial, package it, deploy the package in batch, and
run a session over one normal run and one faulty run it has never seen.

    .venv/bin/python .claude/skills/tep-walkthrough/scripts/step3_run.py

No evaluation is run (that is fit/test.py's job). The trial is promoted once; if it was
promoted before, that blueprint is reused. A package has no values, so the scores and
embeddings in the output are the ones Step 2's optimization pinned
(`output_score`, `output_embeddings`). The two test runs (the first normal run and
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

from ad_api import (create_package, deploy, deployment_ready, download_results, end_session,  # noqa: E402
                    open_session, package_ready, poll_session, upload_file)
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
    if st and (st.get("optimization") != opt or "bundle" in st):
        # an earlier Step 3 built on another optimization, or on a bundle (before Agent
        # Lifecycle 2.0): keep it aside, start over on this one
        old = OUT / f"step3_{st.get('optimization', 'old')}"
        while old.exists():
            old = old.with_name(old.name + "_old")
        DIR.rename(old)
        log(f"earlier Step 3 outputs moved to {old.relative_to(OUT.parent)}"
            + (": Step 2 has a new optimization" if st.get("optimization") != opt else ": they came from a bundle"))
        st = {}
    DIR.mkdir(parents=True, exist_ok=True)
    console = console_base(api_base())

    # 1. promote the best trial of the latest optimization (no evaluation)
    if "blueprint" not in st:
        st["optimization"], st["blueprint"] = opt, promote(opt, None)
        save(st)
    bp = st["blueprint"]
    log(f"blueprint {bp['key']} ({bp['id']}) from trial {bp['trial']}")

    if not bp["values"].get("output_embeddings"):
        sys.exit("this optimization has no embeddings in its output, and a package can't turn them on: "
                 "run step2_optimize.py again (it adds an optimization that has them)")

    # 2. a package of that blueprint (it has no values: the blueprint runs as promoted),
    #    deployed as batch. Both land in the blueprint's project.
    if "package" not in st:
        st["package"] = create_package(bp["id"], "AD TEP walkthrough: score + embeddings")["id"]
        save(st)
    log(f"package {st['package']}")
    if "deployment" not in st:
        package_ready(st["package"])
        st["deployment"] = deploy(st["package"], "batch")["id"]
        save(st)
    deployment_ready(st["deployment"])
    log(f"batch deployment {st['deployment']}")
    project = load_state(state_path("project")).get("project")
    here = f"{console}/projects/{project}" if project else console
    print(f"console: {here}/deployments/{st['deployment']}", flush=True)

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

    # 4. one session per file on the batch deployment, as many at once as the platform allows
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
            sessions = st.setdefault("sessions", {})
            if name not in sessions:
                ses = open_session(st["deployment"], [ids[name]])
                with lock:
                    sessions[name] = ses["id"]
                save(st)
                log(f"{name}: session {ses['id']}  {here}/sessions/{ses['id']}")
            if poll_session(sessions[name], 3600, interval_s=20) != "completed":
                log(f"{name}: session did not report completed; trying /results anyway")
            if not download_results(sessions[name], str(dst), source_csv=str(srcs[name])):
                try:
                    end_session(sessions[name])        # one that timed out may still be running
                except SystemExit as e:
                    log(f"{name}: could not end {sessions[name]}: {str(e).splitlines()[0][:200]}")
                with lock:
                    sessions.pop(name)
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
    links = {"deployment": f"{here}/deployments/{st['deployment']}",
             **{n: f"{here}/sessions/{a}" for n, a in st.get("sessions", {}).items()}}
    (DIR / "links.json").write_text(dump(links))
    if missing:
        log(f"missing outputs: {missing}; rerun to resume")
        return 1
    log(f"all outputs in {DIR}; console links in {DIR / 'links.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
