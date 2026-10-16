<script>
	/**
	 * When the agent first said so, and how many times since.
	 *
	 * The bearings demo has no such table and is right not to: a crossing is not a
	 * discrete event, and its trajectory already draws every one of them as a point
	 * above the line. OSM has a classification log and RED a detection log, and
	 * both earn their place because a class per window IS an event.
	 *
	 * This one earns its place the RED way, by logging EPISODES rather than
	 * windows. A developed TEP fault crosses the threshold for every remaining
	 * window of the run — 200 identical rows. An episode opens when three
	 * consecutive windows cross, absorbs the rest, and closes when one falls back
	 * under, so a clean fault is one row and a flapping borderline run is several.
	 * That distinction is the whole reason to have the table.
	 */
	import Pane from '$lib/components/ui/patterns/pane/index.js';

	/** @type {{tep: any, class?: string, HEADING?: string}} */
	let { tep, class: className = '', HEADING = '' } = $props();

	const s = $derived(tep.state);
	const onsetHours = $derived(
		((s.status?.onsetSample ?? 160) * (s.status?.sampleSeconds ?? 180)) / 3600
	);
	/** Newest first — the last thing that happened is the thing being discussed. */
	const log = $derived([...s.detections].reverse());
</script>

<Pane title="Detections" captionClass={HEADING} class={className}>
	{#snippet actions()}
		<span class="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
			{log.length}
			{log.length === 1 ? 'episode' : 'episodes'}
		</span>
	{/snippet}

	{#if log.length}
		<div class="overflow-x-auto">
			<table class="w-full border-collapse text-left">
				<thead>
					<tr class="text-[10px] tracking-wide text-muted-foreground uppercase">
						<th class="pb-1 pr-4 font-mono font-normal">Opened</th>
						<th class="pb-1 pr-4 font-mono font-normal">After onset</th>
						<th class="pb-1 pr-4 font-mono font-normal">Peak</th>
						<th class="pb-1 font-mono font-normal">Windows</th>
					</tr>
				</thead>
				<tbody>
					{#each log as d (d.sample)}
						<tr>
							<td class="py-1 pr-4 font-mono text-sm tabular-nums text-score-anomaly">
								{d.hours.toFixed(1)} h
							</td>
							<td class="py-1 pr-4 font-mono text-sm tabular-nums text-muted-foreground">
								{d.hours >= onsetHours ? '+' : ''}{(d.hours - onsetHours).toFixed(1)} h
							</td>
							<td class="py-1 pr-4 font-mono text-sm tabular-nums">{d.peak.toFixed(2)}</td>
							<td class="py-1 font-mono text-sm tabular-nums text-muted-foreground">
								{d.windows}{d.closed ? '' : ' · open'}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<p class="text-sm text-muted-foreground">
			No window has crossed the threshold three times in a row.
		</p>
	{/if}
</Pane>
