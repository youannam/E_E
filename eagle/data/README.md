# Data

Eagle Eye uses **only synthetic data**. No public insider-threat dataset (such as the CERT
Insider Threat datasets) is included or required: those datasets have their own licensing terms
and a different event format, and the project brief allowed synthetic data. Every event is
produced by the simulator (`simulator/`) from a fixed random seed, so it can be regenerated
exactly.

Generated files go to `data/generated/` (git-ignored):

| File | Created by | Content |
|---|---|---|
| `training_events.csv` | `python -m ai.train` | Raw events of 40 synthetic employees over 90 days |
| `training_labels.csv` | `python -m ai.train` | One row per user-day: period (train/test), label, scenario |
| `last_evaluation.json` | `python -m ai.train` | AI-only metrics on the test period |
| `system_evaluation.json` | `python -m scripts.evaluate_detection` | Rules / AI / full-system metrics |

## Event schema (one row per activity)

| Field | Type | Meaning |
|---|---|---|
| `user_id` | string (CSV) / integer (API) | Employee identifier |
| `timestamp` | ISO 8601 date-time | Local organization time (`ORG_TIMEZONE`) |
| `event_type` | enum | LOGIN, LOGOUT, FILE_ACCESS, FILE_DOWNLOAD, FILE_UPLOAD, FILE_DELETE, USB_CONNECT, USB_TRANSFER, EMAIL_SENT, APPLICATION_USAGE |
| `resource` | string or empty | File/system path, e.g. `fs://finance/payroll/payroll_2026.xlsx`. Required for file and USB-transfer events |
| `sensitivity` | enum or empty | PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED. Required when a resource is given |
| `file_size_bytes` | integer or empty | Size for downloads, uploads and USB transfers |
| `device_id` | string or empty | e.g. `WS-OMAR-HASSAN` (workstation) or `USB-OMAR-HASSAN` (USB stick) |
| `scenario` | string (CSV only) | Which simulator scenario produced the event |

## Label schema (`training_labels.csv`)

| Field | Meaning |
|---|---|
| `user_id`, `day` | The user-day |
| `period` | `train` (first 60 days, normal behavior only) or `test` (last 30 days) |
| `label` | 1 = suspicious scenario (B-G), 0 = normal day or benign exception (H) |
| `scenario` | NORMAL_USER, UNUSUAL_LOGIN, EXCESSIVE_DOWNLOADS, SENSITIVE_ACCESS, MASS_DELETION, USB_TRANSFER, COMBINED_ANOMALY, BENIGN_EXCEPTION |

## How the synthetic behavior is generated

See `simulator/generator.py`. A normal day: login between the employee's start hour and +50
minutes, about 16 file accesses (scaled by a personal activity level), about 3 downloads, 2
uploads, 1 deletion, 10 emails, 8 application uses, a 5% chance of copying a non-sensitive file to
USB, and logout about 8 hours later. Each employee mostly uses a stable personal set of 8 files,
with an 8% chance per event of a less familiar file. Fridays and Saturdays are weekend days. One
role ("Night Operations Technician") works about 00:30-08:30.

## Limitations of the data

The scenarios were written by the project team, so the detection rules and the attacks were
designed together. Real behavior is noisier, real attacks are rarer and less obvious, and real
logs have missing and inconsistent fields. Results on this data demonstrate that the pipeline
works; they do not measure real-world detection performance.
