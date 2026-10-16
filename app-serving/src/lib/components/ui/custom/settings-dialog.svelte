<script>
	/**
	 * The things you do TO the demo rather than watch it do: where the replay is,
	 * how fast it runs, what is moving over MQTT, and what this run actually is.
	 *
	 * One dialog, reached from the gear beside Run Agent, as all three references
	 * settle on — the two things you do to a demo, start it and configure it, sit
	 * together in the panel that owns the run rather than as icons in the top bar.
	 * Which SIMULATION is replayed is chosen in the Input panel, beside the data
	 * it names.
	 *
	 * THE REVEAL LIVES HERE because it is a deliberate act. On the panel it was a
	 * button beside the verdict, which is exactly where the eye lands when you are
	 * trying not to know the answer yet.
	 */
	import * as Dialog from '@archetypeai/ds-ui-svelte-console/primitives/dialog';
	import { Button } from '@archetypeai/ds-ui-svelte-console/primitives/button';
	import { Badge } from '@archetypeai/ds-ui-svelte-console/primitives/badge';
	import EyeIcon from '@lucide/svelte/icons/eye';
	import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw';
	import WifiIcon from '@lucide/svelte/icons/wifi';
	import WifiOffIcon from '@lucide/svelte/icons/wifi-off';
	import ArrowRightCircleIcon from '@lucide/svelte/icons/circle-arrow-right';
	import GaugeIcon from '@lucide/svelte/icons/gauge';
	import WaypointsIcon from '@lucide/svelte/icons/waypoints';
	import ClockIcon from '@lucide/svelte/icons/clock';
	import ActivityIcon from '@lucide/svelte/icons/activity';
	import FlagIcon from '@lucide/svelte/icons/flag';
	import ObservabilityDiagram from './observability-diagram.svelte';

	/** The topics the strip lists, in the order the data moves. */
	const TOPICS = ['sensors/tep', 'tep/raw', 'tep/status', 'tep/control', 'ad/results'];

	/** @type {{tep: any, open?: boolean}} */
	let { tep, open = $bindable(false) } = $props();

	const s = $derived(tep.state);
	const st = $derived(s.status);
	const cfg = $derived(st?.agent ?? {});
	const step = $derived(Number(cfg.stepSize ?? 4));
	const pct = $derived(st?.totalSamples ? Math.round(((st.sample ?? 0) / st.totalSamples) * 100) : 0);
	const atEnd = $derived(st?.totalSamples ? (st.sample ?? 0) >= st.totalSamples - 1 : false);

	/** IDV 3, 9 and 15 are the ones the literature — and this repo's own
	 *  evaluation, at 0.9–1.2% detection — reports as undetectable. Naming them in
	 *  the reveal is the difference between "the detector failed" and "this fault
	 *  is not visible in these measurements". */
	const HARD = ['idv_03', 'idv_09', 'idv_15'];


	/**
	 * THREE BODY SIZES, and each one means something. The dialog had five —
	 * text-base, text-sm, text-xs, 11px and 10px — with no rule about which got
	 * used where, so the position count was a step smaller than the topic strip
	 * while saying the same kind of thing.
	 *
	 *   READOUT  the figures you opened this dialog to read: position, clock,
	 *            topic rates, run totals. All mono, all the same size, because
	 *            they are the same kind of fact.
	 *   PROSE    the sentences that qualify them.
	 *   LABEL    section headings and the captions under a readout.
	 */
	const READOUT = 'font-mono text-base';
	// `max-w-prose` because the dialog is now wide enough that an unconstrained
	// paragraph runs past a comfortable measure.
	const PROSE = 'max-w-prose text-xs leading-relaxed text-muted-foreground';
	const LABEL = 'font-mono text-[11px] tracking-wider uppercase';
	const SECTION = `flex items-center gap-2 ${LABEL}`;
</script>

<Dialog.Root bind:open>
	<!-- max-w-4xl, because the data-flow plate is DRAWN at 900 units wide with
	     10px type, and the box positions inside it are hand-fitted to that. In a
	     672px dialog the whole thing scaled to 0.75 and its labels rendered at
	     ~7px — unreadable, and not fixable by raising the font size, since the
	     boxes would then overflow. Showing the plate at roughly 1:1 is the fix.
	     The scroll belongs to Dialog.Body, which is `min-h-0 flex-1
	     overflow-y-auto p-4` — putting it on Content instead scrolled the header
	     away with the content. -->
	<!-- `sm:max-w-4xl`, WITH the breakpoint prefix. The DS base sets
	     `sm:max-w-2xl`, and an unprefixed `max-w-4xl` does not override a
	     responsive variant — tailwind-merge keeps them as separate rules and the
	     `sm:` one wins at every width this dialog is ever seen at. -->
	<Dialog.Content class="sm:max-w-4xl">
		<Dialog.Header>
			<Dialog.Title class="font-mono tracking-wider uppercase">Settings</Dialog.Title>
			<Dialog.Description>
				Where in the run the replayer is, what is moving over MQTT, and what is scoring it. Which
				simulation is replayed is chosen in the Input panel. Nothing here changes the detector.
			</Dialog.Description>
		</Dialog.Header>

		<!-- Dialog.Body, not a bare div. The DS gives Content NO padding and puts
		     `p-4` on Header, Body and Footer individually — so a plain div here left
		     every section flush against the dialog's edge, 16px left of the title
		     above it. That was the "strange padding": not a value that needed
		     tuning, a wrapper that was skipped. -->
		<!-- `space-y-5`, not 7. The rhythm was regular — 28px between sections, 8px
		     from a heading to its content, every time — but 28px plus the leading
		     under the last line of text renders as ~44px of air, which is a lot in a
		     dialog whose sections are mostly two lines tall. At 20px the visual gap
		     is ~36px and each heading still reads as attached to what follows it. -->
		<Dialog.Body class="space-y-5">
			<!-- BROKER -->
			<section class="space-y-1.5">
				<h3 class={SECTION}>
					{#if s.connected}<WifiIcon class="size-4" />{:else}<WifiOffIcon class="size-4" />{/if}
					Broker
				</h3>
				<Badge
					variant="status"
					class="font-mono tracking-wider uppercase {s.connected
						? 'border-score-normal text-score-normal'
						: 'border-score-anomaly text-score-anomaly'}"
				>
					{s.connected ? 'Online' : 'Offline'}
				</Badge>
			</section>

			<!-- POSITION -->
			<section class="space-y-1.5">
				<h3 class={SECTION}><ArrowRightCircleIcon class="size-4" />Position</h3>
				<div class="flex items-center gap-4">
					<span class="shrink-0 tabular-nums {READOUT}">
						{st?.sample ?? 0} / {st?.totalSamples ?? 960}
					</span>
					<div class="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
						<div
							class="h-full bg-score-normal transition-[width] duration-200"
							style="width: {pct}%"
						></div>
					</div>
					<!-- The reference's treatment: a bordered button with a mono uppercase
					     label, not a small ghost one. It is the only control in this
					     dialog that DOES something to the run, and it should not read as
					     quieter than the readouts beside it. -->
					<Button
						variant="outline"
						class="shrink-0 gap-2 px-4 font-mono tracking-wider uppercase"
						onclick={() => tep.restart()}
						disabled={!s.connected}
					>
						<RotateCcwIcon class="size-4" />Restart
					</Button>
				</div>
				<p class="{LABEL} text-muted-foreground">
					{atEnd ? 'End of run' : `${(st?.processHours ?? 0).toFixed(1)} h of process time`}
				</p>
			</section>

			<!-- PACE. The platform answers a window in about 0.9 s, so the one thing
			     worth choosing is how many windows to ask about: every 4th sample
			     (a run in a few minutes, the default) or every sample, as Stage 6
			     delivers it (a run in ~15 minutes; alarm times then match Stage 6
			     to the sample). -->
			<section class="space-y-1.5">
				<h3 class={SECTION}><GaugeIcon class="size-4" />Pace</h3>
				<div class="flex gap-2">
					<Button size="sm" variant={step === 4 ? 'secondaryCta' : 'outline'} onclick={() => tep.setStep(4)}>
						Every 4th sample
					</Button>
					<Button size="sm" variant={step === 1 ? 'secondaryCta' : 'outline'} onclick={() => tep.setStep(1)}>
						Every sample (exact)
					</Button>
				</div>
				<p class={PROSE}>
					Platform-paced at <span class="font-mono text-foreground">{s.rate.toFixed(1)} win/s</span>:
					the replayer waits for each block's windows. Every 4th sample plays a run in a few minutes,
					but a detection (3 windows over the line) then spans 36 min of process time and its time is
					approximate. Every sample is how Stage 6 delivered: alarms match its output to the sample, at ~15 min a run.
				</p>
			</section>

			<!-- PROCESS CLOCK, the counterpart of the bearings demo's RECORDING CLOCK.
			     Its rig has a real wall-clock date in the recording; TEP is a simulator,
			     so the equivalent honest reading is process time. -->
			<section class="space-y-1.5">
				<h3 class={SECTION}><ClockIcon class="size-4" />Process clock</h3>
				<p class={READOUT}>
					{(st?.processHours ?? 0).toFixed(1)} h
					<span class="text-muted-foreground">
						of {(((st?.totalSamples ?? 960) * (st?.sampleSeconds ?? 180)) / 3600).toFixed(0)} h · fault
						onset at {(((st?.onsetSample ?? 160) * (st?.sampleSeconds ?? 180)) / 3600).toFixed(0)} h
					</span>
				</p>
			</section>

			<!-- LIVE DATA FLOW -->
			<section class="space-y-1.5">
				<h3 class={SECTION}><WaypointsIcon class="size-4" />Live data flow</h3>
				<!-- The five topics and their observed rate, above the diagram that
				     draws them. The strip answers "is anything moving" at a glance and
				     the diagram answers "which hop is dead", so the strip is the
				     section's HEADLINE and is set at reading size rather than as a
				     footnote — green when data moved in the last tick, muted when it
				     did not. At 11px it was the smallest type in the dialog and the one
				     thing in it you check first. -->
				<div class="grid grid-cols-1 gap-x-8 gap-y-2 font-mono text-base sm:grid-cols-3">
					{#each TOPICS as t (t)}
						{@const r = s.flows[t]?.rate ?? 0}
						<div class={r > 0 ? 'text-score-normal' : 'text-muted-foreground'}>
							{t}
							<!-- One decimal below 10/s. `tep/raw` runs at about 0.2/s here, and
							     rounding printed it as "0/s" — a number that looks like a
							     stopped topic. -->
							<span class="ml-1">{r > 0 ? `${r < 10 ? r.toFixed(1) : Math.round(r).toLocaleString()}/s` : 'idle'}</span>
						</div>
					{/each}
				</div>
				<ObservabilityDiagram {tep} />
			</section>

			<!-- NO "WHAT IS RUNNING" TABLE. It listed encoder, window, stride and
			     detector, and the agent's own box in the diagram above states all four
			     — from the same `tep/status` fields. What the diagram does NOT carry is
			     what the run has cost, so that is the one line kept, inline. -->
			<section class="space-y-1.5">
				<h3 class={SECTION}><ActivityIcon class="size-4" />This run</h3>
				<!-- One line, with the separators OUTSIDE the coloured spans. Written
				     with them inside, the markup collapsed the whitespace around each
				     dot and the line came out as "224 windows scored·0 invalid· …". -->
				<dl class="flex flex-wrap items-baseline gap-x-6 gap-y-1.5 {READOUT}">
					<div class="flex items-baseline gap-1.5">
						<dt class="text-muted-foreground">scored</dt>
						<dd>{s.scored.toLocaleString()}</dd>
					</div>
					<div class="flex items-baseline gap-1.5">
						<dt class="text-muted-foreground">invalid</dt>
						<dd class={s.invalid ? 'text-score-elevated' : ''}>{s.invalid}</dd>
					</div>
					<div class="flex items-baseline gap-1.5">
						<dt class="text-muted-foreground">threshold</dt>
						<dd>{s.threshold.toFixed(3)}</dd>
					</div>
					<div class="flex items-baseline gap-1.5">
						<dt class="text-muted-foreground">fitted at step</dt>
						<dd>{cfg.fittedStep ?? '—'}</dd>
					</div>
					<div class="flex items-baseline gap-1.5">
						<dt class="text-muted-foreground">blueprint</dt>
						<dd>{cfg.blueprint ?? '—'}</dd>
					</div>
					{#if s.detections.length > 1}
						<!-- Only when the run FLAPPED. One episode is the ordinary case and
						     saying so every time is noise; two or more is the thing worth
						     knowing, and nothing else on screen says it. -->
						<div class="flex items-baseline gap-1.5">
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

			<!-- NO DETECTIONS SECTION. It read "8.3 h (+0.3 h after onset) · peak
			     15.86 · 199 windows · open", and the first two of those are already the
			     totals under the trace while the peak is the trace's own high point.
			     The only fact it added was how many EPISODES the run had — which is
			     one, on every run that crosses and stays over — so it is stated below
			     only when it is not one. The bearings demo dropped its crossings table
			     for the same reason. -->
			<!-- GROUND TRUTH -->
			<section class="space-y-1.5">
				<h3 class={SECTION}><FlagIcon class="size-4" />Ground truth</h3>
				{#if st?.revealed && st?.truth}
					{@const hard = HARD.includes(st.truth.faultId)}
					<p class={READOUT}>
						This run is
						<span class="font-mono text-foreground">
							{st.truth.faultId === 'idv_00'
								? 'fault-free'
								: st.truth.faultId.replace('idv_', 'IDV ')}
						</span>
						{#if hard}
							<span class="text-muted-foreground">
								— undetectable by any published method, and caught here 0.9–1.2% of the time.
							</span>
						{/if}
					</p>
				{:else}
					<p class={PROSE}>
						Withheld until you ask, or until the run ends. A crew watching a live plant does not
						know whether a fault is present — and three of the twenty faults are undetectable, so
						watching one do nothing is the honest half of this demo.
					</p>
					<Button size="sm" variant="secondaryCta" onclick={() => tep.reveal()}>
						<EyeIcon class="size-3.5" />Reveal what this run is
					</Button>
				{/if}
			</section>
		</Dialog.Body>
	</Dialog.Content>
</Dialog.Root>
