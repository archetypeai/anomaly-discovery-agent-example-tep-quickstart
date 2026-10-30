#!/usr/bin/env python3
"""Stage 9, once -- the reference library's embeddings, for app-serving/'s embedding view.

    python3 fit/app_blueprint.py             # first, once: the winning configuration with embeddings on
    python3 fit/library_embeddings.py        # 40 batch runs (~8 min), then the view

The promoted detector was fitted on the library's 40 fault-free runs at the
trial's window 48 and step 8, but it is a registry artifact (`aar_…`) with no
download route, so its reference windows can't be read back. They can be
recomputed: a package of fit/app_blueprint.py's blueprint (the winning
configuration, refitted with `output_embeddings: true`, since a package can't
turn embeddings on) runs each library file through the same encoder, on the
same windows, and returns each
window's 33 x 768 Omega embedding with its score (2,280 windows in all).

The view is PCA 1-2 of those embeddings, whitened, in the layout the app
reads: `app-serving/static/detector-view.{json,bin}` holds the 2,280 reference
points, the mean and the two projection rows, so a live window's embedding lands
in the same coordinates. The detector's own PCA is fitted on these embeddings
too, so the axes should be its leading components up to sign; the artifact
can't be read to confirm it.

Outputs: fit/out/library_embeddings/ (the 40 batch outputs, ~0.6 GB, not
committed), fit/out/library_embeddings.json (summary), the view files. Ids go to
fit/out/library_state.json, so a rerun resumes and fit/cleanup.py can delete them.
"""
from __future__ import annotations

import datetime
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from atai import (REPO, ROLES, agents_base, load_dotenv, load_state, log, manifest, request, save_state,
                  state_path, upload_all)
from ad_api import create_package, deployment, download_results, poll_agent

OUT = REPO / "fit" / "out" / "library_embeddings"
VIEW = REPO / "app-serving" / "static"
TIMEOUT_S = 3600
lock = threading.Lock()


def deliver(m: dict, bp: dict) -> list[Path]:
    """One batch agent per library file, outputs checked complete; resumable."""
    STATE = state_path("library")
    state = load_state(STATE)
    save = lambda: save_state(STATE, state)  # noqa: E731
    if "bundle" in state or state.get("blueprint", bp["key"]) != bp["key"]:
        sys.exit(f"{STATE} and fit/out/library_embeddings/ are from an earlier run: move them aside")
    if "package" not in state:
        pkg = create_package(bp["id"], "AD TEP library embeddings")
        state.update(blueprint=bp["key"], package=pkg["id"])
        save()
        log(f"package {pkg['id']} on {bp['key']} (step {bp['values']['step_size']}, embeddings on)")
    paths = [ROLES / f["file"] for f in m["library"]]
    ids = upload_all(paths)
    OUT.mkdir(parents=True, exist_ok=True)

    def one(src: Path) -> Path | None:
        dst = OUT / src.name
        if dst.exists() and dst.stat().st_size:
            return dst
        runs = state.setdefault("agents", {})
        if src.stem not in runs:
            agent = request("POST", f"{agents_base()}/instances", body={
                "package_id": state["package"], "connectors": {"source": [{"type": "file", "id": ids[src], "format": "csv"}]}})
            with lock:
                runs[src.stem] = agent["id"]
                save()
        poll_agent(runs[src.stem], TIMEOUT_S, interval_s=15)
        if download_results(runs[src.stem], str(dst), source_csv=str(src)):
            log(f"{src.name}: done")
            return dst
        with lock:
            runs.pop(src.stem)
            save()
        log(f"{src.name}: no complete output; rerun to retry")
        return None

    with ThreadPoolExecutor(4) as pool:
        got = list(pool.map(one, paths))
    if not all(got):
        sys.exit(f"{got.count(None)} of {len(got)} outputs missing: rerun to resume")
    return got


def main() -> int:
    load_dotenv()
    m = manifest()
    app = load_state(state_path("app_blueprint"))
    test = load_state(state_path("test"))
    if not app.get("blueprint") or app.get("source") != test.get("blueprint", {}).get("key") \
            or deployment(app["endpoint"]) != deployment(agents_base()):
        sys.exit("no app-serving blueprint for this promoted blueprint and deployment: run fit/app_blueprint.py")
    bp = app["blueprint"]
    channels, window, step = m["channels"], bp["values"]["window_size"], bp["values"]["step_size"]
    outs = deliver(m, bp)

    vecs, scores, labels = [], [], []
    for p in outs:
        df = pd.read_csv(p)
        bad = df.invalid.astype(str).str.lower().eq("true")
        if bad.any():
            log(f"{p.name}: {int(bad.sum())} invalid windows dropped")
        df = df[~bad]
        vecs.append(np.stack([np.concatenate([json.loads(r[f"embedding_{c}"]) for c in channels])
                              for _, r in df.iterrows()]).astype(np.float32))
        scores += df.anomaly_score.tolist()
        labels += df.predicted_label.tolist()
    X = np.concatenate(vecs).astype(np.float64)        # float64: in float32 the Gram product raised overflow warnings
    n, dim = X.shape
    log(f"{n:,} windows x {dim:,} values")

    mean = X.mean(axis=0)
    Xc = X - mean
    # PCA through the n x n Gram matrix: n (2,280) is far smaller than dim (25,344)
    eigval, eigvec = np.linalg.eigh(Xc @ Xc.T)
    top = np.argsort(eigval)[::-1][:2]
    var = eigval[top] / (n - 1)
    axes = (Xc.T @ eigvec[:, top]) / np.sqrt(eigval[top])           # unit principal axes, [dim, 2]
    rows = (axes / np.sqrt(var)).T.astype(np.float32)               # whitened projection rows
    ref = (Xc @ rows.T).astype(np.float32)
    explained = var / (Xc.var(axis=0, ddof=1).sum())

    VIEW.mkdir(parents=True, exist_ok=True)
    pieces = {"ref": ref, "mean": mean.astype(np.float32), "pc0": rows[0], "pc1": rows[1]}
    layout, offset = {}, 0
    with open(VIEW / "detector-view.bin", "wb") as f:
        for k, a in pieces.items():
            a = np.ascontiguousarray(a, dtype="<f4")
            f.write(a.tobytes())
            layout[k] = {"offset": offset, "shape": list(a.shape)}
            offset += a.nbytes
    v = bp["values"]
    (VIEW / "detector-view.json").write_text(json.dumps({
        "note": ("PCA 1-2 of the promoted detector's reference library, recomputed: the 40 library runs "
                 "through the promoted blueprint in batch with output_embeddings on (fit/library_embeddings.py). "
                 "For drawing only: the app never recomputes a score."),
        "channels": channels, "embeddingDim": dim // len(channels), "totalDim": dim, "nReference": n,
        "nPcaComponents": v["pca_components"], "whiten": True, "explainedVariance": [round(float(e), 4) for e in explained],
        "threshold": v["threshold"], "nNeighbors": v["n_neighbors"], "metric": v["metric"],
        "windowSize": window, "stepSize": step, "blueprint": bp["key"],
        "layout": layout, "dtype": "float32-le"}, indent=2))

    s = np.array(scores)
    summary = {"blueprint": bp["key"], "window_size": window, "step_size": step, "files": len(outs),
               "windows": n, "dim": dim, "explained_variance_pc1_pc2": [round(float(e), 4) for e in explained],
               "score": {"min": round(float(s.min()), 4), "median": round(float(np.median(s)), 4),
                         "max": round(float(s.max()), 4), "threshold": v["threshold"]},
               "anomaly_windows": labels.count("anomaly"),
               "view_bytes": offset}
    (REPO / "fit" / "out" / "library_embeddings.json").write_text(json.dumps(summary, indent=1))
    print(f"\nreference library: {n:,} windows from {len(outs)} runs, window {window}, step {step}")
    print(f"  scores {s.min():.3f}-{s.max():.3f} (median {np.median(s):.3f}) against threshold {v['threshold']:.3f}; "
          f"{labels.count('anomaly')} labelled anomaly")
    print(f"  PCA 1-2 explain {explained[0]:.1%} and {explained[1]:.1%} of the variance")
    print(f"  -> {(VIEW / 'detector-view.bin').relative_to(REPO)} ({offset / 1e3:.0f} KB), detector-view.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
