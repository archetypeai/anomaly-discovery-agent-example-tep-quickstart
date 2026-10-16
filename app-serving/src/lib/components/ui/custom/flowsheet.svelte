<script>
	/**
	 * The Tennessee Eastman plant, drawn as the process flow diagram the 1993
	 * paper's Figure 1 uses: four gaseous feeds into a cooled reactor, then a
	 * condenser, a vapour-liquid separator with a recycle compressor, and a
	 * steam-stripped product column. Purge leaves the separator overhead.
	 *
	 * WHY A FLOWSHEET AND NOT A BAR CHART OF 33 NUMBERS. The channels are not a
	 * flat list — they are five units connected in a loop, and a fault in the
	 * reactor coolant shows up in the separator because the recycle carries it
	 * there. A plant operator reads the unit, not the tag. Each unit is tinted by
	 * the largest deviation among ITS OWN channels, so the drawing answers "where
	 * is the plant unlike its reference" at a glance, and the channel grid below
	 * answers "which tag".
	 *
	 * WHAT THE TINT IS, AND IS NOT. It is the input's distance from the reference
	 * mean in reference sigmas — computed by this app from the raw value and the
	 * z-score statistics, the same quantity the detector's input carries. It is
	 * NOT the agent's attribution: the AD agent scores a 64-sample window as a
	 * whole and says nothing about which channel moved it. A unit can glow while
	 * the score stays flat, and the score can rise with nothing glowing — the
	 * detector works on the joint shape of all 33 channels, which is exactly the
	 * thing no single-channel view can show. That disagreement is worth watching
	 * rather than hiding.
	 *
	 * PLATE RULES, from the OSM, RED and bearing plates: one nib at one pixel,
	 * stroke set once on the <svg> and inherited; no fills except the tint; the
	 * drawing carries no text a label could carry instead.
	 */
	import { UNITS, deviation } from '$lib/stores/tep.svelte.js';
	import { deviationTone } from '$lib/scores.js';

	/** @type {{tep: any, class?: string}} */
	let { tep, class: className = '' } = $props();
	const s = $derived(tep.state);

	/** Largest |z| among a unit's channels — the unit's distance from normal. */
	/** @param {string} key */
	function unitDeviation(key) {
		const chans = UNITS[key]?.channels ?? [];
		let max = 0;
		for (const c of chans) max = Math.max(max, Math.abs(deviation(s, c)));
		return max;
	}

	/** Tint: the pane's own surface under 1 sigma, then the score ramp. Deliberately
	 *  coarse — a continuous ramp reads as decoration; three steps read as states,
	 *  and they are the SAME three steps the score badge and the tag grid use, so
	 *  the plate and the numbers beside it cannot disagree. */
	/** @param {string} key */
	function tint(key) {
		const d = unitDeviation(key);
		if (d < 1) return 'var(--color-muted)';
		return `color-mix(in oklch, ${deviationTone(d).color} 26%, transparent)`;
	}
	/** @param {string} key */
	function edge(key) {
		const d = unitDeviation(key);
		return d < 1 ? 'var(--plate-ink)' : deviationTone(d).color;
	}

	const units = ['feed', 'reactor', 'separator', 'compressor', 'stripper', 'purge'];
	const readouts = $derived(
		units.map((u) => ({ key: u, label: UNITS[u].label, dev: unitDeviation(u) }))
	);
</script>

<div class="flex min-h-0 flex-col {className}">
	<!-- ELASTIC, not `h-auto`. At h-auto the plate sizes from WIDTH alone — a
	     990px column makes it 318px tall whatever the column has to spare — so on
	     a laptop it overflowed the panel and the Stripper was clipped. `flex-1`
	     with `min-h-0` and `meet` lets it take the slot it is given and scale into
	     it, which is how the references size their plates. -->
	<svg
		viewBox="0 20 760 244"
		preserveAspectRatio="xMidYMid meet"
		class="min-h-0 w-full flex-1"
		stroke="var(--plate-ink)"
		stroke-width="1"
		fill="none"
		vector-effect="non-scaling-stroke"
		aria-label="Tennessee Eastman process flow diagram"
	>
		<!-- ── feeds ───────────────────────────────────────────────────────── -->
		<g>
			<rect x="14" y="96" width="74" height="92" rx="3" fill={tint('feed')} stroke={edge('feed')} />
			{#each ['A', 'D', 'E', 'A+C'] as f, i (f)}
				<line x1="88" y1={110 + i * 22} x2="130" y2={110 + i * 22} />
				<polygon points="130,{106 + i * 22} 138,{110 + i * 22} 130,{114 + i * 22}" fill="var(--plate-ink)" stroke="none" />
				<text x="26" y={114 + i * 22} class="fill-muted-foreground text-[9px]" stroke="none">{f} feed</text>
			{/each}
		</g>

		<!-- ── reactor ─────────────────────────────────────────────────────── -->
		<g>
			<rect x="140" y="80" width="86" height="124" rx="8" fill={tint('reactor')} stroke={edge('reactor')} />
			<!-- cooling coil: the reactor is exothermic and its coolant valve is the
			     manipulated variable three of the twenty faults act on -->
			{#each [0, 1, 2, 3] as i (i)}
				<path d="M150 {104 + i * 26} q 16 -12 33 0 q 16 12 33 0" stroke="var(--plate-detail)" />
			{/each}
			<text x="183" y="220" text-anchor="middle" class="fill-plate-ink text-[10px]" stroke="none">Reactor</text>
			<!-- coolant in/out -->
			<line x1="140" y1="212" x2="118" y2="212" stroke="var(--plate-detail)" />
			<text x="114" y="215" text-anchor="end" class="fill-muted-foreground text-[8px]" stroke="none">CW</text>
		</g>

		<!-- reactor → condenser -->
		<line x1="226" y1="120" x2="286" y2="120" />
		<polygon points="286,116 294,120 286,124" fill="var(--plate-ink)" stroke="none" />

		<!-- ── condenser + separator ───────────────────────────────────────── -->
		<g>
			<!-- condenser: heat-exchanger shell -->
			<rect x="296" y="100" width="58" height="40" rx="3" fill={tint('separator')} stroke={edge('separator')} />
			<line x1="296" y1="120" x2="354" y2="120" stroke="var(--plate-detail)" />
			<text x="325" y="152" text-anchor="middle" class="fill-plate-ink text-[10px]" stroke="none">Condenser</text>

			<line x1="354" y1="120" x2="392" y2="120" />
			<polygon points="392,116 400,120 392,124" fill="var(--plate-ink)" stroke="none" />

			<!-- separator: vertical drum with a liquid level -->
			<rect x="400" y="86" width="64" height="118" rx="26" fill={tint('separator')} stroke={edge('separator')} />
			<path d="M400 168 q 32 10 64 0" stroke="var(--plate-detail)" />
			<text x="432" y="220" text-anchor="middle" class="fill-plate-ink text-[10px]" stroke="none">Separator</text>
		</g>

		<!-- ── purge, up from the separator overhead ───────────────────────── -->
		<g>
			<line x1="432" y1="86" x2="432" y2="46" />
			<line x1="432" y1="46" x2="560" y2="46" />
			<polygon points="560,42 568,46 560,50" fill="var(--plate-ink)" stroke="none" />
			<rect x="568" y="32" width="54" height="28" rx="3" fill={tint('purge')} stroke={edge('purge')} />
			<text x="595" y="50" text-anchor="middle" class="fill-plate-ink text-[9px]" stroke="none">Purge</text>
		</g>

		<!-- ── recycle compressor, back to the reactor ─────────────────────── -->
		<g>
			<line x1="416" y1="86" x2="416" y2="70" />
			<line x1="416" y1="70" x2="330" y2="70" />
			<circle cx="312" cy="70" r="18" fill={tint('compressor')} stroke={edge('compressor')} />
			<path d="M303 70 l 18 -8 v 16 z" fill="var(--plate-detail)" stroke="none" />
			<line x1="294" y1="70" x2="183" y2="70" />
			<line x1="183" y1="70" x2="183" y2="80" />
			<polygon points="179,72 183,80 187,72" fill="var(--plate-ink)" stroke="none" />
			<!-- ABOVE the impeller, not below it. Below put the label at y=102, which
			     is inside the condenser shell (y=100-140) two units to the right, so
			     the label printed straight through the box. Above, the only thing at
			     this x is clear space — the purge run at y=46 starts at x=432. -->
			<text x="312" y="44" text-anchor="middle" class="fill-plate-ink text-[9px]" stroke="none">Compressor</text>
		</g>

		<!-- ── stripper ────────────────────────────────────────────────────── -->
		<g>
			<line x1="464" y1="188" x2="524" y2="188" />
			<polygon points="524,184 532,188 524,192" fill="var(--plate-ink)" stroke="none" />
			<rect x="532" y="96" width="62" height="130" rx="6" fill={tint('stripper')} stroke={edge('stripper')} />
			<!-- trays -->
			{#each [0, 1, 2, 3, 4] as i (i)}
				<line x1="540" y1={120 + i * 20} x2="586" y2={120 + i * 20} stroke="var(--plate-detail)" />
			{/each}
			<text x="563" y="242" text-anchor="middle" class="fill-plate-ink text-[10px]" stroke="none">Stripper</text>
			<!-- steam in -->
			<line x1="532" y1="214" x2="506" y2="214" stroke="var(--plate-detail)" />
			<text x="502" y="217" text-anchor="end" class="fill-muted-foreground text-[8px]" stroke="none">steam</text>
			<!-- Stripper overhead joins the recycle riser at x=416, where the
			     separator's own overhead comes up — one T-junction, then a single
			     line left through the compressor to the reactor. It used to stop at
			     440, twenty-four units short of the riser, which drew a pipe ending
			     in mid-air. -->
			<line x1="563" y1="96" x2="563" y2="70" stroke="var(--plate-detail)" />
			<line x1="563" y1="70" x2="416" y2="70" stroke="var(--plate-detail)" />
		</g>

		<!-- ── product ─────────────────────────────────────────────────────── -->
		<g>
			<line x1="594" y1="214" x2="672" y2="214" />
			<polygon points="672,210 680,214 672,218" fill="var(--plate-ink)" stroke="none" />
			<text x="700" y="217" text-anchor="middle" class="fill-muted-foreground text-[9px]" stroke="none">G, H</text>
		</g>
	</svg>

	<!-- Per-unit deviation, in reference sigmas. The drawing says where; this
	     says how far. Both are input deviation, not the agent's attribution. -->
	<div class="mt-2 grid shrink-0 grid-cols-3 gap-x-4 gap-y-1 sm:grid-cols-6">
		{#each readouts as r (r.key)}
			<div class="flex flex-col gap-0.5">
				<span class="truncate text-[10px] text-muted-foreground">{r.label}</span>
				<span class="font-mono text-xs" style="color: {r.dev >= 1 ? deviationTone(r.dev).color : 'var(--color-foreground)'}">
					{r.dev.toFixed(1)}σ
				</span>
			</div>
		{/each}
	</div>
</div>
