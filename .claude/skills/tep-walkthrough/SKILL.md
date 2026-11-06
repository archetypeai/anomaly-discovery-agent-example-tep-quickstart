---
name: tep-walkthrough
description: >-
  Guided, beginner-friendly walkthrough of Archetype AI's chemical plant (Tennessee Eastman, TEP) anomaly discovery quickstart in this repo, in 3 steps with charts: the data, building the detector with Newton's Optimizations API, then promoting it, running it as batch agents with Omega embeddings on, and charting the anomaly score and a 2-D embedding map. Also sets the repo up first (Git LFS, virtual environment, .env) when it isn't. Use whenever someone asks to set up, try, demo, walk through, explain or "show me" this quickstart, the TEP / chemical plant anomaly example, or anomaly discovery on Newton for a beginner, even if they don't name the skill.
---

# TEP quickstart walkthrough

Walk a beginner through the quickstart in **three steps**, pausing for the user to say
"next" between steps. The audience is new to anomaly detection and to Archetype's
platform, so use plain language, define terms the first time, and keep each step to
what it shows. Talking points for every step are in
[references/talking-points.md](references/talking-points.md); read it before Step 1.

All scripts are in `scripts/` and run from the repo root with the repo's environment,
e.g. `.venv/bin/python .claude/skills/tep-walkthrough/scripts/step1_chart.py`. They do
the deterministic work (data, API calls, charts) so every run of the walkthrough looks
the same; your job is to run them, show what they produce and explain it. Everything
they write goes to `walkthrough_out/` (gitignored).

## Throughout

- **Time first.** Before each step, say roughly how long it will take and whether that
  depends on the free trial or platform load (timings are in the talking points).
- **Newton vs Claude Code.** Say which work runs on Newton, Archetype's platform
  (uploads, Omega embeddings, fitting and scoring the detector, promoting, bundles,
  agent runs), and which runs locally in Claude Code (reading files, preparing inputs,
  computing PCA, drawing charts). This is what shows what the platform and its APIs add.
- **Charts inline.** Show every chart in the chat. If an inline visual tool is available
  (for example `show_widget`), pass it the SVG file's contents unchanged; the files are
  sized for that. Otherwise send or open the file. Either way, give its path.
- **Console links.** After every platform step, give the console link the script prints,
  and list them all again at the end.
- **Stay in scope.** Don't modify `app-serving/static/`, and don't run `fit/test.py`,
  `fit/deliver.py` or later stages: this walkthrough skips evaluation and delivery on
  purpose (Step 3 imports `fit/test.py`'s promote function only).
- **Secrets.** Never print, paste or ask for the API key in chat. Read whether it is set,
  not its value.

## Step 0: setup (only if needed, no pause)

1. If the current folder isn't this repo, clone it into a new folder and work there:
   `git clone https://github.com/archetypeai/anomaly-discovery-agent-example-tep-quickstart.git`
   (Git LFS must be installed, or the data files arrive as empty pointers).
2. Run `./setup.sh`. It fetches the LFS data, creates `.venv`, installs requirements and
   writes `.env` from `ATAI_API_KEY` in the environment. It works for production and
   free-trial users alike: it asks both deployments which one accepts the key and sets
   `ATAI_API_ENDPOINT` to match, so nobody needs to know their endpoint. Tell the user
   which deployment it found (the script says).
3. If it exits with status 2, the key is missing. Ask the user to run, in their own
   terminal (not this chat), the `cd "<repo path>" && ./setup.sh` line the script
   printed, and type the key at the hidden prompt. It writes `.env`, which every script
   reads, so this session needn't restart. When they say it's done, rerun `./setup.sh`
   here to confirm, then continue. (An `export ATAI_API_KEY=...` in a terminal only
   reaches this session if it was done before the session started, so don't suggest it
   now.) Step 1 needs no key, so you can start it meanwhile, but stop before Step 2.
4. Status 3 means both deployments rejected the key: ask the user to check it (a typo,
   an expired free-trial key) and run `./setup.sh` in their terminal again.

## Step 1: Data (local, under a minute)

Run `scripts/step1_chart.py`. Show a table of the four data roles (library, validation,
test, delivery: what each holds, whether it has answers, and what it's used for; see
the talking points), then the chart `walkthrough_out/step1_runs.svg`: the stripper
temperature over 48 h, one run per row on a shared scale, 3 normal runs in blue and 2
fault runs (IDV 1, IDV 10) in yellow, with the fault start marked. Explain what "normal"
looks like, that both fault runs match normal until hour 8, and why IDV 1 is easy and
IDV 10 is hard. Then wait for "next".

## Step 2: Build (Newton, seconds to ~8 minutes)

Run `scripts/step2_optimize.py`. It runs `fit/optimize.py`, which uploads the library and
validation files and creates an optimization on the `ad` blueprint. Newton embeds every
window with Omega, fits a nearest-neighbour detector on normal runs and scores each
setting on validation.

The repo ships its authors' saved optimization. If this key can reach it, the script
just reports it (seconds). If not (another org or deployment, the usual case for a new
user), it moves that file to `walkthrough_out/` and starts a fresh optimization: say it
will take about 6-8 minutes on the free trial, and run it in the background if your
environment allows, so the user isn't left waiting on a silent command.

From `walkthrough_out/step2.json`, explain the winning setting (window, step, features,
PCA, neighbours, threshold) and its scores (macro-F1, recall, precision) in plain words,
and give the optimization's console link. Then wait for "next".

## Step 3: Run (Newton, ~5-15 minutes; faster on production)

1. Run `scripts/step3_run.py` (default `--library 10`). On Newton it promotes the winning
   trial to a blueprint (reusing it if already promoted; no evaluation), creates one
   bundle with `output_score` and `output_embeddings` on, and runs 12 batch agents: one
   normal and one faulty run from test slice 02 with labels removed, plus the first 10
   library files. It blocks until all outputs are downloaded and logs
   `k/12 runs done, ~M min left`.
2. It takes longer than one command can wait, so run it in the background. Tell the user
   how many runs there are and the expected time, give the bundle's console link, and
   relay progress from its log as runs finish. The walkthrough isn't done until the
   charts are shown: when the run finishes, continue straight to the charts.
3. Run `scripts/step3_charts.py` and show both charts:
   - `walkthrough_out/step3_score.svg`: the anomaly score over time for both runs, with
     the fault start and the alarm threshold.
   - `walkthrough_out/step3_pca.svg`: the embedding map, a 2-D PCA fitted on the library
     windows of each window's Omega embedding plus its per-sensor features at equal
     weight. Library grey, normal blue, faulty red, darkening after the fault.
4. Explain them from `walkthrough_out/step3.json`: when the faulty run's first sustained
   alarm came, how the normal run behaved (be honest about any windows over the
   threshold: that is a false alarm), and what the map shows. Give the console links from
   `walkthrough_out/step3/links.json`, then a short recap with every link.

If a run fails or is interrupted, rerun the same script: it resumes from
`walkthrough_out/step3/state.json` and skips finished outputs.
