# Unity Games

A standalone Frappe app that digitises student participation in inter-school
sporting events (CBSE, ZP, Subroto, district, Walnut-internal). Parents register
their child(ren) through a single authenticated Web Form whose dropdowns cascade
through a normalised data model: **organiser → game → age group → events**.

> **Status — Architecture only (15 May 2026).** This repository currently ships
> **DocType JSON + bare scaffolding** (controllers are `pass`, `.js` are stubs,
> tests are `pass`, no logic modules; `hooks.py` `doc_events`/`scheduler_events`
> are commented). All server logic, the Web Form, auth, payments and Google
> Calendar sync are designed and documented but **not yet implemented** — see
> the PRD (§20 is the revision/build-status log).

## Overview

- One authenticated Web Form for parents to register across all organisers + events.
- Configuration-driven: a new game / organiser / season is **data, not code** — no deploy to onboard a new tournament body.
- One submission may carry multiple games; the server fans them out into **one immutable Game Entry per game**, each validated against the student's Program Enrollment.
- Auth via a token-based auto-login link (no OTP/password), modelled on Walnut's existing Student Applicant / CRM Invitation patterns.
- Payments reuse Frappe's `payments` app (a configurable Payments tab on the Web Form — no bespoke payment code).
- Selected registrations are later pushed to the external portal (cbseit.in) by a Playwright RPA, with a CSV-export fallback.
- 100% audit trail via Frappe Version (`track_changes`) + submittable `docstatus`.

## Architecture — 4 layers, 13 DocTypes

**Layer 1 — Master lookups**
- **Game Organiser** — tournament body (CBSE, ZP Pune, …)
- **Age** — age bands (Under 14, Under 17, …)
- **Game Events** — shared pool of all event/category names

**Layer 2 — Composite catalogue**
- **Games** — one row per (organiser, game); name = `{organiser}-{name_of_game}`
  - **Age Group** *(child)* — allowed age bands → Age
  - **Events** *(child)* — allowed events → Game Events

**Layer 3 — Season**
- **Game Authority** *(submittable)* — a running tournament/season; tabs: Details / Gallery / Google Calendar / Rules & Limitations
  - **Game Authority Games** *(child)* — games in scope → Games
  - **Game Authority Image** *(child)* — event gallery
  - **Game Authority Class** *(child)* — eligible classes/divisions → Program

**Layer 4 — Registration (Web Form host)**
- **Game Entry** *(submittable)* — the parent's submission; cascading filters, PE resolution, multi-game fan-out
  - **Game Entry Details** *(child)* — multi-game cart → fan-out snapshot

**Configuration**
- **Unity Games Settings** *(Single)* — default Google Calendar, reminder policy, consent text, RPA credentials, late-fee config

## Tech stack

| Layer | Choice |
| :---- | :---- |
| Backend | Frappe v15 standalone app (`unity_games`) |
| Dependencies | `erpnext`, `education`, `payments`, `edu_quality` |
| Data store | MariaDB |
| Web form | Frappe Web Form on Game Entry |
| Payments | Frappe `payments` app (Payments tab) |
| Auth | Token auto-login (Guardian `form_hash`) |
| External sync | Playwright RPA (Phase 2) + CSV fallback |
| Audit | Frappe Version (`track_changes`) + `docstatus` |

## Key flows (designed; pending implementation)

- **Parent:** auto-login link → pick child (PE resolves server-side) → pick Game Authority → add one or more games (cascading Name of Game → Age Group → Events) → consent → submit once → server fans out to one Game Entry per game → pay once if fee > 0.
- **Coordinator:** seed masters → build Games per (organiser, game) → create a Game Authority per season → publish Web Form + send auto-login notice → review entries → Shortlist/Select → RPA push.

## Project layout

```
unity_games/unity_games/doctype/   # all 13 DocTypes (json + bare py/js/test)
unity_games/hooks.py               # required_apps declared; events deferred
docs/prd/                          # Product Requirements Document
```

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app unity_games
```

## Reference

Full Product Requirements Document: `docs/prd/Unity Games - Revised.md`
(BRD + PRD §1–19, Appendices, and §20 the enhancement/build-status revision log).

## License

mit

---

*Author: Aman Kumar · Unity Edu*
