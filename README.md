# DSA/DTL Commission Calculation App

Letshego Faidika Bank (LFB) monthly DSA/DTL commission calculation: merges
the Branch Manager roster file with the Business Manager payout file,
reconciles them, calculates commission, and produces downloadable Excel
reports.

Everything for this app lives inside this project folder (`c:\laragon\www\dsa`),
including its own Python virtualenv (`venv/`). Nothing outside this folder is
touched except the shared local PostgreSQL 18 instance bundled with Laragon,
which now hosts a dedicated `dsa` database and a scoped `dsa_app` login role
(see "Database" below) - the app never uses the Postgres superuser account.

## Stack

- Backend: Python 3.13 + FastAPI
- DB: PostgreSQL (via SQLAlchemy 2.0 + Alembic + psycopg3)
- File processing: pandas + openpyxl
- Auth: JWT (python-jose), role stored on the user record
- Frontend: minimal server-served vanilla HTML/JS (`frontend/static/`) -
  prioritizes a correct upload -> match -> calculate -> export flow over
  frontend polish, per the build brief.

## Project layout

```
app/
  core/       config, db session, JWT auth, role dependencies
  models/     SQLAlchemy models (see "Data model" below)
  schemas/    Pydantic request/response models
  services/   ingestion, upsert, matching, commission engine, roster sync, audit
  reports/    openpyxl Excel report generation
  api/        FastAPI routers
frontend/static/           minimal JS/HTML UI
migrations/                 Alembic
scripts/seed.py             creates the first ADMIN user
scripts/seed_dsa_dtl_roster.py  one-time load of a supplied DSA/DTL reference list
tests/                       pytest - ingestion quirks, upserts, matching, commission math
```

## Setup

1. **Python deps** (already done in this checkout - `venv/` exists):
   ```
   venv/Scripts/pip.exe install -r requirements.txt
   ```

2. **Database**. Copy `.env.example` to `.env` and fill in the `dsa_app`
   role's connection string (see "Database" below for how that role was
   created). Then:
   ```
   venv/Scripts/alembic.exe revision --autogenerate -m "initial schema"
   venv/Scripts/alembic.exe upgrade head
   ```

3. **Seed an admin user**:
   ```
   venv/Scripts/python.exe scripts/seed.py --email you@example.com --password "..." --name "Your Name"
   ```

4. **Run**:
   ```
   venv/Scripts/uvicorn.exe app.main:app --reload --port 8000
   ```
   Open http://127.0.0.1:8000/ and sign in.

## Database

PostgreSQL 18 is bundled with this machine's Laragon install and runs as the
`postgresql-x64-18` Windows service. Since the superuser password was
unknown, a one-time elevated script (`reset-postgres.ps1`, run outside this
repo, not checked in - it contained credentials) reset the `postgres`
password and created:
- database `dsa`
- login role `dsa_app`, owner of `dsa`, scoped to only that database

The app's `.env` should point `DATABASE_URL` at `dsa_app`, never at the
`postgres` superuser.

## Commission rules

Per calendar month, bucketed by the **Business Manager file's Disbursement
date** (`app/services/matching.py::_commission_period`) - the Branch
Manager's DATE column is informational only and never used for bucketing:

| Payee | New Loan (NL) | Top-up (RF) |
|---|---|---|
| DSA | 7% of gross (Disbursement Amt) | 3% of net |
| DTL | 1% of gross (Disbursement Amt) | 1% of net |

Rates live in `app/core/config.py::Settings` (`dsa_nl_rate`, `dtl_nl_rate`,
`dsa_rf_rate`, `dtl_rf_rate`), not hardcoded in the calculation logic.

### What "net" means for top-ups (RF)

**Not yet signed off by Finance.** Current basis: Business Manager's
**Payout To Client** column - the new money released to the client after
their prior loan balance was settled. This is deliberately isolated in one
place - `Settings.net_topup_basis_field` (see its docstring) and
`app/services/commission.py::get_topup_net_base()` - so it can be corrected
without touching any other calculation logic. If Finance defines "net"
differently, change only that one function/setting.

## Incremental uploads & period selection

Branch Managers (and the Business Manager) don't upload one final file at
month-end - they upload repeatedly through the month as sales happen. Every
upload requires an explicit **period** (month + year, picked in the UI) and
is an **upsert**, not a blind insert:

- `branch_sales` natural key: `(client_account_no, period_month, period_year)`
- `business_transactions` natural key: `(client_disb_ext_account_no, loan_type, disbursement_date)`

A row whose natural key already exists for that period **updates** the
existing row (and logs the diff to `audit_log` via `app/services/upsert.py`)
instead of inserting a duplicate that would double-count commission. A
different period is a genuinely different row (period is part of the key).

**Date validation is hard, per upload:** every row's own date (`DATE` for
Branch Manager, `Disbursement date` for Business Manager) is checked against
the period selected for *that* upload. Outside the period, missing, or
unparseable -> the row is a validation **error**, excluded from ingestion,
and listed in the response/`upload_errors` (never silently accepted or
defaulted) - see `app/services/ingest_branch_manager.py` /
`ingest_business_manager.py`.

**Multi-sheet Branch Manager workbooks** (one sheet per branch, sheet name =
branch name) are supported alongside the normal single-sheet upload - see
`parse_branch_manager_file`. A Branch Manager's own upload only ever
processes the sheet matching their branch (others are rejected, not
silently dropped); an Admin's multi-sheet upload resolves each sheet's
branch by name, for bulk/migration loads.

A period's data is always "current, so far" - there is no "final file";
reports generated before a run is `LOCKED`/`PAID` say so visibly (see
Reports below).

## Matching / reconciliation

- Primary key: `BranchSale.client_account_no == BusinessTransaction.client_disb_ext_account_no`
- Secondary check: `BranchSale.client_check_no == BusinessTransaction.employee_no`
- Classifications: `MATCHED`, `MATCHED_WITH_WARNING`, `UNMATCHED_IN_BUSINESS_FILE`,
  `UNMATCHED_IN_BRANCH_FILE`, `DUPLICATE` (tiebreak: closest disbursement
  date to the branch sale's informational loan_date).
- Only `MATCHED` / `MATCHED_WITH_WARNING` feed commission calculation.
  Everything else surfaces in the Exceptions view/report and **does not
  block** any other part of the pipeline, but must be visible before a run
  is locked (see `app/api/reports.py` exceptions endpoint / Exceptions tab).
- Matching re-runs (and incrementally extends) after every upload -
  `UNMATCHED_*` is never treated as a permanent classification: a branch
  sale uploaded on day 3 with no business-file match yet will pick one up
  automatically once the business file lands on day 10 (`run_matching`
  only leaves `MATCHED` / `MATCHED_WITH_WARNING` / `DUPLICATE` rows alone;
  everything else is recomputed from scratch on every run). An upsert-driven
  correction to an already-matched row (e.g. a DSA reassignment) doesn't
  need a re-match either - commission calculation reads the live row at
  calculation time, so the correction is picked up on the run's next
  (DRAFT-only) recalculation.

## Commission run lifecycle

`DRAFT -> REVIEWED -> LOCKED -> PAID` (`app/services/commission.py`).
- `DRAFT`: calculation can be freely re-run (existing lines for that run are
  replaced).
- Once `LOCKED`, a run's `commission_lines` are **never mutated**.
  Corrections go through `commission_adjustments` rows absorbed by a later
  (non-locked) run - see `POST /api/commission/adjustments`.
- A transaction is never double-paid: before writing lines, the engine
  checks no *other* run (any scope, any status) already has a line for that
  `matched_transaction_id`.
- `run_type` can be `ORG_WIDE` (Business Manager/Admin, all branches) or
  `BRANCH` (Branch Manager, their own branch only). In practice, expect one
  `ORG_WIDE` run per period to be the canonical calculation; per-branch
  Excel exports are filtered views of it (`GET /api/reports/commission/{run_id}?branch_id=`).
  Branch-scoped runs remain available (e.g. for a branch manager's early
  look at their own numbers) and are protected from double-paying by the
  same-transaction guard above.

## Reports

Every sheet of every Excel export (`app/reports/excel.py`) opens with a
2-row banner: the period covered, the generation timestamp, and a status
line - orange/"NOT finalized" for a `DRAFT` (or standalone, run-less)
export, green/"finalized" once the run is `LOCKED` or `PAID`.

## Roles

- `BRANCH_MANAGER`: upload their branch's roster; download their branch's
  sales/commission reports. Scoped to `user.branch_id` everywhere.
- `BUSINESS_MANAGER`: upload the org-wide payout file; view/download
  consolidated and per-branch commission reports.
- `ADMIN`: manage users/branches/DTL codes; review and lock commission runs;
  view exceptions across all branches.

## Known assumption worth flagging

`app/services/roster_sync.py` keeps `dsas` / `dtls` / `dsa_dtl_assignments`
in sync from each Branch Manager upload. Per-transaction DTL attribution for
commission uses the DTL recorded directly on that specific roster row
(`BranchSale.dtl_code`) - the most precise available signal - falling back
to the effective-dated assignment history only if a row's DTL fields are
blank. The assignment table's `effective_from` is taken from that upload's
transaction dates (or the upload date if none), since there's no separate
"assignment change" input file. This is a reasonable default, not something
explicitly specified - flagged here for review.

## Testing

```
venv/Scripts/python.exe -m pytest -q
```

Covers: header-whitespace tolerance, trailing-blank-row filtering,
text-not-numeric CLIENT_CHECK_NO, out-of-period/missing-date rejection,
multi-sheet workbooks, Business Manager header-row detection past the
metadata block, LOANTYPE prefix parsing, whitespace stripping, upsert-not-
duplicate on re-upload (including the different-period-is-a-different-row
case), all five match classifications, `UNMATCHED_*` being re-resolved when
the other file arrives later, the DTL `PENDING-` code reconciliation
(including the same-name-different-branch non-collision case), commission
rate math, and the locked-run-cannot-recalculate guard.
