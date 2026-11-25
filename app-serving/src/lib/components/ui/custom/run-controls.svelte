<script>
	/**
	 * Run / pause the replay, and the settings beside it, in the output panel's
	 * corner as the sibling monitors place them. The button drives the replayer:
	 * the agent scores whatever arrives.
	 */
	import { Button } from '@archetypeai/ds-ui-svelte-console/primitives/button';
	import PlayIcon from '@lucide/svelte/icons/play';
	import PauseIcon from '@lucide/svelte/icons/pause';
	import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw';
	import Settings2Icon from '@lucide/svelte/icons/settings-2';

	/** @type {{tep: any, settingsOpen?: boolean}} */
	let { tep, settingsOpen = $bindable(false) } = $props();
	const st = $derived(tep.state.status);
	const playing = $derived(st?.playing === true);
	const ended = $derived(st?.ended === true);
</script>

<div class="flex items-center gap-2">
	<Button
		disabled={!tep.state.connected || !st}
		onclick={() => (ended ? tep.restart() : playing ? tep.pause() : tep.play())}
	>
		{#if ended}<RotateCcwIcon aria-hidden="true" />Replay agent{:else if playing}<PauseIcon
				aria-hidden="true"
			/>Pause agent{:else}<PlayIcon aria-hidden="true" />Run agent{/if}
	</Button>
	<Button
		variant="outline"
		size="icon"
		aria-label="Settings"
		onclick={() => (settingsOpen = !settingsOpen)}
	>
		<Settings2Icon aria-hidden="true" />
	</Button>
</div>
