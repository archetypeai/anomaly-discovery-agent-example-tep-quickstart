---
name: tep-walkthrough
description: >-
  Guided, beginner-friendly walkthrough of Archetype AI's chemical plant (Tennessee Eastman, TEP) anomaly discovery quickstart in this repo: an overview, then 3 steps with charts: the data, building the Anomaly Detection Agent with Newton's Optimizations API, then promoting it, running it as batch agents with Omega embeddings on, and charting the anomaly score and a 2-D embedding map. Also sets the repo up first (Git LFS, virtual environment, .env) when it isn't. Use whenever someone asks to set up, try, demo, walk through, explain or "show me" this quickstart, the TEP / chemical plant anomaly example, or anomaly discovery on Newton for a beginner, even if they don't name the skill.
---

# TEP quickstart walkthrough

Walk a beginner through the quickstart: **Step 0**, an overview, then **three steps**,
pausing for the user to say "next" after each. The audience is new to anomaly detection
and to Archetype's platform, so use plain language, define terms the first time, and
keep each step to what it shows. Talking points for every step are in
[references/talking-points.md](references/talking-points.md); read it before Step 0.

Order: Setup (silently, only if needed), Step 0, Step 1, Step 2, Step 3.

All scripts are in `scripts/` and run from the repo root with the repo's environment,
e.g. `.venv/bin/python .claude/skills/tep-walkthrough/scripts/step2_optimize.py`. They do
the deterministic work (data, API calls, charts) so every run of the walkthrough looks
the same; your job is to run them, show what they produce and explain it. Everything
they write goes to `walkthrough_out/` (gitignored).

## Throughout

- **Fixed text.** Every message of Steps 0-3 is written in the talking points: Steps 0
  and 1, and the start, link, progress and end messages of Steps 2 and 3 (their end text
  as the scripts fill it in). Show each exactly as written, adding nothing before or
  after. They already say how long each step takes, what runs on Newton and what runs on
  this machine, and give the console links. Answer questions from the "Only if asked"
  notes.
- **Charts inline.** Show every chart in the chat. If an inline visual tool is available
  (for example `show_widget`), pass it the SVG file's contents unchanged; the files are
  sized for that. Only if you can't show it inline, send or open the file and give its
  path.
- **Stay in scope.** Don't run `fit/test.py`, `fit/deliver.py` or later stages: this
  walkthrough skips evaluation and delivery on purpose (Step 3 imports `fit/test.py`'s
  promote function only). The README covers them for anyone who wants to go on.
- **Secrets.** Never print, paste or ask for the API key in chat. Read whether it is set,
  not its value.

## Setup (only if needed, before Step 0, no pause)

Needed when `.venv/bin/python` is missing or `.env` has no `ATAI_API_KEY` (check that
it is set, never print it). Otherwise skip straight to Step 0.

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
   now.) Steps 0 and 1 need no key, so you can start them meanwhile, but stop before Step 2.
4. Status 3 means both deployments rejected the key: ask the user to check it (a typo,
   an expired free-trial key) and run `./setup.sh` in their terminal again.

## Step 0: Overview (no script, no key)

Nothing runs. Show the talking points' Step 0 text exactly as written, from the line
**Step 0: what this quickstart does** to the line ending "to start Step 1.", and add
nothing before or after it (if Setup just ran, one line saying it's ready may come
first). Then wait for "next".

## Step 1: Data (no script, no key)

Nothing runs. Show the talking points' Step 1 text exactly as written, from the line
**Step 1 of 3: the data** to the line ending "building the Anomaly Detection Agent on Newton." (not
the "Only if asked" notes below it), and add nothing before or after it: no time estimate and no Newton vs
Claude Code note (the text already says nothing runs), no chart. Then wait for "next".

## Step 2: Build (Newton, about a minute)

Three messages, each shown exactly as written in the talking points' Step 2 section, with
nothing added before or after:

1. **Start.** Show the text from **Step 2 of 3: building the Anomaly Detection Agent** to
   the line ending "reads back the results.", and in the same turn run
   `scripts/step2_optimize.py` (in the background if your environment allows).
2. **Link.** As soon as the script prints a `console:` line, show the one line
   "Running on Newton. Follow it live: <that link>", plain, as written. Skip it if the
   script has already finished by then (it reused a saved run, in seconds): the end
   text carries the link.
3. **End.** When the script finishes, show `walkthrough_out/step2.md` exactly: the
   script fills the talking points' end text in from this run (both settings' scores, the
   console link). Then wait for "next".

What the script does: it runs `fit/optimize.py`, which uploads the library and validation
files and creates an optimization on the `ad` blueprint. Newton embeds every window with
Omega, fits the Anomaly Detection Agent (a nearest-neighbour model) on normal runs and
scores each setting on validation. The repo ships no saved optimization for the mini
dataset, so a first run starts a fresh one: 52 s on the free trial (2026-11-07: 10 s
uploading, 40 s on Newton), plus any queue. If `fit/out/optimize_state.json` exists and
this key can reach it, the script just reports it (seconds); if not, it moves that file
to `walkthrough_out/` and starts fresh. Answer questions from the talking points' "Only
if asked" notes.

## Step 3: Run (Newton, about a minute)

Four kinds of message, each shown exactly as written in the talking points' Step 3
section, with nothing added before or after:

1. **Start.** Show the text from **Step 3 of 3: running the Anomaly Detection Agent** to
   the line ending "then draws two charts.", and in the same turn run
   `scripts/step3_run.py` in the background (it blocks until every run is downloaded).
2. **Link.** As soon as the script prints a `console:` line, show the one line
   "Running on Newton. Follow it live: <that link>", plain, as written.
3. **Progress.** When its log shows `1/2 runs done`, show the one line "1 of 2 runs
   done." Not at `2/2`: the end follows. Skip it if you only see it once the script has
   exited.
4. **End.** When it finishes, run `scripts/step3_charts.py`, then show the map
   `walkthrough_out/step3_pca.svg`, then the score chart `walkthrough_out/step3_score.svg`
   (see Charts inline), then `walkthrough_out/step3.md` exactly: the script fills the talking
   points' end text in from this run. That ends the walkthrough.

If you can't run the script in the background, run it in the foreground and skip the
link and progress messages: the end text carries the link.

What the scripts do: `step3_run.py` promotes Step 2's winning trial to a blueprint
(reusing it if already promoted; no evaluation), creates one bundle with `output_score`
and `output_embeddings` on, and runs 2 batch agents at once: the first normal run and
the IDV 1 run from `tep_test.csv` with labels removed. 0.8 min on the free trial, 2026-11-07. If Step 2 has a new
optimization since the last Step 3, it moves the old Step 3 outputs aside and starts
over. `step3_charts.py` draws a 2-D map of the two test
runs' windows (PCA fitted on those windows' Omega embeddings plus their per-sensor
features), coloured by the agent's own verdict (blue normal, red anomaly), and the anomaly score over
time.

If a run fails or is interrupted, rerun the same script: it resumes from
`walkthrough_out/step3/state.json` and skips finished outputs.
