/**
 * Score metadata — the one place a score turns into a colour.
 *
 * The domain token layer in `routes/layout.css` defines three stops
 * (`--score-normal`, `--score-elevated`, `--score-anomaly`) plus the threshold
 * line. This is the `$lib/scores.js` shape the bearings demo uses and the
 * `$lib/states.js` shape OSM uses: same three fields, same reason for each.
 *
 *  - `label` — the human name, so no component hardcodes a string either
 *  - `color` — the `var()` expression, for CSS, inline `style` and SVG attributes
 *  - `token` — the bare property name, for APIs that CANNOT take a `var()`
 */

/** @param {string} label @param {string} token */
function meta(label, token) {
	return { label, token, color: `var(${token})` };
}

export const SCORE_META = {
	normal: meta('Nominal', '--score-normal'),
	elevated: meta('Elevated', '--score-elevated'),
	anomaly: meta('Anomaly', '--score-anomaly'),
	threshold: meta('Threshold', '--score-threshold')
};

/**
 * Where a score sits relative to the detector's own threshold.
 *
 * `elevated` is the band below the line but visibly off the floor. It is a
 * fraction of the threshold rather than a fixed number because the threshold is
 * chosen at fit time and lives INSIDE the artifact — a constant here would be
 * right for one detector and wrong for the next. 0.85 puts the band across the
 * last ~15% of approach, which on TEP is where the trajectory starts climbing
 * before it crosses.
 *
 * Returns the `normal` entry for a missing score rather than throwing, so an
 * unexpected value from the agent renders as ordinary rather than as a crash.
 *
 * @param {number | null | undefined} score
 * @param {number | null | undefined} threshold
 */
export function scoreTone(score, threshold) {
	if (score == null || threshold == null) return SCORE_META.normal;
	if (score > threshold) return SCORE_META.anomaly;
	if (score > threshold * 0.85) return SCORE_META.elevated;
	return SCORE_META.normal;
}

/**
 * Deviation of a channel from the reference mean, in reference sigmas, as a
 * tone. The plate and the grid both read it, so the two cannot disagree.
 * @param {number} dev
 */
export function deviationTone(dev) {
	const d = Math.abs(dev);
	if (d >= 2.5) return SCORE_META.anomaly;
	if (d >= 1) return SCORE_META.elevated;
	return SCORE_META.normal;
}
