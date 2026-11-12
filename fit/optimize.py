#!/usr/bin/env python3
"""Stage 4 -- tune on the platform with the Optimizations API.

    python3 fit/optimize.py                          # 2 trials: k 5 and k 10 at the full search's winner
    python3 fit/optimize.py --new --window 32,48,64 --k 5,10,20 --trials 6
                                                     # add another optimization

Training is the library (the 40 fault-free reference sims, labelled by a
constant); validation is eval slice 01 and val_normal with the `label` column.
Both come from data/roles/ (prep/build_roles.py).

Every trial searches the quickstart's own copy of `ad`, in its project
(fit/atai.py's base_blueprint), so what it promotes lands in that project too.

Each option takes one value (pinned in `overrides.values` for every trial) or
several (searched). `feature_names` is a list, so it can only be pinned: search
another feature set with --new. Both Optimize legs use the trial's one
`step_size`, so validation is scored at the fit stride.

Writes fit/out/optimize_state.json (resume) and fit/out/optimize_<id>.json.
"""
from __future__ import annotations

import argparse
import datetime
import json

from atai import (COLUMN, NORMAL, OUT, REPO, ROLES, SEARCH, agents_base, aggregate, api_base,
                  base_blueprint, base_values, example, load_dotenv, load_state, log, manifest,
                  request, save_state, state_path, upload_all, wait)


def values(text: str, cast) -> list:
    return [cast(v) for v in text.split(",") if v]


def build_space(args) -> tuple[dict, dict]:
    """(search_space parameters, pinned values)."""
    space, pinned = {}, {}
    for name, vals in (("n_neighbors", values(args.k, int)), ("window_size", values(args.window, int)),
                       ("step_size", values(args.step, int)), ("metric", values(args.metric, str)),
                       ("pca_components", values(args.pca, int))):
        if len(vals) > 1 or name == "n_neighbors":  # the search space can't be empty
            space[name] = {"kind": "value", "spec": {"type": "categorical", "values": vals}}
        else:
            pinned[name] = vals[0]
    if ":" in args.threshold:
        lo, hi = (float(v) for v in args.threshold.split(":"))
        space["threshold"] = {"kind": "value", "spec": {"type": "float_range", "min": lo, "max": hi}}
    else:
        pinned["threshold"] = float(args.threshold)  # categorical rejects floats
    return space, pinned


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    d = SEARCH
    ap.add_argument("--window", default=d["window_size"], help="window_size, comma-separated")
    ap.add_argument("--step", default=d["step_size"], help="step_size, comma-separated")
    ap.add_argument("--k", default=d["n_neighbors"], help="n_neighbors")
    ap.add_argument("--metric", default=d["metric"], help="l1,l2,cosine")
    ap.add_argument("--pca", default=d["pca_components"], help="pca_components")
    ap.add_argument("--threshold", default=d["threshold"], help="a value, or LOW:HIGH to search")
    ap.add_argument("--features", default=d["feature_names"])
    ap.add_argument("--primary", default="anomaly.macro_f1")
    ap.add_argument("--trials", type=int, default=d["trials"])
    ap.add_argument("--new", action="store_true",
                    help="add another optimization; fit/test.py takes the best trial of all")
    args = ap.parse_args()
    load_dotenv()

    STATE = state_path("optimize")
    state = load_state(STATE)
    if args.new or not state.get("runs"):
        m = manifest()
        lib = [ROLES / f["file"] for f in m["library"]]
        val = [ROLES / f["file"] for f in m["validation"]]
        ids = upload_all(lib + val)
        space, pinned = build_space(args)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bp = base_blueprint()
        body = {"name": f"ad-tep {stamp}", "blueprint_id": bp["id"], "primary": args.primary,
                # output_score is pinned here because a package can't turn an
                # output on: the promoted blueprint is what every later stage runs.
                "overrides": {"values": {**base_values(m), **pinned, "output_score": True,
                                         "feature_names": values(args.features, str)}},
                "search_space": {"parameters": space}, "budget": {"max_trials": args.trials},
                "training_examples": [example(p.stem, ids[p], NORMAL) for p in lib],
                "validation_examples": [example(p.stem, ids[p], COLUMN) for p in val]}
        opt = request("POST", f"{agents_base()}/optimizations", body=body)
        state["endpoint"] = api_base()
        state.setdefault("runs", []).append(
            {"optimization": opt["id"],
             "request": {k: v for k, v in body.items() if not k.endswith("_examples")}})
        save_state(STATE, state)
        log(f"optimization {opt['id']}: {args.trials} trial(s), searching {sorted(space)}")

    ok = True
    for run in state["runs"]:
        opt = wait("optimizations", run["optimization"], every_s=30)
        trials = request("GET", f"{agents_base()}/optimizations/{opt['id']}/trials?limit=1000")["data"]
        (OUT / f"optimize_{opt['id']}.json").write_text(
            json.dumps({"optimization": opt, "trials": trials}, indent=1))
        pinned = run["request"]["overrides"]["values"]
        print(f"\noptimization {opt['id']}: {opt['status']}  (features {','.join(pinned['feature_names'])})")
        for t in sorted(trials, key=lambda t: t.get("objective_value") or -1, reverse=True):
            a = aggregate(t["metrics_report"]) if t.get("metrics_report") else {}
            print(f"  {t['id']}  {t['status']:<9} {json.dumps(t['trial_values']['values'])}  "
                  + "  ".join(f"{k} {a[k]:.4f}" for k in ("macro_f1", "foreground_macro_f1",
                                                          "detection_recall", "detection_precision")
                              if k in a))
            if t["status"] != "completed":
                print(f"    {json.dumps({k: t.get(k) for k in ('error', 'failure_reason', 'message') if t.get(k)})}")
        ok = ok and opt["status"] == "completed"
    if ok:
        print("\nnext: python3 fit/test.py (promotes the best trial across these runs)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
