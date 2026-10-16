/**
 * Replays one Tennessee Eastman simulation onto the local broker as if the
 * plant were running now.
 *
 * The quickstart's copy replays the DELIVERY runs (Stage 6's 4 files, 84 runs:
 * the "ongoing operation" the agent was delivered to), from data/prepared/full/,
 * so every served window can be checked against Stage 6's batch output.
 *
 * app-serving/: the copy of the full example's replayer for the platform-served agent. The
 * agent is scripts/serving-bridge.js, which implements the edge runtime's admin
 * API (/status, /reset, /start) on :9100, so the replay logic below is app/'s.
 * What differs: the ports, the detector's facts (read from fit/test.py's
 * promoted blueprint, not Stage 5's fit record), a `step` the viewer can switch
 * between 4 and 1, and pacing that counts the windows a block really completes.
 *
 * Topics
 *   sensors/tep    replayer -> agent   key=value, `timestamp=<ms>,xmeas_1=<f>,...`
 *                                      Z-SCORED — the detector's contract.
 *   tep/raw        replayer -> app     JSON per block, RAW engineering units
 *   tep/status     replayer -> app     JSON, retained
 *   tep/control    app -> replayer     {action: play|pause|select|restart|reveal}
 *
 * WHY A RUN AT A TIME, AND WHY THE AGENT IS RESET BETWEEN RUNS. The prepared
 * eval slices are 21 simulations concatenated with a day-long timestamp seam
 * between them, because the platform evaluation wanted one file per slice. A
 * live monitor watches ONE plant, so the replayer seeks to a single simulation
 * and publishes only that. Switching runs is a discontinuity: the agent would
 * otherwise hold up to 63 samples of the previous simulation in its window
 * buffer and score windows that are half one plant and half another. So a
 * switch resets the graph over the admin API (POST /reset, POST /start) and
 * starts the new run with a fresh timestamp base — the same move the RED demo
 * makes for the same reason.
 *
 * WHY PROCESS TIME, NOT WALL-CLOCK TIME. TEP samples every 3 minutes, so a
 * 48-hour simulation is 960 samples. Replaying at data rate would take two
 * days. The demo clock runs in PROCESS time: one sample is one observation,
 * the transport reads in process hours, and the whole run plays out in about
 * 90 seconds — fast enough to watch a fault develop, slow enough to see it.
 *
 * WHY IT WAITS FOR THE AGENT. At 33 channels the encoder scores ~2.6
 * windows/s on the CPU backend (app/README.md has the measurements), so about
 * 10 samples/s at step 4. Publishing faster just grows a queue inside the
 * broker: the run would look fast while the scores arrived a minute behind the
 * trace. The replayer publishes a block and waits for its windows to come back
 * (or `--block-timeout` elapses), which self-paces to whatever the host can do.
 * It also keeps the source's inbound queue from overflowing — dumping 960
 * records at once produced 15 invalid windows out of 128 in testing, because
 * dropped records leave gaps the sampling-rate validation rejects.
 *
 * TWO REPRESENTATIONS OF THE SAME SIGNAL, as the OSM, RED and bearing demos
 * all publish their rigs: the agent gets the z-scored columns its detector was
 * fitted on, and the app gets raw engineering units, because a dashboard
 * reporting "-0.42" for a reactor at 2705 kPa is showing the model's
 * coordinates rather than the plant's. Stage 2's z-scoring is one pooled
 * (mean, std) per channel, so the inverse is exact.
 *
 * GROUND TRUTH IS WITHHELD. The selector says "Run 27", never "IDV 5". A crew
 * watching a live plant does not know whether a fault is present, and the
 * demo's whole point — including the three faults nobody can detect — depends
 * on the viewer not knowing either. The truth is revealed only when asked for,
 * or once the run ends.
 */
import mqtt from 'mqtt';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '../..');
const PREPARED = process.env.PREPARED_DIR ?? path.join(REPO, 'data', 'prepared');
/** Stage 6's delivery files: 4 chunks of 21 runs each, with label sidecars. */
const RUNS_DIR = path.join(PREPARED, 'full');

const args = Object.fromEntries(
	process.argv.slice(2).map((a) => {
		const [k, v] = a.replace(/^--/, '').split('=');
		return [k, v ?? true];
	})
);

const MQTT_PORT = Number(process.env.MQTT_PORT ?? 1890);
const BROKER_URL = process.env.BROKER ?? `mqtt://127.0.0.1:${MQTT_PORT}`;
const AGENT_ADMIN = process.env.AGENT_ADMIN ?? `http://127.0.0.1:${process.env.AGENT_PORT ?? 9100}`;
/** Windows per published block. The platform answers a window in ~0.9 s, so 8
 *  windows is a screen update every ~7 s at either step. */
const WINDOWS_PER_BLOCK = Number(args['windows-per-block'] ?? 8);
/** A block's windows normally all come back; this only bounds a lost answer. */
const BLOCK_TIMEOUT = Number(args['block-timeout'] ?? 60000);
/** How long to wait for the agent's admin API before replaying without it. */
const AGENT_WAIT_S = Number(args['agent-wait'] ?? 90);
/** Per-request bound on the admin API. A reset lands while the graph is still
 *  draining, so it is not instant — but it is not unbounded either. */
const RESET_TIMEOUT = Number(args['reset-timeout'] ?? 15000);
/** Process seconds per sample — TEP's 3-minute cadence. */
const SAMPLE_S = 180;
/** Fault onset in the 48-hour set: sample 160, i.e. process hour 8. */
const ONSET_SAMPLE = 160;

// ---------------------------------------------------------------- run registry

/**
 * Every simulation in the prepared eval slices, as a replayable run.
 *
 * The labels sidecar carries (timestamp, label, fault_id, simulationrun,
 * sample) per row, and a simulation's rows are contiguous, so one pass per
 * slice yields every run's row range without touching the 6.5 MB data file.
 */
function buildRegistry() {
	const runs = [];
	for (const file of fs.readdirSync(RUNS_DIR).sort()) {
		const m = /^tep_(full_chunk_\d{3})_labels\.csv$/.exec(file);
		if (!m) continue;
		const slice = m[1];
		const lines = fs.readFileSync(path.join(RUNS_DIR, file), 'utf8').trimEnd().split('\n');
		const h = lines[0].split(',');
		const [iLabel, iFault, iSim, iSample] = ['label', 'fault_id', 'simulationrun', 'sample'].map((c) => h.indexOf(c));
		let cur = null;
		for (let r = 1; r < lines.length; r++) {
			const f = lines[r].split(',');
			const key = `${f[iFault]}/${f[iSim]}`;
			if (!cur || cur.key !== key) {
				if (cur) runs.push(cur);
				cur = {
					key,
					slice,
					faultId: f[iFault],
					sim: Number(f[iSim]),
					startRow: r - 1, // rows in the data file are 0-based after the header
					rows: 0,
					onsetRow: null
				};
			}
			cur.rows++;
			if (cur.onsetRow === null && f[iLabel] === 'fault') cur.onsetRow = r - 1 - cur.startRow;
			cur.lastSample = Number(f[iSample]);
		}
		if (cur) runs.push(cur);
	}
	// Anonymised, stable ids. A seeded shuffle so "Run 05" carries no hint of
	// IDV 5 — the selector must not leak what the detector is supposed to find.
	// Deterministic, so a demo can be rehearsed and repeated.
	let seed = 20260917;
	const rand = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
	const order = runs.map((_, i) => i);
	for (let i = order.length - 1; i > 0; i--) {
		const j = Math.floor(rand() * (i + 1));
		[order[i], order[j]] = [order[j], order[i]];
	}
	order.forEach((runIdx, pos) => {
		runs[runIdx].id = pos + 1;
	});
	return runs.sort((a, b) => a.id - b.id);
}

const REGISTRY = buildRegistry();
if (!REGISTRY.length) {
	console.error(`no delivery files in ${RUNS_DIR}: run prep/prepare_full_eval.py, or git lfs pull`);
	process.exit(1);
}

/**
 * The detector's own fitted configuration, and the stride the runtime is
 * actually using.
 *
 * Read rather than hardcoded. The panel that shows these is proof-of-life for a
 * room that wants to know the agent is real, and a hand-typed "LOF k=20" beside
 * a detector fitted at k=5 is worse than showing nothing. The fitted values come
 * from Stage 5's record; `step_size` is the one thing the blueprint overrides at
 * inference time, so it is read from the blueprint instead.
 */
function agentConfig() {
	const out = { encoder: 'Omega 1.5', serving: true };
	try {
		const bp = JSON.parse(fs.readFileSync(path.join(REPO, 'fit', 'out', 'test_state.json'), 'utf8')).blueprint;
		const v = bp.values ?? {};
		out.blueprint = bp.key;
		out.windowSize = v.window_size;
		out.threshold = v.threshold;
		out.fittedStep = v.step_size;
		out.detector = `kNN k=${v.n_neighbors} ${v.metric} · PCA ${v.pca_components}`;
	} catch { /* the demo runs without it; the panel just shows fewer facts */ }
	out.stepSize = Number(process.env.STEP ?? args.step ?? 4);
	return out;
}
const AGENT_CONFIG = agentConfig();

/** Per-channel (mean, std) so the app can be shown engineering units. */
const ZSTATS = JSON.parse(fs.readFileSync(path.join(PREPARED, 'zscore_stats.json'), 'utf8'));
const CHANNELS = ZSTATS.channels;

// ------------------------------------------------------------------ run loading

const sliceCache = new Map();
function sliceRows(slice) {
	if (!sliceCache.has(slice)) {
		const p = path.join(RUNS_DIR, `tep_${slice}.csv`);
		const lines = fs.readFileSync(p, 'utf8').trimEnd().split('\n');
		const header = lines[0].split(',');
		sliceCache.set(slice, { header, rows: lines.slice(1) });
		// One slice is 6.5 MB of text; four would be 26 MB. Keep only the newest
		// two, which covers flipping between a couple of runs.
		if (sliceCache.size > 2) sliceCache.delete(sliceCache.keys().next().value);
	}
	return sliceCache.get(slice);
}

const state = {
	run: null,
	cursor: 0,
	playing: false,
	loading: false,
	revealed: false,
	/** Monotonic publish clock, ms. Never rewinds, so consecutive runs cannot
	 *  produce a backwards timestamp even though each simulation starts at 0. */
	clock: Date.now(),
	/** The clock value sample 0 of the current run was published at. The app
	 *  maps a result's `finish_timestamp` back to a sample index with it, which
	 *  places each window exactly rather than at wherever the replayer's cursor
	 *  happened to be when the message arrived — a whole block of windows would
	 *  otherwise stack on one x position. */
	clockBase: 0,
	windowsSeen: 0,
	blockDeadline: 0,
	pendingBlock: 0
};

function selectRun(id) {
	const run = REGISTRY.find((r) => r.id === Number(id)) ?? REGISTRY[0];
	state.run = run;
	state.cursor = 0;
	state.revealed = false;
	state.windowsSeen = 0;
	const { header, rows } = sliceRows(run.slice);
	state.colIdx = CHANNELS.map((c) => header.indexOf(c));
	state.rows = rows.slice(run.startRow, run.startRow + run.rows);
	// Sample 0 will be published one tick after the current clock value.
	state.clockBase = state.clock + SAMPLE_S * 1000;
	console.log(`replayer: run ${run.id} (${run.slice} ${run.key}, ${run.rows} samples)`);
}

// ------------------------------------------------------------------ agent reset

/**
 * Reset the graph so no window straddles two simulations.
 *
 * Two calls, not one: a reset stops the graph and leaves it loaded, so it must
 * be started again or nothing is scored. If the admin API is unreachable the
 * run still replays — the cost is the handful of windows that straddle the
 * switch, which is worth a warning rather than a dead demo.
 */
/**
 * Block until the agent's admin API answers, or `--agent-wait` seconds elapse.
 *
 * The runtime binds its admin port only AFTER loading the Omega encoder, which
 * takes ~20 s cold. Without this wait `npm run dev` — which starts broker,
 * agent, replayer and web together — would begin publishing into a broker no
 * agent has subscribed to yet, and the first run would open mid-simulation with
 * a third of its windows never scored. Missing the agent entirely is survivable
 * (the replay still runs, nothing scores it), so this warns rather than exits.
 */
async function waitForAgent() {
	const deadline = Date.now() + AGENT_WAIT_S * 1000;
	let announced = false;
	while (Date.now() < deadline) {
		try {
			const r = await fetch(`${AGENT_ADMIN}/status`, { signal: AbortSignal.timeout(1000) });
			if (r.ok) {
				if (announced) console.log('replayer: agent is up');
				return true;
			}
		} catch {
			if (!announced) {
				console.log(`replayer: waiting for the agent on ${AGENT_ADMIN} (loading Omega takes ~20 s)`);
				announced = true;
			}
		}
		await new Promise((res) => setTimeout(res, 500));
	}
	console.warn(`replayer: no agent on ${AGENT_ADMIN} after ${AGENT_WAIT_S}s — replaying anyway, nothing will score`);
	return false;
}

async function resetAgent() {
	try {
		// EVERY request is bounded. Without a timeout an admin API that accepts the
		// connection and then never answers leaves this await pending forever — and
		// because the caller holds `state.loading` across it, `tick()` returns early
		// on every call and the replayer wedges SILENTLY: no publishing, no error,
		// no log line, and a dashboard whose every topic reads idle. That is exactly
		// how it failed, and the agent is most likely to be slow to answer here of
		// all places, since a reset lands while the graph is mid-flight with a
		// backlog of 282 KB embedding results still draining.
		const r = await fetch(`${AGENT_ADMIN}/reset`, {
			method: 'POST',
			signal: AbortSignal.timeout(RESET_TIMEOUT)
		});
		if (!r.ok) throw new Error(`reset ${r.status}`);
		const s = await fetch(`${AGENT_ADMIN}/start`, {
			method: 'POST',
			signal: AbortSignal.timeout(RESET_TIMEOUT)
		});
		if (!s.ok) throw new Error(`start ${s.status}`);
		await new Promise((res) => setTimeout(res, 400));
	} catch (e) {
		console.warn(`agent reset skipped (${e.message}) — expect a few straddling windows`);
	}
}

// -------------------------------------------------------------------- publishing

const client = mqtt.connect(BROKER_URL, { clientId: `tep-replayer-${Date.now()}` });

function publishStatus() {
	const run = state.run;
	client.publish(
		'tep/status',
		JSON.stringify({
			playing: state.playing,
			loading: state.loading,
			runId: run?.id ?? null,
			sample: state.cursor,
			totalSamples: run?.rows ?? 0,
			processHours: (state.cursor * SAMPLE_S) / 3600,
			onsetSample: ONSET_SAMPLE,
			ended: run ? state.cursor >= run.rows : false,
			revealed: state.revealed,
			// Withheld until asked for, or until the run is over. See the header.
			truth: state.revealed ? { faultId: run.faultId, sim: run.sim, slice: run.slice } : null,
			available: REGISTRY.map((r) => ({ id: r.id, samples: r.rows })),
			channels: CHANNELS,
			zscore: { mean: ZSTATS.mean, std: ZSTATS.std },
			sampleSeconds: SAMPLE_S,
			clockBase: state.clockBase,
			agent: AGENT_CONFIG
		}),
		{ retain: true }
	);
}

/** One block of samples: z-scored to the agent, engineering units to the app. */
function publishBlock() {
	const run = state.run;
	const step = AGENT_CONFIG.stepSize;
	const end = Math.min(state.cursor + WINDOWS_PER_BLOCK * step, run.rows);
	const samples = [];
	for (let i = state.cursor; i < end; i++) {
		const f = state.rows[i].split(',');
		state.clock += SAMPLE_S * 1000;
		// The agent's contract: integer milliseconds, z-scored columns.
		const kv = [`timestamp=${state.clock}`];
		const raw = [];
		for (let c = 0; c < CHANNELS.length; c++) {
			const z = Number(f[state.colIdx[c]]);
			kv.push(`${CHANNELS[c]}=${z}`);
			// Exact inverse of Stage 2's pooled z-score.
			raw.push(z * ZSTATS.std[CHANNELS[c]] + ZSTATS.mean[CHANNELS[c]]);
		}
		client.publish('sensors/tep', kv.join(','), { qos: 1 });
		samples.push({ sample: i, t: state.clock, v: raw });
	}
	client.publish(
		'tep/raw',
		JSON.stringify({
			runId: run.id,
			from: state.cursor,
			to: end,
			processHours: (end * SAMPLE_S) / 3600,
			samples
		})
	);
	// The windows this block completes: one ends on sample k (1-based) when
	// k >= window and (k - window) is a multiple of the step.
	const w = AGENT_CONFIG.windowSize ?? 48;
	let due = 0;
	for (let k = state.cursor + 1; k <= end; k++) if (k >= w && (k - w) % step === 0) due++;
	state.pendingBlock = due;
	state.cursor = end;
	state.blockDeadline = Date.now() + BLOCK_TIMEOUT;
	publishStatus();
}

let watchdogCursor = -1;
let watchdogSince = Date.now();

/** Agent-paced: advance only once this block's windows have come back. */
function tick() {
	if (!state.playing || state.loading || !state.run) return;
	if (state.cursor >= state.run.rows) {
		state.playing = false;
		// The run is over; the answer is no longer a spoiler.
		state.revealed = true;
		publishStatus();
		console.log(`replayer: run ${state.run.id} complete (${state.run.key})`);
		return;
	}
	const waiting = state.pendingBlock > 0 && Date.now() < state.blockDeadline;
	if (!waiting) publishBlock();
}

let started = false;

client.on('connect', async () => {
	console.log(`replayer: connected to ${BROKER_URL}`);
	// mqtt.js re-fires 'connect' on every RECONNECT, and this handler is not
	// idempotent: run twice it re-selects run 1 under the viewer, resets the
	// agent mid-run, and stacks a second tick interval that publishes the same
	// blocks again. Subscriptions do need re-establishing on each connect, so
	// they stay above the guard.
	client.subscribe(['tep/control', 'ad/results'], { qos: 1 });
	if (started) {
		console.warn('replayer: reconnected — keeping the current run');
		return;
	}
	started = true;
	state.loading = true;
	publishStatus();
	try {
		await waitForAgent();
		selectRun(args.run ?? process.env.RUN ?? REGISTRY[0].id);
		publishStatus();
		await resetAgent();
	} finally {
		state.loading = false;
	}
	state.playing = args.paused ? false : true;
	console.log(`replayer: playing=${state.playing} loading=${state.loading} run=${state.run?.id}`);
	publishStatus();
	setInterval(tick, 120);

	/**
	 * Stall watchdog.
	 *
	 * A replayer that stops publishing looks exactly like one that finished, and
	 * on a dashboard whose every topic then reads `idle` there is nothing to tell
	 * the two apart. This says so, once every five seconds, with the state that
	 * explains it — which is the difference between "the demo is over" and "the
	 * demo is broken".
	 */
	setInterval(() => {
		if (!state.playing || state.loading || !state.run) return;
		if (state.cursor >= state.run.rows) return;
		if (state.cursor !== watchdogCursor) {
			watchdogCursor = state.cursor;
			watchdogSince = Date.now();
			return;
		}
		if (Date.now() - watchdogSince > 5000) {
			console.warn(
				`replayer: STALLED at sample ${state.cursor}/${state.run.rows} — ` +
					`pendingBlock=${state.pendingBlock} deadline in ${state.blockDeadline - Date.now()}ms`
			);
			watchdogSince = Date.now();
		}
	}, 1000);
});

client.on('message', async (topic, payload) => {
	if (topic === 'ad/results') {
		// The pacing signal. Every result means a window came back, whether it
		// scored or was invalidated — both consume a block's worth of work.
		state.windowsSeen++;
		if (state.pendingBlock > 0) state.pendingBlock--;
		return;
	}
	let msg;
	try {
		msg = JSON.parse(payload.toString());
	} catch {
		return;
	}
	switch (msg.action) {
		case 'play':
			state.playing = true;
			break;
		case 'pause':
			state.playing = false;
			break;
		// `loading` comes down in a finally on both of these. It gates tick(), so a
		// throw anywhere between raising and lowering it stops the replay dead with
		// nothing on screen to say why.
		case 'restart':
			state.cursor = 0;
			state.clockBase = state.clock + SAMPLE_S * 1000;
			state.revealed = false;
			state.playing = true;
			state.loading = true;
			publishStatus();
			try {
				await resetAgent();
			} finally {
				state.loading = false;
			}
			break;
		case 'select':
			state.playing = false;
			state.loading = true;
			publishStatus();
			try {
				selectRun(msg.value);
				// PUBLISH AGAIN, with the new run AND loading still true. The status
				// above still carries the OLD run id, so on its own the app never sees
				// the new run in a loading state: it goes straight from the old run's
				// scores to the new run with loading already false, and the ten-second
				// reset reads as "awaiting the agent" — as though the agent were late
				// rather than deliberately restarting.
				publishStatus();
				await resetAgent();
			} finally {
				state.loading = false;
				state.playing = true;
			}
			break;
		case 'reveal':
			state.revealed = true;
			break;
		// Settings: 4 (watchable, the default) or 1 (every window the platform scores).
		case 'step': {
			const v = Number(msg.value);
			if (v === 1 || v === 4) {
				AGENT_CONFIG.stepSize = v;
				console.log(`replayer: step ${v}`);
			}
			break;
		}
		default:
			return;
	}
	publishStatus();
});

client.on('error', (e) => console.error('replayer mqtt error:', e.message));

console.log(`replayer: ${REGISTRY.length} runs available from ${path.relative(REPO, PREPARED)}`);
