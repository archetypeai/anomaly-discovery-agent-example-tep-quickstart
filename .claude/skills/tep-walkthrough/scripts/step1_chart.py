#!/usr/bin/env python3
"""Step 1 (local, no API key): the four data roles, and one sensor in 3 normal vs 2 faulty runs.

Writes walkthrough_out/step1_runs.svg (one row per run, shared scale) and prints the role
table and the numbers behind the chart as JSON.
"""
import json

import pandas as pd

from common import BLUE, GREY, ONSET_H, ROLES, SAMPLE_H, YELLOW, polyline, svg, text, write

SENSOR, SENSOR_NAME = "xmeas_18", "stripper temperature"
NORMAL_SIMS = 3
FAULTS = [("idv_01", "feed ratio step"), ("idv_10", "random feed temp.")]


def runs():
    v = pd.read_csv(ROLES / "delivery" / "tep_val_normal.csv")
    vl = pd.read_csv(ROLES / "labels" / "tep_val_normal_labels.csv")
    out = []
    for i, sim in enumerate(sorted(vl.simulationrun.unique())[:NORMAL_SIMS], 1):
        out.append((f"normal {i}", f"sim {sim}", BLUE, v[SENSOR][(vl.simulationrun == sim).values].to_numpy()))
    d = pd.read_csv(ROLES / "test" / "tep_eval_slice_02.csv")
    dl = pd.read_csv(ROLES / "labels" / "tep_eval_slice_02_labels.csv")
    for fid, name in FAULTS:
        out.append((f"anomaly: IDV {int(fid[4:])}", name, YELLOW, d[SENSOR][(dl.fault_id == fid).values].to_numpy()))
    return out


def chart(rows):
    L, R, T, RH, GAP, YMIN, YMAX = 150, 664, 8, 64, 10, -6.5, 17
    X = lambda h: L + (R - L) * h / 48  # noqa: E731
    body, y0 = [], T
    for i, (name, sub, color, x) in enumerate(rows):
        if i == NORMAL_SIMS:                       # divider between normal and anomaly rows
            y0 += 14
            body.append(f'<line x1="12" x2="{R}" y1="{y0-12}" y2="{y0-12}" stroke="{GREY}" stroke-opacity="0.35"/>')
        Y = lambda v, y0=y0: y0 + RH - RH * (min(max(v, YMIN), YMAX) - YMIN) / (YMAX - YMIN)  # noqa: E731
        body += [f'<rect x="{L}" y="{y0}" width="{R-L}" height="{RH}" fill="{color}" fill-opacity="0.04"/>',
                 f'<line x1="{L}" x2="{R}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="{GREY}" stroke-opacity="0.3"/>',
                 f'<text class="th" x="12" y="{y0 + RH / 2 - 2:.0f}" font-size="13">{name}</text>',
                 text(12, y0 + RH / 2 + 14, sub),
                 text(L - 6, Y(0) + 4, "0", "end"), text(L - 6, Y(15) + 4, "15", "end"),
                 # every 4th sample (12 min apart) keeps the file small enough to show inline
                 polyline([(X(j * SAMPLE_H), Y(v)) for j, v in enumerate(x) if j % 4 == 0], color)]
        y0 += RH + GAP
    end = y0 - GAP
    body += [f'<line x1="{X(ONSET_H):.1f}" x2="{X(ONSET_H):.1f}" y1="{T}" y2="{end}" stroke="{GREY}" stroke-width="1.2" stroke-dasharray="4 3"/>',
             text(X(ONSET_H) + 5, T + 13, "faults start (hour 8)")]
    body += [text(X(h), end + 16, f"{h} h", "middle") for h in range(0, 49, 8)]
    return svg(680, end + 26, f"{SENSOR_NAME.capitalize()}: 3 normal runs vs 2 fault runs",
               "One row per run on a shared scale. Normal runs stay flat near zero; the fault runs match them "
               "until hour 8, then IDV 1 jumps far above and IDV 10 swings widely.", "".join(body))


def main():
    m = json.loads((ROLES / "manifest.json").read_text())
    rows = runs()
    path = write("step1_runs.svg", chart(rows))
    post = int(ONSET_H / SAMPLE_H)
    print(json.dumps({
        "chart": str(path),
        "sensor": f"{SENSOR} ({SENSOR_NAME}), z-scored with the library's statistics",
        "roles": {"library": f"{len(m['library'])} fault-free 25 h runs, one file each",
                  "validation": [f["file"] for f in m["validation"]],
                  "test": [f["file"] for f in m["test"]],
                  "delivery": [f["file"] for f in m["delivery"]]},
        "rows": [{"row": n, "source": s, "range": [round(float(x.min()), 1), round(float(x.max()), 1)],
                  "after_onset_mean": round(float(x[post:].mean()), 2)} for n, s, _, x in rows],
    }, indent=1))


if __name__ == "__main__":
    main()
