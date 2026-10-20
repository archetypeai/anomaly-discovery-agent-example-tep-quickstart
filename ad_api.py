#!/usr/bin/env python3
"""Minimal stdlib-only client for the Archetype AI Agent API.

Shared by run_ad_fit.py (build phase) and run_ad_example.py (inference).
Auth and endpoint come from the environment, with a local .env loaded if
present: ATAI_API_KEY, ATAI_API_ENDPOINT.

Adapted from the Rare Event Detection example's `red_api.py`; the endpoints and
polling behaviour are identical, only the blueprint and artifact names differ.

Two names matter and both are easy to get wrong:

  * the inference blueprint is `ad`, and its artifact key is `ad-detector`.
    A near-identical canonical blueprint `ada` also exists with the key
    `ada-detector`. Mixing them is not caught at bundle creation -- the bundle
    is accepted, reports `status: ready`, and then fails ~30 s into the run with
    an error that names the job poller rather than the missing artifact. This is
    the same failure RED documented for its `rad-` / `red-classifier` rename.

  * the fitting blueprint is `ad-fitting`, which reports `is_canonical: false`.
    It is org-scoped, so an org admin must register it once before anyone can
    fit. `blueprint_must_exist` checks up front rather than failing mid-run.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

# First runtime with atai_core #6317 ("identify stream boundaries and align
# barrier copies at fan-ins"). Before it, a periodic checkpoint aborted the
# forked `ad` graph in ConcatColumnsNode; run_ad_eval.py --chunk is the
# workaround for environments still on an older build. tools/check_docs.py
# reads this constant to keep the README's runtime floor in step.
BARRIER_FIX_RUNTIME = "1.1.9-590-194e878"

# runner_config that turns the runner's automatic checkpoint triggers off
# (agent_runner/src/main.rs:50-51 defaults: 50 MiB of source input or 10 min;
# `<= 0` disables). Both launch paths apply it unless --checkpointing is passed.
CHECKPOINTING_OFF = {"checkpointing": {
    "trigger_after_input_byte_size": 0,
    "trigger_after_delay_ms": 0,
}}

# The JOS bucket backing job outputs on dev. A fitted classifier lands at a
# fixed convention path under it; the /results endpoint hands back a presigned
# URL instead, which expires and so cannot be used as a bundle artifact.
JOS_S3_BUCKET = "atai-platform-dev-platform-data-us-west-2"
JOS_OUTPUT_TEMPLATE = ("s3://{bucket}/jos/jobs/{job_id}/agent/worker-0/"
                       "outputs/output/{filename}")


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def api_base() -> str:
    """The deployment root with /api appended — every surface lives under it.

    Accepts a bare root, a /vX.Y suffix or /api itself, so one .env works
    whichever form you have.
    """
    endpoint = os.environ.get("ATAI_API_ENDPOINT", "").rstrip("/")
    if not endpoint:
        sys.exit("ATAI_API_ENDPOINT is not set")
    endpoint = re.sub(r"/api$", "", endpoint)
    endpoint = re.sub(r"/v[0-9]+(\.[0-9]+)*$", "", endpoint)
    return f"{endpoint}/api"


def require_key() -> str:
    load_dotenv()
    key = os.environ.get("ATAI_API_KEY")
    if not key:
        sys.exit("ATAI_API_KEY is not set (put it in .env)")
    return key


def deployment(endpoint: str) -> str:
    """What deployment an endpoint addresses, whatever hostname it arrives under.

    api.dev.u1.archetypeai.app and platform.dev.u1.archetypeai.app are one
    deployment under two names: an agent created through either is visible
    through the other. Verified on 2026-10-20, when a bundle and its agents
    recorded against api.dev.u1 all resolved through platform.dev.u1.

    So state written through one name has to load through the other. The
    generation (api, platform) is everything left of the first dot; the rest
    names the deployment, which still separates dev.u1 from u1 from u2.
    """
    host = re.sub(r"^[a-z]+://", "", endpoint.strip()).split("/")[0].split(":")[0]
    return re.sub(r"^(api|platform)\.", "", host).lower()


def agents_base() -> str:
    return f"{api_base()}/agents"


def bundles_url(bundle_id: str = "") -> str:
    """Bundle collection endpoint.

    NOTE the plural. OSM and RED both use `/agents/bundle` (singular) in their
    code and READMEs; that path now returns 404. Verified on dev 2026-08-14:
      POST /agents/bundles          -> 201
      POST /agents/bundle           -> 404
      POST /agents/bundles/{id}/run -> 422 (reached the handler)
      DELETE /agents/bundles/{id}   -> 204
    There is also no `/agents/bundles/{id}/runs` listing -- to recover a
    bundle's runs, filter `/agents/instances` by `bundle_id`.
    """
    base = f"{api_base()}/agents/bundles"
    return f"{base}/{bundle_id}" if bundle_id else base


def _runs_by_filter(bundle_id: str, progress: bool = True):
    """The bundle's runs via `bundle_id=`, or None if the filter is not honored."""
    out, after = [], None
    while True:
        url = f"{agents_base()}/instances?bundle_id={bundle_id}&limit=100"
        if after:
            url += f"&after={after}"
        try:
            page = request("GET", url)
        except SystemExit:
            return None                            # unsupported: fall back to the scan
        rows = page.get("data", [])
        if any(r.get("bundle_id") != bundle_id for r in rows):
            return None                            # ignored: the rows are everyone's
        out += rows
        if not rows or not page.get("has_more"):
            break
        after = page.get("next_cursor") or rows[-1].get("id")
        if not after:
            break
    if progress:
        print(f"  {len(out)} run(s) belong to this bundle", flush=True)
    return out


def list_bundle_runs(bundle_id: str, progress: bool = True) -> list:
    """Every agent launched from a bundle, newest first.

    The instance listing takes `bundle_id=` and the platform validates it (a
    malformed id answers 400), so one filtered request replaces walking the
    whole listing. Verified on dev 2026-10-20: the delivery bundle answered
    with its five runs and `has_more` false, and the scan below found the same
    five in 37 pages. If a deployment ever ignores the parameter the rows come
    back unfiltered, so the result is checked and the scan runs instead.

    The scan is kept as that fallback. It is slower than it sounds:
    5,100 instances across 51 pages took ~10 s on dev, and it used to print
    nothing while doing it, which reads exactly like a hang.

    The listing paginates with `after=<last id>`, and `next_cursor` is that id.
    It does NOT take `cursor=`: an unknown query parameter is ignored rather than
    rejected, so a client that passed one got the first page back on every
    request, matched the same run each time, and looped forever printing
    "10 pages, 10 runs; 20 pages, 20 runs; ...". Verified on dev 2026-09-04.
    The seen-id guard below makes a repeat page a hard stop rather than a loop,
    in case the parameter name moves again.
    """
    filtered = _runs_by_filter(bundle_id, progress)
    if filtered is not None:
        return filtered

    out, after, pages, seen = [], None, 0, set()
    while True:
        url = f"{agents_base()}/instances?limit=100"
        if after:
            url += f"&after={after}"
        page = request("GET", url)
        pages += 1
        rows = page.get("data", [])
        ids = {r.get("id") for r in rows}
        if not rows or ids <= seen:
            if rows:
                print("  WARNING: the instance listing repeated a page; pagination "
                      "may have changed. Stopping with what was found.", flush=True)
            break
        seen |= ids
        out += [r for r in rows if r.get("bundle_id") == bundle_id]
        if progress and pages % 10 == 0:
            print(f"  ...scanned {pages} pages of instances, "
                  f"{len(out)} run(s) matched so far", flush=True)
        if not page.get("has_more"):
            break
        after = page.get("next_cursor") or rows[-1].get("id")
        if not after:
            break
    if progress:
        print(f"  scanned {pages} page(s); {len(out)} run(s) belong to this bundle",
              flush=True)
    return out


def request(method: str, url: str, body=None, headers=None, raw: bool = False,
            retries: int = 4):
    """Call the API, retrying transient network failures.

    Polls run for hours, and a single DNS hiccup or socket timeout used to kill
    the whole client while the platform job carried on running unattended — the
    job then finished with nobody to download its output. Only *network* errors
    retry; an HTTP status is a real answer from the server and still exits.
    """
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {os.environ['ATAI_API_KEY']}")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = resp.read()
                return payload if raw else json.loads(payload or b"null")
        except urllib.error.HTTPError as e:
            sys.exit(f"{method} {url} failed ({e.code}): {e.read().decode(errors='replace')}")
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                http.client.HTTPException) as e:
            # http.client.IncompleteRead / RemoteDisconnected: the body was cut off
            # mid-transfer. Seen once in ~120 Stage 8 downloads; it killed the worker
            # because it is not a URLError. Retry like any other network fault.
            if attempt == retries:
                sys.exit(f"{method} {url} failed after {retries + 1} attempts: {e}")
            wait = 5 * (2 ** attempt)
            print(f"  network error ({e}); retrying in {wait}s "
                  f"[{attempt + 1}/{retries}]")
            time.sleep(wait)


def upload_file(path: str, rename: str | None = None) -> dict:
    """POST a file to /api/files as multipart/form-data."""
    boundary = uuid.uuid4().hex
    filename = rename or os.path.basename(path)
    content = open(path, "rb").read()
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: text/csv\r\n\r\n",
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(f"{api_base()}/files", data=body, method="POST")
    req.add_header("Authorization", f"Bearer {os.environ['ATAI_API_KEY']}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"upload of {path} failed ({e.code}): {e.read().decode(errors='replace')}")


def blueprint_must_exist(key: str) -> None:
    req = urllib.request.Request(f"{agents_base()}/blueprints/{key}")
    req.add_header("Authorization", f"Bearer {os.environ['ATAI_API_KEY']}")
    try:
        with urllib.request.urlopen(req):
            return
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sys.exit(f"blueprint '{key}' is not registered in your org — ask an org admin.")
        raise


def agent_errors(agent_id: str) -> list:
    """Error-level entries for an agent.

    They live at /logs, NOT /events. `/events` returns only info-level lifecycle
    messages ("run started", "dispatched to JOS as ..."), so a poller watching it
    sees nothing when the pod dies. `/logs` carries the real thing:

        {"level": "ERROR", "event_type": "pod.terminated",
         "message": "Container agent terminated: Error (exit=1)"}

    This matters because `status` is not reliable either -- we observed agents
    whose pod had terminated still reporting `status: running` hours later. With
    both signals missed, a poller waits out its whole timeout on a dead run.
    """
    try:
        data = request("GET", f"{agents_base()}/instances/{agent_id}/logs").get("data", [])
    except SystemExit:
        return []
    return [e for e in data if (e.get("level") or "").upper() == "ERROR"]


def poll_agent(agent_id: str, timeout_s: int, interval_s: int = 20) -> str:
    """Poll until terminal, streaming new audit events as they appear.

    Terminal is decided by THREE signals, because no single one is trustworthy:
      1. `status` reaching a terminal value  -- often never happens;
      2. an ERROR entry at /logs             -- the reliable failure signal;
      3. the timeout                         -- scale it to the expected work.
    """
    agents = agents_base()
    deadline = time.time() + timeout_s
    seen: set[str] = set()
    status = "running"
    while status == "running" and time.time() < deadline:
        time.sleep(interval_s)
        status = request("GET", f"{agents}/instances/{agent_id}").get("status")
        for ev in request("GET", f"{agents}/instances/{agent_id}/events").get("data", []):
            marker = f"{ev.get('created_at')}{ev.get('message')}"
            if marker not in seen:
                seen.add(marker)
                print(f"  [{ev.get('level', 'info')}] {ev.get('created_at', '')}  "
                      f"{ev.get('message', '')}")
        errs = agent_errors(agent_id)
        if errs:
            for e in errs[:3]:
                print(f"  [ERROR] {e.get('event_type', '')}: "
                      f"{(e.get('message') or '')[:160]}")
            if status == "running":
                print("  status still says 'running', but /logs reports an error "
                      "-- treating as failed.")
            return "failed"
        print(f"  {time.strftime('%H:%M:%S')} status={status}")
    if status == "running":
        print(f"  timed out after {timeout_s/60:.0f} min with status still 'running'")
    return status


def jos_job_id(agent_id: str) -> str | None:
    """The JOS job id, needed to build a durable s3:// path for a fitted artifact.

    The instance record carries `job_id` directly, so the event stream is only a
    fallback -- RED had to scrape the "dispatched to JOS as ..." line because it
    did not know the field was there.
    """
    inst = request("GET", f"{agents_base()}/instances/{agent_id}")
    if inst.get("job_id"):
        return inst["job_id"]
    events = request("GET", f"{agents_base()}/instances/{agent_id}/events")
    job_id = None
    for ev in events.get("data", []):
        m = re.search(r"dispatched to JOS as (job_\w+)", str(ev.get("message", "")))
        if m:
            job_id = m.group(1)
    return job_id


def _last_timestamp(csv_path: str) -> float | None:
    """Timestamp of the final sample in an input CSV, read from the last line."""
    last = None
    with open(csv_path, "r") as fh:
        for line in fh:
            if line.strip():
                last = line
    try:
        return float(last.split(",")[0])
    except (AttributeError, ValueError):
        return None


def _output_coverage(out_path: str, source_end: float) -> tuple[float, float]:
    """(fraction of the input covered, shortfall in seconds).

    Compares the last window's finish timestamp against the input's last sample.
    Deliberately derived from the output itself rather than from window/step:
    those come from the detector artifact, so a client that did not pass them
    does not know them, and this check has to work in the default path.
    """
    import csv as _csv
    with open(out_path) as fh:
        rows = list(_csv.DictReader(fh))
    if not rows:
        return 0.0, source_end
    fin = "finish_timestamp" if "finish_timestamp" in rows[0] else list(rows[0])[0]
    sta = "start_timestamp" if "start_timestamp" in rows[0] else None
    try:
        end = max(float(r[fin]) for r in rows if r.get(fin))
    except ValueError:
        return 0.0, source_end
    # One window may legitimately be missing: a tail shorter than the window is
    # dropped rather than padded. Measure a window from the output itself.
    win = 0.0
    if sta:
        try:
            win = max(float(r[fin]) - float(r[sta]) for r in rows[:64] if r.get(sta))
        except ValueError:
            win = 0.0
    shortfall = max(0.0, source_end - end - win * 1.5)
    return (end / source_end if source_end else 1.0), shortfall


def _first_result(agent_id: str) -> tuple[list, dict, str | None]:
    """One /results call: (items, first item's inner data, its download ref).

    The `ref` is a presigned URL that expires (~20 min), so every retry has to ask
    /results again rather than reuse the previous one.
    """
    results = request("GET", f"{agents_base()}/instances/{agent_id}/results")
    items = results.get("data", results if isinstance(results, list) else [])
    if not items:
        return [], {}, None
    inner = items[0].get("data") or {}
    ref = inner.get("ref") or items[0].get("ref") or items[0].get("url")
    return items, inner, ref


def _download(ref: str) -> bytes | None:
    """Follow a result ref. A fitted-artifact ref is an absolute presigned S3 URL;
    a run-output ref is a relative platform path ("/files/download/<name>") that
    resolves under the versioned files API with the bearer token. Network errors
    return None so the caller can poll again instead of dying mid-wait."""
    try:
        if ref.startswith("http"):
            with urllib.request.urlopen(ref, timeout=120) as resp:
                return resp.read()
        return request("GET", f"{api_base()}{ref}", raw=True)
    except (urllib.error.URLError, TimeoutError, ConnectionError,
            http.client.HTTPException) as e:          # incl. IncompleteRead mid-download
        print(f"  download failed ({e}); retrying")
        return None


def download_results(agent_id: str, out_path: str,
                     source_csv: str | None = None,
                     settle_s: int = 180, appear_s: int = 60) -> str | None:
    """Fetch /results and save the first output to out_path, or return None.

    WAITS FOR THE ARTIFACT TO FINISH SYNCING, which is not the same thing as the
    run finishing. The output row is created while the agent is still writing and
    is filled in afterwards, so a download issued the moment the status flips to
    `completed` can capture a prefix. Measured on a 298.94 MB run: the first fetch
    returned 10,652 of 12,648 windows -- 84.2%, a perfectly well-formed CSV with
    zero invalid windows and nothing to suggest it was short. It scored 1002.8
    lead hours against a true 27.0. Re-fetching the same artifact minutes later
    returned all 12,648 rows.

    The console shows this as artifact status PARTIAL -> COMPLETE, but /results
    carries no status field -- only filename, num_bytes and ref -- so a client
    cannot ask. It has to verify by content, which is what this does:

      * `source_csv` given: re-fetch until the last scored window reaches the end
        of that input. Needs no knowledge of window/step -- which come from the
        detector artifact, so the default path does not have them.
      * otherwise: poll until num_bytes stops changing, which is weaker (a stall
        mid-write looks like a finish) but is all that is available.

    Two separate budgets: `appear_s` for the /results row to exist at all (0 to
    try exactly once, for runs that finished long ago or failed), then `settle_s`
    for the artifact to catch up once it does. The file is written to a temporary
    name and only moved to out_path when it passes, so a caller never finds a
    prefix at the real path -- a short file there would be scored as complete by
    evaluate_anomalies.py and skipped as already-downloaded by run_ad_eval.py.
    """
    appear_deadline = time.time() + appear_s
    while True:
        items, inner, ref = _first_result(agent_id)
        if items:
            break
        if time.time() >= appear_deadline:
            print("  no results returned")
            return None
        time.sleep(5)
    print(f"results ({len(items)}):")
    for item in items:
        d = item.get("data") or {}
        print(f"  {d.get('filename') or item.get('id')}  ({d.get('num_bytes', '?')} bytes)")
    if not ref:
        print("  results carried no download ref")
        return None

    source_end = _last_timestamp(source_csv) if source_csv else None
    tmp_path = out_path + ".part"
    deadline = time.time() + settle_s
    frac = short = seen_bytes = None
    while True:
        # The artifact's own status is the authoritative signal and needs nothing
        # to compare against. A run reports `completed` while its outputs are
        # still being written -- measured, about a minute of it -- and the
        # console shows the same pairing, run COMPLETED beside artifact PARTIAL.
        # An absent status reads as ready, so a deployment reporting none is not
        # blocked, and the checks below still apply.
        status = (inner.get("file_attributes", {}).get("job_output", {}).get("status"))
        if status is not None and status != "complete":
            print(f"  artifact reports {status}; waiting")
        elif source_end is None:
            # No input to compare against: fall back to waiting for num_bytes to
            # hold still across two polls. A stall mid-write looks the same,
            # which is why the status above is preferred when present.
            settled = inner.get("num_bytes") == seen_bytes
            seen_bytes = inner.get("num_bytes")
            payload = _download(ref) if settled else None
            if payload is not None:
                open(tmp_path, "wb").write(payload)
                break
        else:
            payload = _download(ref)
            if payload is not None:
                open(tmp_path, "wb").write(payload)
                frac, short = _output_coverage(tmp_path, source_end)
                if short <= 0:
                    print(f"  verified: output covers the full input ({frac * 100:.1f}%)")
                    break
                print(f"  artifact still syncing: covers {frac * 100:.1f}% of the "
                      f"input ({short:,.0f}s short), waiting")
        if time.time() >= deadline:
            _discard(tmp_path)
            if short is not None:
                print(f"  WARNING: output covers {frac * 100:.1f}% of the input, "
                      f"{short:,.0f}s short, after {settle_s}s. The artifact is "
                      f"incomplete -- scoring it would silently give a wrong lead "
                      f"time -- so nothing was saved. Re-download for {agent_id} "
                      f"in a minute.")
            else:
                print(f"  WARNING: the artifact was still changing after {settle_s}s; "
                      f"nothing saved. Re-download for {agent_id} in a minute.")
            return None
        time.sleep(10 if source_end else 5)
        items, inner, ref = _first_result(agent_id)
        if not ref:
            print("  results disappeared mid-download")
            _discard(tmp_path)
            return None
    os.replace(tmp_path, out_path)
    print(f"saved output to {out_path}")
    return out_path


def _discard(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)
