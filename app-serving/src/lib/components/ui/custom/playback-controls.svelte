<script>
	/**
	 * One call to action instead of a transport bar, after OSM, RED and the
	 * bearings demo. It toggles rather than only starting, because a run you
	 * cannot stop is not a control; play and pause share a glyph pair so the two
	 * states read as one button. At the end of a run the glyph becomes rewind — a
	 * play triangle at 960/960 does not say "start over".
	 *
	 * Composed rather than `variant="runSession"`. The published DS ships that
	 * variant as a flat babyblue fill AND injects its own arrow-right glyph while
	 * discarding the caller's children, so the pill came out as a circle with an
	 * arrow in it. The vendoring references add a `runAgent` variant to their own
	 * button; a package consumer cannot, so the geometry and the surface are
	 * applied here. Measured on the platform: 44px tall, 16px type, 10px gap,
	 * asymmetric padding — pl-4 / pr-5, because the play glyph on the left already
	 * carries optical space the text on the right does not.
	 *
	 * Naming note: the button says "Agent" while it actually drives the REPLAYER —
	 * the agent is a separate process that scores whatever arrives. Kept anyway,
	 * because it is the ecosystem's word for "start the demo" and because from the
	 * outside they are one thing: no samples, no windows, no scores.
	 */
	import { cn } from '$lib/utils';
	import { Button } from '@archetypeai/ds-ui-svelte-console/primitives/button';
	import PlayIcon from '@lucide/svelte/icons/play';
	import PauseIcon from '@lucide/svelte/icons/pause';
	import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw';

	/** @type {{tep: any, class?: string}} */
	let { tep, class: className = '' } = $props();

	const status = $derived(tep.state.status);
	const playing = $derived(status?.playing === true);
	const atEnd = $derived(
		status?.totalSamples ? (status?.sample ?? 0) >= status.totalSamples - 1 : false
	);
	const label = $derived(atEnd ? 'Replay Agent' : playing ? 'Pause Agent' : 'Run Agent');
</script>

<div class={cn('flex items-center', className)}>
	<Button
		variant="ghost"
		class="run-agent-surface shadow-bottom-toolbar h-11 gap-2.5 rounded-full border border-transparent pr-5 pl-4 text-base font-normal text-atai-always-black hover:opacity-90"
		onclick={() => (atEnd ? tep.restart() : playing ? tep.pause() : tep.play())}
	>
		{#if atEnd}
			<RotateCcwIcon class="size-4.5" aria-hidden="true" />
		{:else if playing}
			<PauseIcon class="size-4.5" aria-hidden="true" />
		{:else}
			<PlayIcon class="size-4.5" aria-hidden="true" />
		{/if}
		{label}
	</Button>
</div>
