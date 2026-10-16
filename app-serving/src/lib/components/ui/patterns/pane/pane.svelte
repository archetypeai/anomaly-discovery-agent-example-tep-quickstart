<script>
	import { cn } from '$lib/utils';

	/**
	 * Workbench pane: a captioned region of the page background, separated from its
	 * neighbours by a hairline rather than wrapped in a card. Panes carry no border,
	 * radius or surface of their own — the grid that lays them out owns the rules,
	 * so several panes read as one continuous workbench instead of floating cards.
	 *
	 * Ported from the OSM demo so the canonical-agent examples read as siblings.
	 * Two variants, because the layout nests one level:
	 *
	 * - `panel` — a top-level region (Input / Output). Caption is icon + foreground
	 *   text, and the content is FLUSH: no horizontal padding, so the hairlines
	 *   between the blocks inside reach the panel's own edges.
	 * - `block` — a section within a panel. Caption is muted and a step smaller with
	 *   no icon, which is what keeps the hierarchy readable when several captions
	 *   are on screen at once. Content is inset and gapped.
	 *
	 * @typedef {Object} Props
	 * @property {string} [title=""] - caption text, rendered uppercase. Omit it (with
	 *   no icon or actions either) and the caption row is not rendered at all.
	 * @property {'panel'|'block'} [variant="block"] - nesting level
	 * @property {import('svelte').Component} [icon] - lucide icon, left of the caption
	 * @property {string} [class] - additional CSS classes
	 * @property {string} [captionClass] - classes for the caption text itself
	 * @property {import('svelte').Snippet} [actions] - controls pinned right in the caption row
	 * @property {import('svelte').Snippet} [titleAfter] - rendered immediately after the
	 *   caption text, inside the caption itself. For an affordance that belongs to the
	 *   REGION'S NAME rather than to the region — an info tooltip explaining what the block
	 *   is, say. `actions` is the wrong home for those: pinned to the far right they read as
	 *   controls acting on the content, and on a wide panel they end up an inch of whitespace
	 *   away from the words they explain.
	 * @property {string} [subtitle] - second line, for the standing facts about what a
	 *   panel is showing. Panel variant only.
	 * @property {import('svelte').Snippet} [subtitleActions] - pinned right on the subtitle
	 *   row, for live readouts that would jostle the caption row's controls as they change width
	 * @property {import('svelte').Snippet} [children] - the pane's content
 * @property {boolean} [subtitleInline=false] - put the subtitle in the caption row instead
	 *   of on its own line. OSM keeps them apart, and is right to: a subtitle inline with a
	 *   fixed-height row competes with the actions for width and truncates first. Here the
	 *   panels have no caption-row actions and vertical space is the scarce thing — the left
	 *   panel has to fit a laptop without scrolling — so the two rows collapse into one.
	 */

	/** @type {Props} */
	let {
		title = '',
		subtitle = '',
		subtitleActions,
		subtitleInline = false,
		variant = 'block',
		icon: Icon = undefined,
		class: className,
		captionClass,
		actions,
		titleAfter,
		children,
		...restProps
	} = $props();

	let isPanel = $derived(variant === 'panel');
</script>

<section class={cn('flex min-h-0 flex-col', isPanel ? '' : 'gap-2 p-4', className)} {...restProps}>
	<!-- No caption row when there is nothing to put in it: an empty title still
	     reserves its min-height and the gap below, which is dead space. -->
	{#if title || Icon || actions || titleAfter}
		<!-- A panel's caption row is a fixed height so two panels side by side start
		     their content on the same line, whatever each one puts in the row. -->
		<header
			class={cn(
				'flex items-center justify-between gap-2',
				isPanel
					? subtitleInline
						? 'min-h-0 px-4 pt-3 pb-0'
						: 'min-h-[50px] px-4 pt-4 pb-0'
					: 'min-h-6'
			)}
		>
			<span
				class={cn(
					'flex items-center gap-1.5 font-mono uppercase',
					isPanel
						? 'text-[11px] tracking-wider text-foreground'
						: 'text-[10px] tracking-wide text-muted-foreground',
					captionClass
				)}
			>
				{#if Icon}
					<Icon class="size-4" strokeWidth={1.25} aria-hidden="true" />
				{/if}
				{title}
				{#if titleAfter}
					<!-- Inside the caption, so it sits against the last word of the title and
					     inherits nothing but position — the affordance styles itself. -->
					{@render titleAfter()}
				{/if}
				{#if isPanel && subtitleInline && subtitle}
					<span class="min-w-0 truncate tracking-normal text-muted-foreground normal-case">
						— {subtitle}
					</span>
				{/if}
			</span>
			{#if actions}
				<div class="flex items-center gap-2">
					{@render actions()}
				</div>
			{/if}
		</header>
	{/if}

	<!-- Subtitle on its own line rather than appended to the caption: the caption
	     row is a fixed-height flex with actions pinned right, so anything inline
	     competes with the controls for width and truncates first. -->
	{#if isPanel && !subtitleInline && (subtitle || subtitleActions)}
		<div class="flex shrink-0 items-center justify-between gap-3 px-4 pt-1">
			<p class="min-w-0 truncate text-xs text-muted-foreground">{subtitle}</p>
			{#if subtitleActions}
				<div class="flex shrink-0 items-center gap-2">
					{@render subtitleActions()}
				</div>
			{/if}
		</div>
	{/if}

	{@render children?.()}
</section>
