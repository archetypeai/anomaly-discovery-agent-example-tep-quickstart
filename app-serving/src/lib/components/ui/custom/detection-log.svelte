<script>
	/**
	 * Detection EPISODES, newest first, not windows. A developed TEP fault crosses
	 * the threshold for every remaining window of the run, 200 identical rows. An
	 * episode opens when three consecutive windows cross, absorbs the rest, and
	 * closes when one falls back under, so a clean fault is one row and a flapping
	 * borderline run is several.
	 */
	import * as Table from '@archetypeai/ds-ui-svelte-console/primitives/table';
	import { EmptyState } from '@archetypeai/ds-ui-svelte-console/primitives/empty-state';
	import { cn } from '$lib/utils';

	/** @type {{tep: any, class?: string}} */
	let { tep, class: className = '' } = $props();

	const s = $derived(tep.state);
	const onsetHours = $derived(
		((s.status?.onsetSample ?? 160) * (s.status?.sampleSeconds ?? 180)) / 3600
	);
	const log = $derived([...s.detections].reverse());
</script>

<div class={cn('min-h-0 overflow-y-auto', className)}>
	{#if log.length}
		<Table.Root>
			<Table.Header>
				<Table.Row>
					<Table.Head>Opened</Table.Head>
					<Table.Head>After onset</Table.Head>
					<Table.Head>Peak</Table.Head>
					<Table.Head>Windows</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body typography="mono" class="text-xs">
				{#each log as d (d.sample)}
					<Table.Row>
						<Table.Cell class="text-score-anomaly">{d.hours.toFixed(1)} h</Table.Cell>
						<Table.Cell class="text-muted-foreground"
							>{d.hours >= onsetHours ? '+' : ''}{(d.hours - onsetHours).toFixed(1)} h</Table.Cell
						>
						<Table.Cell>{d.peak.toFixed(2)}</Table.Cell>
						<Table.Cell class="text-muted-foreground"
							>{d.windows}{d.closed ? '' : ' · open'}</Table.Cell
						>
					</Table.Row>
				{/each}
			</Table.Body>
		</Table.Root>
	{:else}
		<EmptyState variant="list">No window has crossed the threshold three times in a row.</EmptyState
		>
	{/if}
</div>
