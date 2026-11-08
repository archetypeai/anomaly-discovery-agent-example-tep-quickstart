# Notes for coding agents

Archetype AI's anomaly discovery quickstart on the Tennessee Eastman Process (a simulated
chemical plant): an Anomaly Detection Agent fitted on normal operation only, built and run on Newton,
Archetype's platform. [README.md](README.md) describes every stage.

## Walking someone through it

If you're asked to set up, try, demo or walk someone through this quickstart, follow
[.claude/skills/tep-walkthrough/SKILL.md](.claude/skills/tep-walkthrough/SKILL.md). It is
a Claude Code skill, but plain instructions and scripts any agent can follow: setup, then
an overview (Step 0), then three steps (data, build, run) with charts, pausing for the user between steps.

- **Charts:** the scripts write SVG files to `walkthrough_out/`. Show them inline if you
  can; otherwise give the user the paths.
- **Long runs:** Step 3 (`scripts/step3_run.py`) runs 2 agents on Newton (about a minute on the free trial)
  and blocks until every run is done. If your commands time out sooner, start it in a terminal or in the
  background and wait for `2/2 runs done` in its output before running
  `scripts/step3_charts.py`. Rerunning it is safe: it resumes from
  `walkthrough_out/step3/state.json`.

## Working in this repo

- **Setup:** `./setup.sh` (Git LFS data, `.venv`, requirements, `.env`). Run every script
  from the repo root with `.venv/bin/python`.
- **API key:** never print it, paste it, or ask for it in chat. If `./setup.sh` exits with
  status 2, ask the user to run `./setup.sh` in their own terminal and type the key at its
  hidden prompt. It finds the right endpoint (production or free trial) from the key.
- **Data:** `data/roles/` is a mini dataset, one file per role (5 training runs; IDV 1
  and IDV 10 in 24 h runs), cut from the Tennessee Eastman Process data (see the README).
- **Saved runs:** scripts write state to `fit/out/` and `eval_out/` (both gitignored) and
  resume from the ids in them.
- **Platform cost:** the stages create jobs on Newton under the user's key. Run them when
  asked, and say how long they'll take first. `fit/cleanup.py --yes` deletes the agents
  and bundles they leave.
