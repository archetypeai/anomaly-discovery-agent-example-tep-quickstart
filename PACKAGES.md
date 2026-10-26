# Packages instead of bundles: what changes for a user

Agent Lifecycle 2.0 replaces bundles with packages. This branch (`explore/packages`)
moves the quickstart to packages and records what we measured on Dev on
2026-10-26. **Packages are new and still changing on Dev**: expect breaking
changes, and re-check the calls below before relying on them.

## The calls

| Step | Bundles (`main`) | Packages (this branch) |
|---|---|---|
| Package the promoted blueprint | `POST /agents/bundles` `{blueprint: <key>, name, values}` | `POST /agents/packages` `{blueprint_ids: [<id>], target: {kind: "platform"}, name}`, then poll until `ready` |
| Start an agent | `POST /agents/bundles/{id}/run` `{mode, connectors}` | `POST /agents/instances` `{package_id, mode, connectors}` |
| Query, cancel, delete an agent | unchanged | unchanged |
| List an agent's siblings | `GET /agents/instances?bundle_id=` | `GET /agents/instances?package_id=` |
| Delete | `DELETE /agents/bundles/{id}` (409 while it has agents) | `DELETE /agents/packages/{id}` (409 while it has agents) |

A package names its blueprint by **id**, not key, and pins the models it resolves
to (`resolved_models`). No admin role is needed.

## The idea: optimize once, run what you chose

A bundle could override the blueprint's values per run; a package can't. The agent
is exactly what was promoted. So the configuration Stage 4's optimization chooses
is the configuration every later stage runs, step included. That is the point of
optimizing: the user finds a configuration and keeps it.

`step_size` is the setting this makes visible. It is how far the window moves
between scores, so it sets how often you get an answer (window 48 at step 8, with
TEP's 3-minute samples: a score every 24 minutes over the last 2.4 hours). On
`main`, Stages 4–5 fit and evaluated at step 8 while Stage 6 delivered at step 1
through a bundle override. On this branch every stage runs at the optimized 8:

| Stage | `main` | this branch |
|---|---|---|
| 4 optimize, 5 eval | step 8 | step 8 (unchanged) |
| 6 deliver | step 1, bundle override | step 8, package |
| 8 serve | one query per sample, bundle | one query per 8 samples, package |
| 9 app | step 4 (or 1, a setting), bundle | step 8, package |
| 9 library embeddings | step 8, bundle | step 8, **still a bundle** (see below) |

Which step to use is a search question: the full example's broader search
covers steps (and windows); the quickstart reuses its winner, step 8.

## What a user sees (Dev, 2026-10-26)

- **Same answers.** Stage 6 through a package matched every 8th window of the
  step-1 delivery: the same label everywhere, scores within 0.5%. Stage 8 matched
  Stage 6 in 230/230 windows, scores within 1.6×10⁻⁵, 0.8 s per query.
- **Detection quality unchanged:** mean detection rate 78.5% (78.0% at step 1),
  macro AUROC 0.903 (0.901), 70/80 runs detected (71/80).
- **Coarser timing:** an answer every 24 minutes, so delays are counted in
  24-minute steps (IDV 16 9.2 h against 4.6 h at step 1), and a 3-window alarm
  spans 48 minutes instead of 6.
- **Faster:** delivery 9 min instead of 15, Stage 8 3 min instead of 25, an app
  run 2 min instead of 4.

## What packages can't do yet

`values` on `POST /packages` or `POST /instances` is **accepted and silently
dropped**: no error, and the agent runs as promoted (a query spanning 16 windows
came back with 2 answers with and without `values: {step_size: 1}`). Unknown
fields are dropped the same way. Two things in this example still need a value
the promoted blueprint doesn't have:

- **`output_embeddings: true`**, for the app's embedding view:
  `fit/library_embeddings.py` still uses a bundle for the reference cloud, and the
  app's live embedding trail is empty.
- Nothing else: `output_score` is already on in the promoted blueprint, and
  turning checkpointing off only worked around runtimes before atai_core #6317.

## Questions for the platform team

1. Outputs such as embeddings aren't part of the optimized configuration: how
   should a user turn them on for a promoted blueprint?
2. Can unknown fields, `values` included, be rejected (400) instead of dropped?
   A script ported from bundles keeps passing `values` and silently gets
   different output.
3. On Staging, `POST /packages` dropped `name`; Dev kept it. A version gap?
