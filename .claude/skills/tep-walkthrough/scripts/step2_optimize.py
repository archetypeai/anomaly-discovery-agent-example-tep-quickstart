#!/usr/bin/env python3
"""Step 2 (Newton): run fit/optimize.py, then summarise the winning trial.

The repo ships fit/out/optimize_state.json from its authors' own run. fit/optimize.py
resumes whatever that file names, which only works for a key in the same org on the
same deployment. So first check the saved optimization is reachable with this key:
  * reachable  -> fit/optimize.py just reports it (seconds);
  * not        -> the file is moved to walkthrough_out/ and fit/optimize.py starts a
                  fresh optimization in your org (about 6-8 minutes on the free trial).
Prints the winner, its scores and the console link as JSON (also walkthrough_out/step2.json).
"""
import json
import shutil
import subprocess
import sys

from common import OUT, REPO, console_base, dump, write

from ad_api import deployment  # noqa: E402
from atai import agents_base, aggregate, api_base, load_dotenv, load_state, request, state_path  # noqa: E402


def reachable(state: dict) -> bool:
    if not state.get("runs"):
        return False
    if deployment(state.get("endpoint", "")) != deployment(api_base()):
        return False
    try:
        for run in state["runs"]:
            request("GET", f"{agents_base()}/optimizations/{run['optimization']}")
    except SystemExit:          # ad_api.request exits on an HTTP error (404/403: another org's run)
        return False
    return True


def main() -> int:
    load_dotenv()
    path = state_path("optimize")
    # read the file directly: atai.load_state exits outright on another deployment's state
    state = json.loads(path.read_text()) if path.exists() else {}
    fresh = bool(state.get("runs")) and not reachable(state)
    if fresh:
        OUT.mkdir(exist_ok=True)
        shutil.move(str(path), OUT / "repo_optimize_state.json")
        print("the saved optimization belongs to another org or deployment: moved to "
              "walkthrough_out/repo_optimize_state.json; starting a fresh one (~6-8 min)", flush=True)
    code = subprocess.call([sys.executable, str(REPO / "fit" / "optimize.py")], cwd=REPO)
    if code:
        return code

    opt_id = load_state(path)["runs"][-1]["optimization"]
    saved = json.loads((REPO / "fit" / "out" / f"optimize_{opt_id}.json").read_text())
    opt, trials = saved["optimization"], saved["trials"]
    pinned = load_state(path)["runs"][-1]["request"]["overrides"]["values"]
    ranked = sorted((t for t in trials if t.get("metrics_report")),
                    key=lambda t: t.get("objective_value") or -1, reverse=True)
    summary = {
        "optimization": opt_id, "status": opt["status"], "fresh_run": fresh or not state.get("runs"),
        "console": f"{console_base(api_base())}/optimizations/{opt_id}",
        "pinned": {k: v for k, v in pinned.items() if k not in ("data_columns", "timestamp_column")},
        "trials": [{"id": t["id"], "values": t["trial_values"]["values"],
                    **{k: round(v, 4) for k, v in aggregate(t["metrics_report"]).items()
                       if k in ("macro_f1", "foreground_macro_f1", "detection_recall", "detection_precision")}}
                   for t in ranked],
    }
    write("step2.json", dump(summary))
    print("\n" + dump(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
