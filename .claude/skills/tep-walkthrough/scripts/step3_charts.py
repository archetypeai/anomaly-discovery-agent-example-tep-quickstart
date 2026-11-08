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
               "The normal run stays near 1; the faulty run climbs far past the threshold after the fault starts.", "".join(b))


def pca_chart(P, runs):
    """The two test runs' windows on their own 2 PCA axes, coloured by the agent's verdict:
    blue = normal, red = anomaly. Circles are the normal run, squares the faulty run."""
    w, h, pad = 680, 470, 36
    allp = np.vstack(list(P.values()))
    (x0, y0), (x1, y1) = allp.min(0), allp.max(0)
    span = max(x1 - x0, (y1 - y0) * (w - 2 * pad) / (h - 2 * pad - 44))
    k, cx, cy = (w - 2 * pad) / (span * 1.06), (x0 + x1) / 2, (y0 + y1) / 2
    px = lambda a: w / 2 + (a - cx) * k  # noqa: E731
    py = lambda b: (h - 44) / 2 + 6 - (b - cy) * k  # noqa: E731
    circle = lambda x, y, c: f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3.6" fill="{c}" fill-opacity="0.85"/>'  # noqa: E731
    square = lambda x, y, c: (f'<rect x="{x - 3.4:.0f}" y="{y - 3.4:.0f}" width="6.8" height="6.8" '  # noqa: E731
                              f'fill="{c}" fill-opacity="0.85"/>')
    body = []
    for name, mark in (("normal_run", circle), ("fault_run", square)):
        body += [mark(px(a), py(b), RED if bad else BLUE)
                 for (a, b), bad in zip(P[name], runs[name]["anomaly"])]
    legend = [("normal run", circle(0, 0, GREY)), ("faulty run (IDV 1)", square(0, 0, GREY)),
              ("the agent said normal", circle(0, 0, BLUE)), ("the agent said anomaly", circle(0, 0, RED))]
    for i, (s, mark) in enumerate(legend):
        lx, ly = pad + i * 160, h - 14
        body += [f'<g transform="translate({lx + 4},{ly - 4})">{mark}</g>', text(lx + 14, ly, s)]
    return svg(w, h, "Map of the two new runs' windows",
               "Each dot is one 2.4-hour window, blue where the Anomaly Detection Agent said normal and red "
               "where it said anomaly. The normal run's circles stay in one blue cluster; the faulty run's "
               "squares start there, then turn red and move far away after the fault.", "".join(body))


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
    return template.format(map_sentence=map_sentence, score_sentence=score, bundle_link=links["bundle"])

if __name__ == "__main__":
    main()
