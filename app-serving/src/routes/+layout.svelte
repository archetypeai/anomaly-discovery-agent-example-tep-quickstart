<script>
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import { ModeWatcher } from 'mode-watcher';
	import * as Tooltip from '@archetypeai/ds-ui-svelte-console/primitives/tooltip';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<!-- Dark by default, as the OSM and RED demos are. `defaultMode` only sets the
     starting point — mode-watcher persists the viewer's own choice after that. -->
<ModeWatcher defaultMode="dark" />

<!-- Every `titleAfter` aside on a Pane is a bits-ui tooltip, and each one reads
     this context at CREATE time. Without the provider the page does not degrade
     to a tooltip-less render — it throws `Context "Tooltip.Provider" not found`
     during SSR and the route 500s. The bearings demo wraps its children exactly
     here for the same reason. -->
<Tooltip.Provider delayDuration={200}>
	{@render children?.()}
</Tooltip.Provider>
