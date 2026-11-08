#!/usr/bin/env python3
"""Step 2 (Newton): run fit/optimize.py, then summarise the winning trial.

fit/optimize.py resumes whatever fit/out/optimize_state.json names, which only works for
a key in the same org on the same deployment. So first check a saved optimization, if
there is one, is reachable with this key:
  * none       -> fit/optimize.py starts a fresh optimization in your org;
  * reachable  -> fit/optimize.py just reports it (seconds);
  * not        -> the file is moved to walkthrough_out/ and a fresh one starts.
Prints the console link as soon as the optimization exists, then the winner, its scores
and the link as JSON (also walkthrough_out/step2.json), then the talking points' Step 2
end text filled in from them (also walkthrough_out/step2.md).
"""
import json
import re
import shutil
import subprocess
import sys

from common import OUT, REPO, SKILL, console_base, dump, write

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
              "walkthrough_out/repo_optimize_state.json; starting a fresh one", flush=True)
    # Stream fit/optimize.py's log, adding the console link as soon as the optimization id
    # appears, and dropping its "next: fit/test.py" hint (in the walkthrough, Step 3 is next).
    proc = subprocess.Popen([sys.executable, "-u", str(REPO / "fit" / "optimize.py")], cwd=REPO,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    linked = False
    for line in proc.stdout:
        if line.startswith("next: "):
            continue
        print(line, end="", flush=True)
        m = re.search(r"optimization (opt_\w+):", line)
        if m and not linked:
            print(f"console: {console_base(api_base())}/optimizations/{m.group(1)}", flush=True)
            linked = True
    if code := proc.wait():
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
    write("step2.md", end_text(summary))
    print("\n--- walkthrough_out/step2.md (show this exactly) ---\n" + end_text(summary))
    return 0


def end_text(summary: dict) -> str:
    """The talking points' Step 2 end text, its {fields} filled in from this run."""
    tp = (SKILL / "references" / "talking-points.md").read_text()
    template = tp.split("<!-- step2-end -->\n", 1)[1].split("<!-- /step2-end -->", 1)[0]
    win, *rest = summary["trials"]
    other = rest[0] if rest else {}
    pct = lambda v: f"{v:.0%}" if v is not None else "–"          # noqa: E731
    two = lambda v: f"{v:.2f}" if v is not None else "–"          # noqa: E731
    return template.format(
        console=summary["console"],
        k=win["values"]["n_neighbors"], f1=two(win.get("macro_f1")),
        recall=pct(win.get("detection_recall")), precision=pct(win.get("detection_precision")),
        k2=other.get("values", {}).get("n_neighbors", "–"), f1_2=two(other.get("macro_f1")),
        recall_2=pct(other.get("detection_recall")), precision_2=pct(other.get("detection_precision")))


if __name__ == "__main__":
    raise SystemExit(main())
