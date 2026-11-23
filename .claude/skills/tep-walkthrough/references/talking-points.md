# Talking points

Plain-language material for each step. Use what helps the user; don't read it out,
except the parts marked "Say this, and no more" (Steps 0 and 1): show those exactly.

## Terms: three names, one job each

Never use these interchangeably, in the fixed text or when answering questions.

- **Newton** is Archetype AI's world model. In this quickstart it does one thing: it
  turns each window of sensor readings into a fingerprint (an embedding), with Omega,
  its sensor encoder. Say "Newton" only for that.
- **The Archetype platform** is the service around Newton, used through its Agent APIs
  and its console. It stores files, holds the project, runs the optimization (tries
  settings, tests them, keeps the best), promotes, packages and deploys the agent, and
  runs sessions. Queues, "busy", timings, free trial and production are all the platform.
- **The Anomaly Detection Agent** is what the user builds. It learns what normal looks
  like from Newton's fingerprints, and scores new windows. It lives on the platform.

## Timings

`setup.sh` reports which deployment the key belongs to; quote the matching column.
Free-trial times measured 2026-11-07 on the mini dataset; production not yet timed
(expect the same or faster). For contrast, the full dataset took about 30 min for
Step 2 and 95 min for Step 3's agent runs on the free trial.

| Step | Where it runs | Free trial | Production |
|---|---|---|---|
| 0 · Setup | Claude Code (clone, LFS, venv) | 1-3 min | 1-3 min |
| 1 · Data | Claude Code, locally | seconds | seconds |
| 2 · Build | Archetype platform: Optimizations API (Newton embeds the windows) | ~50 s (10 s upload, 40 s fit), plus any queue | not yet timed |
| 3 · Promote, package, deploy | Archetype platform: Agent APIs | seconds | seconds |
| 3 · 2 sessions | Archetype platform: one batch session per test run, both at once (Newton embeds the windows) | ~1 min (measured with bundles, before Agent Lifecycle 2.0) | not yet timed |
| 3 · Charts | Claude Code: PCA and drawing | seconds | seconds |

Platform times vary with load. The free trial runs on CPU, allows 3 jobs per org at
once and stops any job after 2 hours. On production, the repo's saved optimization is
only reachable for keys in the repo authors' org; everyone else gets a fresh one.

## Who does what

| Archetype platform (through its Agent APIs) | Newton (the world model) | Claude Code (this machine) |
|---|---|---|
| Stores the uploaded files and holds the project | Embeds every window with Omega 1.5, its pretrained sensor encoder (768 numbers per sensor per window) | Reads the repo's CSVs and manifest, and uploads the files |
| Runs the optimization: fits the Anomaly Detection Agent (per-sensor features + Newton's embeddings, PCA, Local Outlier Factor) on normal runs only, and scores each setting on validation | | Cuts the two test runs out of `tep_test.csv` and removes their labels |
| Promotes the winning trial to a reusable blueprint; packages it, deploys the package in batch and runs a session per file, returning per-window scores, labels and embeddings | | Recomputes the per-sensor features for the map, fits the 2-D PCA and draws every chart |

The key point: Newton and the fitted Anomaly Detection Agent live on the Archetype
platform and are reused by anything that calls its APIs (batch runs, the Evals API,
serving one window per query). Claude Code orchestrates and explains; it doesn't do the
modelling.

## Step 0: overview

Say this, and no more:

**Step 0: what this quickstart does**

You'll build an Anomaly Detection Agent that watches a simulated chemical plant and raises an alarm when it stops running normally. It learns from normal operation only: it never needs examples of faults.

Two names you'll see along the way:

- **Newton** is Archetype AI's world model. It reads raw sensor data and turns it into a form physical agents can understand.
- **The Archetype platform** is the service around Newton. Its Agent APIs store your files, build the agent and run it.

The three steps:

- **Step 1 · The data:** what the plant's sensor data looks like, and what each data file is for. Nothing runs.
- **Step 2 · Build the Anomaly Detection Agent:** the Archetype platform builds the agent: Newton reads the sensor data, the agent learns what "normal" looks like from it, and the platform picks the best settings. About a minute.
- **Step 3 · Run it:** the Anomaly Detection Agent checks two runs it has never seen, one normal and one with a fault. Two charts show when it raised the alarm. About a minute.

Say **"next"** to start Step 1.

## Step 1: the data

Say this, and no more:

**Step 1 of 3: the data**

**What it does:** introduces the data. Nothing runs yet. The data is a simulated chemical plant: 33 sensors, one reading every 3 minutes. We cut the original dataset (40 training runs, 20 kinds of fault, 48-hour runs) down to a small sample (5 training runs, 2 faults, 24-hour runs) to make it faster. Each file is one role.

| File | Role | What's in it |
|---|---|---|
| `tep_library.csv` | **Training:** the agent studies these runs to learn what normal looks like (Step 2). | 5 normal runs |
| `tep_validation.csv` | **Choosing the settings:** the Archetype platform tries a few settings and keeps the one that best tells normal from faulty here (Step 2). | 2 normal runs + 2 faulty runs |
| `tep_test.csv` | **Testing:** the agent checks runs it has never seen, to show it works on new data (Step 3). | 2 normal runs + 2 faulty runs |

- The Anomaly Detection Agent learns from **normal runs only**. It never sees a fault while learning.
- Each faulty run is normal for 8 hours, then a fault starts: **IDV 1** (easy to spot) or **IDV 10** (hard to spot).
- No run appears in two files.

Say **"next"** for Step 2: building the Anomaly Detection Agent on the Archetype platform.

Only if asked:
- A run is one simulation, 24 h (training: ~25 h). Values are rescaled so 0 is a
  sensor's usual level.
- IDV 1 is a step in the feed mix: sensors leave normal within an hour and stay out.
  IDV 10 is random feed-temperature variation: readings swing in and out of normal,
  so any single reading can look fine. That's why the Anomaly Detection Agent judges 2.4 h windows
  across all 33 sensors.
- Validation and test have the answers; delivery's are held back for later stages.
- Each file joins its runs with a 1-day gap. The platform skips any window that crosses a gap,
  so no window mixes two runs (checked 2026-11-07: training on the one library file
  scored exactly the same as on 5 separate files).

## Step 2: build the Anomaly Detection Agent

Before running the script, say this, and no more:

**Step 2 of 3: building the Anomaly Detection Agent**

**What it does:** the Archetype platform builds the Anomaly Detection Agent. Newton, Archetype AI's world model, reads the sensor data in the training file; the agent learns what normal looks like from it; and the platform tries 2 settings on the validation file and keeps the one that best tells normal from faulty.

**How long:** about 50 seconds on the free trial (a few seconds to upload, the rest on the platform). Longer if the platform is busy.

- **On the Archetype platform (through its Agent APIs):** creates a project, `AD TEP quickstart`, that holds everything this walkthrough makes; stores the 2 files, fits the Anomaly Detection Agent on normal runs only, and scores each setting.
- **Newton, the world model:** turns every 2.4-hour window into a fingerprint with Omega, its pretrained sensor encoder. Those fingerprints are what the agent learns from.
- **On this machine:** uploads the 2 files, starts the job and reads back the results.

As soon as the script prints the console link, say this, and no more:

View live status in the console: {console}

When it finishes, `scripts/step2_optimize.py` fills in the text between the markers below
(the `{...}` fields) and writes it to `walkthrough_out/step2.md`. Show that file exactly,
and no more.

<!-- step2-end -->
**Step 2 done: you've built your first Anomaly Detection Agent**

It now knows what this plant looks like when it's running normally. It learned that from 5 normal runs alone, without ever seeing a fault, and it lives on the Archetype platform, ready to check new data.

**How good is it?** The platform tested it on the validation file: 2 normal runs and 2 faulty runs it didn't learn from.

- {precision_sentence}
- {recall_sentence} Most of the ones it missed are from IDV 10, the hard fault: its readings drift in and out of the normal range, so some windows look normal.

**How it was chosen:** the platform tried 2 settings and kept the better one.

| Measure | What it means | Winner (k = {k}) | Other setting (k = {k2}) |
|---|---|---|---|
| **Macro-F1** | Overall score, out of 1. It balances doing well on normal windows and on fault windows. | **{f1}** | {f1_2} |
| **Recall** | Of all the fault windows, the share it caught. | {recall} | {recall_2} |
| **Precision** | Of all the alarms it raised, the share that were real faults. | {precision} | {precision_2} |

View live status in the console: {console}

Say **"next"** for Step 3: watch it check two runs it has never seen.
<!-- /step2-end -->

Only if asked:
- The fingerprint per window: Omega's embedding of each sensor plus 4 numbers per sensor
  (std, range, slope, median: how much it wiggles, spreads, trends, and its level),
  compressed to 16 numbers with PCA.
- Macro-F1 averages how well the agent does on normal windows and on fault windows, so
  neither can hide the other. k is the number of
  neighbours the agent compares each window with. Exact numbers are in
  `walkthrough_out/step2.json`.
- A project is where the platform keeps an agent's parts together: the blueprint it starts
  from (a copy of Archetype's `ad` blueprint), the optimization, the promoted blueprint,
  and in Step 3 its package, deployment and sessions. The script creates the project
  once and reuses it on later runs; it shows under Projects in the console.
- Only k (the number of neighbours) is searched. The other settings (window 48, step 8,
  PCA 16, threshold 1.215, ...) were chosen earlier on the full dataset.
- Expect k = 10 to win (macro-F1 0.884 vs 0.853, free trial 2026-11-07); precision 1.00
  vs 0.95. k = 5 vs 10 is close to a tie; the higher macro-F1 wins.

## Step 3: run the Anomaly Detection Agent

Before running the script, say this, and no more:

**Step 3 of 3: running the Anomaly Detection Agent**

**What it does:** the Archetype platform runs the Anomaly Detection Agent from Step 2 on data it has never seen. Newton turns every 2.4-hour window into a fingerprint and the agent scores it: the higher the score, the less it looks like normal.

**How long:** about 50 seconds on the free trial, for both runs together. Longer if the platform is busy.

- **On the Archetype platform (through its Agent APIs):** saves Step 2's winning setting as a reusable Anomaly Detection Agent in the project, deploys it, then runs it on 2 test runs it has never seen, both at once: one normal and one with fault IDV 1, with their answers removed. They show whether it catches the fault.
- **Newton, the world model:** turns every window of both runs into a fingerprint, for the agent to score.
- **On this machine:** prepares those inputs, then draws two charts.

As soon as the script prints a `console:` line, say this, and no more:

View live status in the console: {console}

When the script logs `1/2 runs done`, say this, and no more (the second is followed
straight away by the end text):

1 of 2 runs done.

When the runs finish, `scripts/step3_charts.py` draws the two charts, fills in the text
between the markers below (the `{...}` fields) and writes it to `walkthrough_out/step3.md`.
Show the map, then the score chart, then that file exactly, and no more.

<!-- step3-end -->
**Step 3 done: the Anomaly Detection Agent on two new runs**

- **Map (first chart above):** each dot is one 2.4-hour window from either run; blue where the agent said normal, red where it said anomaly. {map_sentence}
- **Anomaly score (second chart above):** {score_sentence}

View live status in the console: {deployment_link}

**That's the quickstart.** You built an Anomaly Detection Agent from normal runs only, and ran it on runs it had never seen.
<!-- /step3-end -->

Only if asked:
- `sampling-rate variance` warnings in a run's log or the console are expected: each test
  file joins its runs with a one-day gap, and the platform marks any window across a gap
  invalid on purpose, so no window mixes two runs.
- A sustained alarm is 3 windows in a row over the threshold, so one spike doesn't count.
  Expect the faulty run's first alarm about 1-1.5 h after the fault.
- A normal run can cross the line now and then: that's a false alarm. The threshold is a
  trade-off between catching faults and raising false alarms (the repo's later scoring
  stage sets it to a 1% false-alarm rate).
- The map's two axes are the 2 directions in which the two runs' windows differ most
  (PCA), so it shows how the faulty run's windows differ from the normal run's.
- After the fault the faulty run swings far from the normal windows (the plant reacting)
  and stays away: on 2026-11-07 it looped around them for 16 h without coming back.
- Each window's fingerprint is Omega's embedding of every sensor (about 25,000 numbers)
  plus 4 numbers per sensor. The map's two axes keep only ~8% of the variation each; the
  Anomaly Detection Agent itself uses 16 dimensions.
- In Step 3 the platform makes three things in the project: a package (the promoted blueprint
  with its models fixed), a batch deployment of that package, and one session per test
  run. A package takes no settings of its own, so the embeddings the map needs are
  switched on in Step 2's optimization.
- The per-run console links are in `walkthrough_out/step3/links.json`.
