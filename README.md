## Unity Games

A Frappe v15 app for inter-school sports registration. Guardians register
their child across tournament bodies (CBSE, ZP, district, in-house) through
a single web form; one submission may carry many games and fans out into
one immutable record per game with payment, consent, and audit built in.

### Stack

| Layer        | Choice                                              |
| :----------- | :-------------------------------------------------- |
| Backend      | Frappe v15 (`unity_games`)                          |
| Dependencies | `erpnext`, `education`, `payments`, `edu_quality`   |
| Data store   | MariaDB                                             |
| UI           | Frappe Web Form (`/unity-games/new`)                |
| Payments     | Easebuzz via Frappe `payments` app                  |
| Audit        | `frappe.Version` + submittable `docstatus`          |

### Data model

Four layers, twelve DocTypes:

- **Masters** — Game Organiser, Age, Game Events
- **Catalogue** — Games (+ age-group & events children)
- **Season** — Game Authority (+ games, image, class, fees children)
- **Registration** — Game Entry (+ details child); web form is hosted on Game Entry
- **Config** — Unity Games Settings (single), Unity Games Guardian Token

### Flow

1. Guardian opens the auto-login link → picks child → picks Game Authority.
2. Selects one or more games (Name of Game → Age Group → Events cascade).
3. Verifies 4-digit OTP (email + SMS) → submits.
4. Server fans the cart into one Game Entry per game with a shared payment carrier.
5. If a fee is due, the carrier routes through Easebuzz; siblings free-ride.

### Layout

```
unity_games/
├── unity_games/doctype/      DocTypes (json + controller + tests)
├── unity_games/web_form/     Registration web form
├── utils/                    helpers, api, permissions, gallery, tasks, google_calendar
└── hooks.py                  doc_events, scheduler, permission scoping
```

### Install

```bash
cd $PATH_TO_BENCH
bench get-app $REPO_URL --branch main
bench install-app unity_games
```

### License

MIT · Aman Kumar · Unity Edu
