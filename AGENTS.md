# Notes for coding agents

Archetype AI's anomaly discovery quickstart on the Tennessee Eastman Process (a simulated
chemical plant): a detector fitted on normal operation only, built and run on Newton,
Archetype's platform. [README.md](README.md) describes every stage.

## Walking someone through it

If you're asked to set up, try, demo or walk someone through this quickstart, follow
[.claude/skills/tep-walkthrough/SKILL.md](.claude/skills/tep-walkthrough/SKILL.md). It is
a Claude Code skill, but plain instructions and scripts any agent can follow: setup, then
three steps (data, build, run) with charts, pausing for the user between steps.

- **Charts:** the scripts write SVG files to `walkthrough_out/`. Show them inline if you
  can; otherwise give the user the paths.
- **Long runs:** Step 3 (`scripts/step3_run.py`) takes 5-15 minutes and blocks until every
  run is done. If your commands time out sooner, start it in a terminal or in the
  background and wait for `12/12 runs done` in its output before running
  `scripts/step3_charts.py`. Rerunning it is safe: it resumes from
  `walkthrough_out/step3/state.json`.

## Working in this repo

- **Setup:** `./setup.sh` (Git LFS data, `.venv`, requirements, `.env`). Run every script
  from the repo root with `.venv/bin/python`.
- **API key:** never print it, paste it, or ask for it in chat. If `./setup.sh` exits with
  status 2, ask the user to run `./setup.sh` in their own terminal and type the key at its
  hidden prompt. It finds the right endpoint (production or free trial) from the key.
- **Saved runs:** `fit/out/` and `eval_out/` hold this repo's own run, and scripts resume
  from the ids in them. Don't commit changes to them from your own runs.
- **Platform cost:** stages 4-9 create jobs on Newton under the user's key. Run them when
  asked, and say how long they'll take first.
