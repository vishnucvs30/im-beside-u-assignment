"""
procmine.segment
-----------------
A rule-based, unsupervised baseline for turning a raw event stream into
labeled segments ("units of work").

WHY RULE-BASED AND NOT ML: with 63 sessions (dataset A) and no labeled
training signal for dataset B's different departments/apps, a supervised
classifier would overfit to dataset A's specific synthetic vocabulary
(process names, app choices) and would not transfer. A transparent,
tunable heuristic is more defensible for a 7-day engagement, and its
failure modes are auditable (see EVAL notes in the report).

ALGORITHM
=========
1. BOUNDARY DETECTION
   Two independent signals nominate a boundary between event i and i+1:

   (a) IDLE GAP - the wall-clock gap exceeds `idle_gap_s`. Catches breaks,
       lunch, meetings, and any noise blocks between work.

   (b) NOVEL APP ENTRY - the newly-focused app was not part of the
       "active app set" over the preceding `lookback_s` seconds AND the
       current run of events in the old app(s) lasted at least
       `min_segment_s`. This is meant to catch back-to-back process
       switches that happen with ~0 idle gap (which, per validation
       against Dataset A ground truth, is the *common* case here - real
       office workers rarely go idle between tasks).

   Boundaries from (a) and (b) that land within `merge_within_s` of each
   other are merged into one.

2. LABELING
   Each segment gets a fingerprint made of:
     - the sorted tuple of *non-system* apps visited in the segment
       (SYSTEM_APPS filtered out - see io_utils)
     - the top-K most frequent CJK keyword substrings pulled from window
       titles / OCR'd screenshot text / clipboard previews inside the
       segment (cheap substitute for a real tokenizer+TF-IDF, since we
       cannot assume a Japanese NLP stack is available in the target
       environment)

   Segments are grouped into labels with a union-find: two segments are
   merged into the same label if they share the same app-tuple AND their
   keyword sets overlap above `keyword_jaccard_thresh`. This lets us tell
   apart processes that use the same app subset (e.g. this dataset's A/B/E
   families all touch chrome+excel+notepad) as long as their on-screen
   content differs, while still recognizing repeated executions of the
   *same* process as one label.

KNOWN LIMITATIONS (see report for the full discussion):
 - Purely observational; cannot see inside documents beyond OCR'd/extracted
   text, so two processes that look nearly identical on screen may be
   merged.
 - Threshold-driven; the numbers below were picked by grid-search against
   Dataset A ground truth (see eval.py) and may not transfer perfectly to
   Dataset B's different departments.
 - No use of screenshots themselves (only the *metadata/OCR text* already
   present in events.jsonl) - see report for why we deferred that.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .io_utils import Event, SYSTEM_APPS, cjk_keywords

# Event types that carry no "which app/window" signal of their own and are
# too noisy / frequent to use directly as boundary triggers (mouse move,
# screenshots, individual keydown/keyup). We still use their timestamps for
# idle-gap computation, just not as novel-app-entry triggers.
_BOUNDARY_TRIGGER_TYPES = {"app_switch", "window_title_change"}


@dataclass
class Segment:
    start: datetime
    end: datetime
    events: list[Event]


def _idle_and_novelty_boundaries(
    events: list[Event],
    idle_gap_s: float,
    lookback_s: float,
    min_segment_s: float,
) -> list[int]:
    """Return sorted list of event indices i such that a boundary falls
    between events[i-1] and events[i]."""
    boundaries = [0]
    last_boundary_ts = events[0].ts
    # rolling set of (app, ts) seen within lookback window
    recent_apps: list[tuple[str, datetime]] = []

    for i in range(1, len(events)):
        prev, cur = events[i - 1], events[i]
        gap = (cur.ts - prev.ts).total_seconds()

        is_boundary = False

        # (a) idle gap
        if gap >= idle_gap_s:
            is_boundary = True

        # (b) novel app entry
        if (not is_boundary) and cur.event_type in _BOUNDARY_TRIGGER_TYPES and cur.app:
            # prune lookback window
            recent_apps = [(a, t) for (a, t) in recent_apps
                           if (cur.ts - t).total_seconds() <= lookback_s]
            seen_recently = {a for a, _ in recent_apps}
            if cur.app not in seen_recently and cur.app not in SYSTEM_APPS:
                since_last = (cur.ts - last_boundary_ts).total_seconds()
                if since_last >= min_segment_s:
                    is_boundary = True

        if cur.app:
            recent_apps.append((cur.app, cur.ts))

        if is_boundary:
            boundaries.append(i)
            last_boundary_ts = cur.ts

    return boundaries


def _merge_close_boundaries(events, boundary_idxs, merge_within_s):
    if not boundary_idxs:
        return boundary_idxs
    out = [boundary_idxs[0]]
    for idx in boundary_idxs[1:]:
        gap = (events[idx].ts - events[out[-1]].ts).total_seconds()
        if gap < merge_within_s:
            continue  # drop - too close to previous boundary
        out.append(idx)
    return out


def build_segments(
    events: list[Event],
    idle_gap_s: float = 25.0,
    lookback_s: float = 20.0,
    min_segment_s: float = 4.0,
    merge_within_s: float = 2.0,
) -> list[Segment]:
    if not events:
        return []
    boundary_idxs = _idle_and_novelty_boundaries(
        events, idle_gap_s, lookback_s, min_segment_s
    )
    boundary_idxs = _merge_close_boundaries(events, boundary_idxs, merge_within_s)
    boundary_idxs.append(len(events))

    segments = []
    for a, b in zip(boundary_idxs, boundary_idxs[1:]):
        chunk = events[a:b]
        if not chunk:
            continue
        segments.append(Segment(start=chunk[0].ts, end=chunk[-1].ts, events=chunk))
    return segments


# --------------------------------------------------------------------------
# Labeling
# --------------------------------------------------------------------------

def _app_signature(seg: Segment) -> tuple[str, ...]:
    apps = {e.app for e in seg.events if e.app and e.app not in SYSTEM_APPS}
    return tuple(sorted(apps))


def _keyword_signature(seg: Segment, top_k: int = 8) -> frozenset[str]:
    from collections import Counter
    c = Counter()
    for e in seg.events:
        if e.text_blob:
            for kw in cjk_keywords(e.text_blob):
                c[kw] += 1
    return frozenset(k for k, _ in c.most_common(top_k))


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class _UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def label_segments(
    segments: list[Segment],
    keyword_jaccard_thresh: float = 0.30,
) -> list[str]:
    """Assign a label to each segment. Returns list of label strings aligned
    with `segments`."""
    n = len(segments)
    app_sigs = [_app_signature(s) for s in segments]
    kw_sigs = [_keyword_signature(s) for s in segments]

    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if app_sigs[i] != app_sigs[j]:
                continue
            if _jaccard(kw_sigs[i], kw_sigs[j]) >= keyword_jaccard_thresh:
                uf.union(i, j)

    # stable label naming: order clusters by first occurrence
    root_to_label: dict[int, str] = {}
    labels = []
    for i in range(n):
        r = uf.find(i)
        if r not in root_to_label:
            sig = app_sigs[i]
            name = "proc_" + ("_".join(a.replace(".exe", "").lower() for a in sig) or "misc")
            # disambiguate if this app-signature name already used by a
            # different cluster (different keyword content)
            base = name
            k = 2
            existing_names = set(root_to_label.values())
            while name in existing_names:
                name = f"{base}_{k}"
                k += 1
            root_to_label[r] = name
        labels.append(root_to_label[r])
    return labels


def segments_to_records(session_id: str, segments: list[Segment], labels: list[str]):
    for seg, label in zip(segments, labels):
        yield {
            "session_id": session_id,
            "start": seg.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": seg.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "label": label,
        }
