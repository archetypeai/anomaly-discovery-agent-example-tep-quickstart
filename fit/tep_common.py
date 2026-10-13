"""Shared scoring for TEP fault detection — used by the PCA baseline and by the
platform-output evaluator so both are judged by exactly the same code.

A "series" is (timestamp, score) pairs joined to a labels sidecar on timestamp.
For the PCA baseline the timestamp is the row's; for the AD agent it is the
window's `finish_timestamp` (end-row labeling: a score means "how far from
normal is the process NOW, given the last window_size samples").

Per (fault_id, simulationrun) segment:
  * normal part  -> false alarms          (score > threshold)
  * fault part   -> detection rate         (fraction of fault windows alarmed)
                    detected / missed      (first SUSTAINED crossing: `sustain`
                                            consecutive alarms, so one spike is
                                            not a detection)
                    delay in hours         (from onset to that first crossing)
                    AUROC                  (fault scores vs every normal score
                                            in the same file — threshold-free)
Pooled over slices per IDV, then over IDVs.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
PREPARED = REPO / "data" / "prepared"
NORMAL = "idv_00"

IDV_TYPE = {
    "idv_01": "step  A/C feed ratio", "idv_02": "step  B composition",
    "idv_03": "step  D feed temp", "idv_04": "step  reactor coolant temp",
    "idv_05": "step  condenser coolant temp", "idv_06": "step  A feed loss",
    "idv_07": "step  C header pressure", "idv_08": "rand  A/B/C composition",
    "idv_09": "rand  D feed temp", "idv_10": "rand  C feed temp",
    "idv_11": "rand  reactor coolant temp", "idv_12": "rand  condenser coolant temp",
    "idv_13": "drift reaction kinetics", "idv_14": "stick reactor coolant valve",
    "idv_15": "stick condenser coolant valve", "idv_16": "unknown", "idv_17": "unknown",
    "idv_18": "unknown", "idv_19": "unknown", "idv_20": "unknown",
}
# Faults the process-monitoring literature reports as essentially undetectable
# under closed-loop control (their effect sits below the noise floor).
HARD = {"idv_03", "idv_09", "idv_15"}


def load_labels(name: str) -> pd.DataFrame:
    """`name` like 'eval_slice_01' or 'val_normal'."""
    path = REPO / "data" / "roles" / "labels" / f"tep_{name}_labels.csv"   # what the repo ships
    if not path.exists():
        path = PREPARED / f"tep_{name}_labels.csv"
    if not path.exists():
        path = PREPARED / "full" / f"tep_{name}_labels.csv"      # Stage 8 chunks
    if not path.exists():
        raise SystemExit(f"{path} not found — run prep/prepare_tep.py")
    df = pd.read_csv(path)
    df["timestamp"] = df["timestamp"].astype(np.int64)
    return df


def auroc(pos: np.ndarray, neg: np.ndarray) -> float:
    """Rank-based AUROC (Mann–Whitney), ties averaged. No scipy."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = pd.Series(np.concatenate([pos, neg])).rank(method="average").to_numpy()
    r_pos = ranks[:len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def first_sustained(alarms: np.ndarray, sustain: int) -> int | None:
    """Index of the first run of `sustain` consecutive alarms, else None."""
    if sustain <= 1:
        hits = np.flatnonzero(alarms)
        return int(hits[0]) if len(hits) else None
    run = 0
    for i, a in enumerate(alarms):
        run = run + 1 if a else 0
        if run >= sustain:
            return i - sustain + 1
    return None


def series_metrics(labels: pd.DataFrame, ts: np.ndarray, score: np.ndarray,
                   threshold: float, sustain: int = 3) -> dict:
    """Score one file. Returns per-segment records plus file-level counts."""
    joined = labels.merge(pd.DataFrame({"timestamp": ts.astype(np.int64),
                                        "score": score}),
                          on="timestamp", how="inner").sort_values("timestamp")
    unmatched = int(len(ts) - len(joined))
    joined["alarm"] = joined["score"] > threshold
    normal_scores = joined.loc[joined.label == "normal", "score"].to_numpy()

    segments = []
    for (fid, sim), seg in joined.groupby(["fault_id", "simulationrun"], sort=True):
        normal = seg[seg.label == "normal"]
        rec = {"fault_id": fid, "sim": int(sim),
               "n_normal": int(len(normal)), "false_alarms": int(normal.alarm.sum())}
        fault = seg[seg.label == "fault"]
        if len(fault):
            alarms = fault.alarm.to_numpy()
            onset = int(fault.timestamp.iloc[0])
            i = first_sustained(alarms, sustain)
            rec.update({
                "n_fault": int(len(fault)), "fault_alarms": int(alarms.sum()),
                "detected": i is not None,
                "delay_h": (float(fault.timestamp.iloc[i]) - onset) / 3600 if i is not None else None,
                "auroc": auroc(fault.score.to_numpy(), normal_scores),
                "fault_scores": fault.score.to_numpy(),
            })
        segments.append(rec)
    return {"segments": segments, "normal_scores": normal_scores,
            "unmatched": unmatched, "n": int(len(joined))}


def pool(files: list[dict]) -> dict:
    """Pool per-file results into per-IDV and overall figures."""
    per_idv: dict[str, dict] = {}
    all_normal = np.concatenate([f["normal_scores"] for f in files]) if files else np.array([])
    n_normal = fa = 0
    for f in files:
        for s in f["segments"]:
            n_normal += s["n_normal"]
            fa += s["false_alarms"]
            if "n_fault" not in s:
                continue
            d = per_idv.setdefault(s["fault_id"], {
                "n_fault": 0, "fault_alarms": 0, "sims": 0, "detected": 0,
                "delays_h": [], "fault_scores": []})
            d["n_fault"] += s["n_fault"]
            d["fault_alarms"] += s["fault_alarms"]
            d["sims"] += 1
            d["detected"] += int(s["detected"])
            if s["delay_h"] is not None:
                d["delays_h"].append(s["delay_h"])
            d["fault_scores"].append(s["fault_scores"])
    out = {}
    for fid in sorted(per_idv):
        d = per_idv[fid]
        pos = np.concatenate(d["fault_scores"])
        out[fid] = {
            "type": IDV_TYPE.get(fid, ""), "hard": fid in HARD,
            "n_fault": d["n_fault"],
            "detection_rate": d["fault_alarms"] / d["n_fault"] if d["n_fault"] else float("nan"),
            "sims": d["sims"], "sims_detected": d["detected"],
            "median_delay_h": float(np.median(d["delays_h"])) if d["delays_h"] else None,
            "auroc": auroc(pos, all_normal),
        }
    rates = [v["detection_rate"] for v in out.values()]
    aurocs = [v["auroc"] for v in out.values() if not np.isnan(v["auroc"])]
    return {
        "per_idv": out,
        "overall": {
            "n_normal": n_normal, "false_alarms": fa,
            "far": fa / n_normal if n_normal else float("nan"),
            "mean_detection_rate": float(np.mean(rates)) if rates else float("nan"),
            "mean_detection_rate_excl_hard": float(np.mean(
                [v["detection_rate"] for k, v in out.items() if k not in HARD])) if out else float("nan"),
            "sims_detected": sum(v["sims_detected"] for v in out.values()),
            "sims_total": sum(v["sims"] for v in out.values()),
            "macro_auroc": float(np.mean(aurocs)) if aurocs else float("nan"),
            "unmatched": sum(f["unmatched"] for f in files),
        },
    }


def calibrate_threshold(normal_scores: np.ndarray, far: float) -> float:
    """Threshold at which a fraction `far` of normal scores would alarm."""
    return float(np.quantile(normal_scores, 1.0 - far))


def format_table(pooled: dict, baseline: dict | None = None, title: str = "") -> str:
    """Per-IDV table; `baseline` is a pooled dict from the PCA bar, if any."""
    lines = []
    if title:
        lines.append(title)
    head = f"  {'IDV':<7}{'type':<32}{'det%':>6}{'sims':>10}{'delay h':>9}{'AUROC':>7}"
    if baseline:
        head += f"   |{'PCA det%':>9}{'delay h':>9}{'AUROC':>7}"
    lines.append(head)
    lines.append("  " + "-" * (len(head) - 2))
    for fid, v in pooled["per_idv"].items():
        d = v["median_delay_h"]
        sims = f"{v['sims_detected']}/{v['sims']}"
        row = (f"  {fid:<7}{v['type']:<32}{v['detection_rate']*100:>6.1f}"
               f"{sims:>10}"
               f"{(f'{d:.2f}' if d is not None else '—'):>9}{v['auroc']:>7.3f}")
        if baseline and fid in baseline["per_idv"]:
            b = baseline["per_idv"][fid]
            bd = b["median_delay_h"]
            row += (f"   |{b['detection_rate']*100:>9.1f}"
                    f"{(f'{bd:.2f}' if bd is not None else '—'):>9}{b['auroc']:>7.3f}")
        if v["hard"]:
            row += "   (hard)"
        lines.append(row)
    o = pooled["overall"]
    lines.append("")
    lines.append(f"  false-alarm rate on normal windows: {o['far']*100:.2f}%  "
                 f"({o['false_alarms']:,} / {o['n_normal']:,})")
    lines.append(f"  mean detection rate: {o['mean_detection_rate']*100:.1f}%  "
                 f"(excl. 3/9/15: {o['mean_detection_rate_excl_hard']*100:.1f}%)   "
                 f"sims detected: {o['sims_detected']}/{o['sims_total']}   "
                 f"macro AUROC: {o['macro_auroc']:.3f}")
    if baseline:
        bo = baseline["overall"]
        lines.append(f"  PCA bar:             FAR {bo['far']*100:.2f}%   mean det "
                     f"{bo['mean_detection_rate']*100:.1f}% (excl. hard "
                     f"{bo['mean_detection_rate_excl_hard']*100:.1f}%)   "
                     f"sims {bo['sims_detected']}/{bo['sims_total']}   "
                     f"macro AUROC {bo['macro_auroc']:.3f}")
    if o["unmatched"]:
        lines.append(f"  note: {o['unmatched']} scored rows had no label (seam windows "
                     f"or timestamps outside the sidecar)")
    return "\n".join(lines)


def load_baseline(path: Path | None):
    path = path or REPO / "fit" / "out" / "baseline_pca.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def jsonable(pooled: dict) -> dict:
    return json.loads(json.dumps(pooled, default=lambda o: None))
