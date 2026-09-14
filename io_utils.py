"""
procmine.io_utils
------------------
Loading raw operation logs (events.jsonl + manifest.json across chunks) and
ground-truth (gt_manifest.json) into simple, memory-light Python structures.

Design goal: each session may be tens of MB of very verbose JSON (UIA trees,
screenshots metadata, etc). We never hold the raw dicts in memory - we stream
each line and keep only the handful of fields the segmentation algorithm
actually needs.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

# --------------------------------------------------------------------------
# Slim event representation
# --------------------------------------------------------------------------

# Apps that are always running / are the monitoring agent itself. These carry
# no signal about *what business process* is being worked on, so we exclude
# them from app-signature fingerprints (they would otherwise swamp every
# segment with the same "app").
SYSTEM_APPS = {
    "procmine-desktop-agent.exe",
    "explorer.exe",
    "NVIDIA Overlay.exe",
    "WindowsTerminal.exe",  # only used once at session start in this dataset
    "TextInputHost.exe",
    "SearchHost.exe",
    "ShellExperienceHost.exe",
}

# CJK run regex - used to pull out Japanese keyword candidates from window
# titles / OCR'd text without needing a real tokenizer.
_CJK_RUN = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]{2,}")


@dataclass
class Event:
    __slots__ = (
        "ts_ms", "ts", "seq", "chunk_id", "layer", "event_type",
        "app", "window_title", "text_blob",
    )
    ts_ms: int
    ts: datetime
    seq: int
    chunk_id: str
    layer: str
    event_type: str
    app: Optional[str]          # process_name of active app, e.g. "EXCEL.EXE"
    window_title: Optional[str]
    text_blob: str              # concatenation of any text signal on this
                                 # event (clipboard preview, extracted OCR
                                 # text, window title) - used for keyword
                                 # fingerprinting only, not stored verbatim
                                 # anywhere in outputs.


def _extract_text_blob(rec: dict) -> str:
    parts = []
    ctx = rec.get("context") or {}
    aa = ctx.get("active_app") or {}
    if aa.get("window_title"):
        parts.append(aa["window_title"])
    et = ctx.get("extracted_text")
    if isinstance(et, dict) and et.get("text"):
        parts.append(et["text"][:500])  # cap - OCR blobs can be huge
    payload = rec.get("payload") or {}
    for key in ("content_preview", "text_content"):
        v = payload.get(key)
        if isinstance(v, str):
            parts.append(v)
    tf = payload.get("target_field")
    if isinstance(tf, dict) and tf.get("name"):
        parts.append(tf["name"])
    return " ".join(parts)


def _parse_line(line: str) -> Optional[Event]:
    if not line.strip():
        return None
    rec = json.loads(line)
    ctx = rec.get("context") or {}
    aa = ctx.get("active_app") or {}
    corr = rec.get("correlation") or {}
    return Event(
        ts_ms=rec["timestamp_ms"],
        ts=datetime.fromisoformat(rec["timestamp_iso"].replace("Z", "+00:00")),
        seq=corr.get("sequence_number", -1),
        chunk_id=corr.get("chunk_id", ""),
        layer=rec.get("layer", ""),
        event_type=rec.get("event_type", ""),
        app=aa.get("process_name"),
        window_title=aa.get("window_title"),
        text_blob=_extract_text_blob(rec),
    )


def _chunk_dirs_in_order(session_dir: str) -> list[str]:
    """Order chunk directories by their manifest time_range.start_ms so that
    a session split across multiple chunks is read chronologically."""
    chunks = []
    for name in os.listdir(session_dir):
        cdir = os.path.join(session_dir, name)
        manifest_path = os.path.join(cdir, "manifest.json")
        if os.path.isdir(cdir) and os.path.isfile(manifest_path):
            with open(manifest_path, encoding="utf-8") as f:
                m = json.load(f)
            start = m["time_range"]["start_ms"]
            chunks.append((start, cdir))
    chunks.sort(key=lambda x: x[0])
    return [c for _, c in chunks]


def load_session_events(session_dir: str) -> list[Event]:
    """Load and time-order all events for a session across all its chunks."""
    events: list[Event] = []
    for cdir in _chunk_dirs_in_order(session_dir):
        ev_path = os.path.join(cdir, "events.jsonl")
        if not os.path.isfile(ev_path):
            continue
        with open(ev_path, encoding="utf-8") as f:
            for line in f:
                ev = _parse_line(line)
                if ev is not None:
                    events.append(ev)
    events.sort(key=lambda e: (e.ts_ms, e.seq))
    return events


def cjk_keywords(text: str) -> set[str]:
    """Cheap keyword extraction: contiguous CJK runs of length >= 2."""
    return set(_CJK_RUN.findall(text))


# --------------------------------------------------------------------------
# Ground truth (Dataset A only)
# --------------------------------------------------------------------------

@dataclass
class GTExecution:
    code: str
    family_name: str
    domain: str
    case_id: str
    exec_id: str
    start: datetime
    end: datetime
    apps: list[str]


def load_gt_executions(session_dir: str) -> list[GTExecution]:
    path = os.path.join(session_dir, "gt_manifest.json")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    out = []
    for p in d["processes"]:
        for e in p["executions"]:
            out.append(GTExecution(
                code=p["code"],
                family_name=p["family_name"],
                domain=p["domain"],
                case_id=e["case_id"],
                exec_id=e["exec_id"],
                start=datetime.fromisoformat(e["start_ts"]),
                end=datetime.fromisoformat(e["end_ts"]),
                apps=e["apps"],
            ))
    out.sort(key=lambda e: e.start)
    return out
