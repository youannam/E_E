# Eagle Eye role access matrix

All authorization is enforced by the FastAPI backend. Hiding navigation items in a client is only a usability measure and is not the security boundary.

| Capability | Admin | Analyst |
|---|---:|---:|
| View the operational overview / aggregate dashboards | Yes | No |
| View and investigate alerts | Yes | Yes |
| Add investigation notes, assign to self, change alert status, resolve / mark false positive | Yes | Yes |
| Run synthetic Detection Lab scenarios through Rules + AI | Yes | Yes |
| View monitored-user directory and profiles | Yes | No |
| Create, edit, delete monitored users | Yes | No |
| Read raw activity stream | Yes | No |
| Configure detection rules | Yes | No |
| Create, edit, disable, or delete login accounts / roles | Yes | No |
| Reload the AI model and ingest raw activity | Yes | No |

## Demo data

A clean development database contains 25 fictional monitored users, normal synthetic activity history, and three suspicious example scenarios processed through the real ingestion and detection pipeline. The Detection Lab can generate additional synthetic scenarios without resetting the database. These examples are for demonstration and testing only; an alert is a lead for review, not proof of wrongdoing.

## Local demo accounts

- Admin: `admin` / `EagleAdmin@2026!`
- Analyst: `analyst` / `EagleAnalyst@2026!`

These credentials are development-only and must not be reused outside this local demo.
