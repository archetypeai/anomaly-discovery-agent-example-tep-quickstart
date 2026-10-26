# Anomaly Discovery on the Tennessee Eastman Process: quickstart

## TL;DR

- **What:** an agent that watches a chemical plant's 33 process variables,
  sampled every 3 minutes, and every 24 minutes scores how far the process has
  moved from normal over the last 2.4 hours. It is fitted
  on **normal operation only**: no fault is labelled, collected or shown to it
  before deployment. Each window is embedded with frozen Omega 1.5, fused with
  per-channel statistics, and scored by a Local Outlier Factor detector.
- **Data:** the Tennessee Eastman Process, Rieth et al. (2017) release
  ([public domain](#data-attribution)): one simulated plant, run many times,
  with 20 kinds of fault.
  - **Training and scoring:** 40 fault-free runs (training), then incidents
    of every fault type, split into validation and test.
  - **Delivery:** 84 more runs of the plant, 80 of them faulty, with their
    labels held back.
- **The lifecycle:**

| stage | what happens | time (measured 2026-10-13) |
|---|---|---|
| 0 | download the dataset (1.4 GB) and convert it | ~7 min |
| 1a–1c | check the raw data, cut it into runs, check again | ~50 s |
| 2–3 | build the files the platform receives, and check them | ~1 s |
| 4 | **Optimize:** fit on the normal runs, score 2 settings on validation | 6 min |
| 5 | **promote** the best setting to a blueprint, **test** it once with the Evals API | 3 min |
| 6 | **deliver:** a package of that blueprint, run over the delivery files | 3–9 min |
| 7 | **score** the delivery against the held-back labels | seconds |
| 8 | **serve:** the same blueprint answering one window per query (agent serving, Dev and Staging), checked against Stage 6 | ~3 min |
| 9 | optional: **watch it live**, the delivery replayed through a serving agent ([`app-serving/`](app-serving/README.md), Dev and Staging) | ~8 min once, then ~4 min a run |

  About **30 minutes** end to end, 21 of them on the platform. Platform times
  vary with load. Stages 6 and 8 were measured on Dev on 2026-10-26.

- **One configuration throughout.** Stage 4's optimization chooses the
  configuration, and every later stage runs exactly what it chose, step
  included: the eval, the delivery, serving and the app all score a window every
  8 samples (24 minutes). Agent Lifecycle 2.0 packages run a promoted blueprint as
  it is, with no per-run overrides; see [PACKAGES.md](PACKAGES.md).

- **Skip the 1.4 GB download:** Stage 1's prepared files and the role files are
  in the repo, in Git LFS. See [Shortcuts](#shortcuts-skip-the-download).

## The scenario

- **A plant has normal operation on record and no labelled fault library**: the
  faults that will happen have not happened yet. Here that record is 40
  fault-free runs of the Tennessee Eastman Process, 25 hours each.
- **Settings are chosen on the plant's incident record** (validation): one run of
  every fault type, plus ten more fault-free runs.
- **We report how the agent does on incidents it has never seen** (the test), once.
- **We then run it over more of the plant's operation** (the delivery), with
  its labels hidden, and score the outputs afterwards: how many faults it
  catches, how soon, and how often it fires on normal operation.

### The plant and its faults

A closed-loop simulation of a chemical plant (Downs & Vogel, 1993): five units
(reactor, condenser, separator, compressor, stripper), 41 measurements and 11
controller outputs, sampled every 3 minutes. Controllers compensate for
disturbances, so several faults show mainly in what the controllers *do*. This
example uses 33 variables: the 22 continuous measurements and the 11 controller
outputs. The other 19, laboratory analysers, update only every 6–15 minutes.

The 20 faults (IDV 1–20): step changes (1–7), random variations (8–12), a slow
drift (13), sticking valves (14, 15) and five undisclosed mechanisms (16–20). The
literature agrees that **IDV 3, 9 and 15 are essentially undetectable**: under
control, their effect sits below the measurement noise. Every faulty run is
48 hours: 8 hours of normal operation, then the fault.

### The runs, and what each role's files are

Each simulation run is independent (its own noise and disturbance seeds), so the
**run** is the unit no two roles share.

| role | runs | files | rows (normal / anomaly) | labels | used in |
|---|---|---|---|---|---|
| library (training) | 40 fault-free 25 h runs | 40, one per run | 20,000 / 0 | all `normal`, by a constant | 4: every trial |
| validation | 10 fault-free 48 h runs (`val_normal`) + slice 01: 1 fault-free run and run 1 of each of the 20 faults | 2 | 13,760 / 16,000 | `label` column | 4: scores each trial; 7: sets the threshold |
| test | slices 02–04: 3 fault-free runs and runs 2–4 of each fault | 3 | 12,480 / 48,000 | `label` column | 5: scored once |
| delivery | 4 fault-free runs and 4 runs of each fault, drawn with a seed | 4 | 16,640 / 64,000 | none (held back in `_labels.csv` sidecars) | 6: run; 7: scored against the held-back labels |

- **`label`** is `anomaly` from a faulty run's onset (hour 8) and `normal`
  everywhere else, so a faulty run's first 8 hours count as normal operation.
- **Slices and delivery chunks** each join 21 runs into one file, with a one-day
  gap in the timestamps between runs. The platform marks any window across a gap
  invalid instead of mixing two runs.
- **The library is one file per run, 40 runs.**
  - *One file per run* because runs are separate simulations: joined into one
    file, the windows across each boundary would be lost (about 200 in all at
    window 48, step 8). It also keeps each run identifiable, which is how Stage 3
    proves no run is in two roles.
  - *40 runs* because one 500-row run is short (the preflight wants about 2,000
    rows), and 40 give 2,280 windows: well above what the detector's k ≤ 20
    neighbours and 20 PCA components need, and still a fit of about a minute.
    The full example measured fits slowing to 12–20 minutes above about 3,200
    windows. The dataset has 500 fault-free 25-hour runs; the other 460 are
    unused.

## Setup

```sh
git clone https://github.com/archetypeai/anomaly-discovery-agent-example-tep-quickstart.git   # needs Git LFS
cd anomaly-discovery-agent-example-tep-quickstart
python3 -m venv .venv
source .venv/bin/activate          # every later command assumes this
pip install -r requirements.txt    # numpy, pandas, pyreadr
cp .env.example .env               # then set ATAI_API_KEY (needed from Stage 4 on)
```

### Shortcuts: skip the download

Both Stage 1's output (`data/prepared/`, 66 MB) and Stage 2's (`data/roles/`,
70 MB, largely the same files) are in the repo, in Git LFS; a clone fetches
them (`git lfs pull` if it did not).

- **Skip Stages 0–2:** `data/roles/` holds everything Stages 3–7 read: the
  library, validation and test files, the delivery files and every label
  sidecar.

  ```sh
  python3 prep/preflight_roles.py    # Stage 3: 180,835 checks passed
  ```

- **Skip Stages 0–1** and build the role files yourself:

  ```sh
  python3 prep/run_preflight.py --window-size 48 --step-size 8   # 1c, to confirm
  python3 prep/build_roles.py                                    # Stage 2
  python3 prep/preflight_roles.py                                # Stage 3
  ```

Then go to [Stage 4](#stage-4-optimize).

## The stages

**To run again from scratch,** move `fit/out/` and `eval_out/` aside first: they
hold this repo's run (state files with its ids), and with them `test.py` and
`deliver.py` resume that run instead of starting a new one. Every script runs
from the repo root and is safe to rerun.

### Stage 0: download

```sh
python3 prep/download.py          # 1.4 GB from Harvard Dataverse, MD5-checked → data/raw/ (5.7 GB of CSV)
```

Four files, by their Dataverse file id, each checked against the MD5 the dataset
publishes, then converted from R's `.RData` to CSV. The release can only be
downloaded whole: the faulty 48-hour file alone is 837 MB.

### Stage 1: check, prepare, check again

```sh
python3 prep/run_preflight.py --raw                        # 1a: the raw files, read-only
python3 prep/prepare_tep.py                                # 1b: library, validation and test files (38 MB)
python3 prep/prepare_full_eval.py                          # 1b: the delivery files (28 MB)
python3 prep/run_preflight.py --window-size 48 --step-size 8   # 1c: the prepared files, read-only
```

- **1a** runs Archetype AI's preflight checks on one fault-free run, and a purity
  and staircase check on each file. **Expect:** `6 PASS, 3 WARN, 0 FAIL, 1 INFO`
  on the fault-free training file, and one `analyser_staircase` WARN on each of
  the other three. Each WARN prescribes a prep decision: z-score every channel,
  build the library from many short runs, drop the 19 analyser channels.
- **1b** cuts 66 MB out of the raw 5.7 GB into `data/prepared/`: 40 of the
  500 fault-free 25-hour runs, 18 of the 500 fault-free 48-hour runs and 8 runs of
  each fault, on 33 of the 52 variables (the faulty 25-hour file is not used). It
  z-scores every channel with the library runs' statistics only, gives each row a
  timestamp (180 s apart within a run, a day's gap between runs) and writes a
  label sidecar per file. **Expect:** `channels: 33   wrote data/prepared/{40 reference
  files, tep_val_normal, 4 eval slices, …}`, then `wrote 4 chunks (4 faulty + 0
  normal-only), 80,640 rows`.
- **1c** re-checks the prepared files. **Expect:** 40 checks `PASS` and one WARN
  (`nshot_support`: each 500-row run is short on its own, which is why the library
  is 40 of them). It predicts **940 invalid windows per slice** at window 48: the
  windows that cross a gap between runs.

### Stage 2: build the role files

```sh
python3 prep/build_roles.py           # → data/roles/
```

Assigns Stage 1's files to roles; nothing is re-cut. The library files are
linked as they are; validation and test get a `label` column from their
sidecars; the delivery files (the 4 chunks and `val_normal`, which Stage 7 needs
to set its threshold) keep no label column; every sidecar goes to
`data/roles/labels/`. **Expect:**

```
library: 40 files, 20,000 rows, all normal
validation: tep_eval_slice_01.csv 4,160 normal / 16,000 anomaly rows
validation: tep_val_normal.csv 9,600 normal / 0 anomaly rows
test: tep_eval_slice_02.csv 4,160 normal / 16,000 anomaly rows
test: tep_eval_slice_03.csv 4,160 normal / 16,000 anomaly rows
test: tep_eval_slice_04.csv 4,160 normal / 16,000 anomaly rows
delivery: 4 chunks + val_normal under data/roles/delivery, labels held back in data/roles/labels
```

### Stage 3: check the role files against the platform's rules

```sh
python3 prep/preflight_roles.py
```

It checks:
- every row's label against its sidecar, and only `normal` / `anomaly`;
- both classes in validation and in test (macro-F1 scores a missing class 0);
- no label column in the delivery files, the manifest's channels in each, and a
  sidecar for each;
- no run in two roles (a run is its source file and its id). `val_normal` is the
  one file in two: delivered only so Stage 7 can set its threshold, never scored
  as delivery.
- the manifest against the files on disk.

**Expect:** `218 simulation runs, each in one role`, then `180,835 checks passed`.

### Stage 4: Optimize

```sh
python3 fit/optimize.py
```

1. **Upload** the 40 library files and 2 validation files once. The ids are cached
   in `fit/out/uploads.json`.
2. **Optimize:** create an optimization on the `ad` blueprint. Every library row is
   a training example labelled `normal`; each validation file is scored on its
   `label` column, each window by its last row. The platform embeds every window
   with Omega 1.5, fits the detector on the library and reports macro-F1 on
   validation.
3. **Search space:** two settings, window 48, step 8, L2, PCA 16, threshold
   1.215, features `std,range,slope,median`, with **k = 5** and **k = 10**. That is
   the winner of the full example's 24-trial search, where k was 10. A space with
   fewer points than the budget runs every point. The step chosen here is the
   step every later stage uses: window 48 at step 8 means a score every 24
   minutes, from the eval to the app. Choosing among steps (and windows) is the
   full example's broader search.

**Expect:** `uploading 42 of 42 files (16 MB)`, `2 trial(s), searching
['n_neighbors']`, then the ranking. Ours:

```
otr_…  completed {"n_neighbors": 5}   macro_f1 0.8547  foreground_macro_f1 0.8723  detection_recall 0.7805  detection_precision 0.9886
otr_…  completed {"n_neighbors": 10}  macro_f1 0.8540  foreground_macro_f1 0.8703  detection_recall 0.7720  detection_precision 0.9974
```

k = 5 wins here by 0.0007, a tie in practice; k = 10's score is exactly what the
same setting scored in the full example's search. Try others with `--new` and
`--window`, `--step`, `--k`, `--metric`, `--pca`, `--threshold LOW:HIGH`,
`--features`, `--trials`. **Writes:** `fit/out/optimize_<optimization id>.json`.

### Stage 5: promote, then test once

```sh
python3 fit/test.py
```

1. **Promote** the best trial to a blueprint, `ad-tep-qs-<trial>`: its settings and
   fitted detector become a reusable model. `--trial otr_…` picks another trial.
2. **Evaluate** the 3 test slices **once** with the Evals API, with predictions.
3. **Check** every prediction's gold label against the sidecar, and the offline
   confusion matrix against the platform's, before reporting.

**Expect** (ours):

```
eval evl_…  blueprint ad-tep-qs-otr_…  (window 48, step 8, threshold 1.215; 300 abstained)
  platform: macro-F1 0.7331  anomaly F1 0.8733  recall 0.7800  precision 0.9919
  false alarms, fault-free run            18 /    345  0.0522
  false alarms, faulty runs, first 8 h    20 /    900  0.0222
  window detection per IDV (mean 0.780):
```

then one line per fault type: IDV 1, 4–7, 11, 12 and 14 at 99–100%, IDV 10 and 16
at 49% and 35%, IDV 3, 9 and 15 at about 1%. The 300 abstained windows are the
ones across a gap between runs.

- **Macro-F1 is lower than on validation (0.855) because of the class mix,** not
  the detector: the test is 21% normal rows, validation 46%. Anomaly F1 is about
  the same on both (0.873 and 0.872).
- **This is the one-shot test.** Once you have seen its number, the setting is
  frozen: tuning it further would make the test number optimistic.

**Writes:** `fit/out/test.json`, `fit/out/test-predictions.ndjson` and
`fit/out/test_state.json` (the ids, so a rerun resumes instead of testing again).

### Stage 6: deliver

```sh
python3 fit/deliver.py
```

1. **Package:** package Stage 5's blueprint as it is (`POST /api/agents/packages`).
   It runs at the optimized step 8, a score every 24 minutes, the same windows
   Stage 5's eval scored; the blueprint already writes scores into the output.
2. **Run** an instance of it (`POST /api/agents/instances`) over each of
   `data/roles/delivery/`'s files: the 4 delivery files and `val_normal`, all
   five at once, each uploaded without labels.
3. **Download** each output, checking it covers its input in full.

**Expect:** `package pkg_… (ready) on ad-tep-qs-otr_…`, five `agent agt_…` lines, five
`verified: output covers the full input (100.0%)`, then `5 outputs in
eval_out/delivery`. **Writes:** `eval_out/delivery/ad-output-*.csv` and
`fit/out/deliver_state.json`.

### Stage 7: score the delivery

```sh
python3 fit/score_delivery.py
```

- **Pairing:** each window is paired with the held-back label of its last row;
  windows the platform marked invalid (100 per file at step 8, the windows that
  span two runs) are left out.
- **Two thresholds:** the trial's own (1.215, what the agent's labels used) and
  one set to a **1% false-alarm rate on `val_normal`**'s scores, the convention
  TEP papers use.
- **Reported, per fault type:** detection rate (share of post-onset windows over
  the threshold), runs detected (3 consecutive windows over it, 48 minutes apart
  end to end at step 8, so one spike does not count), delay to the first of those
  windows, and AUROC; overall, the false-alarm rate on normal windows.

**Expect** (ours), at the 1%-false-alarm threshold:

```
ad-output-val_normal.csv: 1,150 windows, 45 invalid; FAR at threshold 1.215 = 1.48%; threshold for 1% FAR = 1.219
=== AD agent — calibrated threshold 1.219, sustain 3 ===
  idv_01 step  A/C feed ratio              99.8       4/4     0.00  1.000
  …
  false-alarm rate on normal windows: 2.11%  (35 / 1,660)
  mean detection rate: 78.5%  (excl. 3/9/15: 92.0%)   sims detected: 70/80   macro AUROC: 0.903
```

- **Every detectable fault type is caught in all 4 of its runs**, 17 of 17. IDV 3,
  9 and 15 are the misses (1–2% of windows, near-chance AUROC); a "detection" there
  is a false alarm that happens to fall after onset.
- **Step faults are caught at the first window after onset** (IDV 1, 4, 5, 6, 7
  and 14 at 0.00 h; delays are counted in 24-minute steps). The slow ones take
  hours (IDV 13's drift 2.2 h, IDV 10 7.6 h, IDV 16 9.2 h).
- **The delivery reads like the test:** 78.5% mean window detection, against
  78.0% on the test.
- **False alarms:** 2.11% on the delivery's normal windows (35 of 1,660), against
  the 1% the threshold was set to on `val_normal`. At step 8 there are 8 times
  fewer normal windows to set and check it on, so both numbers are coarser.
- **Against a step-1 delivery** (one score every 3 minutes, which `main` makes with
  a bundle override): the same label in every shared window and the same
  detection rate and AUROC within 0.5 points; slow faults' delays read up to a
  few hours longer, because each is timed in 24-minute steps.

**Writes:** `eval_out/delivery/evaluation.json`.

### Stage 8: serve it, one window per query

```sh
python3 fit/serve.py                          # delivery file 1's fault-free run and IDV 5
python3 fit/serve.py --faults idv_01 idv_19   # other runs of the file; --file full_chunk_002 for another file
python3 fit/serve.py --windows-per-query 16   # up to 16 consecutive windows per query
```

Stage 6 delivers in batch: upload a file, run an agent over it, download the output
when the run is done. **Agent serving** keeps an agent loaded and answers a window
of samples in one round trip, with no upload, queue or polling: what a plant
historian would call every 24 minutes (8 samples) with the latest 48 samples. It is on Dev and
Staging only, for first internal tests; Dev has 3 serving workers for everyone. The
[agent-serving example](https://github.com/archetypeai/agent-serving-example) has the
calls and their limits.

1. **A package of Stage 5's blueprint, as it is** (`POST /api/agents/packages`):
   the same detector, encoder and values. Packages are Agent Lifecycle 2.0's
   replacement for bundles, and need no admin role. A package carries no values:
   the agent is exactly what Stage 5 promoted. In serving mode the platform supplies the serving
   connectors itself, an `atai-records` endpoint that answers one named record per
   window, so no copy of the blueprint is made.
2. **An instance of the package in serving mode** (`POST /api/agents/instances`
   with `package_id` and `mode: "serving"`): an agent that answers over
   `POST /agents/instances/{id}/query`.
3. **Each run replayed at the optimized step,** a query every 8 samples, so the
   served windows are exactly Stage 6's. Every query carries the latest 48
   samples of the 33 tags, one list per tag, and gets one record back:
   `{"anomaly_score": …, "predicted_label": "normal", "invalid": "false",
   "start_timestamp": 0, "finish_timestamp": 47}`. A served agent keeps nothing
   between queries, so a query holds the whole window, and the timestamps are
   sample positions within it.
4. **Every answer against Stage 6:** the label, the score (to within 10⁻⁴
   relative), and each run's first sustained alarm (3 consecutive anomaly
   windows).
5. **Cleanup:** the agent is cancelled and deleted, and the package deleted, however
   the replay ends (Ctrl-C, SIGTERM and SIGHUP included; a second Ctrl-C waits for it).

**Expect** (ours, Dev, 2026-10-26), delivery file 1's fault-free run (sim 96) and
its IDV 5 run (sim 26), 115 windows each:

```
Stage 8: 230 windows of 2 run(s) served in 230 queries, 192 s
  against Stage 6 (batch): predicted_label identical in 230/230, anomaly_score within 1e-4 in 230/230 (max relative difference 1.6e-05); invalid 0
  latency per query: median 797 ms, p95 888 ms, max 943 ms
  idv_00 sim 96: first sustained alarm, served none; batch none
  idv_05 sim 26: first sustained alarm, served 1.20 h after onset; batch 1.20 h after onset
```

- **The served agent gives the delivery's answers:** every label and score, and
  both runs' first alarms. Each answer comes back in about 0.8 s, for a window
  due every 24 minutes.
- **The alarm time is when the third window over the threshold ends:** 1.20 h
  after onset here. Stage 7 times the first of the three, so it reports IDV 5 at
  0.00 h; the two are 48 minutes apart at step 8.
- **A score can differ by a step, now and then.** Serving and batch embeddings
  differ by about 2×10⁻⁴, and with k = 5 that is sometimes enough to change which
  reference window is the 5th nearest. An earlier step-1 run (2026-10-15) had one
  such window in 1,826; this run had none. The labels and the alarm times are what
  should match.
- **One window per query is the way to serve it.** `--windows-per-query 16` sends
  16 consecutive windows (168 samples) and gets 16 answers, but each query took
  about 11 s, and in a live plant it would mean waiting 6 hours of samples before
  asking.

**Writes:** `eval_out/serving/serve_<file>_<runs>_wpq<N>.{csv,json}` (a row per
window; a summary).

### Stage 9 (optional): watch it live, served from the platform

```sh
python3 fit/library_embeddings.py     # once: the reference library's embeddings (~8 min)
cd app-serving && npm install
npm run dev                           # broker + serving bridge + replayer + web
open http://localhost:5180
```

[`app-serving/`](app-serving/README.md) replays Stage 6's delivery runs, one at a
time, as if the plant were running now, and sends every window to a **serving
agent** of Stage 5's blueprint: an agent that stays loaded on the platform and
answers a window in one round trip, under a second, every 8 samples, the step
Stage 4 chose. A flowsheet, the 33 tags, the
anomaly score and an embedding space show the answers as they come. Agent serving
is on Dev and Staging only, for first tests (Dev has 3 workers for everyone); the app holds one
while it runs and gives it back on `npm run stop`.

- **A small Node bridge** keeps the latest 48 samples, sends each window as one
  query, and publishes the answer to the browser. It holds the API key, which never
  reaches the browser.
- **The embedding space** needs the windows the detector was fitted on, but the
  promoted detector can't be downloaded and the APIs return no embeddings. So
  `fit/library_embeddings.py` recomputes them: the 40 library runs through the
  promoted blueprint in batch with embeddings on, 2,280 windows, then PCA 1–2.
- **Pace:** a window every 8 samples, the optimized step that every stage uses,
  so the app's alarms are Stage 6's, window for window; a run takes about 2
  minutes.

**Checked on Dev, 2026-10-15** (on `main`, bundles, every 4th sample): all 229
windows of delivery file 1's IDV 5 run had Stage 6's label, with scores within
1.5×10⁻⁵ of batch, 33 embeddings per window and 866 ms per window. The reference library came out at 2,280 windows scored 0.949–1.108, all under the
1.215 threshold, as the detector's own normal data should be. Stopping the app
(`npm run stop`, or Ctrl-C) cancels and deletes the bridge's agent and package.
The bridge runs a package, which can't turn on `output_embeddings`, so the page's
live embedding trail stays empty; `fit/library_embeddings.py` still uses a bundle
for the reference cloud (Dev, 2026-10-26).

### Clean up the platform

```sh
python3 fit/cleanup.py           # list what would be deleted, and what stays
python3 fit/cleanup.py --yes     # delete it
```

[`fit/cleanup.py`](fit/cleanup.py) deletes the agents, packages and bundles this quickstart
left on Dev, from the ids the stages recorded in `fit/out/`: Stage 6's delivery
agents and package; Stage 8's serving agent and package if `fit/serve.py` was killed
before its own cleanup; and Stage 9's serving bridge leftovers and the 40 batch
agents of `fit/library_embeddings.py`. The promoted blueprint stays, and so do
the optimization and the eval; a `-served-records` copy left by an earlier
version goes. Don't run it while `fit/serve.py` or `app-serving/` is running. To
check that no serving agent of yours is still holding a worker:

```sh
set -a; source .env; set +a
curl -s "$ATAI_API_ENDPOINT/agents/instances?status=running&limit=100" -H "Authorization: Bearer $ATAI_API_KEY" \
  | jq -c '.data[] | select(.mode=="serving") | {id, blueprint, name, created_at}'
```

## Results, and they reproduce

We ran the quickstart twice from scratch on Dev, the second time in a separate
copy with nothing from the first: new prepared files, role files, uploads,
optimization, promoted blueprint, eval and delivery. Every number came out the
same:

| stage | measure | first run | second run |
|---|---|---|---|
| 1–3 | delivery rows; runs in a role; role checks | 80,640; 218; all passed | same, and every prepared file byte-identical |
| 4 | validation macro-F1, k 5 / k 10 | 0.8547 / 0.8540 | same, from its own optimization |
| 5 | test macro-F1; mean window detection | 0.7331; 78.0% | same, from its own blueprint, with all 7,545 predictions identical |
| 6 | delivery outputs | 5 files, full coverage | byte-identical |
| 7 | detection / false alarms / AUROC at the 1% threshold | 78.0% / 1.41% / 0.901 | same |

Those two runs were on `main` (bundles, step-1 delivery). On this branch, two
package deliveries at step 8 on Dev (2026-10-26, each from its own optimization
and blueprint) gave the same Stage 4, 5 and 8 numbers and the same Stage 7
headline at the 1% threshold (78.5% / 2.11% / 0.903), but not byte-identical
outputs: a few scores moved in the last digits, enough to flip IDV 9's one
borderline "detection" (a false alarm after onset) at the trial's threshold.

So the prep, the platform and the scoring are deterministic here, up to those
near-tie score differences. If your run
gives different numbers, something differs in your data or setup, and the
expected outputs above show at which stage.

## What's left out, compared with the full example

| full example | here | why |
|---|---|---|
| delivery over every remaining run: 10,406 runs in 496 files | 84 runs in 4 files | time: hours of agent runs instead of minutes |
| a 24-trial search | 2 trials at its winner | each search costs platform time; the winner is already known |
| the PCA T²/SPE bar every TEP paper compares against | none | the quickstart shows the lifecycle, not a benchmark |
| the first design, through `ad-fitting`, and a live on-device app | none; the live app here is `app-serving/`, served from the platform | |

## Repo layout

| path | what it is |
|---|---|
| `prep/download.py` | Stage 0: the Dataverse download, MD5-checked, and RData → CSV |
| `prep/run_preflight.py`, `prep/preflight_tep.py`, `prep/preflight_static.py` | Stages 1a and 1c |
| `prep/prepare_tep.py`, `prep/prepare_full_eval.py` | Stage 1b: library, validation and test files; the delivery files |
| `prep/build_roles.py`, `prep/preflight_roles.py` | Stages 2 and 3 |
| `ad_api.py`, `fit/atai.py` | stdlib platform helpers: requests, uploads, polling, resume state |
| `fit/optimize.py` | Stage 4 |
| `fit/test.py` | Stage 5 |
| `fit/deliver.py` | Stage 6 |
| `fit/score_delivery.py`, `fit/evaluate_detection.py`, `fit/tep_common.py` | Stage 7 |
| `fit/serve.py` | Stage 8: the promoted blueprint served over `/query` (Dev), delivery runs replayed one window per query, every answer checked against Stage 6 |
| `fit/library_embeddings.py`, `app-serving/` | Stage 9: the reference library's embeddings; the live app, served from the platform ([README](app-serving/README.md)) |
| `fit/cleanup.py` | delete the agents, packages and bundles Stages 6, 8 and 9 left on the platform (`--yes`) |
| `eval_out/serving/` | Stage 8's replay: a row per window, served against batch, and a summary |
| `data/prepared/` | Stage 1's output: library, validation, test and delivery files with their label sidecars (Git LFS) |
| `data/roles/` | Stage 2's output: the role files and label sidecars Stages 3–7 read (Git LFS) |
| `fit/out/`, `eval_out/delivery/` | this repo's run: state, results and the delivered outputs |

## Licence

The code is under the [Apache License 2.0](LICENSE). The data is the Rieth et al.
release, dedicated to the public domain: see [Data attribution](#data-attribution).

## Data attribution

All process data used here comes from **Additional Tennessee Eastman Process
Simulation Data for Anomaly Detection Evaluation**:

- **Authors:** Cory A. Rieth, Ben D. Amsel, Randy Tran, Maia B. Cook.
- **Dataset:** Harvard Dataverse, 2017,
  [doi:10.7910/DVN/6C3JR1](https://doi.org/10.7910/DVN/6C3JR1).
- **Original process:** Downs, J. J., & Vogel, E. F. (1993). *A plant-wide
  industrial process control problem.* Computers & Chemical Engineering, 17(3),
  245–255.
- **Terms:** a public-domain dedication; the dataset's user agreement allows
  copying, modifying and distributing the work without permission.
- **No endorsement:** neither the authors nor Pacific Science & Engineering
  Group, Inc. are involved in this example or endorse it.

**What was changed** (the files in `data/prepared/` and `data/roles/`): a subset of runs was selected; 33 of the 52 variables were
kept; every channel was z-scored with the library runs' statistics; timestamps
were added (180 s per sample, a day's gap between runs); runs were joined into
the files described above, with labels derived from the documented fault onset.
