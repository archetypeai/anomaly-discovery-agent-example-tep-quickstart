#!/usr/bin/env python3
"""Step 3 charts (local), from step3_run.py's outputs:

  walkthrough_out/step3_score.svg  anomaly score over time, normal vs faulty run,
                                   fault start and alarm threshold marked
  walkthrough_out/step3_pca.svg    2-D PCA, fitted on both runs' windows, of each window's
                                   Omega embedding (33 sensors x 768) plus its per-sensor
                                   features (std, range, slope, median), the two blocks
                                   scaled to equal total variance; coloured by the agent's
                                   own verdict (blue normal, red anomaly)
  walkthrough_out/step3.md         the talking points' Step 3 end text, filled in
  walkthrough_out/step3.json       the numbers behind both charts

The per-sensor features are recomputed locally from each window's input rows: the batch
output carries the embeddings and the score, not the Anomaly Detection Agent's features.
"""
import json

import numpy as np
import pandas as pd

from common import BLUE, GREY, ONSET_H, OUT, RED, REPO, RUN_H, SAMPLE_H, SKILL, dump, polyline, svg, text, write

DIR = OUT / "step3"
CH = json.loads((REPO / "data" / "roles" / "manifest.json").read_text())["channels"]
V = json.loads((DIR / "state.json").read_text())["blueprint"]["values"]
W, THR = V["window_size"], V["threshold"]


def load(name, src):
    """Valid windows of one output: embedding, local features, score, hour the window ends."""
    o = pd.read_csv(DIR / f"{name}.csv")
    o = o[~o.invalid.astype(str).str.lower().eq("true")].reset_index(drop=True)
    x = pd.read_csv(src)
    pos = {t: i for i, t in enumerate(x.timestamp)}
    vals, tt = x[CH].to_numpy(), np.arange(W)
    feats = []
    for ft in o.finish_timestamp:
        win = vals[pos[ft] - W + 1: pos[ft] + 1]
        feats.append(np.concatenate([win.std(0), np.ptp(win, 0), np.polyfit(tt, win, 1)[0], np.median(win, 0)]))
    emb = np.stack([np.concatenate([json.loads(c) for c in row])
                    for row in o[[f"embedding_{c}" for c in CH]].to_numpy()])
    hours = (o.finish_timestamp.to_numpy() - x.timestamp.iloc[0]) / 3600 + SAMPLE_H
    return {"emb": emb, "feat": np.array(feats), "score": o.anomaly_score.to_numpy(), "hours": hours,
            "anomaly": o.predicted_label.astype(str).str.lower().eq("anomaly").to_numpy()}


def pca(runs):
    """z-score each column on both runs' windows, scale each block to total variance 1, PCA on them."""
    lib = list(runs.values())
    blocks = []
    for k in ("emb", "feat"):
        Lb = np.concatenate([r[k] for r in lib])
        sd = Lb.std(0)
        sd[sd == 0] = 1
        blocks.append((k, Lb.mean(0), sd * np.sqrt(Lb.shape[1])))
    fuse = lambda r: np.hstack([(r[k] - mu) / sd for k, mu, sd in blocks])  # noqa: E731
    X = np.vstack([fuse(r) for r in lib])
    mean = X.mean(0)
    Xc = X - mean
    ev, evec = np.linalg.eigh(Xc @ Xc.T)          # n x n Gram matrix: n windows << 25,476 columns
    top = np.argsort(ev)[::-1][:2]
    axes = (Xc.T @ evec[:, top]) / np.sqrt(ev[top])
    explained = (ev[top] / (len(X) - 1)) / Xc.var(0, ddof=1).sum()
    return {n: (fuse(r) - mean) @ axes for n, r in runs.items()}, explained


def score_chart(runs):
    w, L, R, T, B = 680, 52, 664, 24, 252
    X = lambda h: L + (R - L) * h / RUN_H  # noqa: E731
    hi = max(r["score"].max() for r in runs.values()) * 1.08
    lo = 0.8
    Y = lambda v: B - (B - T) * (min(max(v, lo), hi) - lo) / (hi - lo)  # noqa: E731
    step = 1 if hi < 4 else 2 if hi < 10 else 5
    b = []
    for t in np.arange(1, hi, step):
        b += [f'<line x1="{L}" x2="{R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="{GREY}" stroke-opacity="0.2"/>',
              text(L - 8, Y(t) + 4, f"{t:g}", "end")]
    b += [text(X(h), B + 18, f"{h} h", "middle") for h in range(0, int(RUN_H) + 1, 4)]
    b += [f'<rect x="{X(ONSET_H):.1f}" y="{T}" width="{X(RUN_H) - X(ONSET_H):.1f}" height="{B - T}" fill="{RED}" fill-opacity="0.06"/>',
          f'<line x1="{X(ONSET_H):.1f}" x2="{X(ONSET_H):.1f}" y1="{T}" y2="{B}" stroke="{RED}" stroke-width="1.5" stroke-dasharray="4 3"/>',
          text(X(ONSET_H) + 6, T + 12, "fault starts (hour 8)"),
          f'<line x1="{L}" x2="{R}" y1="{Y(THR):.1f}" y2="{Y(THR):.1f}" stroke="{GREY}" stroke-width="1.5" stroke-dasharray="2 3"/>',
          text(R, Y(THR) - 6, f"alarm threshold {THR:g}", "end"),
          f'<rect x="452" y="44" width="10" height="3" fill="{RED}"/>', text(468, 50, "faulty run (IDV 1)"),
          f'<rect x="572" y="44" width="10" height="3" fill="{BLUE}"/>', text(588, 50, "normal run"),
          text(14, (T + B) / 2, "anomaly score", "middle", f'transform="rotate(-90 14 {(T + B) / 2:.0f})"')]
    for n, c in (("normal_run", BLUE), ("fault_run", RED)):
        b.append(polyline([(X(h), Y(s)) for h, s in zip(runs[n]["hours"], runs[n]["score"])], c, 2))
    return svg(w, B + 30, "Anomaly score over time, normal vs faulty run",
               "The normal run stays near 1; the faulty run climbs far past the threshold after the fault starts.", "".join(b),
               heading="Anomaly Score from Newton Agent")


def _loops(F, t, step):
    """Closed outlines of the region where the grid F >= t (marching squares; F is 0 on its
    border, so every outline closes). Returns lists of (x, y) in pixels."""
    ny, nx = F.shape
    A = F >= t
    pt, link = {}, {}

    def edge(i, j, horiz):          # the crossing on the edge from (i, j) rightwards or downwards
        key = (i, j, horiz)
        if key not in pt:
            i2, j2 = (i, j + 1) if horiz else (i + 1, j)
            f = (t - F[i, j]) / (F[i2, j2] - F[i, j])
            pt[key] = ((j + (j2 - j) * f) * step, (i + (i2 - i) * f) * step)
        return key

    for i in range(ny - 1):
        for j in range(nx - 1):
            tl, tr, br, bl = A[i, j], A[i, j + 1], A[i + 1, j + 1], A[i + 1, j]
            case = tl * 8 + tr * 4 + br * 2 + bl
            if case in (0, 15):
                continue
            T, R, B, L = (i, j, True), (i, j + 1, False), (i + 1, j, True), (i, j, False)
            pairs = {1: [(L, B)], 2: [(B, R)], 3: [(L, R)], 4: [(T, R)], 6: [(T, B)], 7: [(L, T)],
                     8: [(L, T)], 9: [(T, B)], 11: [(T, R)], 12: [(L, R)], 13: [(B, R)], 14: [(L, B)]}
            if case in (5, 10):     # saddle: join through the middle only if the middle is inside
                mid = F[i:i + 2, j:j + 2].mean() >= t
                pairs[5] = [(L, T), (B, R)] if mid else [(L, B), (T, R)]
                pairs[10] = [(L, B), (T, R)] if mid else [(L, T), (B, R)]
            for e1, e2 in pairs[case]:
                k1, k2 = edge(*e1), edge(*e2)
                link.setdefault(k1, []).append(k2)
                link.setdefault(k2, []).append(k1)
    loops, seen = [], set()
    for start in link:
        if start in seen:
            continue
        loop, prev, cur = [], None, start
        while cur not in seen:
            seen.add(cur)
            loop.append(pt[cur])
            nxt = [n for n in link[cur] if n != prev] or link[cur]
            prev, cur = cur, nxt[0]
        if len(loop) > 3:
            loops.append(loop)
    return loops


def _smooth_path(loop):
    """A closed path through the middles of a loop's sides, its corners as curve handles."""
    n = len(loop)
    mid = [((loop[i][0] + loop[(i + 1) % n][0]) / 2, (loop[i][1] + loop[(i + 1) % n][1]) / 2) for i in range(n)]
    d = [f"M{mid[-1][0]:.0f} {mid[-1][1]:.0f}"]
    d += [f"Q{loop[i][0]:.0f} {loop[i][1]:.0f} {mid[i][0]:.0f} {mid[i][1]:.0f}" for i in range(n)]
    return "".join(d) + "Z"


def _place(ax, ay, tw, th, dots, taken, w, H, radii):
    """Where to centre a tw x th tag near (ax, ay): the closest spot that is inside the
    chart, off every other tag and as clear of the dots as it can be."""
    best, best_score = (ax, ay + radii[0]), -1e9
    for r in radii:
        for ang in np.arange(0, 360, 30):
            cx, cy = ax + r * np.cos(np.radians(ang)), ay + r * np.sin(np.radians(ang))
            x0, y0, x1, y1 = cx - tw / 2, cy - th / 2, cx + tw / 2, cy + th / 2
            if x0 < 4 or y0 < 4 or x1 > w - 4 or y1 > H - 4:
                continue
            if any(x0 < u1 + 6 and u0 - 6 < x1 and y0 < v1 + 6 and v0 - 6 < y1 for u0, v0, u1, v1 in taken):
                continue
            gap = np.hypot(np.maximum.reduce([x0 - dots[:, 0], dots[:, 0] - x1, np.zeros(len(dots))]),
                           np.maximum.reduce([y0 - dots[:, 1], dots[:, 1] - y1, np.zeros(len(dots))])).min()
            score = min(gap, 10) - 0.02 * r
            if score > best_score:
                best, best_score = (cx, cy), score
    taken.append((best[0] - tw / 2, best[1] - th / 2, best[0] + tw / 2, best[1] + th / 2))
    return best


def pca_chart(P, runs):
    """The two test runs' windows on their own 2 PCA axes, grouped by the agent's verdict:
    blue = normal, red = anomaly. Each group is drawn as its windows over soft density
    contours (where its windows crowd, the colour deepens) with a name tag."""
    w, h, pad, step, sigma, strip = 680, 470, 56, 8, 22, 40      # strip: the legend's row at the bottom
    H = h - strip
    levels = (0.07, 0.16, 0.28, 0.42, 0.58, 0.76)      # contour heights, as shares of a group's peak
    allp = np.vstack(list(P.values()))
    (x0, y0), (x1, y1) = allp.min(0), allp.max(0)
    span = max(x1 - x0, (y1 - y0) * (w - 2 * pad) / (H - 2 * pad))
    k, cx, cy = (w - 2 * pad) / (span * 1.06), (x0 + x1) / 2, (y0 + y1) / 2
    to_px = lambda p: np.column_stack([w / 2 + (p[:, 0] - cx) * k, H / 2 - (p[:, 1] - cy) * k])  # noqa: E731
    xy = to_px(allp)
    bad = np.concatenate([runs[n]["anomaly"] for n in P]).astype(bool)

    gy, gx = np.mgrid[0:H // step + 1, 0:w // step + 1] * step
    body = [f'<defs><pattern id="dotgrid" width="20" height="20" patternUnits="userSpaceOnUse">'
            f'<circle cx="10" cy="10" r="1" fill="{GREY}" fill-opacity="0.35"/></pattern></defs>'
            f'<rect x="0" y="0" width="{w}" height="{H}" fill="url(#dotgrid)"/>']
    groups = []
    for label, colour, pts in (("NORMAL OPERATION", BLUE, xy[~bad]), ("ANOMALY", RED, xy[bad])):
        if not len(pts):
            continue
        F = np.exp(-((gx[..., None] - pts[:, 0]) ** 2 + (gy[..., None] - pts[:, 1]) ** 2) / (2 * sigma ** 2)).sum(-1)
        F[[0, -1], :] = 0
        F[:, [0, -1]] = 0
        d = "".join(f'<path d="{"".join(_smooth_path(lp) for lp in _loops(F, F.max() * lv, step))}"/>'
                    for lv in levels)
        body.append(f'<g fill="{colour}" fill-opacity="0.1" fill-rule="evenodd">{d}</g>')
        iy, ix = np.unravel_index(F.argmax(), F.shape)
        groups.append((label, colour, ix * step, iy * step))

    for colour, pts in ((BLUE, xy[~bad]), (RED, xy[bad])):
        body.append(f'<g fill="{colour}" fill-opacity="0.9">'
                    + "".join(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3"/>' for x, y in pts) + "</g>")

    taken = []
    for label, colour, gx0, gy0 in groups:  # a name tag beside the group's densest spot
        tw = 9 * len(label) + 22
        tx, ty = _place(gx0, gy0, tw, 26, xy, taken, w, H, (44, 58, 72, 90))
        body.append(
            f'<rect x="{tx - tw / 2:.0f}" y="{ty - 13:.0f}" width="{tw}" height="26" rx="6" style="fill:var(--surface-2,#ffffff)"/>'
            f'<rect x="{tx - tw / 2:.0f}" y="{ty - 13:.0f}" width="{tw}" height="26" rx="6" fill="{colour}" fill-opacity="0.12" stroke="{colour}"/>'
            f'<text x="{tx:.0f}" y="{ty + 5:.0f}" text-anchor="middle" fill="{colour}" font-size="14" letter-spacing="1" '
            f'style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace">{label}</text>')

    ly, lx = h - 14, 16
    for s, mark in (("normal", f'<circle cx="4" cy="-4" r="3.6" fill="{BLUE}"/>'),
                    ("anomaly", f'<circle cx="4" cy="-4" r="3.6" fill="{RED}"/>')):
        body += [f'<g transform="translate({lx},{ly})">{mark}</g>', text(lx + 16, ly, s)]
        lx += 16 + 6.4 * len(s) + 26
    return svg(w, h, "Map of the two new runs' windows",
               "Each dot is one 2.4-hour window, blue where the Anomaly Detection Agent said normal and red "
               "where it said anomaly, over soft contours that deepen where a group's windows crowd. The "
               "normal windows form one tight blue cluster; the anomaly windows spread far away from it.",
               "".join(body), heading="Embeddings from Newton",
               subheading="Each dot is 2.4 hours of plant data. Dots close together behaved alike.")


def first_alarm(score, hours, n=3):
    """Hour of the first n consecutive windows over the threshold (one spike is not an alarm)."""
    over = score > THR
    hit = next((i for i in range(len(over) - n + 1) if over[i:i + n].all()), None)
    return None if hit is None else round(float(hours[hit + n - 1]), 1)


def main():
    runs = {n: load(n, DIR / f"input_{n}.csv") for n in ("normal_run", "fault_run")}
    P, explained = pca(runs)
    paths = [write("step3_score.svg", score_chart(runs)),
             write("step3_pca.svg", pca_chart(P, runs))]
    summary = {"charts": [str(p) for p in paths], "threshold": THR,
               "pca_explained": [round(float(e), 3) for e in explained],
               "columns": {"omega_embedding": len(CH) * 768, "per_sensor_features": len(CH) * 4}}
    for n, r in runs.items():
        pre, post = r["hours"] <= ONSET_H, r["hours"] > ONSET_H
        summary[n] = {"windows": int(len(r["score"])), "median_before": round(float(np.median(r["score"][pre])), 3),
                      "median_after": round(float(np.median(r["score"][post])), 3),
                      "max": round(float(r["score"].max()), 3),
                      "over_threshold_after": f"{int((r['score'][post] > THR).sum())}/{int(post.sum())}",
                      "first_sustained_alarm_h": first_alarm(r["score"], r["hours"]),
                      "map": {"n": int(len(r["anomaly"])), "red": int(r["anomaly"].sum()),
                              "n_after": int(post.sum()), "red_after": int(r["anomaly"][post].sum())}}
    write("step3.json", dump(summary))
    print(dump(summary))
    write("step3.md", end_text(summary))
    print("\n--- walkthrough_out/step3.md (show this exactly, after the map and the score chart) ---\n"
          + end_text(summary))


def end_text(s: dict) -> str:
    """The talking points' Step 3 end text, its {fields} filled in from this run."""
    tp = (SKILL / "references" / "talking-points.md").read_text()
    template = tp.split("<!-- step3-end -->\n", 1)[1].split("<!-- /step3-end -->", 1)[0]
    f, n = s["fault_run"], s["normal_run"]
    fa, na = f["first_sustained_alarm_h"], n["first_sustained_alarm_h"]
    score = ("The faulty run never raised an alarm (3 windows in a row over the threshold)" if fa is None else
             f"The faulty run raised an alarm (3 windows in a row over the threshold) at hour {fa:g}, "
             f"{fa - ONSET_H:.1f} hours after the fault started")
    score += "; the normal run never did." if na is None else f"; the normal run raised a false alarm at hour {na:g}."
    nr, fr = n["map"], f["map"]
    map_sentence = (f"The agent marked {nr['red']} of the normal run's {nr['n']} windows red, and "
                    f"{fr['red_after']} of the faulty run's {fr['n_after']} windows after the fault.")
    links = json.loads((DIR / "links.json").read_text())
    return template.format(map_sentence=map_sentence, score_sentence=score, deployment_link=links["deployment"])

if __name__ == "__main__":
    main()
