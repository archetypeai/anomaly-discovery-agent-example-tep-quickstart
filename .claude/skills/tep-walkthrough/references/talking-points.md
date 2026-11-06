# Talking points

Plain-language material for each step. Use what helps the user; don't read it out.

## Timings (measured 2026-11)

`setup.sh` reports which deployment the key belongs to; quote the matching column.

| Step | Where it runs | Free trial | Production |
|---|---|---|---|
| 0 · Setup | Claude Code (clone, LFS ~140 MB, venv) | 1-3 min | 1-3 min |
| 1 · Data | Claude Code, locally | under a minute | under a minute |
| 2 · Build | Newton: Optimizations API | ~6-8 min fresh; seconds if the saved run is reachable | about 6 min fresh (README); seconds if reachable |
| 3 · Promote + bundle | Newton | seconds | seconds |
| 3 · 12 agent runs | Newton: batch agents | 3 at a time, ~1-2.5 min each: ~5-12 min | 4 at a time: usually faster |
| 3 · Charts | Claude Code: PCA and drawing | under a minute | under a minute |

Platform times vary with load. The free trial runs on CPU, allows 3 jobs per org at
once and stops any job after 2 hours. On production, the repo's saved optimization is
only reachable for keys in the repo authors' org; everyone else gets a fresh one.

## Newton vs Claude Code

| Newton (Archetype's platform, over its APIs) | Claude Code (this machine) |
|---|---|
| Stores the uploaded files | Reads the repo's CSVs and manifest |
| Embeds every window with Omega 1.5, Archetype's pretrained sensor model (768 numbers per sensor per window) | Cuts the two test runs out of slice 02 and removes their labels |
| Fits the detector (per-sensor features + embeddings, PCA, Local Outlier Factor) on normal runs only, and scores each setting on validation | Recomputes the per-sensor features for the map |
| Promotes the winning trial to a reusable blueprint; creates bundles; runs batch agents and returns per-window scores, labels and embeddings | Fits the 2-D PCA and draws every chart |

The key point: the model, the fitted detector and the scoring live on Newton and are
reused by anything that calls it (batch runs, the Evals API, serving one window per
query). Claude Code orchestrates and explains; it doesn't do the modelling.

## Step 1: the data

The Tennessee Eastman Process is a simulated chemical plant (Downs & Vogel, 1993):
33 sensors and valve settings every 3 minutes. Every faulty run is 48 h: 8 h normal,
then one of 20 faults. Values are z-scored with the library's statistics, so 0 is a
sensor's usual level and 1 is one typical wiggle (a standard deviation).

| Role | What's in it | Answers? | Used for |
|---|---|---|---|
| Library (training) | 40 normal 25 h runs (20,000 readings) | all normal | the agent learns "normal" |
| Validation | 10 normal 48 h runs + one run of each fault | yes | choosing the setting (Step 2) |
| Test | 3 files like validation; we use slice 02 | yes, removed for Step 3 | checking on unseen runs |
| Delivery | 84 more runs | held back | later stages (skipped here) |

A run is never in two roles. The agent never sees a fault while learning: it learns
what normal looks like and flags what doesn't fit.

Reading the chart: the three blue rows are a flat band around 0, the spread of normal.
IDV 1 (a step in the feed mix) leaves it within an hour and never comes back: easy.
IDV 10 (random feed-temperature variation) swings in and out of the band: any single
reading can look normal, which is why the agent judges 2.4 h windows across all 33
sensors. Three faults (IDV 3, 9, 15) are known to be nearly invisible in this plant.

## Step 2: the winning setting

| Setting | Meaning |
|---|---|
| window 48 | looks at the last 2.4 h (48 x 3 min) |
| step 8 | a new verdict every 24 min |
| features std, range, slope, median | how much each sensor wiggles, spreads, trends, and its level |
| PCA 16 | the fingerprint is compressed to 16 numbers |
| n_neighbors (k) | compares each window with its k most similar normal windows |
| threshold | the unusualness score above which a window counts as an anomaly |

- Macro-F1: one score out of 1 averaging how well it does on normal and on fault windows.
- Recall: share of fault windows it caught. Expect ~0.78: the misses are mostly the
  invisible faults and slow ones that take hours to show.
- Precision: share of its alarms that were real. Expect ~0.99.
- k = 5 vs 10 is close to a tie; the higher macro-F1 wins.

## Step 3: the charts

- Score: about 1 is typical. A sustained alarm is 3 windows in a row over the threshold
  (one spike doesn't count). Expect the faulty run's first alarm about 1-1.5 h after the
  fault. A normal run can cross the line now and then: that's a false alarm, and the
  threshold is a trade-off between catching faults and raising them (the repo's later
  scoring stage sets it to a 1% false-alarm rate).
- Map: each dot is a 2.4 h window. Grey (library) and blue (normal run) share one cloud:
  that's normal. The faulty run's open circles sit in it before the fault; afterwards it
  swings far out (the plant reacting) and settles into its own cluster (a new steady
  state that isn't normal). The two axes keep only ~8% of the variation each, because the
  fingerprints have about 25,000 numbers; the map shows the pattern, not exact distances.
  The detector itself uses 16 dimensions.
