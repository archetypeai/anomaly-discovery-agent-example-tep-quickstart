<script>
	/**
	 * What goes INTO the agent. Left side of the workbench.
	 *
	 * Named `Input` with the up-arrow icon, as all three references name theirs:
	 * one side is the thing being watched, the other the thing watching it.
	 *
	 * ONE BLOCK, and that is the references' shape rather than a reduction. The
	 * bearings demo's input panel is a vibration trace and its classical
	 * statistics; RED's is its sensor columns. In every case the input side is the
	 * RAW SIGNAL and the plate lives with the agent. The 33 tags are this demo's
	 * raw signal, and with the flowsheet moved across they get the whole panel —
	 * six unit groups at three columns instead of the cramped two the plate left
	 * room for.
	 */
	import Pane from '$lib/components/ui/patterns/pane/index.js';
	import CircleArrowUpIcon from '@lucide/svelte/icons/circle-arrow-up';
	import * as Tooltip from '@archetypeai/ds-ui-svelte-console/primitives/tooltip';
	import ChannelGrid from './channel-grid.svelte';
	import RunSelector from './run-selector.svelte';

	/** @type {{tep: any, class?: string}} */
	let { tep, class: className = '' } = $props();
	const s = $derived(tep.state);

	// IDENTITY, not explanation — the form the house style gives this line, whose
	// own example is `subtitle="North Sea · Equinor"`.
	const SUBTITLE = 'Tennessee Eastman · Rieth 2017 · 33 tags @ 3 min';
</script>

<Pane
	variant="panel"
	title="Input"
	icon={CircleArrowUpIcon}
	subtitle={SUBTITLE}
	class="min-h-0 {className}"
>
	{#snippet actions()}
		<RunSelector {tep} />
	{/snippet}

	<div class="flex min-h-0 flex-1 flex-col overflow-hidden">
		<Pane title="Process tags" class="min-h-0 flex-1">
			{#snippet titleAfter()}
				<Tooltip.Root>
					<Tooltip.Trigger variant="info" aria-label="About these tags" />
					<Tooltip.Content class="max-w-xs">
						All 33 channels the detector sees — 22 measurements and 11 manipulated variables,
						sampled every three minutes. Values are the plant's own engineering units; the figure on
						the right is the same reading as a distance from the reference mean, in reference
						sigmas. The agent is given the z-scored form, because that is what its detector was
						fitted on; the inverse is exact, so these are the same numbers.
					</Tooltip.Content>
				</Tooltip.Root>
			{/snippet}
			{#snippet actions()}
				<span class="font-mono text-xs text-muted-foreground tabular-nums">
					{s.status?.processHours?.toFixed(1) ?? '0.0'} h
				</span>
			{/snippet}
			<ChannelGrid {tep} class="min-h-0 flex-1 overflow-y-auto" />
		</Pane>
	</div>
</Pane>
