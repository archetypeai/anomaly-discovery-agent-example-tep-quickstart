# Packages instead of bundles: what changes for a user

Agent Lifecycle 2.0 replaces bundles with packages. This branch (`explore/packages`)
moves the quickstart's serving stages to packages and records what we measured on
Dev on 2026-10-26.

## The calls

| Step | Bundles (before) | Packages (now) |
|---|---|---|
| Package the promoted blueprint | `POST /agents/bundles` `{blueprint: <key>, name, values}` | `POST /agents/packages` `{blueprint_ids: [<id>], target: {kind: "platform"}, name}`, then poll until `ready` |
| Start an agent | `POST /agents/bundles/{id}/run` `{mode, connectors}` | `POST /agents/instances` `{package_id, mode, connectors}` |
| Query, cancel, delete an agent | unchanged | unchanged |
| List an agent's siblings | `GET /agents/instances?bundle_id=` | `GET /agents/instances?package_id=` |
| Delete | `DELETE /agents/bundles/{id}` (409 while it has agents) | `DELETE /agents/packages/{id}` (409 while it has agents) |

A package names its blueprint by **id**, not key, and pins the models it resolves
to (`resolved_models`). No admin role is needed, on Dev or Staging.

## What a user gains

- **One lifecycle for batch and serving.** The same package runs either way:
  `mode: "serving"` or not.
- **No admin role.** On Staging, the old route to a changed blueprint
  (`POST /blueprints`) needed it.
- **Pinned models.** The package records which encoder and detection head it
  runs, so a later model change can't silently alter a deployed agent.
- **Same answers.** On Dev, 200 windows served through a package matched Stage 6's
  bundle-based batch output: 200/200 labels, scores within 1.7×10⁻⁵, median 793 ms
  per query. A batch instance from a package ran a delivery file end to end too.

## What a user loses (today)

A bundle could override the blueprint's values; a package can't. `values` on
`POST /packages` or `POST /instances` is **accepted and silently dropped**: no
error, and the agent runs exactly as promoted. Checked on Dev and Staging: a query
spanning 16 windows came back with 2 answers (step 8) with and without
`values: {step_size: 1}`.

For this quickstart, that means:

| Stage | Needed override | With packages |
|---|---|---|
| 8, serve | `step_size: 1` | **Works.** One window per query is one answer at any step. `--windows-per-query` > 1 now needs a step-1 blueprint, and `serve.py` refuses it otherwise. |
| 9, app | `output_embeddings: true` | **Works, minus the live embedding trail** (embeddings stay off). |
| 6, deliver | `step_size: 1` | **Blocked.** Batch runs at step 8: 1,195 scores per file instead of 9,553. Stays on bundles here. |
| 9, library embeddings | `output_embeddings: true`, step | **Blocked.** Stays on bundles here. |
| (checkpointing off) | `runner_config` | Not needed on current runtimes. |

The silent drop is the sharpest edge: a script ported from bundles keeps passing
`values`, gets no error, and gets different output.

## Questions for the platform team

1. Will packages or instances take values (or a value set) the way bundles did?
   If not, how should a user change step or outputs after promote: re-optimize
   with them pinned, or an override at promote?
2. Can unknown fields be rejected (400) instead of dropped? Most surprising:
   `values` and a made-up field are both accepted.
3. On Staging, POST /packages dropped `name`; Dev kept it. Is that a version gap?
