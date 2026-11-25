#!/usr/bin/env python3
"""Stage 0 — fetch the TEP dataset from Harvard Dataverse and convert to CSV.

    python3 prep/download.py                 # ~1.4 GB download, then RData -> CSV
    python3 prep/download.py --verify-only   # check what is on disk, fetch nothing
    python3 prep/download.py --keep-rdata    # do not delete the .RData after converting

Source: Rieth, Amsel, Tran & Cook (2017), "Additional Tennessee Eastman Process
Simulation Data for Anomaly Detection Evaluation", Harvard Dataverse,
doi:10.7910/DVN/6C3JR1. Four R data files, fetched by their Dataverse file id
through the public access API and verified against the MD5s the dataset
metadata publishes. Each is then read with `pyreadr` and written as CSV with
lower-cased column names (`faultnumber, simulationrun, sample, xmeas_1..41,
xmv_1..11`) — the same conversion the batch example used, so the CSVs are
byte-identical to the Kaggle mirror `afrniomelo/tep-csv`.

Idempotent: a file that is present with the right MD5 is not fetched again, and
a CSV that already exists is not rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
API = "https://dataverse.harvard.edu/api/access/datafile/{id}"
DOI = "doi:10.7910/DVN/6C3JR1"

# (filename, Dataverse file id, MD5) from the dataset's `latestVersion.files`.
FILES = [
    ("TEP_FaultFree_Training", 3031241, "ec126484534331f85001d8c4ebce6d17"),
    ("TEP_FaultFree_Testing", 3031240, "38ad9810fc871026157086ae2c2f0ee9"),
    ("TEP_Faulty_Training", 3031242, "c5f594d54c47e620ff877feb58407fda"),
    ("TEP_Faulty_Testing", 3031243, "556bdb64c83021bc0c5f92e427753565"),
]


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def fetch(file_id: int, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(API.format(id=file_id), headers={"User-Agent": "tep-ad-example"})
    t0, done = time.time(), 0
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        while True:
            block = resp.read(1 << 22)
            if not block:
                break
            out.write(block)
            done += len(block)
            if total and done % (1 << 26) < (1 << 22):
                print(f"    {done / 1e6:8.0f} / {total / 1e6:.0f} MB  "
                      f"{done / 1e6 / (time.time() - t0):.1f} MB/s", flush=True)
    tmp.rename(dest)


def convert(rdata: Path, csv: Path) -> None:
    import pyreadr  # only needed for the conversion step
    df = next(iter(pyreadr.read_r(str(rdata)).values()))
    df = df.rename(columns={c: c.strip().lower().replace("(", "_").replace(")", "").replace(" ", "_")
                            for c in df.columns})
    df.to_csv(csv, index=False)
    print(f"    -> {csv.name}  {csv.stat().st_size / 1e6:,.0f} MB, {len(df):,} rows, "
          f"{len(df.columns)} cols", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--keep-rdata", action="store_true",
                    help="keep the .RData files after conversion (1.4 GB)")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    print(f"{DOI} -> {RAW.relative_to(REPO)}/")

    ok = True
    for name, file_id, want in FILES:
        rdata, csv = RAW / f"{name}.RData", RAW / f"{name}.csv"
        if csv.exists():
            print(f"  {csv.name}: present ({csv.stat().st_size / 1e6:,.0f} MB)")
            continue
        if args.verify_only:
            print(f"  {csv.name}: MISSING")
            ok = False
            continue
        if rdata.exists() and md5(rdata) == want:
            print(f"  {rdata.name}: present, MD5 ok")
        else:
            print(f"  {rdata.name}: fetching (file id {file_id})...", flush=True)
            fetch(file_id, rdata)
            got = md5(rdata)
            if got != want:
                rdata.unlink()
                sys.exit(f"MD5 mismatch for {rdata.name}: got {got}, expected {want}")
            print(f"    MD5 ok")
        print(f"  converting {rdata.name}...", flush=True)
        convert(rdata, csv)
        if not args.keep_rdata:
            rdata.unlink()
    if args.verify_only and not ok:
        return 1
    print("done" if not args.verify_only else "all present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
