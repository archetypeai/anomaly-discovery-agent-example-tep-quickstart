# Anomaly Discovery on the Tennessee Eastman Process: quickstart

Build an **Anomaly Detection Agent** on Newton, Archetype AI's platform, that watches a
simulated chemical plant and raises an alarm when it stops running normally. It learns
from **normal operation only**: no fault is labelled, collected or shown to it before it
is deployed.

Each 2.4-hour window of the plant's 33 sensors is embedded with Omega 1.5, Archetype's
pretrained sensor model, fused with per-sensor statistics, and scored by a Local Outlier
Factor (LOF) model: the further a window is from the normal windows it learned, the
higher its anomaly score.

| stage | what happens | script | time (free trial) |
|---|---|---|---|
| setup | Git LFS data, Python environment, API key | `./setup.sh` | 1-3 min |
| 4 | **build:** fit on the normal runs, score 2 settings on validation (Optimizations API) | `fit/optimize.py` | ~1 min |
| 5 | **promote** the best setting to a blueprint, **test** it once (Evals API) | `fit/test.py` | about 1 min |
| 6 | **deliver:** run it as a batch agent over the delivery file | `fit/deliver.py` | about 1 min |
| 7 | **score** the delivery against the held-back labels | `fit/score_delivery.py` | seconds |

Stages 1-3 (downloading the dataset and building the role files) are already done: their
output is in `data/roles/`.

## Walk through it with Claude Code

The repo carries a Claude Code skill, [`tep-walkthrough`](.claude/skills/tep-walkthrough/SKILL.md),
that sets the repo up and walks a newcomer through it: an overview, the data, building
the Anomaly Detection Agent (Stage 4), then running it on two test runs it has never
seen, with charts. About 5 minutes in all. In the repo, ask Claude Code:

```text
/tep-walkthrough
```

From anywhere else, in Claude Code or another coding agent (it clones the repo first):

```text
Clone https://github.com/archetypeai/anomaly-discovery-agent-example-tep-quickstart.git into a new folder and follow .claude/skills/tep-walkthrough/SKILL.md.
```

Other agents find it through [`AGENTS.md`](AGENTS.md). The key is never typed into the
chat: set `ATAI_API_KEY` in your shell first, or run `./setup.sh` in a terminal when the
walkthrough asks.

## The data

The Tennessee Eastman Process (Downs & Vogel, 1993), Rieth et al. (2017) release
([public domain](#data-attribution)): a closed-loop simulation of a chemical plant, run
many times, with 20 kinds of fault. This repo uses a small sample of it, so every stage
runs in minutes: 33 sensors (22 measurements, 11 controller outputs), one reading every
3 minutes, 17 runs.

| role | file | runs | rows (normal / anomaly) | used in |
|---|---|---|---|---|
| training (library) | `tep_library.csv` | 5 normal runs, 24.8 h each | 2,480 / 0 | 4: every setting is fitted on it |
| validation | `tep_validation.csv` | 2 normal runs, IDV 1, IDV 10; 24 h each | 1,280 / 640 | 4: picks the setting |
| test | `tep_test.csv` | 2 normal runs, IDV 1, IDV 10; 24 h each | 1,280 / 640 | 5: scored once |
| delivery | `tep_delivery.csv` | 2 normal runs, IDV 1, IDV 10; 24 h each | 1,280 / 640 | 6: run without labels; 7: scored |

- **Faulty runs** are normal for 8 hours, then the fault starts. **IDV 1** (a step in
  the feed mix) leaves the normal range within an hour and stays out: easy. **IDV 10**
  (random feed-temperature variation) swings in and out of it: hard.
- **Labels:** validation and test carry a `label` column (`anomaly` from hour 8 of a
  faulty run, `normal` elsewhere). The delivery has none: its labels are held back in
  `data/roles/labels/` until Stage 7.
- **Each file joins its runs** with a one-day gap in the timestamps. Newton marks any
  window across a gap invalid, so no window mixes two runs. No run is in two files.
- **Values are z-scored** with the training runs' statistics, so 0 is a sensor's usual
  level.

## Setup

```sh
git clone https://github.com/archetypeai/anomaly-discovery-agent-example-tep-quickstart.git   # needs Git LFS
cd anomaly-discovery-agent-example-tep-quickstart
./setup.sh
```

`setup.sh` fetches the data (Git LFS), creates `.venv`, installs `requirements.txt`
(numpy, pandas) and writes `.env` with `ATAI_API_KEY`, from your environment or a hidden
prompt. It finds `ATAI_API_ENDPOINT` by asking production and the free trial which one
accepts the key, so the same command works for both. Safe to rerun.

Then run every script from the repo root with the environment active
(`source .venv/bin/activate`). Each script saves its ids in `fit/out/` and resumes from
them; to start again from scratch, move `fit/out/` and `eval_out/` aside.

**On the free trial** (`try.archetypeai.app`) jobs run on CPU, 3 at a time, and stop
after 2 hours. The scripts detect it from the endpoint and say when they change a
default for it.

## Stage 4: build (Optimize)

```sh
python3 fit/optimize.py
```

1. **Upload** the training and validation files (cached in `fit/out/uploads.json`).
2. **Optimize** on the `ad` blueprint: every training row is a `normal` example; the
   validation file is scored on its `label` column, each window by its last row. Newton
   embeds every window with Omega, fits the Anomaly Detection Agent on the training runs
   and scores each setting on validation.
3. **Search space:** window 48 (2.4 h), step 8 (a verdict every 24 min), L2, PCA 16,
   threshold 1.215, features `std,range,slope,median`, with **k = 5** and **k = 10**
   neighbours.

**Expect** (free trial, 2026-11-07, 52 s):

```
otr_…  completed {"n_neighbors": 10}  macro_f1 0.8839  foreground_macro_f1 0.8732  detection_recall 0.7750  detection_precision 1.0000
otr_…  completed {"n_neighbors": 5}   macro_f1 0.8532  foreground_macro_f1 0.8310  detection_recall 0.7375  detection_precision 0.9516
```

k = 10 wins. Most missed fault windows are IDV 10's. Try other settings with `--new` and
`--window`, `--step`, `--k`, `--metric`, `--pca`, `--threshold LOW:HIGH`, `--features`,
`--trials`. **Writes:** `fit/out/optimize_<id>.json`, `fit/out/optimize_state.json`.

## Stage 5: promote, then test once

```sh
python3 fit/test.py
```

1. **Promote** the best trial to a blueprint, `ad-<trial>`: its settings and fitted
   Anomaly Detection Agent become a reusable model. `--trial otr_…` picks another trial.
2. **Evaluate** the test file **once** with the Evals API, with predictions.
3. **Check** every prediction's label against the sidecar, and the confusion matrix
   against Newton's, before reporting.

**Expect** (free trial, 2026-11-07, about 1 min):

```
eval evl_…  blueprint ad-otr_…  (window 48, step 8, threshold 1.215; 15 abstained)
  platform: macro-F1 0.7512  anomaly F1 0.6667  recall 0.5000  precision 1.0000
  false alarms, fault-free run             0 /    110  0.0000
  false alarms, faulty runs, first 8 h     0 /     30  0.0000
  window detection per IDV (mean 0.500):
    idv_01     40 /    40  1.000
    idv_10      0 /    40  0.000
```

- **IDV 1 is caught in every window after the fault, IDV 10 in none.** This test run of
  IDV 10 stays inside the normal range at this threshold: the hard fault, as on
  validation. No normal window raised a false alarm.
- **The 15 abstained windows** are the ones across a gap between runs.

This is the one-shot test: once you have seen its number, the setting is frozen, since
tuning it further would make the test number optimistic. **Writes:** `fit/out/test.json`,
`fit/out/test-predictions.ndjson`, `fit/out/test_state.json`.

## Stage 6: deliver

```sh
python3 fit/deliver.py
```

1. **Bundle** Stage 5's blueprint with scores in the output. On production it adds
   `step_size: 1`, a score for every 3-minute sample; on the free trial it keeps the
   trial's step (8), a score every 24 minutes (`--step 1` to override).
2. **Run** it over `tep_delivery.csv`, uploaded without labels.
3. **Download** the output, checking it covers the whole input.

**Expect** (free trial, 2026-11-07, about 1 min): `bundle bnd_…`, `agent agt_…`,
`verified: output covers the full input (100.0%)`, then `1 outputs in eval_out/delivery`.
**Writes:** `eval_out/delivery/ad-output-delivery.csv`, `fit/out/deliver_state.json`.

## Stage 7: score the delivery

```sh
python3 fit/score_delivery.py
```

Pairs each window with the held-back label of its last row (invalid windows, those
across a gap, are left out) and reports, per fault type, the detection rate (share of
windows after the fault over the threshold), runs detected (3 windows in a row over it,
so one spike doesn't count), the delay to that detection and AUROC; and the false-alarm
rate on normal windows.

**Expect** (free trial, 2026-11-07):

```
ad-output-delivery.csv: 220 windows, 15 invalid  score median 1.073  p99 7.631  max 7.985

=== AD agent — artifact threshold 1.215, sustain 3 ===
  IDV    type                              det%      sims  delay h  AUROC
  idv_01 step  A/C feed ratio             100.0       1/1     0.00  1.000
  idv_10 rand  C feed temp                 62.5       1/1     6.40  0.851

  false-alarm rate on normal windows: 0.71%  (1 / 140)
  mean detection rate: 81.2%   sims detected: 2/2   macro AUROC: 0.925
```

- **Both faults are caught** in the delivery: IDV 1 at once, IDV 10 after 6.4 hours, with
  62.5% of its windows over the threshold. IDV 10's runs differ: the test run's stayed
  below it.
- **One false alarm** in 140 normal windows (0.71%).
- **At step 8 a window ends every 24 minutes,** so the delay is in steps of 0.4 h.

**Writes:** `eval_out/delivery/evaluation.json`.

## Clean up

```sh
python3 fit/cleanup.py           # list what would be deleted, and what stays
python3 fit/cleanup.py --yes     # delete it
```

Deletes the agents and bundles left on Newton by Stage 6 and by the walkthrough's
Step 3. The promoted blueprint, the optimization and the eval stay.

## Repo layout

| path | what it is |
|---|---|
| `setup.sh`, `requirements.txt`, `.env.example` | setup |
| `data/roles/` | the role files, their label sidecars and `manifest.json` (Git LFS) |
| `ad_api.py`, `fit/atai.py` | stdlib platform helpers: requests, uploads, polling, resume state |
| `fit/optimize.py` | Stage 4 |
| `fit/test.py` | Stage 5 |
| `fit/deliver.py` | Stage 6 |
| `fit/score_delivery.py`, `fit/evaluate_detection.py`, `fit/tep_common.py` | Stage 7 |
| `fit/cleanup.py` | delete the agents and bundles left on Newton |
| `.claude/skills/tep-walkthrough/` | the Claude Code walkthrough; it writes to `walkthrough_out/` |
| `AGENTS.md` | notes for other coding agents |

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

**What was changed** (the files in `data/roles/`): 17 runs were selected and cut to
their first 24 hours (training runs: 496 rows); 33 of the 52 variables were kept; every
channel was z-scored with the training runs' statistics; timestamps were added (180 s
per sample, a day's gap between runs); runs were joined into one file per role, with
labels derived from the documented fault onset.
