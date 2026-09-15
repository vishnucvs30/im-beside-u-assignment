# Data Specification

A reference for working with the provided data. This document explains **only how to read
the data.** It does not explain what to analyze or how — that is the task itself.

---

## 1. Directory structure

```
dataset_a/                                    <- with ground truth (63 sessions)
  ses_20260630-121953-LAPTOP-R36BQBTE/        <- session
    chunk_20260630-1200-LAPTOP-R36BQBTE/      <- chunk
      events.jsonl
      manifest.json
      screenshots/                            <- screen captures for this chunk
    chunk_20260630-1230-LAPTOP-R36BQBTE/
      events.jsonl
      manifest.json
      screenshots/
    gt.jsonl                                  <- ground truth
    gt_manifest.json                          <- ground truth summary

dataset_b/                                    <- no ground truth (15 sessions)
  ses_.../
    chunk_.../
      events.jsonl
      manifest.json
      screenshots/
```

### Sessions and chunks

- **Session** — one continuous recording, from start to stop.
  Directory name format: `ses_<date>-<time>-<machine>`
- **Chunk** — a session divided into fixed time buckets.
  This is a property of the recording agent and has **nothing to do with where business
  processes begin or end.** A single session may span multiple chunks.

---

## 2. events.jsonl — the operation log

One JSON object per line. A single session contains several hundred to several thousand
events.

### Common structure

```json
{
  "schema_version": "1.0.0",
  "event_id": "evt_...",
  "session_id": "ses_...",
  "timestamp_ms": 1782931327345,
  "timestamp_iso": "2026-07-01T18:42:07.345Z",
  "layer": "L2",
  "event_type": "app_switch",
  "source":      { "agent_version": "...", "machine_id": "...", "os": "...", "username_hash": "..." },
  "context":     { ... },
  "correlation": { ... },
  "payload":     { ... },
  "metadata":    {},
  "extensions":  {}
}
```

**All timestamps are UTC** (`timestamp_iso` ends with `Z`).

### layer — where the event came from

| layer | Meaning |
|---|---|
| `SYSTEM` | The agent's own activity (recording start/stop, uploads, browser extension state) |
| `L1` | Screen capture |
| `L2` | OS-level operations (app switching, keystrokes, mouse, clipboard, windows) |
| `L3` | In-browser operations (captured via a browser extension) |

### event_type reference

| layer | event_type | Description |
|---|---|---|
| L2 | `app_switch` | The active application changed |
| L2 | `keystroke` | A key press (one event per key) |
| L2 | `shortcut` | A keyboard shortcut |
| L2 | `mouse_click` / `mouse_double_click` | Mouse click |
| L2 | `mouse_scroll` | Scrolling |
| L2 | `mouse_drag_drop` | Drag and drop |
| L2 | `clipboard_change` | The clipboard contents changed |
| L2 | `text_input_complete` | Text entry finalized (**see the caveat below**) |
| L2 | `window_title_change` / `window_state_change` | Window state changes |
| L2 | `dialog_opened` / `dialog_closed` | A dialog was opened or closed |
| L1 | `screenshot_smart` | A screen capture was taken |
| L3 | `browser_click` | A click inside the browser (includes the clicked element) |
| L3 | `browser_form_input` | Input into a form field |
| L3 | `browser_navigation` | Page navigation |
| L3 | `browser_tab_event` | Tab operations |
| L3 | `browser_alert` | A browser alert |
| L3 | `browser_error` | A browser-side error |
| SYSTEM | `session_start` / `session_end` | Recording started / stopped |
| SYSTEM | `extension_connected` / `extension_disconnected` | Browser extension connection state |
| SYSTEM | `upload_started` / `upload_completed` / `upload_failed` | Transmission to the server |

### context — the situation when the event occurred

Present on every event, though how often each field is populated varies.

| Field | Description |
|---|---|
| `active_app` | The foreground application (`app_name`, `process_name`, `window_title`) |
| `active_monitor` | Monitor information (resolution, etc.) |
| `open_apps` | Applications running at that moment |
| `active_browser_tab` | Browser tab information (URL, title) |
| `visible_windows` | Windows visible on screen, with their coordinates |
| `extracted_text` | **Text read from the screen.** Present on roughly 4% of events |

### correlation — relationships between events

| Field | Description |
|---|---|
| `sequence_number` | Sequential index within the chunk |
| `chunk_id` | The chunk this event belongs to |
| `triggered_by` | The `event_id` of the event that triggered this one |
| `ms_since_last_event` | Milliseconds elapsed since the previous event |

### payload — details specific to each event type

The contents depend on `event_type`. The main ones:

- `app_switch` — `new_app` / `previous_app`
- `keystroke` — `key`, `character`, `modifiers`, `target_field` (information about the
  field receiving input)
- `browser_click` — `element` (with DOM attributes such as `id`, `class`, `placeholder`
  under `attributes`), `click_coordinates`
- `clipboard_change` — the clipboard transition
- `screenshot_smart` — `file_reference` (points to an image in the chunk's
  `screenshots/` folder), `trigger_reason`

### Screenshots

The images captured by `screenshot_smart` events are included in each chunk's
`screenshots/` folder (JPEG).

- To find the image for an event, use `payload.file_reference.filename` —
  the file sits at `<chunk>/screenshots/<filename>`.
- Filenames embed the capture time as epoch milliseconds (matching the event's
  `timestamp_ms`) and the monitor the capture came from, e.g.
  `scr_smart_1782885411296_monitor_1_post.jpg`.
- Resolve images through `file_reference` rather than by parsing filenames.
- A chunk that recorded no captures has no `screenshots/` folder, and in rare
  cases a referenced image may be absent (a single file across the whole
  distribution). Treat a missing file as "no capture available," not as an error
  in your pipeline.

Screen text is also available directly in the log through `context.extracted_text`
(see above) — you do not have to run OCR on the images to get at screen content.

### Caveats
- **`text_input_complete` is not reliable.** Due to a recording defect, some entries are
  missing their content, and some events that are not actually text input (such as
  keyboard shortcuts) are mixed in. If you need text input, reconstruct it from
  `keystroke` or `clipboard_change`.

---

## 3. gt.jsonl — ground truth (Dataset A only)

One JSON object per line. Records **which business process started when, and when the
worker switched away from it.**

**Timestamps are in the `ts_utc` field** (UTC, with timezone).

| event | Description | Key fields |
|---|---|---|
| `run_config` | Session configuration (first line) | `operator`, `operator_dept`, `machine_id` |
| `process_started` | A business process began | `process_code`, `process_name`, `case_id` |
| `process_switched_out` | Switched away to another process | `from`, `to` |
| `process_suspended` | The process was suspended | `from`, `to`, `split_id` |
| `process_resumed` | A suspended process resumed | `process_code`, `split_id`, `phase` |
| `task_started` | An individual task within a process began | `task_id`, `action`, `entity` |
| `clipboard_copy` / `clipboard_paste` | Copy and paste | `content_preview`, `target_app` |
| `session_ended` | The session ended | `total_tasks`, `duration_seconds` |

Every line also carries `current_process` (the process in progress at that moment) and
`process_variant`.

### Quirks in the recording

Because of how it is generated, `gt.jsonl` sometimes emits the same `process_started`
twice in a row. Also, `process_switched_out` does not always pair up with every process
start. **Verify consistency yourself before relying on it.**

---

## 4. gt_manifest.json — ground truth summary (Dataset A only)

A per-session summary of the business processes it contains.

```json
{
  "schema_version": "1.1.0",
  "run_id": "theme_m1_...",
  "session": { "start_ts": "...", "end_ts": "..." },
  "processes": [
    {
      "code": "A",
      "family_name": "住民税通知確認",
      "domain": "hr",
      "executions": [
        {
          "code": "A",
          "variant": "std",
          "case_id": "RT-132457-001",
          "start_ts": "2026-07-01T07:57:12.251773+00:00",
          "end_ts":   "2026-07-01T07:57:39.461211+00:00",
          "apps": ["chrome", "excel", "notepad"],
          "phase": 1,
          "seq": 1,
          "continues_from_prev": false,
          "continues_to_next": false
        }
      ]
    }
  ],
  "expected_boundaries": [ ... ]
}
```

| Field | Description |
|---|---|
| `processes[].code` / `family_name` | Process identifier and name |
| `processes[].domain` | Business domain |
| `executions[]` | **One entry per execution of that process** |
| `executions[].variant` | The handling pattern used in that execution |
| `executions[].start_ts` / `end_ts` | Execution start and end time (UTC) |
| `executions[].continues_from_prev` / `continues_to_next` | Whether the execution spans adjacent chunks |

---

## 5. Language

The logs come from a Japanese company. The following are in Japanese:

- Business process names (e.g. `住民税通知確認` — resident tax notification check)
- Screen text under `context.extracted_text`
- Application UI labels, window titles, and DOM attributes in the portal system

You are free to use translation tools or LLMs to work with this content.

---

## 6. Differences between Dataset A and B

| | dataset_a | dataset_b |
|---|---|---|
| Sessions | 63 | 15 |
| Events | ~162,000 | ~20,000 |
| Ground truth | Yes | **No** |
| Departments / processes | — | **Different from A** |
| Applications used | — | **Different from A** |

**Both come from the same company, but from different departments.** The work being
performed and the applications in use are different. An approach that works well on
Dataset A will not necessarily transfer to Dataset B.
