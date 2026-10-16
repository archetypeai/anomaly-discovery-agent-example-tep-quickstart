<script>
	/**
	 * Which simulation is playing. Sits in the input panel's caption row, where
	 * the bearings demo puts `SET 2 · BEARING 1` — the selector belongs to the
	 * panel whose input it names.
	 *
	 * IT SAYS "RUN 27", NEVER "IDV 5". A crew watching a live plant does not know
	 * whether a fault is present, and this demo's whole point depends on the
	 * viewer not knowing either: three of the twenty faults (IDV 3, 9 and 15) are
	 * undetectable by any published method, and picking one of those and watching
	 * nothing happen is the honest half of the story. If the selector named the
	 * fault, a false alarm and a true detection would look different before the
	 * detector said anything.
	 *
	 * The run ids are a seeded shuffle of the 84 simulations in the eval slices,
	 * so "Run 05" carries no hint of IDV 5, and the shuffle is deterministic so a
	 * demo can be rehearsed. The answer lives behind the reveal in Settings, and
	 * arrives on its own once the run ends — at which point it is a result rather
	 * than a spoiler.
	 */
	import * as Select from '@archetypeai/ds-ui-svelte-console/primitives/select';

	/** @type {{tep: any}} */
	let { tep } = $props();

	const s = $derived(tep.state);
	const available = $derived(s.status?.available ?? []);
	const value = $derived(String(s.status?.runId ?? ''));
	const label = $derived(s.status?.runId ? `RUN ${String(s.status.runId).padStart(2, '0')}` : '—');
</script>

<Select.Root
	type="single"
	{value}
	onValueChange={(/** @type {string} */ v) => v && tep.select(Number(v))}
	disabled={!s.connected || !available.length}
>
	<Select.Trigger class="h-[34px] font-mono text-[11px] tracking-wider uppercase">
		{label}
	</Select.Trigger>
	<Select.Content>
		{#each available as r (r.id)}
			<Select.Item value={String(r.id)} class="font-mono text-[11px] tracking-wider uppercase">
				RUN {String(r.id).padStart(2, '0')}
			</Select.Item>
		{/each}
	</Select.Content>
</Select.Root>
