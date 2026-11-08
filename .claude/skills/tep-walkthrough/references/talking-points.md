# Talking points

Plain-language material for each step. Use what helps the user; don't read it out,
except the parts marked "Say this, and no more" (Steps 0 and 1): show those exactly.

## Timings

`setup.sh` reports which deployment the key belongs to; quote the matching column.
Free-trial times measured 2026-11-07 on the mini dataset; production not yet timed
(expect the same or faster). For contrast, the full dataset took about 30 min for
Step 2 and 95 min for Step 3's agent runs on the free trial.

| Step | Where it runs | Free trial | Production |
|---|---|---|---|
| 0 · Setup | Claude Code (clone, LFS, venv) | 1-3 min | 1-3 min |
| 1 · Data | Claude Code, locally | seconds | seconds |
| 2 · Build | Newton: Optimizations API | ~50 s (10 s upload, 40 s fit), plus any queue | not yet timed |
| 3 · Promote + bundle | Newton | seconds | seconds |
| 3 · 2 agent runs | Newton: batch agents, both at once | ~1 min | not yet timed |
| 3 · Charts | Claude Code: PCA and drawing | seconds | seconds |

Platform times vary with load. The free trial runs on CPU, allows 3 jobs per org at
once and stops any job after 2 hours. On production, the repo's saved optimization is
only reachable for keys in the repo authors' org; everyone else gets a fresh one.

## Newton vs Claude Code

| Newton (Archetype's platform, over its APIs) | Claude Code (this machine) |
|---|---|
| Stores the uploaded files | Reads the repo's CSVs and manifest |
| Embeds every window with Omega 1.5, Archetype's pretrained sensor model (768 numbers per sensor per window) | Cuts the two test runs out of `tep_test.csv` and removes their labels |
| Fits the Anomaly Detection Agent (per-sensor features + embeddings, PCA, Local Outlier Factor) on normal runs only, and scores each setting on validation | Recomputes the per-sensor features for the map |
| Promotes the winning trial to a reusable blueprint; creates bundles; runs batch agents and returns per-window scores, labels and embeddings | Fits the 2-D PCA and draws every chart |

The key point: the model, the fitted Anomaly Detection Agent and the scoring live on Newton and are
reused by anything that calls it (batch runs, the Evals API, serving one window per
query). Claude Code orchestrates and explains; it doesn't do the modelling.

## Step 0: overview

Say this, and no more:

**Step 0: what this quickstart does**

You'll build an Anomaly Detection Agent that watches a simulated chemical plant and raises an alarm when it stops running normally. It learns from normal operation only: it never needs examples of faults.

- **Step 1 · The data:** what the plant's sensor data looks like, and what each data file is for. Nothing runs.
- **Step 2 · Build the Anomaly Detection Agent:** Newton, Archetype AI's platform, learns what "normal" looks like and picks the best settings. About a minute.
- **Step 3 · Run it:** the Anomaly Detection Agent checks two runs it has never seen, one normal and one with a fault. Two charts show when it raised the alarm. About a minute.

Say **"next"** to start Step 1.

## Step 1: the data

Say this, and no more:

**Step 1 of 3: the data**

**What it does:** introduces the data. Nothing runs yet. The data is a simulated chemical plant: 33 sensors, one reading every 3 minutes. We cut the original dataset (40 training runs, 20 kinds of fault, 48-hour runs) down to a small sample (5 training runs, 2 faults, 24-hour runs) to make it faster. Each file is one role.

| File | Role | What's in it |
|---|---|---|
| `tep_library.csv` | **Training:** the agent studies these runs to learn what normal looks like (Step 2). | 5 normal runs |
| `tep_validation.csv` | **Choosing the settings:** Newton tries a few settings and keeps the one that best tells normal from faulty here (Step 2). | 2 normal runs + 2 faulty runs |
| `tep_test.csv` | **Testing:** the agent checks runs it has never seen, to show it works on new data (Step 3). | 2 normal runs + 2 faulty runs |

- The Anomaly Detection Agent learns from **normal runs only**. It never sees a fault while learning.
- Each faulty run is normal for 8 hours, then a fault starts: **IDV 1** (easy to spot) or **IDV 10** (hard to spot).
- No run appears in two files.

Say **"next"** for Step 2: building the Anomaly Detection Agent on Newton.

Only if asked:
- A run is one simulation, 24 h (training: ~25 h). Values are rescaled so 0 is a
  sensor's usual level.
- IDV 1 is a step in the feed mix: sensors leave normal within an hour and stay out.
  IDV 10 is random feed-temperature variation: readings swing in and out of normal,
  so any single reading can look fine. That's why the Anomaly Detection Agent judges 2.4 h windows
  across all 33 sensors.
- Validation and test have the answers; delivery's are held back for later stages.
- Each file joins its runs with a 1-day gap. Newton skips any window that crosses a gap,
  so no window mixes two runs (checked 2026-11-07: training on the one library file
  scored exactly the same as on 5 separate files).

## Step 2: build the Anomaly Detection Agent

Before running the script, say this, and no more:

**Step 2 of 3: building the Anomaly Detection Agent**

**What it does:** Newton, Archetype AI's platform, learns what normal looks like from the training file, tries 2 settings on the validation file, and keeps the one that best tells normal from faulty. About a minute on the free trial, longer if Newton is busy.

- **On Newton:** stores the 2 files, turns every 2.4-hour window into a fingerprint with Omega (Archetype's pretrained sensor model), fits the Anomaly Detection Agent on normal runs only, and scores each setting.
- **On this machine:** starts the job and reads back the results.

As soon as the script prints the console link, say this, and no more:

Running on Newton. Follow it live: {console}

When it finishes, `scripts/step2_optimize.py` fills in the text between the markers below
(the `{...}` fields) and writes it to `walkthrough_out/step2.md`. Show that file exactly,
and no more.

<!-- step2-end -->
**Step 2 done: the Anomaly Detection Agent is built**

Newton tried 2 settings and kept the better one. How they did on the validation file:

| | Winner (k = {k}) | Other setting (k = {k2}) |
|---|---|---|
| Overall score (macro-F1, out of 1) | **{f1}** | {f1_2} |
| Fault windows caught (recall) | {recall} | {recall_2} |
| Alarms that were real (precision) | {precision} | {precision_2} |

The fault windows it missed are mostly from IDV 10, the hard fault: its readings drift in and out of the normal range, so some windows look normal.

Console: {console}

Say **"next"** for Step 3: running the Anomaly Detection Agent on two runs it has never seen.
<!-- /step2-end -->

Only if asked:
- The fingerprint per window: Omega's embedding of each sensor plus 4 numbers per sensor
  (std, range, slope, median: how much it wiggles, spreads, trends, and its level),
  compressed to 16 numbers with PCA.
- Macro-F1 averages how well it does on normal windows and on fault windows, so neither
  can hide the other.
- Only k (the number of neighbours) is searched. The other settings (window 48, step 8,
  PCA 16, threshold 1.215, ...) were chosen earlier on the full dataset.
- Expect k = 10 to win (macro-F1 0.884 vs 0.853, free trial 2026-11-07); precision 1.00
  vs 0.95. k = 5 vs 10 is close to a tie; the higher macro-F1 wins.

## Step 3: run the Anomaly Detection Agent

Before running the script, say this, and no more:

**Step 3 of 3: running the Anomaly Detection Agent**

**What it does:** Newton runs the Anomaly Detection Agent from Step 2 on data it has never seen, and scores every 2.4-hour window: the higher the score, the less it looks like normal. About a minute on the free trial, longer if Newton is busy.

- **On Newton:** saves Step 2's winning setting as a reusable Anomaly Detection Agent, then runs it on 2 test runs it has never seen, both at once: one normal and one with fault IDV 1, with their answers removed. They show whether it catches the fault.
- **On this machine:** prepares those inputs, then draws two charts.

As soon as the script prints a `console:` line, say this, and no more:

Running on Newton. Follow it live: {console}

When the script logs `1/2 runs done`, say this, and no more (the second is followed
straight away by the end text):

1 of 2 runs done.

When the runs finish, `scripts/step3_charts.py` draws the two charts, fills in the text
between the markers below (the `{...}` fields) and writes it to `walkthrough_out/step3.md`.
Show the map, then the score chart, then that file exactly, and no more.

<!-- step3-end -->
**Step 3 done: the Anomaly Detection Agent on two new runs**

- **Map (first chart above):** each mark is one 2.4-hour window, circles for the normal run and squares for the faulty run; blue where the agent said normal, red where it said anomaly. {map_sentence}
- **Anomaly score (second chart above):** {score_sentence}

Console: {bundle_link}

**That's the quickstart.** You built an Anomaly Detection Agent from normal runs only, and ran it on runs it had never seen.
<!-- /step3-end -->

Only if asked:
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
- The per-run console links are in `walkthrough_out/step3/links.json`.
