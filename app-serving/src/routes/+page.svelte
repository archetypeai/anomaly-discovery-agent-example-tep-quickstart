<script>
	/**
	 * AD TEP Monitor — the workbench.
	 *
	 * Two rows, as OSM, RED and the bearings demo have: identity, then the work.
	 * The workbench itself is two columns — what goes INTO the agent on the left,
	 * what comes OUT on the right, separated by a single hairline.
	 *
	 * app-serving/: the same workbench as app/, with the agent on the Archetype AI
	 * platform. mosquitto carries the data, the serving bridge (scripts/
	 * serving-bridge.js) sends each window to a serving agent of the detector
	 * fit/test.py promoted, and this page subscribes to the broker directly. The
	 * API key stays with the bridge; the page never sees it.
	 */
	import { onMount, onDestroy } from 'svelte';
	import Menubar from '$lib/components/ui/patterns/menubar/index.js';
	import { Badge } from '@archetypeai/ds-ui-svelte-console/primitives/badge';
	import { tep } from '$lib/stores/tep.svelte.js';
	import InputPanel from '$lib/components/ui/custom/input-panel.svelte';
	import OutputPanel from '$lib/components/ui/custom/output-panel.svelte';
	import SettingsDialog from '$lib/components/ui/custom/settings-dialog.svelte';

	// One dialog, reached from the gear beside Run Agent — the two things you do to
	// this demo, start it and configure it, sit together in the panel that owns the
	// run. Same move all three references settled on.
	let settingsOpen = $state(false);

	const s = $derived(tep.state);

	onMount(() => tep.connect());
	onDestroy(() => tep.disconnect());
</script>

<svelte:head><title>AD TEP Monitor — platform</title></svelte:head>

<!-- `w-full`, not `w-screen`. 100vw INCLUDES the scrollbar gutter, so on any
     document that has a scrollbar the root is wider than its own container and
     the page overflows sideways. It shows up when a dropdown opens: bits-ui
     locks body scroll and adds compensating padding, the horizontal overflow
     appears and disappears with it, and both scrollbars flicker. `h-dvh` rather
     than `h-screen` for the same class of reason on mobile, where the toolbar
     makes 100vh taller than the visible viewport. -->
<div class="grid h-dvh w-full grid-rows-[auto_1fr] overflow-hidden">
	<!-- The menubar carries identity and the theme switch. The live throughput and
	     the connection state ride in its children slot: they are properties of the
	     PAGE's link to the broker rather than of the run, which is why they are not
	     in the agent panel with the run's own controls. -->
	<Menubar>
		<span class="hidden font-mono text-[10px] text-muted-foreground lg:inline">
			{s.rate.toFixed(1)} win/s
		</span>
		<Badge
			variant="status"
			class={s.connected
				? 'border-score-normal text-score-normal'
				: 'border-score-anomaly text-score-anomaly'}
		>
			{s.connected ? 'platform · serving' : 'no broker'}
		</Badge>
	</Menubar>

	<!-- Workbench. The panels are full-bleed and carry no surface of their own, so
	     the grid's rule is the only thing between them. `grid-cols-2` is
	     repeat(2, minmax(0, 1fr)) — the 0 minimum matters, or a wide row inside a
	     panel pushes its track past half and shifts the rule off centre. -->
	<div class="grid min-h-0 grid-cols-1 lg:grid-cols-2">
		<InputPanel {tep} class="min-h-0 border-separator lg:border-r" />
		<OutputPanel
			{tep}
			bind:settingsOpen
			class="min-h-0 border-t border-separator lg:border-t-0"
		/>
	</div>
</div>

<SettingsDialog {tep} bind:open={settingsOpen} />
