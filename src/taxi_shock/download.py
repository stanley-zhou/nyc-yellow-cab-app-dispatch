"""Downloads: TLC yellow-taxi Parquet, zone lookup + shapefile, Open-Meteo hourly weather.

Files are written under data/raw/ (paths from config); the 60th Street geometry used by
`taxi_shock.cbd` comes from OpenStreetMap through the Overpass API.

TLC downloads are resumable (HTTP Range), verified against the server's Content-Length, retried
with exponential backoff, and recorded in `data/raw/manifest.csv` (file, bytes, download date) so
`make data` can re-fetch anything that is deleted.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import logging
import time
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from taxi_shock.config import load_config, path, repo_root

log = logging.getLogger(__name__)
USER_AGENT = "taxi-shock-pipeline/0.1 (research; python-requests)"
CHUNK = 1 << 20


class DownloadError(RuntimeError):
    """Raised when a file cannot be fetched or fails its size check after all retries."""


def month_range(start: str, end: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' strings between two 'YYYY-MM' bounds."""
    periods = pd.period_range(start=start, end=end, freq="M")
    return [p.strftime("%Y-%m") for p in periods]


def _session() -> requests.Session:
    """HTTP session. `Accept-Encoding: identity` matters: CloudFront gzips CSVs for clients that
    accept gzip and then omits Content-Length, which breaks the size check and HTTP Range resume."""
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    s.headers["Accept-Encoding"] = "identity"
    return s


def remote_size(session: requests.Session, url: str, timeout: float) -> int:
    """Content-Length of `url` via HEAD; raises DownloadError on non-200."""
    r = session.head(url, timeout=timeout, allow_redirects=True)
    if r.status_code != 200:
        raise DownloadError(f"HEAD {url} -> HTTP {r.status_code}")
    size = r.headers.get("Content-Length")
    if size is None:
        raise DownloadError(f"HEAD {url} returned no Content-Length")
    return int(size)


def download_file(url: str, dest: Path, cfg: dict[str, Any] | None = None) -> int:
    """Download `url` to `dest` with resume, size check and retry. Returns bytes on disk.

    Skips the transfer if `dest` already exists with the remote size.
    """
    cfg = cfg or load_config()
    retries = int(cfg["sources"]["http_retries"])
    timeout = float(cfg["sources"]["http_timeout_seconds"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    session = _session()

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            expected = remote_size(session, url, timeout)
            if dest.exists() and dest.stat().st_size == expected:
                log.info("skip %s (already %d bytes)", dest.name, expected)
                return expected
            have = part.stat().st_size if part.exists() else 0
            if have > expected:  # corrupt partial; start again
                part.unlink()
                have = 0
            headers = {"Range": f"bytes={have}-"} if have else {}
            with session.get(url, headers=headers, stream=True, timeout=timeout) as r:
                if have and r.status_code != 206:  # server ignored Range: restart cleanly
                    have = 0
                    part.unlink(missing_ok=True)
                elif r.status_code not in (200, 206):
                    raise DownloadError(f"GET {url} -> HTTP {r.status_code}")
                with part.open("ab" if have else "wb") as fh:
                    for chunk in r.iter_content(CHUNK):
                        fh.write(chunk)
            got = part.stat().st_size
            if got != expected:
                raise DownloadError(f"{dest.name}: size {got} != Content-Length {expected}")
            part.replace(dest)
            log.info("downloaded %s (%d bytes)", dest.name, got)
            return got
        except (requests.RequestException, DownloadError) as err:
            last_err = err
            wait = min(2**attempt, 60)
            log.warning("attempt %d/%d for %s failed: %s; retry in %ds",
                        attempt, retries, url, err, wait)
            if attempt < retries:
                time.sleep(wait)
    raise DownloadError(f"giving up on {url}: {last_err}")


def update_manifest(rows: Iterable[tuple[Path, int]], cfg: dict[str, Any] | None = None) -> Path:
    """Upsert (file, bytes, download_date) rows into the manifest CSV; file paths repo-relative.

    Rows whose file no longer exists on disk are dropped, so the manifest always describes the
    raw files actually present."""
    cfg = cfg or load_config()
    manifest = path("manifest", cfg)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict[str, str]] = {}
    if manifest.exists():
        with manifest.open(newline="", encoding="utf-8") as fh:
            existing = {r["file"]: r for r in csv.DictReader(fh)}
    today = dt.date.today().isoformat()
    root = repo_root()
    for file_path, size in rows:
        rel = file_path.resolve().relative_to(root).as_posix()
        prev = existing.get(rel)
        if prev and int(prev["bytes"]) == size:
            continue  # unchanged file keeps its original download date
        existing[rel] = {"file": rel, "bytes": str(size), "download_date": today}
    existing = {k: v for k, v in existing.items() if (root / k).exists()}
    with manifest.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "bytes", "download_date"], lineterminator="\n")
        w.writeheader()
        for key in sorted(existing):
            w.writerow(existing[key])
    return manifest


def download_yellow(months: Iterable[str], cfg: dict[str, Any] | None = None) -> list[Path]:
    """Download yellow-taxi monthly Parquet files for the given 'YYYY-MM' months."""
    cfg = cfg or load_config()
    base = cfg["sources"]["tlc_base_url"].rstrip("/")
    out_dir = path("raw_yellow", cfg)
    done: list[tuple[Path, int]] = []
    for month in months:
        rel = cfg["sources"]["yellow_path"].format(month=month)
        dest = out_dir / Path(rel).name
        size = download_file(f"{base}/{rel}", dest, cfg)
        done.append((dest, size))
        update_manifest([(dest, size)], cfg)
    return [p for p, _ in done]


def download_lookups(cfg: dict[str, Any] | None = None) -> list[Path]:
    """Zone lookup CSV and the zone shapefile (unzipped next to the archive)."""
    cfg = cfg or load_config()
    base = cfg["sources"]["tlc_base_url"].rstrip("/")
    out_dir = path("raw_lookup", cfg)
    rows: list[tuple[Path, int]] = []
    for key in ("zone_lookup_path", "zone_shapefile_path"):
        rel = cfg["sources"][key]
        dest = out_dir / Path(rel).name
        rows.append((dest, download_file(f"{base}/{rel}", dest, cfg)))
    update_manifest(rows, cfg)
    shp_zip = out_dir / Path(cfg["sources"]["zone_shapefile_path"]).name
    with zipfile.ZipFile(shp_zip) as zf:
        for member in zf.namelist():
            name = Path(member).name
            if not name or not name.startswith("taxi_zones."):
                continue  # skip directories and __MACOSX artefacts
            (out_dir / name).write_bytes(zf.read(member))
    return [p for p, _ in rows]


OSM_60TH_FILE = "osm_60th_street.json"


def overpass_query(street_names: list[str]) -> str:
    """Overpass QL for every highway way inside Manhattan named exactly one of `street_names`."""
    alt = "|".join(street_names)
    return ('[out:json][timeout:60];area["name"="Manhattan"]["boundary"="administrative"]->.m;'
            f'(way["highway"]["name"~"^({alt})$"](area.m););out geom;')


def download_osm_60th_street(cfg: dict[str, Any] | None = None) -> Path:
    """OpenStreetMap geometry of 60th Street (Manhattan) via Overpass, saved once as raw JSON.

    Used to draw the line through the two endpoints of 60th St for the geometric `is_cbd` step
    (PLAN Phase 1). Skipped when the file exists, so the line stays fixed across rebuilds.
    """
    cfg = cfg or load_config()
    dest = path("raw_lookup", cfg) / OSM_60TH_FILE
    if dest.exists() and dest.stat().st_size > 0:
        log.info("skip %s", dest.name)
    else:
        query = overpass_query(cfg["cbd"]["street_names"])
        payload = _post_json(_session(), cfg["sources"]["osm_overpass_url"], {"data": query}, cfg)
        if not payload.get("elements"):
            raise DownloadError("Overpass returned no 60th Street ways")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps({"query": query, "retrieved": dt.date.today().isoformat(),
                                    **payload}, indent=1), encoding="utf-8")
        log.info("osm %s: %d ways", dest.name, len(payload["elements"]))
    update_manifest([(dest, dest.stat().st_size)], cfg)
    return dest


def _post_json(session: requests.Session, url: str, data: dict[str, str],
               cfg: dict[str, Any]) -> dict[str, Any]:
    retries = int(cfg["sources"]["http_retries"])
    timeout = float(cfg["sources"]["http_timeout_seconds"])
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = session.post(url, data=data, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            last = DownloadError(f"POST {url} -> HTTP {r.status_code}: {r.text[:200]}")
        except requests.RequestException as err:
            last = err
        if attempt < retries:
            time.sleep(min(2**attempt, 60))
    raise DownloadError(f"giving up on {url}: {last}")


def _year_chunks(start: dt.date, end: dt.date) -> list[tuple[dt.date, dt.date]]:
    chunks = []
    for year in range(start.year, end.year + 1):
        lo = max(start, dt.date(year, 1, 1))
        hi = min(end, dt.date(year, 12, 31))
        chunks.append((lo, hi))
    return chunks


def download_weather(start: str, end: str, cfg: dict[str, Any] | None = None) -> list[Path]:
    """Open-Meteo archive hourly weather in yearly chunks, one CSV per chunk.

    Open-Meteo applies a *fixed* UTC offset for `timezone=America/New_York` (EST, -18000 s, even
    in July), which shifts every summer hour by one. We therefore request GMT unix seconds, pad
    each chunk by `weather_pad_days` on both sides so the local-time window is fully covered, and
    convert to local wall-clock time in dbt (`stg_weather`). Files are named by their exact
    requested range, so a partial smoke chunk never masquerades as a full year.
    """
    cfg = cfg or load_config()
    src = cfg["sources"]
    out_dir = path("raw_weather", cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    session = _session()
    written: list[tuple[Path, int]] = []
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    pad = dt.timedelta(days=int(src["weather_pad_days"]))
    for lo, hi in _year_chunks(s, e):
        lo, hi = lo - pad, hi + pad
        dest = out_dir / f"open_meteo_{lo.isoformat()}_{hi.isoformat()}.csv"
        if dest.exists() and dest.stat().st_size > 0:
            log.info("skip %s", dest.name)
            written.append((dest, dest.stat().st_size))
            continue
        params = {
            "latitude": src["weather_point"][0],
            "longitude": src["weather_point"][1],
            "start_date": lo.isoformat(),
            "end_date": hi.isoformat(),
            "hourly": ",".join(src["weather_hourly"]),
            "timezone": "GMT",
            "timeformat": "unixtime",
            **src["weather_units"],
        }
        payload = _get_json(session, src["weather_url"], params, cfg)
        hourly = payload["hourly"]
        df = pd.DataFrame(hourly).rename(columns={"time": "unix_time"})
        missing = [v for v in src["weather_hourly"] if v not in df.columns]
        if missing:
            raise DownloadError(f"Open-Meteo response lacks variables {missing}")
        if df.empty:
            raise DownloadError(f"Open-Meteo returned zero rows for {lo}..{hi}")
        df.to_csv(dest, index=False)
        written.append((dest, dest.stat().st_size))
        log.info("weather %s: %d hourly rows", dest.name, len(df))
    update_manifest(written, cfg)
    return [p for p, _ in written]


def _get_json(session: requests.Session, url: str, params: dict[str, Any],
              cfg: dict[str, Any]) -> dict[str, Any]:
    retries = int(cfg["sources"]["http_retries"])
    timeout = float(cfg["sources"]["http_timeout_seconds"])
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            last = DownloadError(f"GET {url} -> HTTP {r.status_code}: {r.text[:200]}")
        except requests.RequestException as err:
            last = err
        if attempt < retries:
            time.sleep(min(2**attempt, 60))
    raise DownloadError(f"giving up on {url}: {last}")


def plan_downloads(
    datasets: dict[str, list[str]], cfg: dict[str, Any] | None = None
) -> pd.DataFrame:
    """HEAD every file that a full download would fetch; no data is transferred.

    `datasets` maps a config path template key (e.g. 'yellow_path') to a list of months.
    Returns one row per file with its Content-Length (NaN if unavailable) and HTTP status.
    """
    cfg = cfg or load_config()
    base = cfg["sources"]["tlc_base_url"].rstrip("/")
    timeout = float(cfg["sources"]["http_timeout_seconds"])
    session = _session()
    rows = []
    for key, months in datasets.items():
        for month in months:
            url = f"{base}/{cfg['sources'][key].format(month=month)}"
            try:
                r = session.head(url, timeout=timeout, allow_redirects=True)
                status = r.status_code
                size = int(r.headers["Content-Length"]) if status == 200 else None
            except requests.RequestException as err:
                status, size = f"error: {err}", None
            rows.append({"dataset": key.removesuffix("_path"), "month": month, "url": url,
                         "http_status": status, "bytes": size})
    return pd.DataFrame(rows)
