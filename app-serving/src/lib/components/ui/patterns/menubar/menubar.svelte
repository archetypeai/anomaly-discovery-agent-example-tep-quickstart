<script>
	/**
	 * The workbench header: identity and the theme switch, nothing else.
	 *
	 * Composed here rather than using the labs `Menubar` primitive, for the reason the
	 * bearings demo gives: two of that component's internals are fixed and both are the
	 * things this lockup is about. It renders `<Logo />` at the default 24px with no way
	 * to pass `size`, and it puts a lucide `minus` glyph between the mark and the partner
	 * slot. The references' lockup is a 16px mark, a vertical hairline, and the product
	 * endorsement on two lines — so the primitive would have had to be fought on both.
	 *
	 * The ARTWORK is still the DS's: `Logo` comes from the labs package at `size="sm"`.
	 * Nothing about the mark is hand-drawn here; only the arrangement around it is local,
	 * which is what a pattern is for. All three references do the same.
	 *
	 * The theme toggle stays in the bar because it is a property of the page rather than
	 * of the run. It reads `mode-watcher` rather than the DS `darkMode` primitive, which
	 * is what OSM and RED use and what gives this app its dark default — see +layout.svelte.
	 */
	import Logo from '@archetypeai/ds-ui-svelte-labs/primitives/logo';
	import { Button } from '@archetypeai/ds-ui-svelte-console/primitives/button';
	import SunIcon from '@lucide/svelte/icons/sun';
	import MoonIcon from '@lucide/svelte/icons/moon';
	import { mode, toggleMode } from 'mode-watcher';

	let { children } = $props();

	// View-transitioned so the two surfaces cross-fade instead of snapping. Guarded because
	// the API is Chromium-only; everywhere else it is the plain toggle.
	//
	// All three promises are caught, not just `finished`: a transition started while another
	// is still running — two quick clicks — aborts the first, and Chrome rejects `ready`
	// with `InvalidStateError`. Nothing is wrong when that happens (the theme still flips,
	// the browser just skips the animation), but unhandled it surfaces as an uncaught
	// exception in the console of a demo whose console is one of the things being shown.
	function toggleDark() {
		if (!document.startViewTransition) {
			toggleMode();
			return;
		}
		const t = document.startViewTransition(() => toggleMode());
		t.ready?.catch(() => {});
		t.finished?.catch(() => {});
		t.updateCallbackDone?.catch(() => {});
	}
</script>

<header class="flex items-center justify-between border-b border-separator px-4 py-2">
	<!-- One label on the lockup; the mark and the endorsement are both hidden from the
	     accessibility tree so the name is announced once, as words. -->
	<span class="inline-flex items-center gap-2.5" aria-label="AD TEP Monitor — Built by Archetype">
		<Logo size="sm" aria-hidden="true" role="presentation" />
		<!-- A hairline rule, not the primitive's `minus` glyph: an em-dash-shaped icon sits
		     on the type's baseline and reads as punctuation between two names, where the
		     lockup wants a divider between a mark and a caption. 24px tall, spanning both
		     lines. -->
		<span class="h-6 w-px shrink-0 bg-separator" aria-hidden="true"></span>
		<span
			class="shrink-0 text-left text-[11px] leading-[1.25] text-muted-foreground"
			aria-hidden="true"
		>
			AD TEP Monitor<br />Built by Archetype
		</span>
	</span>

	<div class="flex items-center gap-2">
		{@render children?.()}
		<Button variant="outline" size="icon" aria-label="Toggle dark mode" onclick={toggleDark}>
			{#if mode.current === 'dark'}<SunIcon class="size-4" />{:else}<MoonIcon class="size-4" />{/if}
		</Button>
	</div>
</header>
