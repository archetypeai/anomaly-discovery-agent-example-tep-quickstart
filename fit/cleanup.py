#!/usr/bin/env python3
"""Clean up: delete the sessions, deployments and packages this quickstart left on the platform.

    python3 fit/cleanup.py            # list what would be deleted, and what stays
    python3 fit/cleanup.py --yes      # delete it

It starts from the packages the stages recorded in fit/out/:

  Stage 8   fit/serve.py's, if it was killed before it could delete them
            (serve_state.json).
  Stage 9   the serving bridge's, if app-serving/ was killed before it could
            delete them (app_serving_state.json): a serving deployment holds a
            worker until it is stopped. And fit/library_embeddings.py's
            (library_state.json; the embeddings are already on disk).
  Stage 6   the delivery's (deliver_state.json). Its outputs are already in
            eval_out/delivery/.

For each package it lists the package's deployments and their sessions, so a
session or deployment a stage never got to record is found too. Sessions go
first, then deployments, then the package: each holds the one after it. A
session still going is cancelled and a deployment still up is stopped before
it is deleted, and an id already gone counts as done. Progress goes to
fit/out/cleanup_state.json, so a rerun picks up where it stopped.

What stays: the project, its copy of `ad`, the promoted blueprint, and the
optimization and eval the README cites; fit/app_blueprint.py's blueprint and
optimization too. After a cleanup, rerunning fit/deliver.py needs
fit/out/deliver_state.json moved aside, since its package is gone.
"""
from __future__ import annotations

import argparse
import sys

from atai import load_dotenv, load_state, log, request, save_state, state_path
from ad_api import TERMINAL, deployments_url, packages_url, sessions_url

URLS = {"sessions": sessions_url, "deployments": deployments_url, "packages": packages_url}


def call(method: str, kind: str, obj: str, suffix: str = "", body=None):
    """None when the object is already gone."""
    try:
        return request(method, URLS[kind](obj) + suffix, body=body, raw=method == "DELETE")
    except SystemExit as e:
        if "(404)" in str(e):
            return None
        raise


def listing(kind: str, **query) -> list[str]:
    q = "&".join(f"{k}={v}" for k, v in query.items())
    return [r["id"] for r in request("GET", f"{URLS[kind]()}?{q}&limit=1000")["data"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yes", action="store_true", help="delete; without it, only list")
    args = ap.parse_args()
    load_dotenv()

    states = {"serve": "Stage 8", "app_serving": "Stage 9", "library": "Stage 9", "deliver": "Stage 6"}
    targets = []                                   # (stage, kind, id), each before what it holds
    for name, stage in states.items():
        pkg = load_state(state_path(name)).get("package")
        if not pkg or not call("GET", "packages", pkg):
            continue
        deployments = listing("deployments", package_id=pkg)
        targets += [(stage, "sessions", s) for d in deployments for s in listing("sessions", deployment_id=d)]
        targets += [(stage, "deployments", d) for d in deployments]
        targets += [(stage, "packages", pkg)]

    done_path = state_path("cleanup")
    done = load_state(done_path)
    gone = set(done.get("deleted", []))
    todo = [t for t in targets if t[2] not in gone]
    for stage in ("Stage 9", "Stage 8", "Stage 6"):
        mine = [t for t in todo if t[0] == stage]
        print(f"{stage}: " + ", ".join(f"{sum(t[1] == kind for t in mine)} {kind}" for kind in URLS) + " to delete")
    test = load_state(state_path("test"))
    if test.get("blueprint"):
        print(f"stays: blueprint {test['blueprint']['key']}, optimization {test.get('optimization')} "
              f"and eval {test.get('eval')}, and the project with its copy of `ad`")
    if not args.yes:
        print("\nnothing deleted: rerun with --yes")
        return 0

    stuck = []
    for k, (stage, kind, obj) in enumerate(todo, 1):
        try:
            info = call("GET", kind, obj)
            if kind == "sessions" and info and info["status"] not in TERMINAL:
                call("POST", kind, obj, "/cancel", body={})
            if kind == "deployments" and info and info["status"] not in ("stopped", "failed"):
                call("POST", kind, obj, "/stop", body={})
            call("DELETE", kind, obj)
            gone.add(obj)
        except SystemExit as e:
            # keep going: one object that will not delete must not strand the rest
            stuck.append((kind, obj, str(e).splitlines()[0][:200]))
        if k % 25 == 0 or k == len(todo):
            done["deleted"] = sorted(gone)
            save_state(done_path, done)
            log(f"deleted {k - len(stuck)}/{len(todo)}")

    if stuck:
        print(f"\n{len(stuck)} object(s) would not delete:")
        for kind, obj, why in stuck:
            print(f"  {kind}/{obj}: {why}")
        print("a session holds its deployment, and a deployment its package: "
              "delete what holds them, then rerun")
    else:
        for name in ("serve", "app_serving"):
            state_path(name).unlink(missing_ok=True)
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
