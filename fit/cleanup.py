#!/usr/bin/env python3
"""Clean up: delete the agents and bundles this quickstart left on the platform.

    python3 fit/cleanup.py            # list what would be deleted, and what stays
    python3 fit/cleanup.py --yes      # delete it

What it deletes, from the ids the stages recorded in fit/out/:

  Stage 6       the delivery agents and their bundle (deliver_state.json). Their
                outputs are already in eval_out/delivery/.
  Walkthrough   Step 3's 2 agents and their bundle (walkthrough_out/step3/state.json).

Agents go first (a bundle that still has an agent answers 409), a running one is
cancelled before it is deleted, and an id already gone counts as done. Progress
goes to fit/out/cleanup_state.json, so a rerun picks up where it stopped.

What stays: the promoted blueprint, the optimization and the eval.
After a cleanup, rerunning fit/deliver.py needs fit/out/deliver_state.json moved
aside, since its bundle is gone.
"""
from __future__ import annotations

import argparse
import json
import sys

from atai import REPO, agents_base, load_dotenv, load_state, log, request, save_state, state_path
from ad_api import list_bundle_runs


def call(method: str, path: str, body=None):
    """None when the object is already gone."""
    try:
        return request(method, f"{agents_base()}{path}", body=body, raw=method == "DELETE")
    except SystemExit as e:
        if "(404)" in str(e):
            return None
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yes", action="store_true", help="delete; without it, only list")
    args = ap.parse_args()
    load_dotenv()

    deliver = load_state(state_path("deliver"))
    test = load_state(state_path("test"))
    targets = []                                   # (stage, kind, id), agents before their bundle
    if deliver.get("bundle"):
        # the state holds each file's last attempt; the bundle's listing also finds replaced ones
        agents = set(deliver.get("agents", {}).values())
        agents |= {r["id"] for r in list_bundle_runs(deliver["bundle"])}
        targets += [("Stage 6", "instances", a) for a in sorted(agents)]
        targets += [("Stage 6", "bundles", deliver["bundle"])]
    walk_path = REPO / "walkthrough_out" / "step3" / "state.json"
    walk = json.loads(walk_path.read_text()) if walk_path.exists() else {}
    if walk.get("bundle"):
        agents = set(walk.get("agents", {}).values())
        agents |= {r["id"] for r in list_bundle_runs(walk["bundle"])}
        targets += [("Walkthrough", "instances", a) for a in sorted(agents)]
        targets += [("Walkthrough", "bundles", walk["bundle"])]

    done_path = state_path("cleanup")
    done = load_state(done_path)
    gone = set(done.get("deleted", []))
    todo = [t for t in targets if t[2] not in gone]
    for stage in ("Stage 6", "Walkthrough"):
        mine = [t for t in todo if t[0] == stage]
        print(f"{stage}: {sum(t[1] == 'instances' for t in mine)} agent(s), "
              f"{sum(t[1] == 'bundles' for t in mine)} bundle(s) to delete")
    print(f"already deleted: {len(gone & {t[2] for t in targets})}")
    bp = test.get("blueprint", {}).get("key")
    if bp:
        print(f"stays: blueprint {bp}, optimization {test.get('optimization')} "
              f"and eval(s) {', '.join(test.get('evals') or []) or 'none'}")
    if not args.yes:
        print("\nnothing deleted: rerun with --yes")
        return 0

    stuck = []
    for k, (stage, kind, obj) in enumerate(todo, 1):
        try:
            if kind == "instances":
                info = call("GET", f"/instances/{obj}")
                if info and info.get("status") not in ("completed", "failed", "cancelled", "canceled"):
                    call("POST", f"/instances/{obj}/cancel", body={})
            call("DELETE", f"/{kind}/{obj}")
            gone.add(obj)
        except SystemExit as e:
            # keep going: one object that will not delete used to strand every
            # object behind it, including whole stages further down the list
            stuck.append((kind, obj, str(e).splitlines()[0][:200]))
        if k % 25 == 0 or k == len(todo):
            done["deleted"] = sorted(gone)
            save_state(done_path, done)
            log(f"deleted {k - len(stuck)}/{len(todo)}")

    if stuck:
        print(f"\n{len(stuck)} object(s) would not delete:")
        for kind, obj, why in stuck:
            print(f"  {kind}/{obj}: {why}")
        print("an agent holds its bundle, and a bundle holds its blueprint: "
              "delete what holds them, then rerun")
    for kind, st in (("serve", serve), ("app_serving", bridge)):
        if st.get("bundle"):
            state_path(kind).unlink()
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
