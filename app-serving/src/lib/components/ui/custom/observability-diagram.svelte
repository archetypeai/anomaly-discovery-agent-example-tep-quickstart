<script>
	/**
	 * Observability — the app/README architecture diagram, drawn live.
	 *
	 * Same idea as the OSM, RED and bearings demos': every box is a process on
	 * this machine and every arrow is an MQTT topic, with the rate the browser is
	 * actually observing on it. Green means data moved in the last second. If
	 * something is wrong, the diagram tells you WHICH hop is dead rather than
	 * leaving you to guess between a stopped replayer, a crashed agent and a
	 * broker that never bound.
	 *
	 * Rates are measured by this browser tab over its own tick, so they are what
	 * the app sees rather than what a process reports about itself — a wedged
	 * process still calls itself running.
	 *
	 * Bare content: no overlay, no close button, no heading. The dialog that holds
	 * it owns the chrome.
	 */
	import { brokerLabel } from '$lib/stores/tep.svelte.js';

	/** @type {{tep: any}} */
	let { tep } = $props();

	const s = $derived(tep.state);
	const f = $derived(s.flows);
	const cfg = $derived(s.status?.agent ?? {});

	// Liveness from stream freshness rather than from any status field.
	const replayerAlive = $derived(f['tep/status']?.rate > 0 || f['tep/raw']?.rate > 0);
	const agentAlive = $derived(f['ad/results']?.rate > 0);

	// No hex fallback. These are DS tokens, always defined once the theme
	// stylesheet is loaded, and a literal second value is a colour named in a
	// component — the one thing the token layer exists to prevent.
	const GOOD = 'var(--score-normal)';
	const MUTED = 'var(--color-muted-foreground)';
	const dot = (/** @type {boolean} */ on) => (on ? GOOD : MUTED);
	const rateOf = (/** @type {string} */ t) => f[t]?.rate ?? 0;
	// Whole messages per second is the resolution anyone reads these at.
	// One decimal below 10. The replayer publishes one block every few seconds, so
	// rounding turned a live edge into "0 blk/s" — indistinguishable from a dead one.
	const fmt = (/** @type {number} */ r, /** @type {string} */ unit = 'msg/s') =>
		r > 0 ? `${r < 10 ? r.toFixed(1) : Math.round(r).toLocaleString()} ${unit}` : 'idle';
</script>

<svg viewBox="0 0 900 560" class="w-full" font-family="var(--font-mono, ui-monospace, monospace)">
	<defs>
		<marker
			id="tep-arr"
			viewBox="0 0 8 8"
			refX="7"
			refY="4"
			markerWidth="6"
			markerHeight="6"
			orient="auto"
		>
			<path d="M0,0 L8,4 L0,8 z" fill="var(--color-muted-foreground)" />
		</marker>
	</defs>

	{#snippet box(
		/** @type {number} */ x,
		/** @type {number} */ y,
		/** @type {number} */ w,
		/** @type {number} */ h,
		/** @type {string} */ title,
		/** @type {boolean} */ alive
	)}
		<rect
			{x}
			{y}
			width={w}
			height={h}
			rx="2"
			fill="var(--color-background)"
			stroke="var(--color-border)"
		/>
		<circle cx={x + 14} cy={y + 16} r="4" fill={dot(alive)} />
		<text x={x + 26} y={y + 20} font-size="13" fill="var(--color-foreground)" letter-spacing="1"
			>{title}</text
		>
	{/snippet}

	{#snippet flow(
		/** @type {string} */ path,
		/** @type {string} */ label,
		/** @type {number} */ rate,
		/** @type {number} */ lx,
		/** @type {number} */ ly,
		/** @type {string} */ unit = 'msg/s'
	)}
		<path
			d={path}
			fill="none"
			stroke="var(--color-border)"
			stroke-width="1.5"
			marker-end="url(#tep-arr)"
		/>
		{#if rate > 0}
			<!-- A mark travelling the edge. The direction of flow is the one thing a
			     static arrowhead states weakly and motion states instantly.
			     BEFORE the labels, not after: the dot travels the path, the labels sit
			     beside it, and painted last the dot rode over the type — "1.6 win/s"
			     rendered as "●6 win/s" every time it passed. -->
			<circle r="3.5" fill={GOOD}>
				<animateMotion dur="1.4s" repeatCount="indefinite" {path} />
			</circle>
		{/if}
		<text x={lx} y={ly} font-size="11" fill={rate > 0 ? GOOD : MUTED}>{label}</text>
		<text x={lx} y={ly + 13} font-size="10" fill={rate > 0 ? GOOD : MUTED}>{fmt(rate, unit)}</text>
	{/snippet}

	<!-- Label widths are hand-fitted to their boxes: mono advances ~6px at
	     font-size 10 and ~8.8px at 13 with letter-spacing 1. Lengthening a string
	     without widening its box will overflow it. -->

	<!-- source -->
	{@render box(268, 10, 366, 52, 'data/prepared/tep_eval_slice_*.csv', replayerAlive)}
	<text x="294" y="44" font-size="10" fill={MUTED}>
		{s.status
			? `run ${s.status.runId} · ${(s.status.totalSamples ?? 960).toLocaleString()} samples · 3-min cadence`
			: '84 simulations · 3-min cadence'}
	</text>

	<!-- replayer -->
	{@render box(40, 130, 280, 110, 'replayer (node)', replayerAlive)}
	<text x="66" y="172" font-size="10" fill={MUTED}>z-scored to agent, raw units to app</text>
	<text x="66" y="188" font-size="10" fill={MUTED}>one simulation at a time</text>
	<text x="66" y="204" font-size="10" fill={MUTED}>self-paced: waits for each block</text>
	<text x="66" y="220" font-size="10" fill={MUTED}>resets the bridge between runs</text>

	<!-- agent -->
	{@render box(600, 130, 290, 118, 'Anomaly Discovery Agent', agentAlive)}
	<text x="626" y="168" font-size="10" fill={MUTED}>agent serving · platform (Dev)</text>
	<text x="626" y="184" font-size="10" fill={MUTED}>
		window {cfg.windowSize ?? 48} · a query every {cfg.stepSize ?? 4} samples
	</text>
	<text x="626" y="200" font-size="10" fill={MUTED}>
		tee → {cfg.encoder ?? 'Omega 1.5'} ‖ ChannelFeatures
	</text>
	<!-- Two lines, not one. "fuse → LOF k=5 L2 · PCA 8 · 1,120 reference windows"
	     is ~50 characters; at font-size 10 mono that is ~300px from x=626, which
	     runs past the box's right edge at 890 and printed outside it. The note at
	     the top of this file says exactly this would happen — a string lengthened
	     without widening its box — and the detector string got longer when it
	     started being read from the fit record instead of typed. -->
	<text x="626" y="216" font-size="10" fill={MUTED}>fuse → {cfg.detector ?? 'kNN'}</text>
	<text x="626" y="232" font-size="10" fill={MUTED}>
		via the serving bridge · key stays local
	</text>

	<!-- broker. The CONFIGURED endpoint, not a default: on a host with custom
	     ports a hardcoded label is a diagram that lies. -->
	{@render box(200, 330, 500, 50, brokerLabel(), s.connected)}

	<!-- app -->
	{@render box(150, 470, 600, 60, 'web app (this browser tab, mqtt.js over ws)', s.connected)}
	<text x="176" y="515" font-size="10" fill={MUTED}>
		flowsheet · 33 tags · score trajectory · embedding space · detections
	</text>

	<!-- csv -> replayer -->
	{@render flow(
		'M 308,62 C 240,84 190,100 182,128',
		'reads + paces',
		replayerAlive ? rateOf('tep/raw') : 0,
		196,
		88,
		'blk/s'
	)}

	<!-- replayer -> broker. Three topics leave the replayer and one comes back, so
	     each arrow gets its own lane: sensors/tep hugs the left and enters the
	     broker's left edge, tep/raw takes the middle, and tep/control returns
	     between them. Labels sit beside their own arrow rather than in the shared
	     corridor, where two of them would land on the same pixels. -->
	{@render flow(
		'M 60,240 C 60,300 130,346 198,346',
		'sensors/tep',
		rateOf('sensors/tep'),
		66,
		262,
		'rows/s'
	)}
	{@render flow(
		'M 215,240 C 235,275 290,302 330,328',
		'tep/raw',
		rateOf('tep/raw'),
		270,
		262,
		'blk/s'
	)}
	<text x="270" y="290" font-size="10" fill={rateOf('tep/status') > 0 ? GOOD : MUTED}>
		tep/status {fmt(rateOf('tep/status'))}
	</text>

	<!-- broker -> agent -->
	{@render flow(
		'M 600,328 C 645,292 675,262 700,242',
		'sensors/tep',
		rateOf('sensors/tep'),
		612,
		300,
		'rows/s'
	)}

	<!-- agent -> broker -->
	{@render flow(
		'M 790,240 C 775,288 706,312 668,330',
		'ad/results',
		rateOf('ad/results'),
		726,
		288,
		'win/s'
	)}
	<text x="726" y="314" font-size="10" fill={rateOf('ad/results') > 0 ? GOOD : MUTED}>
		+ 33 × 768-d embedding
	</text>

	<!-- broker -> app -->
	{@render flow(
		'M 490,380 C 500,410 510,440 520,468',
		'tep/raw · ad/results',
		rateOf('ad/results') + rateOf('tep/raw'),
		500,
		420
	)}
	<text x="500" y="446" font-size="10" fill={rateOf('tep/status') > 0 ? GOOD : MUTED}>
		tep/status → transport · run
	</text>

	<!-- app -> broker -> replayer -->
	{@render flow(
		'M 380,468 C 380,440 385,410 395,382',
		'tep/control',
		rateOf('tep/control'),
		250,
		420
	)}
	{@render flow(
		'M 278,328 C 225,310 190,282 185,242',
		'tep/control',
		rateOf('tep/control'),
		100,
		300
	)}
</svg>
