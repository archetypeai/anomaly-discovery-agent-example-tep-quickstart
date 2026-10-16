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
	 * The transport is a floating CTA on this panel's lower-right corner, where
	 * all three references put theirs: a run control belongs with the run, not in
	 * a bar across the top of the page. The gear beside it opens Settings, which
	 * holds the reveal and what is actually running.
	 */
	import Pane from '$lib/components/ui/patterns/pane/index.js';
	import { Badge } from '@archetypeai/ds-ui-svelte-console/primitives/badge';
	import { Button } from '@archetypeai/ds-ui-svelte-console/primitives/button';
	import { Separator } from '@archetypeai/ds-ui-svelte-console/primitives/separator';
	import * as Tooltip from '@archetypeai/ds-ui-svelte-console/primitives/tooltip';
	import * as Tabs from '@archetypeai/ds-ui-svelte-console/primitives/tabs';
	import CircleArrowDownIcon from '@lucide/svelte/icons/circle-arrow-down';
	import InfoIcon from '@lucide/svelte/icons/info';
	import Settings2Icon from '@lucide/svelte/icons/settings-2';
	import ScatterChartIcon from '@lucide/svelte/icons/chart-scatter';
	import FactoryIcon from '@lucide/svelte/icons/factory';
	import { scoreTone, SCORE_META } from '$lib/scores.js';
	import ScoreTrajectory from './score-trajectory.svelte';
	import EmbeddingSpace from './embedding-space.svelte';
	import Flowsheet from './flowsheet.svelte';
	import PlaybackControls from './playback-controls.svelte';

	/** @type {{tep: any, settingsOpen?: boolean, class?: string}} */
	let { tep, settingsOpen = $bindable(false), class: className = '' } = $props();

	const s = $derived(tep.state);
	const latest = $derived(s.scores.at(-1));
	const playing = $derived(s.status?.playing === true);

	const HEADING = 'font-sans text-sm tracking-normal normal-case text-foreground';


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
	const SUBTITLE = 'Omega 1.5 + kNN · Archetype AI platform (Dev)';

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
		view === 'plant'
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

<!-- Tabs.Root wraps the panel so the switcher can sit in the panel's caption row
     while the tab bodies stay in its content — both still share Root's context
     because the Pane is a descendant of it. -->
<Tabs.Root bind:value={view} class="flex min-h-0 flex-col {className}">
	<Pane
		variant="panel"
		title="AD Agent"
		icon={CircleArrowDownIcon}
		subtitle={SUBTITLE}
		class="relative min-h-0 flex-1"
	>
		<!-- The aside sits ON the panel's name, not pinned to the far right: it
		     explains what this region IS, and at the right-hand edge it read as a
		     control acting on the content. -->
		{#snippet titleAfter()}
			<Tooltip.Root>
				<Tooltip.Trigger variant="info" aria-label="About this view">
					<InfoIcon class="size-3.5 text-muted-foreground" aria-hidden="true" />
				</Tooltip.Trigger>
				<Tooltip.Content class="max-w-xs text-xs leading-snug">{aside}</Tooltip.Content>
			</Tooltip.Root>
		{/snippet}

		{#snippet actions()}
			<!-- The segmented icon switch both references put in this row, at the same
			     34px the run selector opposite is, so the two caption rows sit level. -->
			<Tabs.List variant="toggle">
				<Tabs.Trigger value="plant" variant="icon" title="Plant" aria-label="Plant">
					<FactoryIcon />
				</Tabs.Trigger>
				<Tabs.Trigger
					value="embedding"
					variant="icon"
					title="Embedding space"
					aria-label="Embedding space"
				>
					<ScatterChartIcon />
				</Tabs.Trigger>
			</Tabs.List>
		{/snippet}

		<!-- `relative` so the transport can anchor to this panel's lower-right corner. -->
		<div class="relative flex min-h-0 flex-1 flex-col overflow-hidden">
			<!-- The body is the ELASTIC region: it takes whatever the score block
			     leaves, and both views size themselves from the slot they are given. -->
			<!-- The body is the ELASTIC region: it takes whatever the score block
			     leaves, and both views size themselves from the slot they are given. -->
			<Tabs.Content value="plant" class="flex min-h-0 flex-col p-4 {bodyShare}">
				<Flowsheet {tep} class="flex-1" />
			</Tabs.Content>

			<Tabs.Content value="embedding" class="flex min-h-0 flex-col p-4 {bodyShare}">
				<EmbeddingSpace {tep} class="flex-1" />
			</Tabs.Content>

			<Separator />

			<!-- The score block is FIXED: it is the live reading, and it must not be
			     the thing that gives when the body grows. -->
			<Pane title="Anomaly score" captionClass={HEADING} class="min-h-0 {scoreShare}">
				{#snippet titleAfter()}
					<Tooltip.Root>
						<Tooltip.Trigger variant="info" aria-label="How to read the anomaly score">
							<InfoIcon class="size-3.5 text-muted-foreground" aria-hidden="true" />
						</Tooltip.Trigger>
						<Tooltip.Content class="max-w-sm text-xs leading-snug">
							<p>
								1.0 means "as ordinary as its neighbours". Log-scaled, because the decision
								happens just above 1.0 while a developed fault reaches 60. The trace is coloured
								by band and the strip under the axis is the same run measured in time. The dashed
								marker is where the simulator introduced the disturbance: a property of the data,
								not of the detector's opinion.
							</p>
							<p class="mt-2">
								<span class="text-foreground">Crossings</span> counts windows over the threshold,
								not separate alarms — on a developed fault nearly every window after onset crosses.
								<span class="text-foreground">Detected</span> is when the first
								<em>sustained</em> detection began: three consecutive windows over the line, the same
								rule Stages 7 and 8 score with. <span class="text-foreground">After onset</span> is
								that moment minus the fault's own start, in plant time. On a fault-free run
								Detected stays "—" and any crossings are false alarms.
							</p>
						</Tooltip.Content>
					</Tooltip.Root>
				{/snippet}

				<!-- Label + badge, the pair all three references put under this caption.
				     The label is a step under the badge in size and mono, so the row reads
				     as field-then-value rather than as one flat run of type. -->
				<div class="flex min-w-0 shrink-0 items-center gap-2">
					<span
						class="shrink-0 font-mono text-[11px] tracking-wider text-muted-foreground uppercase"
					>
						Detection state
					</span>
					{#if verdict}
						<!-- `transition-none` is load-bearing. The DS badge base carries
						     `transition-colors`, which is right for a badge that changes on a
						     click and wrong for one that changes with every window: the colour
						     would be permanently mid-interpolation, so the chip can show an
						     amber border while its text already reads NOMINAL. -->
						<Badge
							variant="status"
							class="shrink-0 px-2 py-0 font-mono text-[11px] tracking-wider uppercase transition-none"
							style="color: {verdict.color}; border-color: {verdict.color}"
						>
							{s.detectedHours !== null ? 'Anomaly' : verdict.label}
						</Badge>
					{:else}
						<Badge
							variant="status"
							class="shrink-0 border-border px-2 py-0 font-mono text-[11px] tracking-wider text-muted-foreground uppercase"
						>
							Awaiting
						</Badge>
					{/if}
				</div>

				<ScoreTrajectory {tep} class="min-h-0 flex-1" />

				{#if !s.scores.length}
					<!-- THREE messages, because there are three different waits, and saying
					     the wrong one is what made a run switch look broken.
					     A switch takes about ten seconds — the replayer resets the graph
					     (~3 s) and the agent then needs a full 64-sample window before it can
					     score anything — and for all of it the chart is empty. With only two
					     messages a switch showed BOTH and neither was true: "Press Run Agent"
					     while `playing` was briefly false, then "Awaiting the agent's first
					     window". Nothing needs pressing, and the agent is not late — it is
					     being restarted on purpose. The switch names itself now. -->
					<p class="shrink-0 text-center text-sm text-muted-foreground">
						{#if s.status?.loading}
							Switching run — resetting the agent
						{:else if playing}
							Awaiting the agent's first window
						{:else}
							Press Run Agent to see scores
						{/if}
					</p>
				{/if}

				<!-- The run's totals, under the trace, on one line split in thirds. NO
				     RULES: hairlines on this page separate PANES, and repeating them inside
				     a block to fence off three readings draws a boundary where there is no
				     change of subject. `-mx-4` cancels the block's inset so each third is a
				     true third of the panel; the cells pay the inset back individually. -->
				<!-- The right padding is on the ROW, not on the last cell. The pill and
				     its gear occupy about 238px of the panel's lower-right corner; 144px
				     on the last cell alone was not enough and the pill printed over
				     "After onset". Padding the row shrinks all three cells evenly to
				     ~167px, which still fits the longest label and its figure, and
				     nothing is drawn under the pill. -->
				<div class="-ml-4 grid shrink-0 grid-cols-3 pt-3 pr-60">
					{#each totals as t (t.label)}
						<div class="flex min-w-0 items-baseline gap-2 px-4">
							<span
								class="shrink-0 font-mono text-[10px] tracking-wide text-muted-foreground uppercase"
							>
								{t.label}
							</span>
							<span
								class="shrink-0 font-mono text-sm tabular-nums"
								style={t.color ? `color: ${t.color}` : ''}
							>
								{t.value}
							</span>
						</div>
					{/each}
				</div>

				<!-- Clearance for the floating transport. 32px, not the 56 it was: the
				     pill is 44px tall on a 16px inset, so a full-height spacer reserves a
				     band nothing but the pill's right-hand corner ever occupies. The
				     totals row pays for the rest with right padding on its last cell,
				     which is the only one the pill actually reaches — and the 24px that
				     buys goes to the chart, which on the embedding tab was down to 78px
				     and could not print four tick labels. -->
				<div class="h-8 shrink-0"></div>
			</Pane>
		</div>

		<!-- `pointer-events-none` on the wrapper with it re-enabled on the controls:
		     the wrapper spans the corner, and without that it would swallow hover
		     from whatever it sits over. -->
		<div class="pointer-events-none absolute right-4 bottom-4 z-10 flex items-center gap-2">
			<div class="pointer-events-auto">
				<PlaybackControls {tep} />
			</div>
			<!-- The pill's sibling: same construction, neutral surface instead of
			     babyblue, square at the same 44px so the two read as one cluster. -->
			<Button
				variant="ghost"
				class="bottom-toolbar-surface shadow-bottom-toolbar pointer-events-auto size-11 rounded-full border border-transparent p-0 text-atai-always-black hover:opacity-90"
				aria-label="Settings"
				onclick={() => (settingsOpen = !settingsOpen)}
			>
				<Settings2Icon class="size-4" aria-hidden="true" />
			</Button>
		</div>
	</Pane>
</Tabs.Root>
