<script>
	/**
	 * What you do to the demo rather than watch: the pace, where the replay is,
	 * what the serving agent is doing, what is moving over MQTT, and the reveal.
	 * Which simulation is replayed is chosen in the Input panel.
	 *
	 * The reveal lives here because it is a deliberate act: beside the verdict it
	 * sat exactly where the eye lands when you are trying not to know yet.
	 */
	import * as Dialog from '@archetypeai/ds-ui-svelte-console/primitives/dialog';
	import * as Tabs from '@archetypeai/ds-ui-svelte-console/primitives/tabs';
	import { Button } from '@archetypeai/ds-ui-svelte-console/primitives/button';
	import { Badge } from '@archetypeai/ds-ui-svelte-console/primitives/badge';
	import { Label } from '@archetypeai/ds-ui-svelte-console/primitives/label';
	import { Progress } from '@archetypeai/ds-ui-svelte-console/primitives/progress';
	import EyeIcon from '@lucide/svelte/icons/eye';
	import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw';
	import ObservabilityDiagram from './observability-diagram.svelte';

	/** The topics the strip lists, in the order the data moves. */
	const TOPICS = ['sensors/tep', 'tep/raw', 'tep/status', 'tep/control', 'ad/results'];

	/** @type {{tep: any, open?: boolean}} */
	let { tep, open = $bindable(false) } = $props();

	const s = $derived(tep.state);
	const st = $derived(s.status);
	const a = $derived(s.agent);
	const cfg = $derived(st?.agent ?? {});
	const step = $derived(Number(cfg.stepSize ?? 4));
	const hours = (/** @type {number} */ samples) => (samples * (st?.sampleSeconds ?? 180)) / 3600;

	/** IDV 3, 9 and 15 are the ones the literature, and this repo's own evaluation
	 *  at 0.9–1.2% detection, reports as undetectable: naming them in the reveal is
	 *  the difference between "the detector failed" and "this fault is not visible
	 *  in these measurements". */
	const HARD = ['idv_03', 'idv_09', 'idv_15'];
	const PROSE = 'max-w-prose text-xs text-muted-foreground';
</script>

<Dialog.Root bind:open>
	<!-- sm:max-w-4xl: the data-flow plate is drawn 900 units wide and reads at about 1:1. -->
	<Dialog.Content class="sm:max-w-4xl">
		<Dialog.Header>
			<Dialog.Title>Settings</Dialog.Title>
			<Dialog.Description>
				The replay's pace and what the serving agent is doing. Nothing here changes the detector.
			</Dialog.Description>
		</Dialog.Header>
		<Dialog.Body class="space-y-5">
			<section class="space-y-2">
				<Label variant="sectionHeader">Agent</Label>
				<div class="flex flex-wrap items-center gap-x-6 gap-y-1 font-mono text-xs">
					<Badge
						variant="status"
						class={a?.phase === 'running' ? 'text-atai-good' : 'text-atai-warning'}
						>{a?.phase ?? 'no bridge'}</Badge
					>
					<span><span class="text-muted-foreground">agent</span> {a?.agent ?? '—'}</span>
					<span><span class="text-muted-foreground">bundle</span> {a?.bundle ?? '—'}</span>
					<span
						><span class="text-muted-foreground">median query</span>
						{a?.medianLatencyMs != null ? `${a.medianLatencyMs} ms` : '—'}</span
					>
				</div>
				<p class="font-mono text-xs text-muted-foreground">{a?.blueprint ?? ''}</p>
				{#if a?.detail}<p class={PROSE}>{a.detail}</p>{/if}
			</section>

			<section class="space-y-2">
				<Label variant="sectionHeader">Pace</Label>
				<Tabs.Root
					value={String(step)}
					onValueChange={(/** @type {string} */ v) => tep.setStep(Number(v))}
				>
					<Tabs.List variant="segmented">
						<Tabs.Trigger value="4">Every 4th sample</Tabs.Trigger>
						<Tabs.Trigger value="1">Every sample (exact)</Tabs.Trigger>
					</Tabs.List>
				</Tabs.Root>
				<p class={PROSE}>
					Paced by the platform at {s.rate.toFixed(1)} windows/s: the replayer waits for each block's
					windows. Every 4th sample plays a run in a few minutes, but a detection (3 windows over the
					line) then spans 36 min of process time and its time is approximate. Every sample is how Stage
					6 delivered: alarms match its output to the sample, at ~15 min a run.
				</p>
			</section>

			<section class="space-y-2">
				<Label variant="sectionHeader">Position</Label>
				<div class="flex items-center gap-4">
					<span class="shrink-0 font-mono text-sm tabular-nums">
						{(st?.processHours ?? 0).toFixed(1)} h
						<span class="text-muted-foreground"
							>/ {hours(st?.totalSamples ?? 960).toFixed(0)} h · onset at {hours(
								st?.onsetSample ?? 160
							).toFixed(0)} h</span
						>
					</span>
					<Progress
						value={st?.totalSamples ? (100 * (st.sample ?? 0)) / st.totalSamples : 0}
						size="sm"
						class="flex-1"
						aria-label="Position in the run"
					/>
					<Button variant="outline" size="sm" disabled={!s.connected} onclick={() => tep.restart()}>
						<RotateCcwIcon aria-hidden="true" />Restart the run
					</Button>
				</div>
				<p class="font-mono text-xs text-muted-foreground tabular-nums">
					sample {(st?.sample ?? 0).toLocaleString()} of {(
						st?.totalSamples ?? 960
					).toLocaleString()}{st?.ended ? ' · end of run' : ''}
				</p>
			</section>

			<section class="space-y-2">
				<Label variant="sectionHeader">This run</Label>
				<dl class="flex flex-wrap gap-x-6 gap-y-1 font-mono text-sm">
					<div class="flex gap-1.5">
						<dt class="text-muted-foreground">scored</dt>
						<dd>{s.scored.toLocaleString()}</dd>
					</div>
					<div class="flex gap-1.5">
						<dt class="text-muted-foreground">invalid</dt>
						<dd class={s.invalid ? 'text-atai-warning' : ''}>{s.invalid}</dd>
					</div>
					<div class="flex gap-1.5">
						<dt class="text-muted-foreground">threshold</dt>
						<dd>{s.threshold.toFixed(3)}</dd>
					</div>
					<div class="flex gap-1.5">
						<dt class="text-muted-foreground">fitted at step</dt>
						<dd>{cfg.fittedStep ?? '—'}</dd>
					</div>
					{#if s.detections.length > 1}
						<!-- Only when the run flapped: one episode is the ordinary case. -->
						<div class="flex gap-1.5">
							<dt class="text-muted-foreground">episodes</dt>
							<dd class="text-score-elevated">{s.detections.length}</dd>
						</div>
					{/if}
				</dl>
				<p class={PROSE}>
					An invalid window is one the agent rejected, or a query the platform didn't answer (the
					serving bridge's log says which). It is not a sign that the detector is wrong.
				</p>
			</section>

			<section class="space-y-2">
				<Label variant="sectionHeader">Ground truth</Label>
				{#if st?.revealed && st?.truth}
					<p class="text-sm">
						This run is
						<span class="font-mono"
							>{st.truth.faultId === 'idv_00'
								? 'fault-free'
								: st.truth.faultId.replace('idv_', 'IDV ')}</span
						>{#if HARD.includes(st.truth.faultId)}<span class="text-muted-foreground"
								>: undetectable by any published method, and caught here 0.9–1.2% of the time.</span
							>{/if}
					</p>
				{:else}
					<p class={PROSE}>
						Withheld until you ask, or until the run ends. A crew watching a live plant does not
						know whether a fault is present, and three of the twenty faults are undetectable, so
						watching one do nothing is the honest half of this demo.
					</p>
					<Button variant="outline" size="sm" disabled={!s.connected} onclick={() => tep.reveal()}>
						<EyeIcon aria-hidden="true" />Reveal what this run is
					</Button>
				{/if}
			</section>

			<section class="space-y-2">
				<Label variant="sectionHeader">Live data flow</Label>
				<div class="grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-xs sm:grid-cols-5">
					{#each TOPICS as t (t)}
						{@const r = s.flows[t]?.rate ?? 0}
						<span class={r > 0 ? 'text-atai-good' : 'text-muted-foreground'}
							>{t} {r > 0 ? `${r < 10 ? r.toFixed(1) : Math.round(r)}/s` : 'idle'}</span
						>
					{/each}
				</div>
				<ObservabilityDiagram {tep} />
			</section>
		</Dialog.Body>
	</Dialog.Content>
</Dialog.Root>
