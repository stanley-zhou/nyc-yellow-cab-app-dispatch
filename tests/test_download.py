"""Download helper: resume via HTTP Range, size check, identity encoding, manifest."""

from __future__ import annotations

import http.server
import threading
from pathlib import Path

import pytest

from taxi_shock import download as dl

PAYLOAD = bytes(range(256)) * 400  # 102,400 bytes


class RangeHandler(http.server.BaseHTTPRequestHandler):
    payload = PAYLOAD
    truncate_first = False  # simulate a dropped connection on the first full GET
    calls: list[str] = []

    def log_message(self, *args):  # silence
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()

    def do_GET(self):
        RangeHandler.calls.append(self.headers.get("Range") or "")
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].rstrip("-"))
            body = self.payload[start:]
            self.send_response(206)
            last, total = len(self.payload) - 1, len(self.payload)
            self.send_header("Content-Range", f"bytes {start}-{last}/{total}")
        else:
            body = self.payload
            self.send_response(200)
        if RangeHandler.truncate_first and not rng:
            RangeHandler.truncate_first = False
            body = body[: len(body) // 3]
            self.send_header("Content-Length", str(len(body)))
        else:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def cfg():
    return {"sources": {"http_retries": 3, "http_timeout_seconds": 5}}


def test_month_range():
    assert dl.month_range("2024-11", "2025-02") == ["2024-11", "2024-12", "2025-01", "2025-02"]


def test_session_requests_identity_encoding():
    assert dl._session().headers["Accept-Encoding"] == "identity"


def test_resume_after_truncated_transfer(server, cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(dl.time, "sleep", lambda s: None)
    RangeHandler.truncate_first, RangeHandler.calls = True, []
    dest = tmp_path / "f.parquet"
    n = dl.download_file(f"{server}/f.parquet", dest, cfg)
    assert n == len(PAYLOAD) and dest.read_bytes() == PAYLOAD
    assert RangeHandler.calls[0] == "" and RangeHandler.calls[1].startswith("bytes=")
    assert not dest.with_name("f.parquet.part").exists()


def test_existing_complete_file_is_skipped(server, cfg, tmp_path: Path):
    dest = tmp_path / "f.parquet"
    dest.write_bytes(PAYLOAD)
    RangeHandler.calls = []
    assert dl.download_file(f"{server}/f.parquet", dest, cfg) == len(PAYLOAD)
    assert RangeHandler.calls == []


def test_manifest_upsert(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(dl, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "path", lambda key, cfg=None: tmp_path / "manifest.csv")
    f = tmp_path / "a.bin"
    f.write_bytes(b"xyz")
    m = dl.update_manifest([(f, 3)], cfg={})
    dl.update_manifest([(f, 3)], cfg={})
    lines = m.read_text().strip().splitlines()
    assert lines[0] == "file,bytes,download_date"
    assert len(lines) == 2 and lines[1].startswith("a.bin,3,")


def test_manifest_drops_files_no_longer_on_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(dl, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "path", lambda key, cfg=None: tmp_path / "manifest.csv")
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"x")
    b.write_bytes(b"yy")
    dl.update_manifest([(a, 1), (b, 2)], cfg={})
    b.unlink()
    m = dl.update_manifest([(a, 1)], cfg={})
    rows = m.read_text().strip().splitlines()[1:]
    assert [r.split(",")[0] for r in rows] == ["a.bin"]


def test_weather_request_uses_gmt_unixtime_and_padding(tmp_path: Path, monkeypatch):
    """Guards the Open-Meteo DST decision: the API applies a fixed EST offset for
    timezone=America/New_York, so we must request GMT unix seconds with a padded window."""
    captured: list[dict] = []

    def fake_get_json(session, url, params, cfg):
        captured.append(params)
        return {"hourly": {"time": [0], **{v: [1.0] for v in cfg["sources"]["weather_hourly"]}}}

    cfg = {
        "timezone": "America/New_York",
        "sources": {"weather_point": [40.7, -74.0], "weather_hourly": ["temperature_2m"],
                    "weather_units": {}, "weather_url": "http://x", "weather_pad_days": 1,
                    "http_retries": 1, "http_timeout_seconds": 1},
    }
    monkeypatch.setattr(dl, "_get_json", fake_get_json)
    monkeypatch.setattr(dl, "path", lambda key, c=None: tmp_path)
    monkeypatch.setattr(dl, "update_manifest", lambda rows, c=None: None)
    dl.download_weather("2024-07-01", "2024-07-31", cfg)
    (p,) = captured
    assert p["timezone"] == "GMT" and p["timeformat"] == "unixtime"
    assert (p["start_date"], p["end_date"]) == ("2024-06-30", "2024-08-01")
