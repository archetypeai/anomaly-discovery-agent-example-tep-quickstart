/**
 * The agent, on the Archetype AI platform: a bridge between the local broker
 * and a serving agent of the promoted TEP detector.
 *
 * In app/ the agent is `agent_edge_runtime` on this laptop, subscribed to the
 * broker. Here the agent runs on the platform (Dev's agent serving), and this
 * process stands where the runtime stood:
 *
 *   sensors/tep ──► bridge: the latest 48 samples ──POST /query──► serving agent
 *                     ▲                                               │
 *                     └─────────── ad/results ◄── one record per window ┘
 *
 * - THE BROWSER NEVER HOLDS THE API KEY. The bridge reads it from the repo's
 *   .env and is the only thing that talks to the platform.
 * - A QUERY CARRIES THE WHOLE WINDOW. A served agent keeps nothing between
 *   queries (fit/serve.py, Stage 8), so the bridge keeps the buffer and sends the latest
 *   `window_size` samples every `step_size` samples, the blueprint's own step.
 * - THE SAME MESSAGE AS THE EDGE RUNTIME. `ad/results` gets the record the
 *   agent answered (anomaly_score, predicted_label, invalid, embedding_<tag>),
 *   with the window's timestamps put back: the served agent numbers samples
 *   0..47 within the query, the bridge knows which samples it sent.
 * - THE SAME ADMIN API AS THE EDGE RUNTIME, so the replayer is unchanged:
 *   GET /status answers once the serving agent is running, POST /reset drops
 *   the buffer and anything queued (a run switch), POST /start is a no-op.
 * - ONE SERVING WORKER, HELD WHILE THIS RUNS. Dev has 3 for everyone. On exit
 *   the agent is cancelled and deleted, and the package deleted; the ids sit in
 *   fit/out/app_serving_state.json until then, so `python3 fit/cleanup.py`
 *   finds them after a hard kill. An agent the platform released (20 minutes
 *   without a query, e.g. a paused replay) is deleted and replaced on the next
 *   window: a package that still has an agent can't be deleted. Starting
 *   one retries while all the workers are taken, and windows wait in the queue
 *   until the agent is running.
 * - THE PAGE SEES THE AGENT'S PHASE on `ad/agent` (retained): starting,
 *   waiting, running, replacing, stopped. An MQTT will clears a stale
 *   "running" if this process dies without saying so.
 * - A PACKAGE, NOT A BUNDLE (Agent Lifecycle 2.0). A package carries no values,
 *   so the agent runs the blueprint as promoted. Step is the bridge's own (one
 *   window per query), but `output_embeddings` stays as promoted (false), so
 *   the page's live embedding trail stays empty.
 *
 * Env (repo .env): ATAI_API_ENDPOINT (dev or staging), ATAI_API_KEY.
 * Env (app-serving/.env): MQTT_PORT, AGENT_PORT.
 */
import mqtt from 'mqtt';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { REPO, loadEnv, readJson } from './common.js';

loadEnv();

// The deployment root, with any /api or /vX.Y suffix removed, then /api appended:
// every platform surface lives under it, and one .env works whichever form you have.
// Keeping /api on ENDPOINT also matches what fit/ writes into the state files.
const ROOT = (process.env.ATAI_API_ENDPOINT ?? '')
	.replace(/\/+$/, '')
	.replace(/\/api$/, '')
	.replace(/\/v\d+(\.\d+)*$/, '');
const ENDPOINT = ROOT ? `${ROOT}/api` : '';
const KEY = process.env.ATAI_API_KEY;
if (!ENDPOINT || !KEY) {
	console.error('bridge: set ATAI_API_ENDPOINT and ATAI_API_KEY in the repo .env');
	process.exit(1);
}
// Match the deployment, not one host: dev is api.dev.* and platform.dev.*, staging platform.stage.*
if (!['.dev.', '.stage.'].some((d) => ROOT.includes(d))) {
	console.error(`bridge: ${ENDPOINT}: agent serving is on dev and staging only for now`);
	process.exit(1);
}
const MQTT_PORT = Number(process.env.MQTT_PORT ?? 1890);
const BROKER_URL = process.env.BROKER ?? `mqtt://127.0.0.1:${MQTT_PORT}`;
const ADMIN_PORT = Number(process.env.AGENT_PORT ?? 9100);
const MODEL = 'tep-ad';
const STATE = path.join(REPO, 'fit', 'out', 'app_serving_state.json');

if (fs.existsSync(STATE)) {
	console.error(`bridge: ${path.relative(REPO, STATE)} holds an earlier bridge's agent: run python3 fit/cleanup.py --yes`);
	process.exit(1);
}
const test = readJson(path.join(REPO, 'fit', 'out', 'test_state.json'));
if (!test?.blueprint?.key) {
	console.error('bridge: no fit/out/test_state.json: run fit/test.py first');
	process.exit(1);
}
/** The deployment an endpoint addresses, whatever hostname it arrives under (as ad_api.py). */
const deployment = (e) =>
	e.trim().replace(/^[a-z]+:\/\//, '').split('/')[0].split(':')[0].replace(/^(api|platform)\./, '').toLowerCase();
if (test.endpoint && deployment(test.endpoint) !== deployment(ENDPOINT)) {
	console.error(
		`bridge: fit/out/test_state.json is from ${test.endpoint}, a different deployment from ${ENDPOINT}`
	);
	process.exit(1);
}
const PROMOTED = test.blueprint.key;
const PROMOTED_ID = test.blueprint.id;
const CHANNELS = test.blueprint.values.data_columns;
const WINDOW = test.blueprint.values.window_size;
const step = Number(test.blueprint.values.step_size ?? 8);

// ------------------------------------------------------------------ the platform

async function api(method, p, body) {
	const r = await fetch(`${ENDPOINT}/agents${p}`, {
		method,
		headers: { Authorization: `Bearer ${KEY}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
		body: body ? JSON.stringify(body) : undefined,
		signal: AbortSignal.timeout(120_000)
	});
	const text = await r.text();
	if (!r.ok) {
		const e = new Error(`${method} ${p} → ${r.status}: ${text.slice(0, 300)}`);
		e.status = r.status;
		throw e;
	}
	return text ? JSON.parse(text) : {};
}

/** `agents`: every agent of the package not yet deleted, the current one last. */
const live = { package: null, agent: null, agents: [], running: false, phase: 'starting' };
const save = () => fs.writeFileSync(STATE, JSON.stringify(
	{ endpoint: ENDPOINT, package: live.package, agent: live.agent, agents: live.agents }, null, 1));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const latencies = [];

/** What the page shows about the agent (retained, so a reload sees it at once). */
function announce(phase, detail = '') {
	live.phase = phase;
	const ms = [...latencies].sort((a, b) => a - b);
	client.publish('ad/agent', JSON.stringify({ phase, detail, running: live.running, agent: live.agent,
		package: live.package, blueprint: PROMOTED, step, queued: queue.length,
		medianLatencyMs: ms[Math.floor(ms.length / 2)] ?? null }), { retain: true });
}

async function startAgent() {
	if (!live.package) {
		// The promoted blueprint as it is: the platform supplies the serving
		// connectors in serving mode, so no served copy is made.
		let pkg = await api('POST', '/packages', { blueprint_ids: [PROMOTED_ID], target: { kind: 'platform' },
			name: 'TEP app-serving' });
		live.package = pkg.id;
		save();
		while (pkg.status === 'building') {
			await sleep(2000);
			pkg = await api('GET', `/packages/${live.package}`);
		}
		if (pkg.status !== 'ready') throw new Error(`package ${live.package} is ${pkg.status}`);
	}
	live.agent = (await api('POST', '/instances', { package_id: live.package, mode: 'serving' })).id;
	live.agents.push(live.agent);
	save();
	announce('starting', `agent ${live.agent}`);
	const t0 = Date.now();
	for (;;) {
		const s = (await api('GET', `/instances/${live.agent}`)).status;
		if (s === 'running') break;
		if (['failed', 'completed', 'cancelled', 'canceled'].includes(s) || Date.now() - t0 > 600_000)
			throw new Error(`agent ${live.agent} is ${s}`);
		await sleep(2000);
	}
	live.running = true;
	announce('running');
	console.log(`bridge: serving agent ${live.agent} running (package ${live.package}, ${PROMOTED})`);
}

/** Cancel and delete an agent; true once it is gone (404 counts). */
async function dropAgent(id) {
	await api('POST', `/instances/${id}/cancel`, {}).catch(() => {});   // a released agent is already stopped
	try {
		await api('DELETE', `/instances/${id}`);
	} catch (e) {
		if (e.status !== 404) {
			console.error(`bridge: ${e.message}`);
			return false;
		}
	}
	live.agents = live.agents.filter((a) => a !== id);
	if (live.agent === id) live.agent = null;
	save();
	return true;
}

let stopping = false;
async function shutdown(sig) {
	if (stopping) return;
	stopping = true;
	console.log(`bridge: ${sig}, cleaning up`);
	live.running = false;
	let left = 0;
	try {
		for (const id of [...live.agents]) if (!(await dropAgent(id))) left++;
		if (live.package && !left) {
			try {
				await api('DELETE', `/packages/${live.package}`);
			} catch (e) {
				if (e.status !== 404) {
					console.error(`bridge: ${e.message}`);
					left++;
				}
			}
		}
		if (left) {
			// Keep the ids for fit/cleanup.py rather than leaving them on the platform unrecorded.
			console.error(`bridge: not everything was deleted; run python3 fit/cleanup.py --yes (ids in ${path.relative(REPO, STATE)})`);
		} else {
			fs.rmSync(STATE, { force: true });
			console.log(`bridge: deleted its agent(s) and package ${live.package ?? '(none)'}`);
		}
		announce('stopped');
		await new Promise((r) => client.end(false, {}, r));
	} finally {
		process.exit(left ? 1 : 0);
	}
}
for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(sig, () => shutdown(sig));
// Anything unexpected still cleans up: an exit without it would hold a Dev worker.
process.on('uncaughtException', (e) => { console.error('bridge:', e); shutdown('error'); });
process.on('unhandledRejection', (e) => { console.error('bridge:', e); shutdown('error'); });

/** Start an agent, retrying while Dev's serving workers are all taken. */
async function startWithRetry() {
	live.running = false;
	for (let wait = 15_000; !stopping; wait = Math.min(wait * 2, 120_000)) {
		try {
			await startAgent();
			return;
		} catch (e) {
			console.error(`bridge: could not start a serving agent (${e.message}); retrying in ${wait / 1000} s`);
			announce('waiting', `no serving worker free; retrying in ${wait / 1000} s`);
			if (live.agent) await dropAgent(live.agent);
			await sleep(wait);
		}
	}
}

// ------------------------------------------------------------------ the windows

/** Samples of the current run, oldest first: {t, values[33]}. */
let buffer = [];
/** Samples seen since the last reset: a window ends on sample `seen` when
 *  seen >= WINDOW and (seen - WINDOW) is a multiple of the step. */
let seen = 0;
/** Bumped on every reset, so an answer to a query sent before it is dropped. */
let generation = 0;
const queue = [];
let busy = false;

function onSample(payload) {
	const kv = Object.fromEntries(payload.toString().split(',').map((p) => p.split('=')));
	const t = Number(kv.timestamp);
	buffer.push({ t, values: CHANNELS.map((c) => Number(kv[c])) });
	if (buffer.length > WINDOW + 64) buffer.splice(0, buffer.length - WINDOW);
	seen++;
	if (seen >= WINDOW && (seen - WINDOW) % step === 0) {
		queue.push({ gen: generation, rows: buffer.slice(-WINDOW) });
		drain().catch((e) => console.error(`bridge: ${e.message}`));
	}
}

async function drain() {
	if (busy || !live.running) return;
	busy = true;
	try {
		while (queue.length && live.running && !stopping) {
			const job = queue.shift();
			if (job.gen !== generation) continue;
			const body = { model: MODEL, query: '', events: [{ type: 'data.numeric_array',
				event_data: { contents: CHANNELS.map((_, c) => job.rows.map((r) => r.values[c])) } }] };
			let answer;
			const t = Date.now();
			try {
				answer = await api('POST', `/instances/${live.agent}/query`, body);
			} catch (e) {
				if (e.status === 409) {
					// Released after 20 minutes without a query, or cancelled elsewhere.
					console.warn(`bridge: agent ${live.agent} no longer running; replacing it`);
					announce('replacing', `agent ${live.agent} was released`);
					if (live.agent) await dropAgent(live.agent);
					queue.unshift(job);
					await startWithRetry();
					continue;
				}
				console.error(`bridge: query failed: ${e.message}`);
				publish({ predicted_label: 'INVALID_STATE', invalid: 'true',
					start_timestamp: job.rows[0].t, finish_timestamp: job.rows.at(-1).t });
				continue;
			}
			latencies.push(Date.now() - t);
			if (latencies.length > 200) latencies.shift();
			if (latencies.length % 10 === 0) announce('running');
			if (job.gen !== generation) continue;
			const rec = (answer.response ?? answer).data?.[0];
			if (!rec) {
				console.error(`bridge: no record in ${JSON.stringify(answer).slice(0, 200)}`);
				continue;
			}
			// Keep the score, the verdict and the 33 embeddings; drop the per-channel
			// features (unused by the app) to save the browser 4 KB a window.
			const msg = { anomaly_score: rec.anomaly_score, predicted_label: rec.predicted_label, invalid: rec.invalid,
				start_timestamp: job.rows[0].t, finish_timestamp: job.rows.at(-1).t, latency_ms: Date.now() - t };
			for (const c of CHANNELS) msg[`embedding_${c}`] = rec[`embedding_${c}`];
			publish(msg);
		}
	} finally {
		busy = false;
	}
}

// The will clears a retained "running" if this process dies without saying so (kill -9).
const client = mqtt.connect(BROKER_URL, {
	clientId: `tep-serving-bridge-${Date.now()}`,
	will: { topic: 'ad/agent', payload: JSON.stringify({ phase: 'stopped', running: false }), retain: true, qos: 1 }
});
const publish = (msg) => client.publish('ad/results', JSON.stringify(msg));

client.on('connect', () => {
	client.subscribe(['sensors/tep', 'tep/status'], { qos: 1 });
	if (live.phase === 'starting' && !live.agent) announce('starting', 'creating the agent');
	console.log(`bridge: connected to ${BROKER_URL}`);
});
client.on('message', (topic, payload) => {
	if (topic === 'sensors/tep') return onSample(payload);
});
client.on('error', (e) => console.error('bridge mqtt error:', e.message));

// ------------------------------------------------- the edge runtime's admin API

function reset() {
	generation++;
	buffer = [];
	seen = 0;
	queue.length = 0;
}

http.createServer((req, res) => {
	const reply = (code, body) => {
		res.writeHead(code, { 'Content-Type': 'application/json' });
		res.end(JSON.stringify(body));
	};
	if (req.method === 'GET' && req.url === '/status') {
		const ms = [...latencies].sort((a, b) => a - b);
		return reply(live.running ? 200 : 503, { running: live.running, agent: live.agent, package: live.package,
			blueprint: PROMOTED, step, queued: queue.length, medianLatencyMs: ms[Math.floor(ms.length / 2)] ?? null });
	}
	if (req.method === 'POST' && req.url === '/reset') {
		reset();
		return reply(200, { reset: true });
	}
	if (req.method === 'POST' && req.url === '/start') return reply(200, { started: true });
	reply(404, { error: 'not found' });
}).listen(ADMIN_PORT, '127.0.0.1', () => console.log(`bridge: admin API on http://127.0.0.1:${ADMIN_PORT}`));

// ------------------------------------------------------------------------ start

try {
	await startWithRetry();
	drain().catch((e) => console.error(`bridge: ${e.message}`));
} catch (e) {
	console.error(`bridge: ${e.message}`);
	await shutdown('startup failure');
}
