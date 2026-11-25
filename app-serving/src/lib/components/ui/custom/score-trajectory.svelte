<script>
	/**
	 * The anomaly score over the run. Hand-rolled rather than a chart primitive,
	 * for the reason the bearing demo gives: only ONE of the four things on this
	 * plot is a series. The threshold is a decision line, fault onset is an
	 * event, and the detection point is a verdict — a chart library would render
	 * all four as data.
	 *
	 * THE Y AXIS IS LOGARITHMIC. LOF scores are a ratio of local densities: 1.0
	 * means "as ordinary as its neighbours", the decision sits at 1.218, and a
	 * developed fault reaches 60. On a linear axis the entire interesting range
	 * — 0.99 to 1.3 — collapses into the bottom two percent of the plot and the
	 * run reads as a flat line with a cliff, which is the opposite of what this
	 * demo is about: the score moves long before it is obvious.
	 *
	 * ONSET IS DRAWN, NOT THE LABEL. The marker at hour 8 is where the simulator
	 * introduced the disturbance — a property of the data, not of the detector's
	 * opinion. Everything else on the plot is the agent's.
	 */
	import { scoreTone } from '$lib/scores.js';

	/** @type {{tep: any, class?: string}} */
	let { tep, class: className = '' } = $props();

	// One import, and it is the same ramp the plate and the tag grid read.
	// Colour on this page is reserved for a claim; the trace itself is ink.

	const s = $derived(tep.state);

	// The viewBox TRACKS THE BOX. A fixed viewBox has to be scaled to fit, and
	// both ways of doing that are wrong for a chart: `meet` preserves the ratio
	// and leaves dead space (or overflows), `none` fills the slot but stretches
	// every axis label with it. Measuring instead makes one user unit one pixel,
	// so the chart fills whatever height the block has and the type stays round.
	let boxW = $state(640);
	let boxH = $state(200);
	const W = $derived(Math.max(boxW, 220));
	const H = $derived(Math.max(boxH, 120));
	// `b` covers the hour labels AND the band strip beneath them.
	const PAD = { l: 34, r: 8, t: 10, b: 34 };
	/** The classification strip: one slice per scored window, full run width. */
	const STRIP_H = 7;

	const totalHours = $derived(
		((s.status?.totalSamples ?? 960) * (s.status?.sampleSeconds ?? 180)) / 3600
	);
	const onsetHours = $derived(
		((s.status?.onsetSample ?? 160) * (s.status?.sampleSeconds ?? 180)) / 3600
	);

	// Fixed floor, ceiling from the run: the bottom of the useful range is a
	// property of LOF (nothing scores below ~0.9), the top is not.
	const yMin = 0.9;
	const yMax = $derived(Math.max(2, ...s.scores.map((/** @type {any} */ p) => p.score)) * 1.15);

	/** @param {number} h */
	const x = (h) => PAD.l + (h / Math.max(totalHours, 1)) * (W - PAD.l - PAD.r);
	/** @param {number} v */
	const y = (v) => {
		const lo = Math.log10(yMin);
		const hi = Math.log10(yMax);
		const t = (Math.log10(Math.max(v, yMin)) - lo) / (hi - lo);
		return H - PAD.b - t * (H - PAD.t - PAD.b);
	};

	/**
	 * The trace, split into runs of the same band.
	 *
	 * One path in one colour says "here is the score"; this says "here is the
	 * score AND what the detector made of it at every point", which is the same
	 * information the badge gives for the newest window, extended over the run.
	 * The approach is the part worth seeing — amber appearing among the teal
	 * before anything crosses is the demo's whole argument, and a single-colour
	 * line cannot show it.
	 *
	 * Consecutive points sharing a band become one path rather than one path per
	 * segment: a 225-window run is a handful of paths instead of 224.
	 */
	const segments = $derived.by(() => {
		/** @type {{d: string, color: string, last: string}[]} */
		const out = [];
		/** @type {{d: string, color: string, last: string} | null} */
		let cur = null;
		for (const p of s.scores) {
			const color = scoreTone(p.score, s.threshold).color;
			const pt = `${x(p.hours).toFixed(1)} ${y(p.score).toFixed(1)}`;
			if (!cur || cur.color !== color) {
				// Start the new run AT the previous point, so the colour changes on a
				// join rather than leaving a gap where the band does.
				const head = cur === null ? 'M' : `M${cur.last}L`;
				/** @type {{d: string, color: string, last: string}} */
				const next = { d: head + pt, color, last: pt };
				out.push(next);
				cur = next;
			} else {
				cur.d += `L${pt}`;
				cur.last = pt;
			}
		}
		return out;
	});

	/** One slice per scored window, in run order — the same bands as a timeline.
	 *  It answers "how much of this run was elevated" which the trace, drawn on a
	 *  log axis where a long mild excursion looks small, does not. */
	const strip = $derived(
		s.scores.map((/** @type {any} */ p) => ({
			x: x(p.hours),
			color: scoreTone(p.score, s.threshold).color
		}))
	);
	const sliceW = $derived(
		Math.max(
			(W - PAD.l - PAD.r) /
				Math.max(totalHours / (((s.status?.sampleSeconds ?? 180) * 4) / 3600), 1),
			1.2
		)
	);
	/** Decade ticks that fall inside the range, plus the threshold's own line. */
	const ticks = $derived([1, 2, 5, 10, 20, 50].filter((v) => v >= yMin && v <= yMax));
	const latest = $derived(s.scores.at(-1));
	const playing = $derived(s.status?.playing === true);
</script>

<div class="flex min-h-0 flex-col {className}" bind:clientWidth={boxW} bind:clientHeight={boxH}>
	<!-- Elastic for the same reason as the plate: at `h-auto` a 990px column gave
	     the chart 309px of height whether or not the block had it, which on a
	     laptop pushed the totals out of the panel and left the trace stranded in
	     dead space. `none` rather than `meet` — this is a chart, not a drawing,
	     and it should fill its slot rather than preserve a ratio. -->
	<svg
		viewBox="0 0 {W} {H}"
		class="min-h-0 w-full flex-1"
		role="img"
		aria-label="Anomaly score over the run"
	>
		<!-- reference band: at or below 1.0 the window is as ordinary as the
		     reference data the detector was fitted on -->
		<rect
			x={PAD.l}
			y={y(1.0)}
			width={W - PAD.l - PAD.r}
			height={Math.max(0, H - PAD.b - y(1.0))}
			fill="var(--color-muted)"
			opacity="0.5"
		/>

		{#each ticks as t (t)}
			<line
				x1={PAD.l}
				y1={y(t)}
				x2={W - PAD.r}
				y2={y(t)}
				stroke="var(--color-border)"
				stroke-width="1"
			/>
			<text x={PAD.l - 6} y={y(t) + 3} text-anchor="end" class="fill-muted-foreground text-2xs"
				>{t}</text
			>
		{/each}

		<!-- the decision line -->
		<line
			x1={PAD.l}
			y1={y(s.threshold)}
			x2={W - PAD.r}
			y2={y(s.threshold)}
			stroke="var(--score-threshold)"
			stroke-width="1"
			stroke-dasharray="4 3"
		/>
		<text
			x={W - PAD.r}
			y={y(s.threshold) - 4}
			text-anchor="end"
			class="fill-score-threshold text-2xs"
		>
			threshold {s.threshold.toFixed(3)}
		</text>

		<!-- fault onset: the simulator's, not the detector's -->
		<line
			x1={x(onsetHours)}
			y1={PAD.t}
			x2={x(onsetHours)}
			y2={H - PAD.b}
			stroke="var(--color-muted-foreground)"
			stroke-width="1"
			stroke-dasharray="2 3"
		/>
		<text x={x(onsetHours) + 3} y={PAD.t + 8} class="fill-muted-foreground text-2xs">onset</text>

		{#each segments as seg, i (i)}
			<path
				d={seg.d}
				fill="none"
				stroke={seg.color}
				stroke-width="1.5"
				stroke-linejoin="round"
				stroke-linecap="round"
			/>
		{/each}

		<!-- The live value, at the head of the trace. Hidden when the run is not
		     moving: the chip says "this is the score right now", and a paused or
		     finished run has no now — on the paused frame it also sits over the
		     final climb, which is the part you stopped to look at. -->
		{#if latest && playing}
			{@const cx = x(latest.hours)}
			{@const cy = y(latest.score)}
			{@const flip = cx > W - 96}
			<g>
				<rect
					x={flip ? cx - 58 : cx + 6}
					y={cy - 9}
					width="52"
					height="18"
					rx="3"
					fill={scoreTone(latest.score, s.threshold).color}
				/>
				<text
					x={flip ? cx - 32 : cx + 32}
					y={cy + 4}
					text-anchor="middle"
					class="fill-atai-always-black font-mono text-2xs tabular-nums"
				>
					{latest.score.toFixed(3)}
				</text>
			</g>
		{/if}

		<!-- the verdict -->
		{#if s.detectedHours !== null}
			<line
				x1={x(s.detectedHours)}
				y1={PAD.t}
				x2={x(s.detectedHours)}
				y2={H - PAD.b}
				stroke="var(--score-anomaly)"
				stroke-width="1"
			/>
			<circle
				cx={x(s.detectedHours)}
				cy={y(
					s.scores.find((/** @type {any} */ p) => p.sample >= s.detectedAt)?.score ?? s.threshold
				)}
				r="3"
				fill="var(--score-anomaly)"
				stroke="none"
			/>
		{/if}

		<!-- The classification strip, under the axis: every window this run has
		     scored, in order, coloured by its band. The trace is on a log axis
		     where a long mild excursion occupies very little height; this is the
		     same run measured in TIME instead, so a stretch of amber reads as a
		     stretch. -->
		<rect
			x={PAD.l}
			y={H - PAD.b + 18}
			width={W - PAD.l - PAD.r}
			height={STRIP_H}
			rx="1"
			fill="var(--color-muted)"
		/>
		{#each strip as sl, i (i)}
			<rect x={sl.x} y={H - PAD.b + 18} width={sliceW} height={STRIP_H} fill={sl.color} />
		{/each}

		<!-- x axis: process hours, because that is the axis every number in the
		     repo's evaluation is quoted on -->
		<line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} stroke="var(--color-border)" />
		{#each [0, 12, 24, 36, 48].filter((/** @type {number} */ h) => h <= totalHours) as h (h)}
			<text x={x(h)} y={H - PAD.b + 12} text-anchor="middle" class="fill-muted-foreground text-2xs"
				>{h}h</text
			>
		{/each}
	</svg>
</div>
