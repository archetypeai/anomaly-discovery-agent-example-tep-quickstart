# Bundles vs packages: what changed, and is it better?

Agent Lifecycle 2.0 replaces bundles with packages. This branch
(`explore/packages`) is a **preview**: it moves the TEP Anomaly Discovery
quickstart to packages and runs Stages 4–8 end to end (2026-10-26, on a
pre-release deployment). **Packages are new and still changing**: re-check the
calls below before relying on them.

## Summary

- **Everything that ran on bundles runs on packages.** The one output switch a
  package can't set, `output_embeddings` (only the app's embedding view needs it),
  takes a stop-gap: a second, 1-trial optimization of the winning configuration
  with embeddings on, promoted as the app's own blueprint.
- **A package runs the promoted blueprint exactly as promoted.** There are no
  per-run overrides. That forced one real decision: use the optimized
  configuration, `step_size` included, in every stage.
- **Results are the same.** Detection quality is unchanged. Timing is coarser,
  and that comes from the step the optimization chose, not from packages.
- **Packages are better, with two gaps to close:**
  - Values are silently dropped.
  - Query-based serving doesn't enforce the step.

## 1. The objects and calls

| | Bundles (`main`) | Packages (this branch) |
|---|---|---|
| What it is | a blueprint **plus values that override it** | the promoted blueprint **as it is**, plus the models it resolved to |
| Create | `POST /agents/bundles` `{blueprint: <key>, name, values}` | `POST /agents/packages` `{blueprint_ids: [<id>], target: {kind: "platform"}, name}`, then poll until `ready` (immediate in our runs) |
| Run | `POST /agents/bundles/{id}/run` `{mode, connectors}` | `POST /agents/instances` `{package_id, mode, connectors}` |
| Query, cancel, delete an agent | — | unchanged |
| An agent's siblings | `GET /agents/instances?bundle_id=` | `GET /agents/instances?package_id=` |
| Delete | `DELETE /agents/bundles/{id}`, 409 while it has agents | `DELETE /agents/packages/{id}`, 409 while it has agents |

Stages 4 and 5 (Optimizations, promote, Evals) touch neither, and didn't change.

**What a user can set after promote** (2026-10-26):

| | Settable | Not settable |
|---|---|---|
| Package | `blueprint_ids` (exactly one: two returned 400 "may name at most 1"); `target.kind` = `platform` (`edge` returned 501 "not supported yet"); `name`, `description` | `values` and unknown fields: silently dropped |
| Instance | `package_id`; `mode` (`serving`, or omitted for batch); `connectors` (batch input files; none in serving) | `name` (the instance takes the package's name); `values`: silently dropped |

Everything that affects behaviour (window, step, threshold, k, features, PCA,
outputs) is fixed in the blueprint at promote time. The package adds the pinned
model versions; the instance adds only the data source and the mode.

## 2. What changed in the example

There are three separate effects. They are easy to confuse:

| Effect | Caused by | What it changed |
|---|---|---|
| **A. The API** | packages | Create a package, then start an instance. Cleanup deletes packages. A blueprint is named by id. |
| **B. One configuration throughout** | packages can't override values | Every stage runs the optimized configuration. On `main`, Stages 4–5 ran at step 8 and Stage 6 at step 1 through a bundle override. Now every stage runs at step 8. |
| **C. Step 8 instead of step 1 downstream** | the optimization's choice (via B) | 8 times fewer windows to score: a score every 24 minutes instead of every 3. Faster runs and coarser timing. |

**Packages make nothing faster by themselves.** The time savings are all effect C:

| Stage | `main` | this branch |
|---|---|---|
| 4 optimize, 5 promote + eval | step 8 | step 8 (unchanged) |
| 6 deliver | step 1, bundle override, ~15 min | step 8, package, 3–9 min |
| 8 serve | a query per sample, bundle, ~25 min | a query per 8 samples, package, ~3 min |
| 9 app | step 4 or 1, bundle, embeddings on | step 8, package of the app's blueprint, embeddings on |
| 9 library embeddings | step 8, bundle | step 8, package of the app's blueprint |

Stages 4–8 keep `output_embeddings: false`: on, every delivery file would grow from
about 100 KB to hundreds of MB. `fit/app_blueprint.py` runs a 1-trial optimization
that pins every winning value plus `output_embeddings: true` and promotes it; its
trial scored the same validation macro-F1 as Stage 5's winner (0.8547, recall
0.7805, precision 0.9886). Copying the blueprint instead would lose the link to the
trial.

## 3. Results (2026-10-26)

Stages 4–8 were run from a fresh optimization, all through packages, in 16½ minutes:

| | `main` (step-1 delivery) | this branch (step 8) |
|---|---|---|
| Stage 4 validation macro-F1, k 5 / k 10 | 0.8547 / 0.8540 | same |
| Stage 5 test macro-F1, mean window detection | 0.7331, 78.0% | same (the same blueprint step) |
| Stage 7 mean detection rate (1% threshold) | 78.0% | 78.5% |
| Stage 7 macro AUROC | 0.901 | 0.903 |
| Stage 7 runs detected | 71/80 | 70/80 |
| Stage 7 delay, IDV 16 (counted in steps) | 4.6 h | 9.2 h |
| Stage 8 served vs batch | 1,826/1,826 labels | 230/230 labels, scores within 1.7×10⁻⁵ |

The step-8 delivery has the same label as every 8th window of the step-1
delivery, with scores within 0.5%. Two step-8 package deliveries agreed on
every headline number, but not to the byte (near-tie score differences).

## 4. step_size: what a package fixes, and what it doesn't

`step_size` is how far the 48-sample window moves between scores. TEP samples
every 3 minutes, so step 8 means a score every 24 minutes over the last 2.4 hours.
It plays two roles:

- **At fit time** it sets the density of the reference library, so it changes the
  model. It's fixed inside the fitted detector once Stage 4 runs.
- **At run time** it only decides which windows get scored.

A package fixes the run-time step at the optimized value. Whether that holds
depends on who keeps the buffer of recent rows:

| How the agent gets rows | Who applies the step | Is step 8 enforced? |
|---|---|---|
| Batch: a CSV per run | the agent | yes |
| Edge runtime: rows from MQTT, one message per row | the agent (its window node) | yes |
| Platform serving: `/query`, one window per request | **the client** | **no**: the agent keeps nothing between queries, and a 48-row query gets one answer at any step. The step only slices multi-window queries. |

So in query-based serving, the client decides the cadence. Each answer is
correct at any cadence, but **the alarm behaviour was only evaluated at the
optimized one**. Measured over 630 hours of normal operation in the delivery:

| Client sends | Alarm rule | False alarms per day | Runs caught | Confirmed alarm, IDV 16 |
|---|---|---:|---:|---:|
| every 8th sample (as optimized) | 3 windows in a row (48 min) | 0 | 71/80 | 10.0 h |
| every sample | 3 windows in a row (6 min) | 1.22 | 72/80 | 4.7 h |
| every sample | 17 windows in a row (48 min) | 0 | 69/80 | 10.3 h |

Sending on every sample is natural for a live client. But it trades faster alarms
for more false alarms, and that trade wasn't part of the evaluation. The
quickstart sends a window every 8 samples, the cadence its numbers describe.

## 5. Is the packages approach better?

**Yes, mainly because what you evaluate is what you deploy.**

1. **The eval measures the delivered agent.** On `main`, Stage 5 evaluated step 8
   and Stage 6 delivered step 1: the numbers a user was shown described a
   different configuration from the one they ran. With packages, Optimize →
   promote → eval → deliver is one configuration end to end. That's the point
   of the optimization: find a configuration, then keep it.
2. **Reproducible deployments.** A package pins the encoder and detection-head
   versions it resolved to. A later model release can't silently change an
   agent that is already deployed.
3. **One object for batch and serving.** The same package runs over files or
   answers queries. Only `mode` differs.
4. **No blueprint copies.** Nothing in the example copies a blueprint any more.
5. **A simpler model to explain:** blueprint (a configuration) → package (fixed,
   deployable) → instance (running).

**What's worse, or still missing:**

1. **`values` are silently dropped.** `POST /packages` and `POST /instances`
   accept `values`, and any unknown field, without an error. A script ported
   from bundles keeps passing `step_size: 1` and gets step-8 output with no
   warning. This should be a 400.
2. **Output switches are tied to the configuration.** `output_embeddings` isn't a
   modelling choice, but a package can't turn it on, so the app needs a blueprint
   of its own: a second optimization (about 5 minutes) and a second fitted
   detector, just to switch an output on.
3. **Query-based serving doesn't enforce the configuration.** See section 4.
   The client has to rebuild the window node (buffer, `window_size`,
   `step_size`), and nothing tells it the step.
4. **The step has to be right at Stage 4.** Changing it means a new
   optimization. And Optimize uses one step to fit *and* validate, so "fit at
   step 8, validate at step 1" (what a step-1 serving client needs evaluated)
   can't be expressed.
5. **Still changing.** Packages are new, and details such as whether a package
   keeps its `name` have differed between platform versions.

## 6. Known limitations

1. **Unknown fields, `values` included, are dropped rather than rejected.** A 400
   would catch scripts ported from bundles.
2. **No way yet to turn on an output such as embeddings** for a promoted blueprint
   without changing its configuration. This branch's stop-gap is
   `fit/app_blueprint.py`.
3. **Platform serving has no streaming source** where the agent keeps the buffer
   and applies its own `window_size` and `step_size`, and an instance doesn't
   expose those values, so a query client has to follow them itself.
4. **Optimize can't validate at a different step from the one it fits at,** so
   the cadence a client will serve at can't be evaluated directly.
