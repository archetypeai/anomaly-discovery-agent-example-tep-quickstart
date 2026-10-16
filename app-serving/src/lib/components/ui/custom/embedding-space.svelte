<script>
	/**
	 * Where this run sits inside the detector's own space.
	 *
	 * app-serving/: the field is the 2,280 reference windows the PROMOTED detector
	 * was fitted on (40 fault-free simulations, window 48, step 8), recomputed by
	 * fit/library_embeddings.py: the library run through the promoted blueprint in
	 * batch with output_embeddings on, then PCA 1-2 of those embeddings, whitened.
	 * The detector itself is a registry artifact with no download route, so this
	 * is a recomputed view of the same windows, not read from the detector. The
	 * trail is the current run's path through the same two axes, from the
	 * embeddings the served agent returns, newest point filled.
	 *
	 * A DENSITY, NOT 1,120 DOTS. The reference set is the model's definition of
	 * normal, and what matters about it is its SHAPE — where normal is thick and
	 * where it thins out. As a scatter that shape is carried by dot crowding,
	 * which reads as noise and competes with the live trail drawn over it. Filled
	 * bands at low opacity put the cloud behind the run, which is where it belongs:
	 * the trail is the subject, the cloud is the ground it is measured against.
	 * The bearings demo made the same move for the same reason.
	 *
	 * WHAT THIS PICTURE CANNOT TELL YOU, and it matters more here than in the
	 * bearings demo. The detector scores in 140 dimensions — 8 PCA components plus
	 * 132 z-scored channel features — and this plot draws two of them. A window
	 * can sit inside the field and still score high on an axis that is not drawn.
	 * Measured on this very run: a window scoring 13.66 had a nearest reference
	 * neighbour 0.44 away in these coordinates, well inside the cloud's spread.
	 * So the trail leaving the field is evidence, and the trail staying in it is
	 * NOT evidence of nothing. The score is the detector's answer; this is a
	 * cross-section.
	 */
	// @ts-expect-error - d3-contour ships no types and @types/d3-contour does not exist
	import { contourDensity } from 'd3-contour';
	import { scoreTone } from '$lib/scores.js';

	/** @type {{tep: any, class?: string}} */
	let { tep, class: className = '' } = $props();

	const s = $derived(tep.state);
	const view = $derived(tep.view);
	const trail = $derived(s.trail);

	// The viewBox TRACKS THE BOX, one user unit to one pixel. A fixed viewBox has
	// to be scaled to fit, and in a wide short slot `meet` fits by HEIGHT — the
	// drawing came out 560 units wide in a 990px column with the rest as margin,
	// which is why it looked postage-stamp sized.
	let boxW = $state(560);
	let boxH = $state(380);
	const W = $derived(Math.max(boxW, 240));
	const H = $derived(Math.max(boxH, 200));
	const PAD = 22;

	// Fixed to the reference cloud's own extent, not to the data on screen.
	// Autoscaling would re-frame the plot every time the run leaves the cloud,
	// which is the one event the plot exists to show — the cloud would shrink and
	// the excursion would look the same size as a normal window's wander.
	const bounds = $derived.by(() => {
		if (!view) return { lo: -3, hi: 3 };
		let m = 0;
		for (let i = 0; i < view.ref.length; i++) m = Math.max(m, Math.abs(view.ref[i]));
		// 1.15, not 1.35: the extra margin was framing empty space. The run still
		// has room to leave the cloud, which is the one thing that must stay
		// visible when it happens.
		return { lo: -m * 1.15, hi: m * 1.15 };
	});

	// EQUAL SCALE ON BOTH AXES, with the leftover width as margin. Stretching PC1
	// to fill a wide box and PC2 to fill a short one would make the same distance
	// look different depending on its direction — on a plot whose whole subject is
	// how far the run has moved from the cloud, that is a lying picture.
	const unit = $derived(
		Math.min(W - 2 * PAD, H - 2 * PAD) / (bounds.hi - bounds.lo)
	);
	const sx = (/** @type {number} */ v) => W / 2 + v * unit;
	const sy = (/** @type {number} */ v) => H / 2 - v * unit;

	/**
	 * d3-contour returns GeoJSON MultiPolygons, not path data — assigning one
	 * straight to `d` renders the string "[object Object]" and the browser reports
	 * `Expected moveto path command`. d3-geo's geoPath would do this, but it is a
	 * dependency for one loop: a contour ring is already a list of [x, y] in
	 * SCREEN space, so it is an M, a run of Ls and a Z.
	 *
	 * `evenodd` on the fill, because a band with a hole in it (a dip in the middle
	 * of the density) arrives as two rings wound the same way, and nonzero would
	 * fill the hole in.
	 *
	 * @param {any} mp
	 */
	function ringsToPath(mp) {
		let d = '';
		for (const polygon of mp.coordinates ?? []) {
			for (const ring of polygon) {
				d += 'M' + ring.map((/** @type {number[]} */ pt) => `${pt[0].toFixed(1)} ${pt[1].toFixed(1)}`).join('L') + 'Z';
			}
		}
		return d;
	}

	/** The reference set as a density field. Computed once — the library does not
	 *  change while the page is open, and a KDE over 1,120 points on every window
	 *  would be the most expensive thing on the screen. */
	const bands = $derived.by(() => {
		if (!view) return [];
		/** @type {[number, number][]} */
		const pts = [];
		for (let i = 0; i < view.ref.length; i += 2) pts.push([view.ref[i], view.ref[i + 1]]);
		const density = contourDensity()
			.x((/** @type {any} */ d) => sx(d[0]))
			.y((/** @type {any} */ d) => sy(d[1]))
			.size([W, H])
			.bandwidth(Math.max(10, unit * 0.14))
			.thresholds(7);
		const cs = density(pts);
		// Low to high, so the faint outer band paints first and the dense core last.
		return cs.map((/** @type {any} */ c, /** @type {number} */ i) => ({
			d: ringsToPath(c),
			o: 0.06 + (i / Math.max(cs.length - 1, 1)) * 0.22
		}));
	});

	const path = $derived(
		trail.length > 1
			? trail
					.map(
						(/** @type {any} */ p, /** @type {number} */ i) =>
							`${i ? 'L' : 'M'}${sx(p.x).toFixed(1)} ${sy(p.y).toFixed(1)}`
					)
					.join(' ')
			: ''
	);
	const head = $derived(trail.at(-1));

	/** What the picture is made of, for the margin beside it. */
	const readouts = $derived(
		view
			? [
					{ label: 'Fitted normal', value: view.manifest.nReference.toLocaleString() },
					{ label: 'This run', value: String(trail.length) },
					{ label: 'Drawn of', value: `2 / ${view.manifest.nPcaComponents + 132}` }
				]
			: []
	);

	/** The field's label, pinned just above its centre — the reference set names
	 *  itself where it is, rather than in a legend the eye has to travel to. */
	const labelY = $derived(sy(0) - Math.min(unit * 1.6, H / 2 - PAD - 14));
</script>

<div class="flex min-h-0 flex-col {className}">
	{#if !view}
		<p class="py-8 text-center text-sm text-muted-foreground">
			The reference library's projection has not loaded. Run
			<span class="font-mono">python3 fit/library_embeddings.py</span> to write it.
		</p>
	{:else}
		<!-- ELASTIC, not `h-auto`. At h-auto the viewBox scales to the panel's full
		     width and comes out taller than the block, which pushed the readouts
		     below the fold. `flex-1` with `min-h-0` lets it take exactly the slot it
		     is given, which is how the references size their plates. -->
		<!-- The measured box is the SVG'S OWN slot. Binding to the wrapper included
		     the legend row below, so the viewBox was 48px taller than the element it
		     described and every coordinate was off by that ratio. -->
		<div class="min-h-0 w-full flex-1" bind:clientWidth={boxW} bind:clientHeight={boxH}>
			<svg
				viewBox="0 0 {W} {H}"
				class="h-full w-full"
				fill="none"
				role="img"
				aria-label="The run's path through PCA 1-2 of the detector's space"
			>
			<defs>
				<!-- The ground the field is drawn on. A grid of points rather than
				     rules: it gives the plot a floor and a sense of scale without
				     drawing lines that compete with the trail. -->
				<pattern id="tep-emb-grid" width="18" height="18" patternUnits="userSpaceOnUse">
					<circle cx="1" cy="1" r="0.75" fill="var(--color-muted-foreground)" opacity="0.35" />
				</pattern>
			</defs>
			<rect x="0" y="0" width={W} height={H} fill="url(#tep-emb-grid)" />

			<!-- The axes cross at the field's centre, which is the origin: these
			     components are whitened, so the reference set is zero-mean and
			     unit-variance by construction. -->
			<line x1={sx(0)} y1={PAD} x2={sx(0)} y2={H - PAD} stroke="var(--color-border)" />
			<line x1={PAD} y1={sy(0)} x2={W - PAD} y2={sy(0)} stroke="var(--color-border)" />

			{#each bands as b, i (i)}
				<path d={b.d} fill="var(--score-normal)" fill-rule="evenodd" opacity={b.o} stroke="none" />
			{/each}

			{#if path}
				<path
					d={path}
					stroke="var(--plate-ink)"
					stroke-width="1"
					stroke-linejoin="round"
					opacity="0.9"
				/>
			{/if}

			<!-- Recent windows as marks on the path, coloured by their own band, so
			     the run's approach is legible and not just its endpoint. -->
			{#each trail.slice(-60) as p, i (i)}
				<circle
					cx={sx(p.x)}
					cy={sy(p.y)}
					r="1.6"
					fill={scoreTone(p.score, s.threshold).color}
					opacity="0.7"
				/>
			{/each}

			{#if head}
				<circle
					cx={sx(head.x)}
					cy={sy(head.y)}
					r="4.5"
					fill={scoreTone(head.score, s.threshold).color}
					stroke="var(--color-background)"
					stroke-width="1.5"
				/>
			{/if}

			<!-- The field names itself, where it is. -->
			<g>
				<rect
					x={sx(0) - 66}
					y={labelY - 9}
					width="132"
					height="18"
					rx="3"
					fill="var(--color-background)"
					stroke="var(--score-normal)"
					opacity="0.95"
				/>
				<text
					x={sx(0)}
					y={labelY + 4}
					text-anchor="middle"
					class="fill-score-normal font-mono text-[9px] tracking-wider uppercase"
				>
					{view.manifest.nReference.toLocaleString()} fitted normal
				</text>
			</g>

				<text
					x={sx(bounds.hi) - 4}
					y={sy(0) - 6}
					text-anchor="end"
					class="fill-muted-foreground text-[9px]">PC 1</text
				>
				<text x={sx(0) + 6} y={sy(bounds.hi) + 10} class="fill-muted-foreground text-[9px]">PC 2</text>

				<!-- The readouts live in the LEFT MARGIN, not in a row under the plot.
				     Equal-scale axes make the drawing square, so in this panel's 2:1
				     slot roughly a third of the width can never be drawn on — and a
				     row underneath spent height the square actually wanted. -->
				<g transform="translate(6, {H / 2 - 44})">
					{#each readouts as r, i (r.label)}
						<text y={i * 32} class="fill-muted-foreground font-mono text-[9px] tracking-wide uppercase"
							>{r.label}</text
						>
						<text y={i * 32 + 15} class="fill-foreground font-mono text-[13px]">{r.value}</text>
					{/each}
				</g>
			</svg>
		</div>
		{#if !trail.length}
			<!-- The field is real whether or not a run is being projected onto it, so
			     the view still earns its place — but it must say which half is
			     missing rather than present an empty cloud as a result. The live
			     trail needs `output_embeddings: true` on the blueprint; see
			     app/README.md, "The embedding space". -->
			<p class="shrink-0 pt-1 text-center text-[11px] text-muted-foreground">
				No window projected yet — the trail needs <span class="font-mono">output_embeddings</span> on
				the agent.
			</p>
		{/if}
	{/if}
</div>
