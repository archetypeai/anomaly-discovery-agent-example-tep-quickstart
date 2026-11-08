"""Shared paths, design tokens and small SVG helpers for the walkthrough scripts.

Run the scripts with the repo's virtual environment from the repo root, e.g.
    .venv/bin/python .claude/skills/tep-walkthrough/scripts/step2_optimize.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
REPO = SKILL.parents[2]
OUT = REPO / "walkthrough_out"          # gitignored; every chart and run output lands here
ROLES = REPO / "data" / "roles"
sys.path[:0] = [str(REPO / "fit"), str(REPO)]

# Archetype AI design system (@archetypeai/ds-lib-tokens v0.20.0), resolved to hex.
# Mid-tone stops are used so each colour reads on both light and dark backgrounds.
BLUE = "#2b7fff"      # --atai-neutral (blue-500): normal operation
RED = "#ff6467"       # --atai-critical (red-400): fault / alarm
GREY = "#71717b"      # --muted-foreground (zinc-500): grid, legend shapes, threshold
RED_RAMP = ["#ffc9c9", "#ff6467", "#c10007", "#82181a"]   # red-200 → red-400 → red-700 → red-900
FONT = "font-family:'PP Neue Montreal',ui-sans-serif,system-ui,-apple-system,sans-serif"

ONSET_H = 8.0          # every faulty run is normal for 8 h, then the fault starts
SAMPLE_H = 0.05        # one sample every 3 minutes
RUN_H = 24.0           # every validation, test and delivery run is 24 h long


def svg(width: int, height: int, title: str, desc: str, body: str) -> str:
    """A standalone SVG. Text uses class "ts" so inline hosts theme it; fill is the fallback."""
    return (f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" '
            f'style="{FONT}"><title>{title}</title><desc>{desc}</desc>{body}</svg>')


def text(x, y, s, anchor="start", extra=""):
    return f'<text class="ts" x="{x:.0f}" y="{y:.0f}" text-anchor="{anchor}" fill="{GREY}" font-size="12" {extra}>{s}</text>'


def polyline(points, color, width=1.6, extra=""):
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" {extra}/>'


def write(name: str, content: str) -> Path:
    OUT.mkdir(exist_ok=True)
    p = OUT / name
    p.write_text(content)
    return p


def console_base(api_base: str) -> str:
    """The console lives at the deployment root: https://<host>/console/dashboard/..."""
    return api_base.removesuffix("/api") + "/console/dashboard"


def dump(obj) -> str:
    return json.dumps(obj, indent=1)
