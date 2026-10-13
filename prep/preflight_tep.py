"""Preflight checks specific to one-class detection on the TEP layout.

`preflight_static.py` is vendored verbatim from omega-1-4-preflight and written
for the supervised two-class case. Anomaly Discovery has one class — the fit
sees normal data only — so `check_schema_match`, `check_class_balance` and
`check_expected_accuracy_prior` are not run. What replaces them are the
questions that decide whether a normal-only build on simulation data will hold:

  * REFERENCE PURITY    is every reference row actually fault-free, and do the
                        reference simulations agree with each other? A one-class
                        detector fits whatever it is handed.
  * REFERENCE COVERAGE  enough reference windows for the LOF neighbourhood and
                        the PCA block — both clamp silently.
  * ROLE SEPARATION     no simulation run in more than one of reference /
                        validation / eval.
  * SEAMS               concatenated simulations must be separated by a gap the
                        platform's 5% sampling-rate tolerance will invalidate,
                        and the count of windows lost to that must be known.
  * COVERAGE            every eval slice carries every IDV with its 160-row
                        normal prefix and 800 fault rows.
  * NORMALISATION       z-score stats were fitted on the reference only and the
                        reference pools to mean 0 / std 1.
  * ANALYSER STAIRCASE  the composition analysers update every 6 or 15 minutes,
                        so at a 3-minute cadence most consecutive values repeat —
                        the evidence behind the 33-channel default.
"""
from __future__ import annotations

import math

from preflight_static import CheckResult, PASS, WARN, FAIL, INFO


def check_reference_purity(faulty_rows: int, total_rows: int, label: str) -> CheckResult:
    if faulty_rows:
        return CheckResult("reference_purity", FAIL,
                           f"{label}: {faulty_rows:,} of {total_rows:,} rows carry a "
                           f"non-zero faultnumber — the reference is not normal-only.")
    return CheckResult("reference_purity", PASS,
                       f"{label}: all {total_rows:,} rows have faultnumber 0.")


def check_reference_agreement(per_sim_rms: dict, tolerance: float = 0.25) -> CheckResult:
    """Do the reference simulations look alike? Each sim's RMS of the z-scored
    channels should sit near 1; a sim far off is a different regime being
    taught as normal."""
    vals = list(per_sim_rms.values())
    med = sorted(vals)[len(vals) // 2]
    off = {s: r for s, r in per_sim_rms.items() if abs(r - med) / med > tolerance}
    details = {"median_rms": med, "n_sims": len(vals), "outliers": off}
    if off:
        return CheckResult("reference_agreement", WARN,
                           f"{len(off)} of {len(vals)} reference sims deviate >{tolerance:.0%} "
                           f"from the median RMS {med:.3f}: {list(off)[:5]}", details=details)
    return CheckResult("reference_agreement", PASS,
                       f"{len(vals)} reference sims agree: per-sim RMS within {tolerance:.0%} "
                       f"of the median {med:.3f}.", details=details)


def check_reference_coverage(n_ref_windows: int, n_neighbors: int = 20,
                             pca_components: int = 20) -> CheckResult:
    eff_k = min(n_neighbors, max(n_ref_windows - 1, 1))
    eff_p = min(pca_components, max(n_ref_windows - 1, 1))
    details = {"n_reference_windows": n_ref_windows, "n_neighbors": n_neighbors,
               "pca_components": pca_components}
    if n_ref_windows < 2:
        return CheckResult("reference_coverage", FAIL,
                           f"only {n_ref_windows} reference window(s) — LOF cannot be fit.",
                           details=details)
    if eff_k < n_neighbors or eff_p < pca_components:
        return CheckResult("reference_coverage", WARN,
                           f"{n_ref_windows} reference windows silently clamp n_neighbors "
                           f"{n_neighbors}->{eff_k}, pca {pca_components}->{eff_p}.",
                           details=details)
    return CheckResult("reference_coverage", PASS,
                       f"{n_ref_windows:,} reference windows support n_neighbors={n_neighbors} "
                       f"and pca_components={pca_components} without clamping.", details=details)


def check_window_span(window_size: int, step_size: int, sample_s: float,
                      rows_per_sim: int) -> CheckResult:
    hours = window_size * sample_s / 3600
    per_sim = (rows_per_sim - window_size) // step_size + 1
    details = {"window_hours": hours, "windows_per_reference_sim": per_sim}
    if per_sim < 4:
        return CheckResult("window_span", WARN,
                           f"window_size={window_size} ({hours:.1f} h) at step {step_size} "
                           f"yields only {per_sim} window(s) per {rows_per_sim}-row reference "
                           f"sim.", details=details)
    return CheckResult("window_span", INFO,
                       f"window_size={window_size} = {hours:.1f} h of process at "
                       f"{sample_s:.0f} s/sample; {per_sim} windows per {rows_per_sim}-row "
                       f"reference sim at step {step_size}. A window is also the floor on "
                       f"detection delay under end-row scoring.", details=details)


def check_seams(name: str, timestamps: list, seam_gap: float, sample_s: float,
                expected_seams: int, window_size: int, tolerance: float = 0.05) -> CheckResult:
    deltas = [b - a for a, b in zip(timestamps, timestamps[1:])]
    if any(d <= 0 for d in deltas):
        return CheckResult("seams", FAIL, f"{name}: timestamps are not strictly increasing.")
    nominal = [d for d in deltas if abs(d - sample_s) <= tolerance * sample_s]
    seams = [d for d in deltas if d == seam_gap]
    other = len(deltas) - len(nominal) - len(seams)
    lost = len(seams) * (window_size - 1)          # straddling windows at step 1
    details = {"nominal": len(nominal), "seams": len(seams), "other": other,
               "windows_invalidated_at_step1": lost}
    if other or len(seams) != expected_seams:
        return CheckResult("seams", FAIL,
                           f"{name}: {len(seams)} seams (expected {expected_seams}), "
                           f"{other} interval(s) neither nominal nor seam.", details=details)
    return CheckResult("seams", PASS,
                       f"{name}: {len(nominal):,} nominal {sample_s:.0f} s intervals, "
                       f"{len(seams)} seams of {seam_gap:,.0f} s; at window {window_size} the "
                       f"platform's {tolerance:.0%} tolerance invalidates {lost} straddling "
                       f"windows ({lost / (len(deltas) + 1):.1%}).", details=details)


def check_slice_coverage(name: str, labels: list[dict], n_faults: int,
                         rows_per_sim: int, onset: int) -> CheckResult:
    by_id: dict[str, dict] = {}
    for row in labels:
        d = by_id.setdefault(row["fault_id"], {"normal": 0, "fault": 0})
        d[row["label"]] += 1
    expected_ids = {"idv_00"} | {f"idv_{i:02d}" for i in range(1, n_faults + 1)}
    missing = expected_ids - set(by_id)
    wrong = {k: v for k, v in by_id.items()
             if (k == "idv_00" and v != {"normal": rows_per_sim, "fault": 0})
             or (k != "idv_00" and v != {"normal": onset, "fault": rows_per_sim - onset})}
    if missing or wrong:
        return CheckResult("slice_coverage", FAIL,
                           f"{name}: missing {sorted(missing)}; unexpected counts {wrong}",
                           details={"counts": by_id})
    return CheckResult("slice_coverage", PASS,
                       f"{name}: idv_00 + {n_faults} IDVs, each faulty sim {onset} normal -> "
                       f"{rows_per_sim - onset} fault rows.", details={"counts": by_id})


def check_role_separation(roles: dict[str, set]) -> CheckResult:
    """roles: role name -> set of (faultnumber, simulationrun)."""
    names = list(roles)
    shared = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            both = roles[a] & roles[b]
            if both:
                shared[f"{a} & {b}"] = sorted(both)[:5]
    if shared:
        return CheckResult("role_separation", FAIL,
                           f"simulations shared across roles: {shared}", details=shared)
    total = sum(len(v) for v in roles.values())
    return CheckResult("role_separation", PASS,
                       f"{total} (fault, sim) segments across {len(roles)} roles, none shared.")


def check_normalisation(pooled_mean_abs_max: float, pooled_std_min: float,
                        pooled_std_max: float, stats_fitted_on: str) -> CheckResult:
    details = {"mean_abs_max": pooled_mean_abs_max, "std_min": pooled_std_min,
               "std_max": pooled_std_max, "fitted_on": stats_fitted_on}
    if pooled_mean_abs_max > 1e-3 or abs(pooled_std_min - 1) > 1e-3 or abs(pooled_std_max - 1) > 1e-3:
        return CheckResult("normalisation", FAIL,
                           f"reference does not pool to z-scores: |mean| up to "
                           f"{pooled_mean_abs_max:.2e}, std {pooled_std_min:.4f}–{pooled_std_max:.4f}.",
                           details=details)
    return CheckResult("normalisation", PASS,
                       f"reference pools to |mean| < {pooled_mean_abs_max:.1e}, std "
                       f"{pooled_std_min:.4f}–{pooled_std_max:.4f}; stats fitted on "
                       f"'{stats_fitted_on}'.", details=details)


def check_filename_labels(names: list[str], token: str = "normal") -> CheckResult:
    bad = [n for n in names if token not in n.lower()]
    if bad:
        return CheckResult("filename_labels", FAIL,
                           f"{len(bad)} reference file(s) lack '{token}' in the name — the "
                           f"fitting runner labels by filename: {bad[:3]}")
    return CheckResult("filename_labels", PASS,
                       f"all {len(names)} reference filenames carry '{token}' — the fitting "
                       f"runner's filename→state match resolves every file.")


def check_analyser_staircase(repeat_fraction: dict[str, float],
                             continuous: list[str], analysers: list[str]) -> CheckResult:
    """Fraction of consecutive equal values per channel: near 0 for a continuous
    measurement, ~0.5 for a 6-min analyser and ~0.8 for a 15-min one."""
    c = sum(repeat_fraction[k] for k in continuous) / len(continuous)
    a = sum(repeat_fraction[k] for k in analysers) / len(analysers)
    details = {"continuous_mean_repeat": c, "analyser_mean_repeat": a}
    if a > 0.3 and c < 0.1:
        return CheckResult("analyser_staircase", WARN,
                           f"xmeas_23..41 repeat the previous value {a:.0%} of the time "
                           f"(continuous channels: {c:.1%}) — held-sample analysers appear "
                           f"as staircases at the 3-min cadence. Prep defaults to the "
                           f"33-variable set; `--channels all` keeps them.", details=details)
    return CheckResult("analyser_staircase", PASS,
                       f"no staircase channels (repeat fraction {a:.1%} vs {c:.1%}).",
                       details=details)
