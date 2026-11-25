/**
 * The single MQTT-backed store the whole dashboard reads from.
 *
 * Subscribes over the broker's WebSocket listener — the browser talks to
 * mosquitto directly, so there is no backend in this app at all.
 *
 *   tep/raw       replayer -> one block of samples, RAW engineering units
 *   tep/status    replayer -> transport, run registry, z-score stats (retained)
 *   ad/results    AGENT    -> one scored window
 *   ad/agent      bridge   -> the serving agent's phase (retained)
 *
 * Everything the agent claims comes from `ad/results` and nothing else. The
 * replayer's ground truth arrives on a separate topic, is withheld until the
 * run ends or the viewer asks, and never colours a score — the detector and the
 * label are allowed to disagree on screen, because that is what a false alarm
 * looks like.
 */
import mqtt from 'mqtt';
import { env } from '$env/dynamic/public';

const WS_PORT = env.PUBLIC_MQTT_WS_PORT || '9008';
const WS_PATH = env.PUBLIC_MQTT_WS_PATH || '/mqtt';
const MQTT_MODE = env.PUBLIC_MQTT_MODE || 'direct';

/** Scores kept for the trajectory. A run is 960 samples ≈ 115 windows at
 *  step 8, so this holds several runs without a ring buffer mattering. */
const MAX_SCORES = 4000;
/** Samples kept per channel for the sparklines — one whole run and then some. */
const MAX_SAMPLES = 1200;
/**
 * Every topic this demo moves, in the order the data does.
 *
 * The app subscribes to all five, but only parses the three it renders from:
 * `sensors/tep` is the z-scored feed to the agent at ~10 msg/s and `tep/control`
 * is the app's own clicks coming back — both are COUNTED so the data-flow diagram
 * can show the hop is alive, and neither is parsed, because nothing on screen
 * reads them. Counting a message is free; parsing 33 key=value pairs ten times a
 * second to increment an integer is not.
 */
const TOPICS = ['sensors/tep', 'tep/raw', 'tep/status', 'tep/control', 'ad/results'];

/** Window the per-topic rates are averaged over. Five seconds, not one: a topic
 *  that publishes once per block is silent for most one-second ticks, and a rate
 *  that reads `idle` four ticks in five is reporting a dead pipeline. */
const RATE_WINDOW_MS = 5000;

/** Points kept on the embedding trail. One run at step 8 is ~115 windows, and
 *  the trail is the run's path through the detector's space — not a history. */
const MAX_TRAIL = 400;

/** A detection is N consecutive windows over threshold: the same `--sustain`
 *  rule Stage 7 scores with, so the dashboard and the README agree. */
const SUSTAIN = 3;

/** Which plant unit each channel belongs to, for the flowsheet and the grid.
 *  From the TEP process description (Downs & Vogel 1993, Table 1).
 *  @type {Record<string, {label: string, channels: string[]}>} */
export const UNITS = {
	feed: {
		label: 'Feeds',
		channels: ['xmeas_1', 'xmeas_2', 'xmeas_3', 'xmeas_4', 'xmv_1', 'xmv_2', 'xmv_3', 'xmv_4']
	},
	reactor: {
		label: 'Reactor',
		channels: ['xmeas_6', 'xmeas_7', 'xmeas_8', 'xmeas_9', 'xmeas_21', 'xmv_10']
	},
	separator: {
		label: 'Condenser / separator',
		channels: ['xmeas_11', 'xmeas_12', 'xmeas_13', 'xmeas_14', 'xmeas_22', 'xmv_7', 'xmv_11']
	},
	compressor: { label: 'Compressor', channels: ['xmeas_5', 'xmeas_20', 'xmv_5'] },
	stripper: {
		label: 'Stripper',
		channels: ['xmeas_15', 'xmeas_16', 'xmeas_17', 'xmeas_18', 'xmeas_19', 'xmv_8', 'xmv_9']
	},
	purge: { label: 'Purge', channels: ['xmeas_10', 'xmv_6'] }
};

/** Human labels and engineering units, so the grid reads as a plant rather than
 *  as a column index. Downs & Vogel's variable table.
 *  @type {Record<string, [label: string, unit: string]>} */
export const CHANNEL_META = {
	xmeas_1: ['A feed', 'kscmh'],
	xmeas_2: ['D feed', 'kg/h'],
	xmeas_3: ['E feed', 'kg/h'],
	xmeas_4: ['A+C feed', 'kscmh'],
	xmeas_5: ['Recycle flow', 'kscmh'],
	xmeas_6: ['Reactor feed', 'kscmh'],
	xmeas_7: ['Reactor pressure', 'kPa'],
	xmeas_8: ['Reactor level', '%'],
	xmeas_9: ['Reactor temp', '°C'],
	xmeas_10: ['Purge rate', 'kscmh'],
	xmeas_11: ['Separator temp', '°C'],
	xmeas_12: ['Separator level', '%'],
	xmeas_13: ['Separator pressure', 'kPa'],
	xmeas_14: ['Separator underflow', 'm³/h'],
	xmeas_15: ['Stripper level', '%'],
	xmeas_16: ['Stripper pressure', 'kPa'],
	xmeas_17: ['Stripper underflow', 'm³/h'],
	xmeas_18: ['Stripper temp', '°C'],
	xmeas_19: ['Stripper steam', 'kg/h'],
	xmeas_20: ['Compressor work', 'kW'],
	xmeas_21: ['Reactor cool. out', '°C'],
	xmeas_22: ['Separator cool. out', '°C'],
	xmv_1: ['D feed valve', '%'],
	xmv_2: ['E feed valve', '%'],
	xmv_3: ['A feed valve', '%'],
	xmv_4: ['A+C feed valve', '%'],
	xmv_5: ['Compressor recycle', '%'],
	xmv_6: ['Purge valve', '%'],
	xmv_7: ['Separator liquid', '%'],
	xmv_8: ['Stripper liquid', '%'],
	xmv_9: ['Stripper steam valve', '%'],
	xmv_10: ['Reactor coolant', '%'],
	xmv_11: ['Condenser coolant', '%']
};

function brokerUrl() {
	if (typeof location === 'undefined') return `ws://127.0.0.1:${WS_PORT}`;
	if (MQTT_MODE === 'proxy') {
		const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
		return `${scheme}://${location.host}${WS_PATH}`;
	}
	return `ws://${location.hostname}:${WS_PORT}`;
}

export function brokerLabel() {
	return MQTT_MODE === 'proxy'
		? `MQTT (mosquitto) · ws via proxy ${WS_PATH}`
		: `MQTT (mosquitto) · tcp :${env.PUBLIC_MQTT_TCP_PORT || '1890'} · ws :${WS_PORT}`;
}

function emptyState() {
	return {
		connected: false,
		/** @type {{sample:number, score:number, hours:number, invalid:boolean, over:boolean}[]} */
		scores: [],
		/** latest raw value per channel @type {Record<string, number>} */
		latest: {},
		/** @type {Record<string, number[]>} per-channel history for sparklines */
		history: {},
		/** @type {number[]} process hours, parallel to history */
		hours: [],
		/** The last retained tep/status message, verbatim. @type {any} */
		status: null,
		threshold: 1.215,
		crossings: 0,
		/** sample index where the first sustained crossing began, once it has
		 *  @type {number | null} */
		detectedAt: null,
		/** @type {number | null} */
		detectedHours: null,
		/** Detection EPISODES, not windows: one entry per run of consecutive
		 *  crossings, opened at the third and closed when one falls back under.
		 *  @type {{sample:number, hours:number, peak:number, windows:number,
		 *          closed:boolean, untilHours?:number}[]} */
		detections: [],
		/** The run's path through PCA 1-2 of the detector's own space.
		 *  @type {{x:number, y:number, score:number, over:boolean}[]} */
		trail: [],
		rate: 0,
		/** The bridge's last word on the serving agent: {phase, detail, agent, ...}.
		 *  @type {any} */
		agent: null,
		/** Windows the agent emitted, split by whether it scored them. An invalid
		 *  window is one the graph rejected before the encoder — a timestamp gap or
		 *  an off-cadence sample — and it is worth showing rather than hiding,
		 *  because a rising invalid count is the signal that the publisher is
		 *  outrunning the source's queue. */
		scored: 0,
		invalid: 0,
		/** Per-topic observed rate, msg/s, measured by THIS browser tab over the
		 *  tick's elapsed time — what the app sees, not what a process reports
		 *  about itself. A wedged process still calls itself running.
		 *  @type {Record<string, {rate: number}>} */
		flows: Object.fromEntries(TOPICS.map((t) => [t, { rate: 0 }]))
	};
}

class TepStore {
	state = $state(emptyState());
	/** @type {import('mqtt').MqttClient | null} */
	#client = null;
	/**
	 * Arrival times per topic, over a rolling window.
	 *
	 * NOT a per-tick counter. This demo's topics publish BELOW 1 Hz — the replayer
	 * sends one `tep/raw` per block of 32 samples, so roughly one every five
	 * seconds — and a counter reset every second reads zero on four ticks out of
	 * five. The strip showed `idle` for every topic while the agent was visibly
	 * scoring, which is worse than no strip: it says the pipeline is dead when it
	 * is working. The bearings demo never meets this because its `sensors/bearing`
	 * runs at ~11,000/s.
	 *
	 * @type {Record<string, number[]>}
	 */
	#arrivals = Object.fromEntries(TOPICS.map((t) => [t, []]));
	/** @type {number[]} */
	#windowTimes = [];

	connect() {
		if (this.#client) return;
		const url = brokerUrl();
		this.#client = mqtt.connect(url, {
			clientId: `tep-app-${Math.random().toString(16).slice(2)}`
		});
		this.#client.on('connect', () => {
			this.state.connected = true;
			this.#client?.subscribe([...TOPICS, 'ad/agent'], { qos: 0 });
			this.loadDetectorView();
		});
		this.#client.on('close', () => (this.state.connected = false));
		this.#client.on('error', () => (this.state.connected = false));
		this.#client.on('message', (topic, payload) => this.#onMessage(topic, payload));
		// Per-topic rates for the observability view, and the agent's throughput.
		this.#rateTimer = setInterval(() => {
			const now = Date.now();
			/** @type {Record<string, {rate: number}>} */
			const flows = {};
			for (const topic of TOPICS) {
				const times = this.#arrivals[topic].filter((ts) => now - ts < RATE_WINDOW_MS);
				this.#arrivals[topic] = times;
				flows[topic] = { rate: times.length / (RATE_WINDOW_MS / 1000) };
			}
			this.state.flows = flows;
			this.#windowTimes = this.#windowTimes.filter((t) => now - t < 5000);
			this.state.rate = this.#windowTimes.length / 5;
		}, 1000);
	}

	disconnect() {
		if (this.#rateTimer) clearInterval(this.#rateTimer);
		this.#client?.end(true);
		this.#client = null;
		this.state = emptyState();
	}

	/** @type {ReturnType<typeof setInterval> | null} */
	#rateTimer = null;

	/** The detector's projection, fetched once. `null` until it lands, which is
	 *  why every reader checks — the first windows can arrive before it does.
	 *  @type {{manifest: any, ref: Float32Array, mean: Float32Array,
	 *          pc0: Float32Array, pc1: Float32Array} | null} */
	#view = $state.raw(null);
	get view() {
		return this.#view;
	}

	/**
	 * Load PCA 1-2 of the fitted detector, exported by prep/export_detector_view.py.
	 *
	 * 306 KB of float32 in one fetch: the reference cloud, the mean subtracted
	 * before projecting, and the first two rows of the transform. Two rows, not
	 * eight — the plot draws two axes, and the other six would be 810 KB nobody
	 * renders.
	 */
	async loadDetectorView() {
		if (this.#view) return;
		try {
			const [manifest, buf] = await Promise.all([
				fetch('/detector-view.json').then((r) => r.json()),
				fetch('/detector-view.bin').then((r) => r.arrayBuffer())
			]);
			const take = (/** @type {string} */ name) => {
				const l = manifest.layout[name];
				const n = l.shape.reduce((/** @type {number} */ a, /** @type {number} */ b) => a * b, 1);
				return new Float32Array(buf, l.offset, n);
			};
			this.#view = {
				manifest,
				ref: take('ref'),
				mean: take('mean'),
				pc0: take('pc0'),
				pc1: take('pc1')
			};
		} catch {
			// The view is an extra, not the demo. Without it the scatter says so and
			// everything else — the score, the log, the plate — is unaffected.
			this.#view = null;
		}
	}

	/**
	 * Project one window's per-channel embeddings onto the detector's first two
	 * principal components.
	 *
	 * The agent publishes `embedding_<channel>` per channel, 768 numbers each. The
	 * detector's transform expects them concatenated in ITS OWN `data_columns`
	 * order, which the manifest carries — a JSON object's key order is not
	 * something to trust with a 25,344-long dot product.
	 *
	 * Only the two coordinates are kept. The 282 KB the window arrived as is
	 * discarded here rather than stored: a run is 225 windows, and holding them
	 * would be 63 MB of embeddings to draw 450 numbers.
	 *
	 * @param {any} msg
	 * @returns {{x:number, y:number} | null}
	 */
	#project(msg) {
		const v = this.#view;
		if (!v) return null;
		const { channels, embeddingDim, totalDim } = v.manifest;
		let x = 0;
		let y = 0;
		let o = 0;
		for (const c of channels) {
			const e = msg[`embedding_${c}`];
			if (!Array.isArray(e) || e.length !== embeddingDim) return null;
			for (let i = 0; i < embeddingDim; i++, o++) {
				const d = e[i] - v.mean[o];
				x += v.pc0[o] * d;
				y += v.pc1[o] * d;
			}
		}
		return o === totalDim ? { x, y } : null;
	}

	/** @param {string} topic @param {Uint8Array} payload */
	#onMessage(topic, payload) {
		if (topic in this.#arrivals) this.#arrivals[topic].push(Date.now());
		// Counted above, deliberately not parsed — see TOPICS.
		if (topic === 'sensors/tep' || topic === 'tep/control') return;
		let msg;
		try {
			msg = JSON.parse(payload.toString());
		} catch {
			return;
		}
		if (topic === 'ad/agent') {
			this.state.agent = msg;
			return;
		}
		if (topic === 'tep/status') {
			const prevRun = this.state.status?.runId;
			this.state.status = msg;
			if (Number.isFinite(msg.agent?.threshold)) this.state.threshold = msg.agent.threshold;
			// A new run (or a restart) clears everything the previous one built up.
			if (msg.runId !== prevRun || (msg.sample === 0 && this.state.scores.length)) this.#resetRun();
			return;
		}
		if (topic === 'tep/raw') {
			const channels = this.state.status?.channels ?? Object.keys(CHANNEL_META);
			for (const s of msg.samples ?? []) {
				this.state.hours.push((s.sample * (this.state.status?.sampleSeconds ?? 180)) / 3600);
				if (this.state.hours.length > MAX_SAMPLES) this.state.hours.shift();
				for (let i = 0; i < channels.length; i++) {
					const c = channels[i];
					const v = s.v[i];
					this.state.latest[c] = v;
					(this.state.history[c] ??= []).push(v);
					if (this.state.history[c].length > MAX_SAMPLES) this.state.history[c].shift();
				}
			}
			return;
		}
		// ad/results — the only thing the agent says.
		this.#windowTimes.push(Date.now());
		const invalid = msg.predicted_label === 'INVALID_STATE' || String(msg.invalid) === 'true';
		const score = Number(msg.anomaly_score);
		if (invalid || !Number.isFinite(score)) {
			this.state.invalid++;
			return;
		}
		this.state.scored++;
		// The window's own position in the run, from the timestamp the agent
		// echoes back. The replayer publishes the clock value sample 0 went out
		// at, so this is exact: a window that ends on sample N lands on N. Using
		// the replayer's cursor instead would stack a whole block of windows on
		// one x position, because the cursor only moves once per block.
		const base = this.state.status?.clockBase;
		const sampleSeconds = this.state.status?.sampleSeconds ?? 180;
		const finish = Number(msg.finish_timestamp);
		const sample =
			base && Number.isFinite(finish)
				? Math.round((finish - base) / (sampleSeconds * 1000))
				: (this.state.status?.sample ?? this.state.scores.length);
		const hours = (sample * sampleSeconds) / 3600;
		const over = score > this.state.threshold;
		this.state.scores.push({ sample, score, hours, invalid: false, over });

		// The same window's place in the detector's own space, when the agent is
		// publishing embeddings and the projection has loaded.
		const p = this.#project(msg);
		if (p) {
			this.state.trail.push({ x: p.x, y: p.y, score, over });
			if (this.state.trail.length > MAX_TRAIL) this.state.trail.shift();
		}
		if (this.state.scores.length > MAX_SCORES) this.state.scores.shift();
		if (over) this.state.crossings++;

		// A detection is SUSTAIN consecutive windows over the line — one spike is
		// noise at a 1% false-alarm threshold.
		const tail = this.state.scores.slice(-SUSTAIN);
		const sustained = tail.length === SUSTAIN && tail.every((p) => p.over);
		if (sustained) {
			if (this.state.detectedAt === null) {
				this.state.detectedAt = tail[0].sample;
				this.state.detectedHours = tail[0].hours;
			}
			// One entry per episode: a detection opens when three windows in a row
			// cross and stays open until one falls back under. Logging every window
			// of a developed fault would be 200 identical rows.
			const last = this.state.detections.at(-1);
			if (!last || last.closed) {
				this.state.detections.push({
					hours: tail[0].hours,
					sample: tail[0].sample,
					peak: score,
					windows: SUSTAIN,
					closed: false
				});
			} else {
				last.peak = Math.max(last.peak, score);
				last.windows++;
				last.untilHours = hours;
			}
		} else if (!over) {
			const last = this.state.detections.at(-1);
			if (last && !last.closed) last.closed = true;
		}
	}

	#resetRun() {
		this.state.scores = [];
		this.state.history = {};
		this.state.hours = [];
		this.state.latest = {};
		this.state.crossings = 0;
		this.state.scored = 0;
		this.state.invalid = 0;
		this.state.detectedAt = null;
		this.state.detectedHours = null;
		this.state.detections = [];
		this.state.trail = [];
	}

	/** @param {string} action @param {unknown} [value] */
	#publish(action, value) {
		this.#client?.publish('tep/control', JSON.stringify({ action, value }));
	}
	play() {
		this.#publish('play');
	}
	pause() {
		this.#publish('pause');
	}
	restart() {
		this.#publish('restart');
	}
	reveal() {
		this.#publish('reveal');
	}
	/** @param {number} id */
	select(id) {
		this.#publish('select', id);
	}
}

export const tep = new TepStore();

/** Deviation of a channel from the reference mean, in reference sigmas. The
 *  app computes it from the RAW value and the z-score stats the replayer
 *  publishes, so it is the same quantity the detector's input carries.
 *
 *  This is INPUT deviation, not model attribution: the AD agent scores a window
 *  as a whole and says nothing about which channel moved it. Labelled as such
 *  wherever it is shown.
 *  @param {any} state @param {string} channel @returns {number} */
export function deviation(state, channel) {
	const v = state.latest[channel];
	const z = state.status?.zscore;
	if (v === undefined || !z) return 0;
	const std = z.std[channel];
	return std ? (v - z.mean[channel]) / std : 0;
}
