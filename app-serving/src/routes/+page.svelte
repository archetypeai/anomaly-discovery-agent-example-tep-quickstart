<script>
	/**
	 * AD TEP Monitor: the workbench. What goes into the agent on the left (the
	 * plant's 33 process tags), what comes out on the right (its anomaly score).
	 *
	 * The agent runs on the Archetype AI platform: mosquitto carries the data, the
	 * serving bridge (scripts/serving-bridge.js) sends each window to a serving
	 * agent of the detector fit/test.py promoted, and this page subscribes to the
	 * broker. The API key stays with the bridge.
	 */
	import { onMount, onDestroy } from 'svelte';
	import Menubar from '@archetypeai/ds-ui-svelte-labs/primitives/menubar';
	import { Badge } from '@archetypeai/ds-ui-svelte-console/primitives/badge';
	import { tep } from '$lib/stores/tep.svelte.js';
	import InputPanel from '$lib/components/ui/custom/input-panel.svelte';
	import OutputPanel from '$lib/components/ui/custom/output-panel.svelte';
	import SettingsDialog from '$lib/components/ui/custom/settings-dialog.svelte';

	let settingsOpen = $state(false);
	const s = $derived(tep.state);
	const phase = $derived(!s.connected ? 'no broker' : (s.agent?.phase ?? 'no agent'));
	const tone = $derived(
		phase === 'running'
			? 'text-atai-good'
			: phase === 'no broker' || phase === 'stopped' || phase === 'no agent'
				? 'text-atai-critical'
				: 'text-atai-warning'
	);

	onMount(() => tep.connect());
	onDestroy(() => tep.disconnect());
</script>

<svelte:head><title>AD TEP Monitor · platform</title></svelte:head>

<div class="grid h-dvh w-full grid-rows-[auto_1fr] overflow-hidden bg-background">
	<Menubar>
		{#snippet partnerLogo()}
			<span class="text-xs text-muted-foreground">AD TEP Monitor</span>
		{/snippet}
		<span class="hidden font-mono text-xs text-muted-foreground lg:inline"
			>{s.rate.toFixed(1)} win/s</span
		>
		<Badge variant="status" class={tone}>
			{phase === 'running' ? 'platform · serving' : phase}
		</Badge>
	</Menubar>

	<div class="grid min-h-0 grid-cols-1 lg:grid-cols-2">
		<InputPanel {tep} class="min-h-0 border-border lg:border-r" />
		<OutputPanel {tep} bind:settingsOpen class="min-h-0 border-t border-border lg:border-t-0" />
	</div>
</div>

<SettingsDialog {tep} bind:open={settingsOpen} />
