#!/usr/bin/env python3
"""Step 3 charts (local), from step3_run.py's outputs:

  walkthrough_out/step3_score.svg  anomaly score over time, normal vs faulty run,
                                   fault start and alarm threshold marked
  walkthrough_out/step3_pca.svg    2-D PCA, fitted on the library windows, of each window's
                                   Omega embedding (33 sensors x 768) plus its per-sensor
                                   features (std, range, slope, median), the two blocks
                                   scaled to equal total variance
  walkthrough_out/step3.json       the numbers behind both charts

The per-sensor features are recomputed locally from each window's input rows: the batch
output carries the embeddings and the score, not the detector's features.
"""
import json

import numpy as np
import pandas as pd

from common import BLUE, GREY, ONSET_H, OUT, RED, RED_RAMP, REPO, SAMPLE_H, dump, polyline, svg, text, write

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
    return {"emb": emb, "feat": np.array(feats), "score": o.anomaly_score.to_numpy(), "hours": hours}


def pca(lib, runs):
    """z-score each column on the library, scale each block to total variance 1, PCA on the library."""
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
    return Xc @ axes, {n: (fuse(r) - mean) @ axes for n, r in runs.items()}, explained, len(X)


def score_chart(runs):
    w, L, R, T, B = 680, 52, 664, 24, 252
    X = lambda h: L + (R - L) * h / 48  # noqa: E731
    hi = max(r["score"].max() for r in runs.values()) * 1.08
    lo = 0.8
    Y = lambda v: B - (B - T) * (min(max(v, lo), hi) - lo) / (hi - lo)  # noqa: E731
    step = 1 if hi < 4 else 2 if hi < 10 else 5
    b = []
    for t in np.arange(1, hi, step):
        b += [f'<line x1="{L}" x2="{R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="{GREY}" stroke-opacity="0.2"/>',
              text(L - 8, Y(t) + 4, f"{t:g}", "end")]
    b += [text(X(h), B + 18, f"{h} h", "middle") for h in range(0, 49, 8)]
    b += [f'<rect x="{X(ONSET_H):.1f}" y="{T}" width="{X(48) - X(ONSET_H):.1f}" height="{B - T}" fill="{RED}" fill-opacity="0.06"/>',
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


def pca_chart(P_lib, P, fault_hours, explained, n_lib_files):
    w, h, pad = 680, 500, 36
    allp = np.vstack([P_lib, *P.values()])
    (x0, y0), (x1, y1) = allp.min(0), allp.max(0)
    span = max(x1 - x0, (y1 - y0) * (w - 2 * pad) / (h - 2 * pad - 44))
    k, cx, cy = (w - 2 * pad) / (span * 1.06), (x0 + x1) / 2, (y0 + y1) / 2
    px = lambda a: w / 2 + (a - cx) * k  # noqa: E731
    py = lambda b: (h - 44) / 2 + 12 - (b - cy) * k  # noqa: E731

    def ramp(t):
        t = float(np.clip(t, 0, 1)) * (len(RED_RAMP) - 1)
        i = min(int(t), len(RED_RAMP) - 2)
        a, c = (np.array([int(s[j:j + 2], 16) for j in (1, 3, 5)]) for s in RED_RAMP[i:i + 2])
        return "#" + "".join(f"{int(round(v)):02x}" for v in a + (c - a) * (t - i))

    dot = lambda a, b, r: f'<circle cx="{px(a):.0f}" cy="{py(b):.0f}" r="{r}"/>'  # noqa: E731
    body = [text(w - pad, 16, f"PC1 {explained[0]:.0%} · PC2 {explained[1]:.0%} of library variance", "end"),
            f'<g fill="{GREY}" fill-opacity="0.35">' + "".join(dot(a, b, 2.2) for a, b in P_lib) + "</g>",
            f'<g fill="{BLUE}" fill-opacity="0.85">' + "".join(dot(a, b, 3) for a, b in P["normal_run"]) + "</g>",
            f'<g fill="none" stroke="{RED_RAMP[0]}" stroke-width="1.4">'
            + "".join(dot(a, b, 3) for (a, b), hh in zip(P["fault_run"], fault_hours) if hh <= ONSET_H) + "</g>"]
    body += [dot(a, b, 3.4).replace("/>", f' fill="{ramp((hh - ONSET_H) / (48 - ONSET_H))}"/>')
             for (a, b), hh in zip(P["fault_run"], fault_hours) if hh > ONSET_H]
    legend = [(f"library (normal, {n_lib_files} runs)", f'<circle r="4" fill="{GREY}" fill-opacity="0.5"/>'),
              ("normal run", f'<circle r="4" fill="{BLUE}"/>'),
              ("faulty run, before fault", f'<circle r="3.5" fill="none" stroke="{RED_RAMP[0]}" stroke-width="1.4"/>'),
              ("after fault: light → dark over 40 h",
               "".join(f'<circle cx="{i * 9}" r="4" fill="{c}"/>' for i, c in enumerate(RED_RAMP)))]
    for i, (s, mark) in enumerate(legend):
        lx, ly, off = pad + (i % 2) * 300, h - 30 + (i // 2) * 20, 36 if "light" in s else 10
        body += [f'<g transform="translate({lx + 4},{ly - 4})">{mark}</g>', text(lx + off + 4, ly, s)]
    return svg(w, h, "2-D PCA map of window fingerprints",
               "Library windows in grey and the normal run in blue share one cloud; the faulty run leaves it "
               "after the fault, swings wide, then settles into its own cluster.", "".join(body))


def first_alarm(score, hours, n=3):
    """Hour of the first n consecutive windows over the threshold (one spike is not an alarm)."""
    over = score > THR
    hit = next((i for i in range(len(over) - n + 1) if over[i:i + n].all()), None)
    return None if hit is None else round(float(hours[hit + n - 1]), 1)


def main():
    lib_names = sorted(p.stem for p in DIR.glob("tep_ref_normal_sim*.csv"))
    lib = [load(n, REPO / "data" / "roles" / "library" / f"{n}.csv") for n in lib_names]
    runs = {n: load(n, DIR / f"input_{n}.csv") for n in ("normal_run", "fault_run")}
    P_lib, P, explained, n_win = pca(lib, runs)
    paths = [write("step3_score.svg", score_chart(runs)),
             write("step3_pca.svg", pca_chart(P_lib, P, runs["fault_run"]["hours"], explained, len(lib)))]
    summary = {"charts": [str(p) for p in paths], "threshold": THR, "library_files": len(lib),
               "library_windows": n_win, "pca_explained": [round(float(e), 3) for e in explained],
               "columns": {"omega_embedding": len(CH) * 768, "per_sensor_features": len(CH) * 4}}
    for n, r in runs.items():
        pre, post = r["hours"] <= ONSET_H, r["hours"] > ONSET_H
        summary[n] = {"windows": int(len(r["score"])), "median_before": round(float(np.median(r["score"][pre])), 3),
                      "median_after": round(float(np.median(r["score"][post])), 3),
                      "max": round(float(r["score"].max()), 3),
                      "over_threshold_after": f"{int((r['score'][post] > THR).sum())}/{int(post.sum())}",
                      "first_sustained_alarm_h": first_alarm(r["score"], r["hours"])}
    write("step3.json", dump(summary))
    print(dump(summary))


if __name__ == "__main__":
    main()
