#!/usr/bin/env python3
"""Stage 9, once -- a blueprint for app-serving: the winning configuration, embeddings on.

    python3 fit/app_blueprint.py        # one 1-trial optimization (~5 min), then promote

A package runs a blueprint exactly as promoted, and Stage 5's blueprint has
`output_embeddings: false`, so its agents return no embeddings and the app's
embedding view gets no live trail. Until a package or instance can turn an
output on, this is the stop-gap: a second optimization that pins every value
of Stage 5's winning trial (window, step, k, metric, PCA, threshold, features)
plus `output_embeddings: true`, on the same library and validation files, with
one trial. Promoting that trial gives a blueprint that is the winning
configuration with embeddings on, promoted like any other (no copied
document), which the bridge and fit/library_embeddings.py package.

The trial refits the detector, so it is a second artifact of the same
configuration; its validation scores are printed next to the winner's, and
fit/serve.py-style checks against Stage 6 are how to confirm it answers the same.

Writes fit/out/app_blueprint_state.json (resume: an optimization already
started is polled, a trial already promoted is reused).
"""
from __future__ import annotations

import datetime
import sys

from atai import (COLUMN, NORMAL, ROLES, aggregate, agents_base, api_base, example, load_dotenv,
                  load_state, log, manifest, request, save_state, state_path, upload_all, wait)


def main() -> int:
    load_dotenv()
    test = load_state(state_path("test"))
    if "blueprint" not in test:
        sys.exit("no promoted blueprint: run fit/test.py first")
    winner = test["blueprint"]
    STATE = state_path("app_blueprint")
    state = load_state(STATE)
    if state.get("source") not in (None, winner["key"]):
        sys.exit(f"{STATE} is for {state['source']}, not {winner['key']}: move it aside")
    state["source"] = winner["key"]

    if "optimization" not in state:
        m = manifest()
        lib = [ROLES / f["file"] for f in m["library"]]
        val = [ROLES / f["file"] for f in m["validation"]]
        ids = upload_all(lib + val)
        pinned = {k: v for k, v in winner["values"].items() if k != "n_neighbors"}
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        body = {"name": f"ad-tep app {stamp}", "blueprint_id": request("GET", f"{agents_base()}/blueprints/ad")["id"],
                "primary": "anomaly.macro_f1",
                "overrides": {"values": {**pinned, "output_embeddings": True}},
                # the search space can't be empty: k, with the winner's one value
                "search_space": {"parameters": {"n_neighbors": {
                    "kind": "value", "spec": {"type": "categorical", "values": [winner["values"]["n_neighbors"]]}}}},
                "budget": {"max_trials": 1},
                "training_examples": [example(p.stem, ids[p], NORMAL) for p in lib],
                "validation_examples": [example(p.stem, ids[p], COLUMN) for p in val]}
        opt = request("POST", f"{agents_base()}/optimizations", body=body)
        state.update(endpoint=api_base(), optimization=opt["id"])
        save_state(STATE, state)
        log(f"optimization {opt['id']}: 1 trial, {winner['key']}'s values with output_embeddings on")

    if "blueprint" not in state:
        opt = wait("optimizations", state["optimization"], every_s=30)
        trials = request("GET", f"{agents_base()}/optimizations/{opt['id']}/trials?limit=10")["data"]
        trial = next((t for t in trials if t["status"] == "completed"), None)
        if opt["status"] != "completed" or not trial:
            sys.exit(f"{opt['id']} is {opt['status']}; no completed trial")
        a = aggregate(trial["metrics_report"])
        log(f"{trial['id']}: validation macro_f1 {a['macro_f1']:.4f}, "
            f"recall {a['detection_recall']:.4f}, precision {a['detection_precision']:.4f}")
        bp = trial.get("promoted_blueprint") or request(
            "POST", f"{agents_base()}/optimizations/{opt['id']}/trials/{trial['id']}/promote", body={
                "blueprint_key": f"ad-tep-qs-app-{trial['id']}",
                "name": f"AD TEP quickstart, app-serving ({winner['key']} with embeddings on)",
                "description": f"{winner['key']}'s configuration with output_embeddings: true, "
                               f"refitted in {opt['id']}, for app-serving's embedding view."})
        state["blueprint"] = {"id": bp["id"], "key": bp["blueprint_key"], "trial": trial["id"],
                              "values": {**winner["values"], "output_embeddings": True}}
        save_state(STATE, state)
        log(f"promoted {trial['id']} -> {bp['blueprint_key']} ({bp['id']})")
    print(f"\napp-serving blueprint: {state['blueprint']['key']}; "
          f"next: python3 fit/library_embeddings.py, then app-serving/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
