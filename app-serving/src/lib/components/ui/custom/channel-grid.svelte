<script>
	/**
	 * All 33 process variables, in engineering units, grouped by the unit they
	 * belong to.
	 *
	 * ONE LINE PER TAG, in TWO COLUMNS, and both halves of that are the same
	 * constraint: thirty-three tags have to fit a laptop without scrolling,
	 * because a monitor you have to scroll is a monitor that hides the reading you
	 * needed — and they have to USE that height rather than huddle at the top.
	 *
	 * The two-line form (name above value) cost 36px a tag and ran to ~620px,
	 * which overflowed a 14" screen. Three columns fixed the overflow and
	 * overshot: 410px of content in a 670px panel, with every name truncated to
	 * "Reactor fee…" to fit a third of the width. Two columns is the size the
	 * content actually is — 18 rows that fill the panel, and ~470px a cell, which
	 * is enough for the longest label ("Separator underflow") to print in full.
	 *
	 * The sparkline is deliberately unlabelled: at this size it carries SHAPE only
	 * — flat, drifting, oscillating — which is exactly what it is for beside a
	 * number that already gives the level. The figure on the right is the same
	 * reading as a distance from the reference mean, in reference sigmas, and it
	 * is what the flowsheet's tint is computed from, so the two cannot disagree.
	 */
	import { UNITS, CHANNEL_META, deviation } from '$lib/stores/tep.svelte.js';
	import { deviationTone } from '$lib/scores.js';

	/** @type {{tep: any, class?: string}} */
	let { tep, class: className = '' } = $props();
	const s = $derived(tep.state);

	/** @param {number[] | undefined} values */
	function spark(values) {
		if (!values || values.length < 2) return '';
		const lo = Math.min(...values);
		const hi = Math.max(...values);
		const range = hi - lo || 1;
		const n = values.length;
		return values
			.map(
				(v, i) =>
					`${i ? 'L' : 'M'}${((i / (n - 1)) * 72).toFixed(1)} ${(13 - ((v - lo) / range) * 12).toFixed(1)}`
			)
			.join(' ');
	}

	/** @param {number | undefined | null} v */
	function fmt(v) {
		if (v === undefined || v === null || !Number.isFinite(v)) return '—';
		const a = Math.abs(v);
		return a >= 1000 ? v.toFixed(0) : a >= 10 ? v.toFixed(1) : v.toFixed(2);
	}
</script>

<div class={className}>
	{#each Object.entries(UNITS) as [key, unit] (key)}
		<div class="mb-2">
			<!-- The unit caption is the Pane `block` voice — mono, uppercase, muted,
			     a step down from the panel caption above it. -->
			<div class="mb-0.5 flex items-baseline gap-2">
				<span class="font-mono text-[10px] tracking-wide text-muted-foreground uppercase"
					>{unit.label}</span
				>
				<span class="h-px flex-1 bg-separator"></span>
			</div>
			<div class="grid grid-cols-1 gap-x-8 md:grid-cols-2">
				{#each unit.channels as c (c)}
					{@const dev = deviation(s, c)}
					{@const meta = CHANNEL_META[c] ?? [c, '']}
					{@const tone = Math.abs(dev) >= 1 ? deviationTone(dev).color : ''}
					<div class="flex items-center gap-2 py-[3px]">
						<span class="min-w-0 flex-1 truncate text-xs leading-tight text-foreground">
							{meta[0]}
						</span>
						<span
							class="shrink-0 font-mono text-xs tabular-nums"
							style={tone ? `color: ${tone}` : ''}
						>
							{fmt(s.latest[c])}
						</span>
						<span class="w-10 shrink-0 text-[10px] text-muted-foreground">{meta[1]}</span>
						<svg viewBox="0 0 72 14" class="h-3.5 w-[72px] shrink-0" fill="none" aria-hidden="true">
							<path
								d={spark(s.history[c])}
								stroke={tone || 'var(--color-muted-foreground)'}
								stroke-width="1"
								stroke-linejoin="round"
							/>
						</svg>
						<span
							class="w-11 shrink-0 text-right font-mono text-[11px] tabular-nums"
							style={tone ? `color: ${tone}` : 'color: var(--color-muted-foreground)'}
						>
							{dev >= 0 ? '+' : ''}{dev.toFixed(1)}σ
						</span>
					</div>
				{/each}
			</div>
		</div>
	{/each}
</div>
