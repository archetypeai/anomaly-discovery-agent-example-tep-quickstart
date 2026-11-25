<script>
	/**
	 * What the agent produces. Right side of the workbench.
	 *
	 * Named for the AGENT, mirroring the left panel being named for its input:
	 * one side is the thing being watched, the other the thing watching it.
	 *
	 *   Anomaly score  the live call, the trace, and the run's totals under it
	 *   Detections     one row per episode, not per window
	 *
	 * Everything here comes from `ad/results` and nothing else.
	 *
	 * Run / pause and the Settings gear sit in this panel's lower-right corner, as
	 * in the sibling monitors: a run control belongs with the run.
	 */
	import Pane from '$lib/components/ui/patterns/pane/index.js';
	import { Badge } from '@archetypeai/ds-ui-svelte-console/primitives/badge';
	import { Separator } from '@archetypeai/ds-ui-svelte-console/primitives/separator';
	import * as Tooltip from '@archetypeai/ds-ui-svelte-console/primitives/tooltip';
	import * as Tabs from '@archetypeai/ds-ui-svelte-console/primitives/tabs';
	import CircleArrowDownIcon from '@lucide/svelte/icons/circle-arrow-down';
	import ScatterChartIcon from '@lucide/svelte/icons/chart-scatter';
	import FactoryIcon from '@lucide/svelte/icons/factory';
	import ListIcon from '@lucide/svelte/icons/list';
	import { scoreTone, SCORE_META } from '$lib/scores.js';
	import ScoreTrajectory from './score-trajectory.svelte';
	import EmbeddingSpace from './embedding-space.svelte';
	import Flowsheet from './flowsheet.svelte';
	import DetectionLog from './detection-log.svelte';
	import RunControls from './run-controls.svelte';

	/** @type {{tep: any, settingsOpen?: boolean, class?: string}} */
	let { tep, settingsOpen = $bindable(false), class: className = '' } = $props();

	const s = $derived(tep.state);
	const latest = $derived(s.scores.at(-1));
	const playing = $derived(s.status?.playing === true);

	// The PLATE on load, as all three references open on their drawing: it says
	// what is being watched before anyone has to read an axis. The map and the log
	// are the deliberate second looks.
	let view = $state('plant');
	// The split follows the VIEW, because the two drawings want opposite shapes.
	// The flowsheet is a 3:1 plate and reads fine in a wide short slot, so the
	// score block takes the larger share — it spends most of its height on chrome
	// where the plate is all drawing. The embedding space is a scatter with equal
	// scale on both axes: in that same slot the cloud was capped at 61% of the
	// height while 80% of the width sat empty, because a square cannot use width
	// it has no height to match.
	const bodyShare = $derived(view === 'embedding' ? 'flex-[1.25]' : 'flex-1');
	const scoreShare = $derived(view === 'embedding' ? 'flex-1' : 'flex-[1.25]');

	// IDENTITY, not explanation: model · where it runs, in the shape of
	// field · operator. Here the agent runs on the platform, through agent serving.
	const SUBTITLE = 'Omega 1.5 + kNN · Archetype AI platform, agent serving';

	// The agent's call on the newest window, in words — OSM's `PREDICTION STATE`
	// pair and RED's `Detection State`, applied to a continuous output. Three
	// bands, not the detector's two: `normal` and `anomaly` are its own call
	// either side of the threshold, while `elevated` is this app's approach band.
	// Naming it is the point of the badge; a bare number cannot say "on its way".
	const verdict = $derived(latest ? scoreTone(latest.score, s.threshold) : null);

	const onsetHours = $derived(
		((s.status?.onsetSample ?? 160) * (s.status?.sampleSeconds ?? 180)) / 3600
	);
	const fmtH = (/** @type {number|null} */ h) => (h == null ? '—' : `${h.toFixed(1)} h`);

	// What the RUN has accumulated — a count and two durations, none of which the
	// chart can state. The live value is printed at the head of the trace, where
	// it cannot be mistaken for a total.
	// The teaching aside for whichever view is showing. Both were standing
	// paragraphs under the thing they explained; a tooltip is where an aside
	// belongs, and the affordance never changes width as the view changes.
	const aside = $derived(
		view === 'log'
			? 'Detection episodes, newest first. An episode opens when three consecutive windows cross the threshold (the rule Stage 7 scores with), takes in every crossing after it, and closes when a window falls back under. A developed fault is one row; a borderline run that flaps is several.'
			: view === 'plant'
				? "Six units connected in a loop, each tinted by the largest deviation among its own tags, in reference sigmas. That is INPUT deviation, not the agent's attribution: the detector scores a 48-sample window across all 33 channels jointly and says nothing about which one moved it, so a unit can glow while the score stays flat, and the score can rise with nothing glowing. It is drawn on this side because a fault in the reactor coolant shows up in the separator — the recycle carries it there — and that is a property of the plant the score alone cannot show."
				: "The cloud is the 2,280 reference windows the promoted detector was fitted on (the 40 fault-free library runs at window 48, step 8), recomputed by running them through the promoted blueprint in batch with embeddings on, and drawn in PCA 1 and 2 of their Omega embeddings, whitened. The trail is this run through the same two axes, from the embeddings the served agent returns. The detector's own PCA is fitted on these embeddings too, but it is a registry artifact that can't be read, so this is a recomputed view, not the detector's. And the detector scores in more dimensions than two (PCA 16 plus the per-channel features): the trail leaving the cloud is evidence; the trail staying in it is not evidence of nothing."
	);

	const totals = $derived([
		{ label: 'Crossings', value: String(s.crossings), color: null },
		{
			label: 'Detected',
			value: fmtH(s.detectedHours),
			color: s.detectedAt !== null ? SCORE_META.anomaly.color : null
		},
		{
			label: 'After onset',
			value: s.detectedHours == null ? '—' : fmtH(Math.max(0, s.detectedHours - onsetHours)),
			color: s.detectedAt !== null ? SCORE_META.anomaly.color : null
		}
	]);
</script>

<Tabs.Root bind:value={view} class="flex min-h-0 flex-col {className}">
	<Pane
		variant="panel"
		title="AD Agent"
		icon={CircleArrowDownIcon}
		subtitle={SUBTITLE}
		class="relative min-h-0 flex-1"
	>
		{#snippet titleAfter()}
			<Tooltip.Root>
				<Tooltip.Trigger variant="info" aria-label="About this view" />
				<Tooltip.Content class="max-w-xs">{aside}</Tooltip.Content>
			</Tooltip.Root>
		{/snippet}
		{#snippet actions()}
			<Tabs.List variant="segmented">
				<Tabs.Trigger value="plant" variant="icon" title="Plant" aria-label="Plant"
					><FactoryIcon /></Tabs.Trigger
				>
				<Tabs.Trigger
					value="embedding"
					variant="icon"
					title="Embedding space"
					aria-label="Embedding space"><ScatterChartIcon /></Tabs.Trigger
				>
				<Tabs.Trigger value="log" variant="icon" title="Detections" aria-label="Detections"
					><ListIcon /></Tabs.Trigger
				>
			</Tabs.List>
		{/snippet}

		<div class="flex min-h-0 flex-1 flex-col overflow-hidden">
			<Tabs.Content value="plant" class="flex min-h-0 flex-col p-4 {bodyShare}">
				<Flowsheet {tep} class="flex-1" />
			</Tabs.Content>
			<Tabs.Content value="embedding" class="flex min-h-0 flex-col p-4 {bodyShare}">
				<EmbeddingSpace {tep} class="flex-1" />
			</Tabs.Content>
			<Tabs.Content value="log" class="flex min-h-0 flex-col p-4 {bodyShare}">
				<DetectionLog {tep} class="flex-1" />
			</Tabs.Content>

			<Separator />

			<!-- Fixed: the live reading must not be what gives when the body grows. -->
			<Pane title="Anomaly score" class="min-h-0 {scoreShare}">
				{#snippet titleAfter()}
					<Tooltip.Root>
						<Tooltip.Trigger variant="info" aria-label="How to read the anomaly score" />
						<Tooltip.Content class="max-w-sm">
							<p>
								1.0 means "as ordinary as its neighbours". Log-scaled, because the decision happens
								just above 1.0 while a developed fault reaches 60. The trace is coloured by band and
								the strip under the axis is the same run measured in time. The dashed marker is
								where the simulator introduced the disturbance: a property of the data, not of the
								detector's opinion.
							</p>
							<p class="mt-2">
								<span class="text-foreground">Crossings</span> counts windows over the threshold,
								not separate alarms — on a developed fault nearly every window after onset crosses.
								<span class="text-foreground">Detected</span> is when the first
								<em>sustained</em> detection began: three consecutive windows over the line, the
								same rule Stages 7 and 8 score with.
								<span class="text-foreground">After onset</span> is that moment minus the fault's own
								start, in plant time. On a fault-free run Detected stays "—" and any crossings are false
								alarms.
							</p>
						</Tooltip.Content>
					</Tooltip.Root>
				{/snippet}
				{#snippet actions()}
					<!-- transition-none: the DS badge animates its colour, which on a badge that
					     changes every window leaves it permanently mid-interpolation. -->
					{#if verdict}
						<Badge variant="status" class="transition-none" style="color: {verdict.color}">
							{s.detectedHours !== null ? 'Anomaly' : verdict.label}
						</Badge>
					{:else}
						<Badge variant="status" class="text-muted-foreground">
							{s.agent?.phase === 'running' || !s.agent ? 'Awaiting' : s.agent.phase}
						</Badge>
					{/if}
				{/snippet}

				<ScoreTrajectory {tep} class="min-h-0 flex-1" />

				{#if !s.scores.length}
					<!-- Three different waits; saying the wrong one made a run switch look broken. -->
					<p class="shrink-0 text-center text-sm text-muted-foreground">
						{#if s.status?.loading}
							Switching run: resetting the agent
						{:else if s.agent && s.agent.phase !== 'running'}
							The serving agent is {s.agent.phase}{s.agent.detail ? ` (${s.agent.detail})` : ''}
						{:else if playing}
							Awaiting the agent's first window
						{:else}
							Press Run agent to see scores
						{/if}
					</p>
				{/if}

				<!-- The run's totals. The right padding keeps them clear of the run controls. -->
				<div class="grid shrink-0 grid-cols-3 gap-x-6 pt-2 pr-56">
					{#each totals as t (t.label)}
						<div class="flex flex-col">
							<span class="font-mono text-2xs text-muted-foreground uppercase">{t.label}</span>
							<span
								class="font-mono text-sm tabular-nums"
								style={t.color ? `color: ${t.color}` : ''}>{t.value}</span
							>
						</div>
					{/each}
				</div>
			</Pane>
		</div>

		<div class="absolute right-4 bottom-4 z-10">
			<RunControls {tep} bind:settingsOpen />
		</div>
	</Pane>
</Tabs.Root>
