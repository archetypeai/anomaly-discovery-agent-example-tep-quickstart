# AD TEP Monitor, served from the platform

A live monitoring workbench for the quickstart's agent. Stage 6's delivery runs are
replayed as if the plant were running now, and every window goes to a **serving
agent** of the detector Stage 5 promoted, on the Archetype AI platform. The answers
come back to a flowsheet, 33 process tags, the anomaly score and an embedding space.

> **Dev only.** Agent serving is on `https://api.dev.u1.archetypeai.app` for first
> internal tests. Dev has **3 serving workers for everyone**: this app holds one
> while it runs, and gives it back when you stop it.

It is the same app as the [full example's
`app-serving/`](https://github.com/archetypeai/anomaly-discovery-agent-example-tep/tree/main/app-serving),
with two differences: it serves this repo's promoted blueprint (k 5), and it replays
the **delivery** runs (Stage 6's 4 files, 84 runs), so every served window can be
checked against Stage 6's batch output.

## Architecture

```
  data/prepared/full/tep_full_chunk_*.csv     fit/out/test_state.json (the promoted blueprint)
                │                                          │ (the replayer reads it too, for the facts it shows)
                ▼                                          ▼                     repo .env: ATAI_API_KEY
┌───────────────────────────┐  GET /status    ┌──────────────────────────────┐          │
│ replayer (node)           │  POST /reset    │ serving bridge (node)        │◀─────────┘
│ one delivery run at a     │  POST /start    │ the API key stays here;      │   POST /query   ┌──────────────────────────┐
│ time, from data/prepared/ │────────────────▶│ keeps the last 48 samples,   │────────────────▶│ serving agent (Dev)      │
│ waits for each block's    │  admin :9100    │ one query per window         │  the latest 48  │ promoted detector,       │
│ windows before the next   │                 │                              │  samples        │ atai-records,            │
└───────────────────────────┘                 └──────────────────────────────┘◀────────────────│ embeddings on            │
  pub │ sensors/tep (z-scored)                   sub ▲ sensors/tep   │ pub        one record   └──────────────────────────┘
  pub │ tep/raw, tep/status (eng. units)         sub ▲ tep/status    │ ad/results (score, label,
  sub ▲ tep/control, ad/results (pacing)             │ (the Pace)    ▼ 33 × 768 embedding)
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                     mosquitto · TCP :1890 · WebSockets :9008                        │
└─────────────────────────────────────────────────────────────────────────────────────┘
               sub ▼ tep/raw, tep/status, ad/results     pub ▲ tep/control (play, pause, run, restart, reveal, Pace)
                     web app (SvelteKit, :5180, mqtt.js over ws): flowsheet · 33 tags · score · embedding space
```

- **The serving bridge** (`scripts/serving-bridge.js`) is the agent's local end. On
  start it makes sure the served copy of the promoted blueprint exists
  (`<promoted key>-served-records`: the same blueprint with an `atai-records` serving
  endpoint in place of its CSV source and sink, at step 1), creates a bundle with
  `output_embeddings: true` and starts a serving agent. For every window it sends the
  latest 48 samples as one query, and publishes the answer on `ad/results` with the
  window's timestamps put back (a served agent numbers the samples 0–47 within a
  query).
- **A served agent keeps nothing between queries**, so the bridge keeps the buffer
  and every query carries the whole window. It also answers `GET /status`,
  `POST /reset` and `POST /start` on :9100, which the replayer calls: a run switch
  clears the buffer, so no window mixes two runs.
- **The API key never reaches the browser.** The bridge reads `ATAI_API_ENDPOINT` and
  `ATAI_API_KEY` from the repo's `.env`, the same file the Python stages use.
- **On exit** (Ctrl-C, `npm run stop`) the bridge cancels and deletes its agent and
  deletes its bundle. If it's killed hard, the ids are still in
  `fit/out/app_serving_state.json`, and `python3 fit/cleanup.py --yes` removes them.
  An agent the platform released after 20 minutes without a query (a replay paused that
  long) is deleted and replaced on the next window, retrying while Dev's serving workers
  are all taken. If anything can't be deleted on exit, the bridge says so and keeps the
  ids for `fit/cleanup.py`. See [Stop and clean up](#stop-and-clean-up).

## The embedding space: the reference library, recomputed

The promoted detector is a registry artifact (`aar_…`) with no download route, and
the Optimizations and Evals APIs return values, metrics and predictions, not
embeddings. So the windows the detector was fitted on are recomputed:

```sh
python3 fit/library_embeddings.py     # once, from the repo root: 40 batch runs, ~8 min
```

It runs the 40 library files through the promoted blueprint in **batch**, at the
trial's step 8 with `output_embeddings: true`: the same windows and encoder as the
fit, 2,280 of them. PCA 1–2 of their embeddings, whitened, gives the cloud and the
projection, in `static/detector-view.{json,bin}`. Each live window's embedding from
the served agent goes through the same projection. The detector's own PCA is fitted
on these embeddings too, but it can't be read to confirm the axes, so the view is a
recomputed one.

## Run it

Prerequisites: Node 20+, `brew install mosquitto`, and Stages 4–6 run on Dev. In the [repo README](../README.md) this is Stage 9
(`fit/out/test_state.json` names the promoted blueprint). Then:

```sh
python3 fit/library_embeddings.py     # once, from the repo root (writes static/detector-view.*)
cd app-serving
npm install
npm run dev                           # broker + serving bridge + replayer + web
open http://localhost:5180
```

When you're done, stop it and check it cleaned up: [Stop and clean up](#stop-and-clean-up).

### Pace

The platform answers a window in under a second with embeddings on, so the replay is
paced by the platform: the replayer publishes a block of samples and waits for its
windows. Settings → Pace chooses how many windows to ask about:

| | windows per run | a run takes | a detection (3 windows over the line) spans |
|---|---:|---|---|
| **every 4th sample** (default) | 229 | ~3–4 min | 36 min of process time; alarm times approximate |
| every sample (exact) | 913 | ~15 min | 9 min; alarms match Stage 6's delivery to the sample |

A window scores the same either way; the step only decides which windows are asked
about.

## Stop and clean up

A running app holds a serving agent on Dev, and so one of its 3 serving workers,
until the bridge deletes the agent or the platform releases it after 20 minutes
without a query. Closing the browser tab does not stop it.

1. **Stop the app.** Press Ctrl-C **once** in the `npm run dev` terminal and
   wait for `bridge: deleted its agent(s) and bundle …`; a second Ctrl-C can cut
   that short. Or, from `app-serving/` in any terminal (also for an app started
   in the background or from a terminal since closed):

   ```sh
   npm run stop      # SIGTERM to the bridge, stops the rest, checks the ports
   ```

   Either way the bridge cancels and deletes its agent, deletes its bundle and
   removes `fit/out/app_serving_state.json`. `npm run stop` ends with
   `all ports free (1890 · 9008 · 9100 · 5180)`; a port still held names its process
   (9100 is the bridge: it may still be deleting, so run `npm run stop` again after a few seconds).

2. **Check nothing is left**, from the repo root:

   ```sh
   ls fit/out/app_serving_state.json        # "No such file": the bridge cleaned up
   set -a; source .env; set +a
   curl -s "$ATAI_API_ENDPOINT/agents/instances?status=running&limit=100" -H "Authorization: Bearer $ATAI_API_KEY" \
     | jq -c '.data[] | select(.mode=="serving") | {id, blueprint, name, created_at}'
   ```

   No line named `TEP app-serving` means no agent of this app is running.
   `status=running` filters on the server; `mode=serving` is ignored there, so
   `jq` picks the serving agents (other people's may show up too).

3. **If something is left** (the bridge was killed hard with `kill -9`, the
   machine slept or lost power, or it printed `not everything was deleted`), the
   ids are still in `fit/out/app_serving_state.json`:

   ```sh
   python3 fit/cleanup.py            # lists what it would delete, stage by stage
   python3 fit/cleanup.py --yes      # deletes it
   ```

   It also finds agents the bridge replaced (from the bundle's own listing),
   cancels a running agent before deleting it, and removes the state file when
   done. Without a state file, an agent of yours from the listing above can be
   removed by its id:

   ```sh
   curl -s -X POST "$ATAI_API_ENDPOINT/agents/instances/<agt_id>/cancel" -H "Authorization: Bearer $ATAI_API_KEY" \
     -H "Content-Type: application/json" -d '{}'
   curl -s -X DELETE "$ATAI_API_ENDPOINT/agents/instances/<agt_id>" -H "Authorization: Bearer $ATAI_API_KEY"
   ```

   Its bundle (`bnd_…`, from `GET /agents/instances/<agt_id>`) can then be
   deleted with `DELETE /agents/bundles/<bnd_id>`; a bundle that still has any
   agent, even a cancelled one, answers 409.

`fit/library_embeddings.py`'s 40 batch agents and their bundle hold no serving
worker; `fit/cleanup.py --yes` deletes them too, with the rest of the platform
path's agents (see the [repo README](../README.md)), whenever you're done with them.

## Ports

| MQTT TCP | MQTT WS | Web | Agent admin |
|---|---|---|---|
| 1890 | 9008 | 5180 | 9100 (the serving bridge) |

The same slot as the full example's `app-serving/`, so run one of the two at a time.

## Layout

| Path | What |
|---|---|
| `scripts/serving-bridge.js` | the agent's local end: broker ↔ serving agent on the platform, and the admin API the replayer calls |
| `scripts/replayer.js` | replays Stage 6's delivery runs one at a time, paced by the agent, with the step switch |
| `scripts/run-broker.sh`, `scripts/stop.sh`, `mosquitto/` | the broker on 1890 / 9008, and stopping everything |
| `static/detector-view.{json,bin}` | the recomputed reference cloud and projection, from `fit/library_embeddings.py` |
| `src/` | the SvelteKit workbench, with the Pace switch in Settings |

## Licence and data

The same as the repo: TEP data from Rieth et al. (2017), Harvard Dataverse,
[doi:10.7910/DVN/6C3JR1](https://doi.org/10.7910/DVN/6C3JR1); see the
[repo README](../README.md#data-attribution).
