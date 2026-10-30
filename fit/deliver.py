#!/usr/bin/env python3
"""Stage 6 -- deliver: run the promoted blueprint in batch over files with no labels.

    python3 fit/deliver.py

A package of fit/test.py's promoted blueprint, which already holds the detector
and every value the trial pinned, `output_score` included. A package adds nothing
(it has no values), so delivery runs at the trial's own step 8, the step Optimize
chose and the eval scored: one score every 8 samples (24 minutes). The package is
deployed as `batch`, and a session on that deployment runs over each delivery
chunk and val_normal, all five at once. The inputs are data/roles/delivery/, which carry no label column: the labels
stay in data/roles/labels/ until Stage 7 reads them.

val_normal (ten fault-free runs from the validation role) is delivered too:
Stage 7 sets the 1%-false-alarm threshold from its scores.

Writes eval_out/delivery/ad-output-*.csv and fit/out/deliver_state.json (resume:
finished outputs are skipped, started sessions are polled, not started again).
"""
from __future__ import annotations

import argparse
import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from atai import REPO, load_dotenv, load_state, log, manifest, save_state, state_path
from ad_api import create_package, deploy, download_results, open_session, poll_session, upload_file

OUT = REPO / "eval_out" / "delivery"
TIMEOUT_S = 3 * 3600
NETWORK_WAIT_S, NETWORK_RETRIES = 60, 60   # ride out an outage of up to an hour
lock = threading.Lock()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parallel", type=int, default=5)
    args = ap.parse_args()
    load_dotenv()
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

    def save():
        with lock:
            save_state(STATE, state)

    if "bundle" in state or "agents" in state:
        raise SystemExit(f"{STATE} is from a bundle or instance delivery: move it aside")
    if "package" not in state:
        pkg = create_package(bp["id"], "AD TEP quickstart delivery")
        state["package"] = pkg["id"]
        save()
        log(f"package {pkg['id']} ({pkg['status']}) on {bp['key']}")
    if "deployment" not in state:
        dpl = deploy(state["package"], "batch")
        state["deployment"] = dpl["id"]
        save()
        log(f"batch deployment {dpl['id']} ({dpl['status']})")

    files = [REPO / "data" / "roles" / f["file"] for f in m["delivery"]]
    if not files:
        raise SystemExit("no delivery files in the manifest: run prep/build_roles.py")
    OUT.mkdir(parents=True, exist_ok=True)

    def one(src: Path) -> Path | None:
        dst = OUT / f"ad-output-{src.stem.removeprefix('tep_')}.csv"
        if dst.exists() and dst.stat().st_size:
            return dst
        runs = state.setdefault("sessions", {})
        if src.stem not in runs:
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            fid = upload_file(str(src), rename=f"ad-tep-qs-{src.stem}-{stamp}.csv")["file_id"]
            ses = open_session(state["deployment"], [fid])
            with lock:
                runs[src.stem] = ses["id"]
            save()
            log(f"{src.name}: session {ses['id']}")
        if poll_session(runs[src.stem], TIMEOUT_S, interval_s=30) != "completed":
            log(f"{src.name}: session did not report completed; trying /results anyway")
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
