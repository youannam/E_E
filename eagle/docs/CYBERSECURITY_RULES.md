# Cybersecurity rules

Code: `backend/detection/rules.py` (logic), `backend/detection/rule_config.py` (default settings),
table `rule_settings` (current settings), `GET/PATCH /api/v1/rules`, web page *Detection rules*.

Each rule is a small Python function that looks at one user-day and returns either nothing or a
finding: `rule_id`, `name`, `severity`, `contribution` (its weight), a human-readable `reason`,
`evidence` numbers, and the IDs of the events that matched (linked to the alert as evidence).

## Personal thresholds

Most rules compare today's count with the user's baseline (see
[AI_METHODOLOGY.md](AI_METHODOLOGY.md#3-behavioral-baseline)):

    threshold = max(minimum, mean + k × standard deviation)        (default k = 3)

*mean + 3 × std* adapts to each person's normal workload; *minimum* stops the rule from firing on
tiny numbers when someone's history is almost always zero. A value equal to the threshold does not
trigger; only values above it do.

## The rules

| # | Rule ID | Severity | Weight | Fires when | Required fields | Parameters (defaults) |
|---|---|---|---|---|---|---|
| 1 | `UNUSUAL_LOGIN_TIME` | MEDIUM | 15 | a LOGIN between 22:00 and 06:00 **and** the user's baseline has fewer than 0.2 night logins per day | event_type, timestamp | `max_usual_night_logins_per_day` 0.2 |
| 2 | `EXCESSIVE_DOWNLOADS` | HIGH | 20 | downloads today > max(15, mean + 3·std) | event_type | `std_multiplier` 3, `minimum_count` 15 |
| 3 | `EXCESSIVE_DOWNLOAD_VOLUME` | HIGH | 20 | MB downloaded today > max(150, mean + 3·std) | event_type, file_size_bytes | `std_multiplier` 3, `minimum_mb` 150 |
| 4 | `SENSITIVE_RESOURCE_ACCESS` | CRITICAL | 25 | any file/USB event on a resource more sensitive than the job role's clearance | event_type, resource, sensitivity | `role_clearance` per role, `default_clearance` INTERNAL |
| 5 | `MASS_FILE_DELETION` | HIGH | 20 | deletions today > max(20, mean + 3·std) | event_type | `std_multiplier` 3, `minimum_count` 20 |
| 6 | `USB_SENSITIVE_TRANSFER` | CRITICAL | 30 | ≥ 1 USB_TRANSFER of a CONFIDENTIAL or RESTRICTED file | event_type, sensitivity | `minimum_transfers` 1 |
| 7 | `UNUSUAL_RESOURCE_ACCESS` | MEDIUM | 10 | ≥ 5 resources today never used by the user in the previous 30 days (INDIVIDUAL baseline only) | event_type, resource | `minimum_new_resources` 5 |
| 8 | `HIGH_ACTIVITY_VOLUME` | MEDIUM | 10 | events today > max(120, mean + 3·std) | event_type | `std_multiplier` 3, `minimum_events` 120 |

Time window: one day for every rule; rule 7 also looks back 30 days.

### Role clearances (rule 4, organization policy)

| Job role | Highest allowed sensitivity |
|---|---|
| Finance Manager, HR Manager | RESTRICTED |
| Software Engineer, Accountant, HR Specialist, Sales Manager, System Administrator | CONFIDENTIAL |
| QA Engineer, Sales Representative, Night Operations Technician | INTERNAL |
| any other role | INTERNAL (`default_clearance`) |

The data only says how sensitive a resource is, not which department owns it, so this rule uses
role + sensitivity only. Access to *other departments'* files is caught by rule 7 instead, when
those files are new for the user.

## Rule score

    rule_score = min(100, sum of the weights of the triggered rules)

The cap keeps overlapping rules (a download burst can trigger rules 2, 3 and 8) inside the 0-100
scale. How the rule score is combined with the AI score is in [RISK_SCORING.md](RISK_SCORING.md).

## Configuration

* Defaults live in `backend/detection/rule_config.py` and are copied to `rule_settings` by `init-db`.
* An administrator can enable/disable a rule, change its weight and change numeric thresholds or
  role clearances on the *Detection rules* page or with `PATCH /api/v1/rules/{rule_id}`. Unknown
  parameters and negative numbers are rejected; each change is written to the audit log.
* Settings apply to analyses from that moment on; existing alerts keep the snapshot of the rules
  that produced them.

## Example finding (real output of the combined-anomaly demo for omar.hassan)

```json
{"rule_id": "EXCESSIVE_DOWNLOADS", "name": "Excessive downloads", "severity": "HIGH",
 "contribution": 20.0,
 "reason": "26 file downloads today, above the threshold of 15 (individual baseline average 3.1)",
 "evidence": {"observed": 26.0, "threshold": 15, "baseline_type": "INDIVIDUAL", "baseline_mean": 3.091, "baseline_std": 1.276}}
```

Here mean + 3·std = 3.091 + 3 × 1.276 = 6.9, which is below the minimum, so the threshold is 15.

## Tests

`tests/test_rules.py` checks every rule in triggered, not-triggered and edge cases (value exactly at
the threshold, night-shift baseline, unknown role, PEER/DEFAULT baselines for rule 7, disabled rules,
changed thresholds, the 100-point cap).
