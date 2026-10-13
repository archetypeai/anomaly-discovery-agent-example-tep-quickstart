# Plan — TEP Anomaly Discovery quickstart

Status legend: ✅ done · 🔄 in progress · ⬜ not started

## Goal

A short, public-ready version of the TEP AD example
(`anomaly-discovery-agent-example-tep`, private), in the shape of the OSM
LARCO quickstart: the whole lifecycle on Dev's Optimizations and Evals APIs in
about 20 minutes, with every expected output written down and reproduced.

## Scope (decided 2026-10-13)

| | quickstart | full example |
|---|---|---|
| data | the same Rieth (2017) download and prep | same |
| library / validation / test | 40 fault-free runs / slice 01 + `val_normal` / slices 02–04 | same |
| delivery | 4 chunks of the 48-hour set (84 runs), seeded | 496 chunks (10,406 runs) |
| search | 2 trials: k 5 and 10 at the full search's winner (window 48, step 8, L2, PCA 16, threshold 1.215) | 24 trials |
| PCA T²/SPE bar | left out | yes |
| shipped data | `data/prepared/` (66 MB) and `data/roles/` (70 MB, mostly the same files) in Git LFS, so a clone can skip the 1.4 GB download | — |
| archive, live app, literature comparison | left out | yes |

Repo: `archetypeai/anomaly-discovery-agent-example-tep-quickstart`, private
until reviewed. The full TEP and IMS repos are private, so the quickstart does
not link to them yet.

## Data licence

Harvard Dataverse doi:10.7910/DVN/6C3JR1 is a public-domain dedication ("You can
copy, modify, distribute and perform the work … without asking permission"); the
one condition is not implying endorsement by Pacific Science & Engineering
Group. Derived files can ship in the repo.

## Steps

| # | Step | Status | Notes |
|---|---|---|---|
| 1 | Scripts copied from the full example and renumbered (Stages 0–7) | ✅ | 2-point search default, 4-chunk delivery default, `ad-tep-qs-` names, delivery and scoring split (Stages 6, 7), PCA bar removed |
| 2 | Run from scratch: download, prep, roles, Optimize, Evals, delivery, scoring | ✅ | 2026-10-13: download 7 min, Stages 1–3 50 s, Optimize 5.6 min, Evals 2.6 min, delivery 14.8 min, scoring 1 s. Validation k 5 0.8547 / k 10 0.8540; test macro-F1 0.7331, window detection 78.0%; delivery at 1% FAR 78.0% / 1.41% / AUROC 0.901 |
| 3 | Run again from scratch and compare every number | ✅ | separate copy, new everything: every number the same; prepared files, delivery outputs and all 7,545 test predictions byte-identical. Delivery 885 s with 5 agents at once vs 886 s with 4: the slowest agent sets the time |
| 4 | README in the OSM quickstart's shape | ✅ | TL;DR with a timed lifecycle table, scenario, roles, setup, shortcut, stages with "Expect", results, what's left out, layout, licence, attribution |
| 5 | Push; fresh-clone check | ⬜ | |
