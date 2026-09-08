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
- Frontend: server-served vanilla HTML/JS (`frontend/static/`), LFB-branded
  (see "Brand" below) - prioritizes a correct upload -> match -> calculate
  -> export flow over frontend polish, per the build brief.

## Brand

Rebranded to Letshego Faidika Bank per
`docs/design_handoff_lfb_commission_rebrand/README.md` - visual layer only,
no functional change: black/`#FECD07` yellow LFB palette, Poppins
typeface, and the top tab bar replaced by a persistent left sidebar
(`app/static/index.html` + `style.css`; `app.js`'s element IDs and
event-wiring logic are unchanged, per that handoff's explicit constraint -
verified by diffing every `id=` attribute against the pre-rebrand version).
`app/static/assets/lfb-logo.png` is the supplied logo asset.

Three points where the handoff's mockup diverged from actual app behavior
or scope, resolved with the business owner before building (see git log):
- Commission Runs' footer copy about locking being blocked by open
  exceptions was **false** (the engine deliberately never blocks a lock on
  exceptions) - replaced with accurate copy instead of shipping the claim.
- "Reopen" (on PAID runs) and "History" (on DSAs) appear in the mockup but
  have no backing endpoint - omitted rather than shipped as dead links.
- Login's "Remember me" / "Forgot password?" / language switcher are
  inert by agreement (no backend support exists) - kept as non-misleading
  placeholders since the session is already always persisted regardless.

Verified with a full Playwright screenshot pass against every screen
(login, uploads incl. the tabbed upload-detail stat strip, commission
runs, exceptions, and all five Admin sub-sections) - caught and fixed two
real CSS specificity bugs along the way (sidebar items inheriting the base
button's yellow fill and full border; a stale `.active` class left on the
Admin sidebar group when navigating back to a top-level tab).

## Project layout

```
app/
  core/       config, db session, JWT auth, permission dependencies
  models/     SQLAlchemy models (see "Data model" below), rbac.py = roles/permissions
  schemas/    Pydantic request/response models
  services/   ingestion, upsert, matching, commission engine, roster sync, audit, permissions
  reports/    openpyxl Excel report generation
  api/        FastAPI routers
  api/admin/  users.py, roles.py, branches.py, dsas.py, dtls.py - mirrors the Admin sub-nav 1:1
frontend/static/           minimal JS/HTML UI
migrations/                 Alembic
scripts/seed.py             creates the first ADMIN user
scripts/seed_dsa_dtl_roster.py  one-time load of a supplied DSA/DTL reference list
scripts/deploy_summary.py   deploy-time Branch/DSA/DTL count summary - see "Deployment / CI-CD"
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

### WHT, SDL, WCF (DSA only - DTL is untouched)

**WHT (Withholding Tax) is deducted, DSA only.** `wht_amount = round(commission_amount
* Settings.dsa_wht_rate, 2)` (5%), computed per `CommissionLine` at calc
time alongside `net_commission_amount = commission_amount - wht_amount` -
the actual payable figure (e.g. for a future bank file). DTL lines never
get these set (`NULL`) - DTL commission math is completely unchanged.

**SDL and WCF are statutory REPORTING figures only - never deducted** from
what the DSA is paid. `SDL = Total Amount * 3.5%`, `WCF = Total Amount *
0.5%` (`Settings.dsa_sdl_rate` / `dsa_wcf_rate`), where Total Amount = that
DSA's Net Salary (post-WHT) on the run being reported, plus any manual
`commission_adjustments` already applied to them on that same run (see
`app/reports/excel.py::_dsa_adjustment_totals`) - there's no automatic
drop/clawback-from-transactions mechanism yet, only the manual adjustments
one, so this is the run-scoped default until that's built. Based on how the
legacy spreadsheet's formulas were structured - confirm with Finance before
ever changing this to an actual deduction.

### What "net" means for top-ups (RF)

**Confirmed by the business owner, 2026-09.** Current basis: Business
Manager's **Appl Amount minus Letshego Topup** - the portion of the
applied amount not already covered by Letshego's own top-up settlement.
(Superseded an earlier best-current-interpretation, Payout To Client -
`payout_to_client` is still stored on `business_transactions` for
reference/reconciliation, just no longer used as the commission base.)
This is deliberately isolated in one place -
`Settings.net_topup_minuend_field` / `net_topup_subtrahend_field` (see
their docstring) and `app/services/commission.py::get_topup_net_base()` -
so it can be corrected again without touching any other calculation logic.

**A non-positive net base (zero, negative, or a missing component) is
never used silently.** `calculate_commission_run` excludes that
transaction from commission (matches the existing zero/missing-base
guard), and `app/services/exceptions.py::find_exceptions()` surfaces it
in the Exceptions view/report as `INVALID_TOPUP_BASE` - computed fresh
every call (never stored), so a later upload correcting the Appl
Amount/Letshego Topup figures clears the flag automatically, the same way
`UNMATCHED_*` self-resolves.

**Formula changes never touch a LOCKED run.** Recalculation is refused
outright for anything but a `DRAFT` run (see "Commission run lifecycle"
below); a `LOCKED`/`PAID` run's `commission_lines` keep whatever was
computed under whichever formula was live at calc time. Correcting an
already-locked run to a newer formula is a deliberate
`commission_adjustments` entry, not something the app does automatically.

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
export, green/"finalized" once the run is `LOCKED` or `PAID`. Applies
identically everywhere the DSA/DTL Summary sheets are generated - branch-
scoped Branch Manager downloads and consolidated/per-branch Business
Manager downloads all come from the same `_add_dsa_summary_sheet` /
`_add_dtl_summary_sheet`.

**DSA Summary**: DSA Code, DSA Name, Branch, DSA Bank Account (`dsa_account_no`,
blank/"Not set" if unassigned), New Loans Amount, Topup Loans Amount,
Commission Total (Gross), WHT (5%), Net Salary (the actual payable figure),
SDL (informational only), WCF (informational only) - plus a sheet footnote
reiterating that SDL/WCF are statutory reporting figures, not a further
deduction. See "WHT, SDL, WCF" above. **DTL Summary** (unchanged by that):
DTL Name, Branch, DSAs Supervised, DTL Bank Account (`dtl_account_no`,
"Not set" until backfilled via Admin > DTLs), New Loans Amount, Topup Loans
Amount, Total Commission.

The two Amount columns are summed from the exact same `CommissionLine.base_amount`
values that produced that row's Commission Total (`aggregate_dsa_summary`
/ `aggregate_dtl_summary` in `app/reports/excel.py`, kept as pure,
independently-testable functions for exactly this reason) - so
`New Loans Amount * dsa_nl_rate + Topup Loans Amount * dsa_rf_rate` always
equals the row's Commission Total (Gross) by construction, not by
coincidence, and likewise `Commission Total (Gross) - WHT == Net Salary`;
see `tests/test_topup_base_and_reports.py::test_dsa_and_dtl_summary_amounts_reconcile_with_total_commission`
and `tests/test_wht_sdl_wcf.py`. Every monetary column across all four
sheet types renders as a real Excel currency cell (`number_format =
"#,##0.00"`), not a raw float.

## Sessions & auto-logout

This is a banking-adjacent internal tool, so a session doesn't just sit
valid for its full absolute JWT lifetime (`access_token_expire_minutes`,
8h) regardless of activity - it auto-expires after inactivity, and "logged
out" is enforced server-side, not just by the browser forgetting a token.

- **`user_sessions`** (`app/models/session.py`): one row per issued token,
  keyed by its `jti` claim. `app/core/deps.py::_authenticate` (shared by
  `get_current_user` / `get_current_session`) checks it on every request:
  revoked -> reject; idle longer than `session_inactivity_grace_minutes`
  -> revoke + reject; otherwise `last_seen_at` is bumped (sliding window)
  and the request proceeds.
- **Two timeouts, one policy** (`app/core/config.py`): `session_inactivity_minutes`
  (10) is what `app.js` actually enforces - it tracks mouse/keyboard/
  scroll/touch activity and every successful `api()` call, warns the user
  60 seconds before the cutoff (any activity, including passive mouse
  movement, dismisses the warning and resets the clock - see
  `#inactivity-warning` / `showInactivityWarning()`), and auto-logs-out if
  nothing resets it. `session_inactivity_grace_minutes` (12) is the
  server's own backstop, deliberately a bit longer: `app.js` throttles its
  "keep the server-side session fresh" pings to once every 60s, so a
  server cutoff at exactly 10 minutes could 401 a genuinely-active user a
  few seconds early. The grace period exists so the client-side timer -
  not a hair-trigger server clock - drives the real UX; the server backstop
  still means a token can't be replayed indefinitely if it's ever used
  directly against the API (bypassing the frontend's timer entirely).
- **`POST /api/auth/logout`** revokes only the calling token's own session
  (not every session the user has - a logout in one tab/device doesn't
  kill another). Both the manual Sign Out button and the frontend's
  auto-logout call it - `finishSignOut()` in `app.js` is the single place
  that actually clears local state and redirects, so neither path can
  skip the server-side revocation.
- A `401` from any `api()` call (revoked or inactivity-expired) forces the
  same sign-out path immediately, rather than leaving the UI acting as if
  it's still authenticated.

## Roles & permissions (RBAC)

Roles are no longer a fixed enum - `roles` / `permissions` / `role_permissions`
(`app/models/rbac.py`) replace it, managed via the Admin → Roles UI
(`MANAGE_ROLES`). Every endpoint is gated by a single reusable FastAPI
dependency, `require_permission(key)` / `require_any_permission(*keys)`
(`app/core/deps.py`) - no endpoint compares role name strings directly.
`app/services/permissions.py` is the canonical, editable-going-forward
permission catalog (19 permissions) and the starter grants for the three
seeded roles; the RBAC migration keeps its own frozen literal copy of that
same data (migrations must never re-import a live module that can change
later).

**What vs. where**: a role's permissions decide what a user can do;
`users.branch_id` (unchanged) decides which branch's data they can do it
to - a user has no branch (org-wide) or exactly one. Concretely: branch
scoping throughout the API keys off `current_user.branch_id is not None`
(forced to their own branch) vs. holding the matching `VIEW_ALL_*` /
`UPLOAD_*` permission (unrestricted) - see `_scope_uploads_query`,
`_scope_runs_query`, `_resolve_branch_scope` etc. in the relevant `app/api/*.py`.

Seeded system roles (`is_system_role=True` - permissions editable, role
itself never deletable):

| Role | Permissions |
|---|---|
| `ADMIN` | all 19 |
| `BRANCH_MANAGER` | `UPLOAD_BRANCH_FILE`, `VIEW_OWN_BRANCH_REPORTS`, `VIEW_OWN_BRANCH_EXCEPTIONS`, `VIEW_OWN_BRANCH_UPLOADS`, `OPERATE_COMMISSION_RUNS` |
| `BUSINESS_MANAGER` | `UPLOAD_BUSINESS_FILE`, `VIEW_ALL_REPORTS`, `VIEW_ALL_EXCEPTIONS`, `VIEW_ALL_UPLOADS`, `OPERATE_COMMISSION_RUNS`, `TRIGGER_MATCHING` |

Run-lifecycle actions (Review/Lock/Mark Paid/Adjustments) each have their
own permission (`REVIEW_COMMISSION_RUN`, `LOCK_COMMISSION_RUN`,
`MARK_RUN_PAID`, `MANAGE_ADJUSTMENTS`) rather than being bundled - all
admin-only in the starter grant, but a custom role could split them apart
(e.g. a reviewer who can't lock). Creating/viewing/(re)calculating a DRAFT
run (`OPERATE_COMMISSION_RUNS`) and viewing uploads (`VIEW_ALL_UPLOADS` /
`VIEW_OWN_BRANCH_UPLOADS`) are new permissions with no explicit spec
mapping - confirmed with the business owner before building; see git log
for that exchange.

**Lockout guard**: no role edit or delete may leave zero *active* users
holding `MANAGE_ROLES` system-wide - `_would_lose_all_manage_roles_access()`
in `app/api/admin/roles.py` (tested in `tests/test_rbac.py`, including the
inactive-user edge case). System roles can't be deleted at all
(`is_system_role`), and a role with users still assigned can't be deleted
either (409, reassign first).

**Admin UI**: the Admin tab is now a sub-nav (`app/api/admin/` package
mirrors it 1:1: `users.py` / `roles.py` / `branches.py` / `dsas.py` /
`dtls.py`) - Users, Roles, Branches, DSAs, DTLs. Each sub-nav item's
visibility is gated client-side by the matching `MANAGE_*` permission
(`GET /api/auth/me` now returns the caller's effective `permissions: []`
for exactly this). DSAs is new: an admin can onboard one directly (before
their first sale) and edit their branch/DTL - a DTL reassignment here goes
through the same `sync_assignment()` effective-dated mechanism an upload
uses, not a raw overwrite. While building that, found and fixed a real bug
in `sync_assignment()`: two reassignments on the same calendar day (e.g. an
admin correcting a DSA right after creating them) silently no-op'd against
a `<=` guard that was only meant to reject stale, late-arriving *upload*
data - same-day corrections now update the still-open assignment in place
instead (see `tests/test_roster_sync.py`).

**Bulk Update (DSAs and DTLs)**: `POST /api/admin/dtls/bulk-update` /
`.../dsas/bulk-update` (`MANAGE_DTLS` / `MANAGE_DSAS`), driven from a "Bulk
Update" button next to "+ New DTL/DSA". A correction path, not an
onboarding one - it takes a CSV/Excel file (DTL columns: `DTL_NAME`,
`BRANCH`, `DTL_CODE`, `DTL_ACCOUNT_NO`; DSA: `DSA_NAME`/`DSA_CODE`/
`DSA_ACCOUNT_NO` + `BRANCH`) and only ever updates the code/account number
on an **existing** record - it never creates one. Matching is by (name,
branch), case-insensitive and whitespace-**trimmed only** (deliberately not
whitespace-collapsed - real names here legitimately contain internal double
spaces, e.g. "Neema Jonas  Mussa", and collapsing them would silently break
a match that should succeed; branch casing like "RUVUMA" vs "Ruvuma" is
still handled since both sides are lowercased before comparing). A row that
doesn't match an existing record is never guessed at - it comes back
`UNMATCHED` in the response for an admin to review (new record? typo?
branch mismatch?), same as a code collision with another existing record or
a malformed (non-digit) account number comes back as an `ERROR` row,
neither applied. Also strips known copy-paste junk (stray tabs/quotes)
from the code/account number fields before validating them. Shared
matching/parsing logic: `app/services/bulk_details.py` (`tests/test_bulk_details.py`).
Used to bulk-correct 34 DTLs' real codes/account numbers from a legacy
roster export - see "Known assumption worth flagging" below for the two
DTLs that source file didn't cover, and for the one row (a name mismatch -
"Geofrey Oziniel" in the system vs "Geofrey  Oziniel Sylvester" in the
source file) that came back `UNMATCHED` and was deliberately left for an
admin to review rather than guessed at.

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

Two DTLs found in a real commission file but missing from the app (Jeremia
Mwakalase - Mbeya; Farida Matola - Tabora) were added via Admin > DTLs
(`PENDING-035` / `PENDING-036` - the source had no `DTL_CODE` for either, so
per the existing `PENDING-` convention above, a real code will be adopted
automatically onto these records the first time a Branch Manager upload
carries one for a matching name/branch, same as every other `PENDING-`
DTL). No other data from that legacy spreadsheet was imported.

A later 34-row bulk-update file (see "Bulk Update" above) covered neither
of those two - still `PENDING-035`/`PENDING-036`, unaffected by this
task's data load, exactly as expected. That file also had one row
(`PENDING-032`, "Geofrey Oziniel" in the system, Tanga) come back
`UNMATCHED` because the source file's name for the same branch was
"Geofrey  Oziniel Sylvester" - a real name mismatch, not a whitespace/
casing artifact, so the bulk-update matcher correctly left it alone rather
than guessing; still `PENDING-032` pending manual review of which name is
right.

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
(including the same-name-different-branch non-collision case), same-day
vs. next-day DTL reassignment history, commission rate math, the DSA-only
WHT deduction and SDL/WCF statutory reporting figures (including that DTL
lines/the DTL Summary report are untouched - `tests/test_wht_sdl_wcf.py`),
the locked-run-cannot-recalculate guard, permission checks
(`test_rbac.py::test_user_has_permission_reflects_role_grants`), the
MANAGE_ROLES lockout guard including the inactive-user edge case
(`test_rbac.py::test_lockout_guard_*`), the top-up net base formula and
its zero/negative/missing-component guard, the `INVALID_TOPUP_BASE`
exception being computed fresh (and clearing itself when the upstream
figures are corrected, without a re-match), the DSA/DTL Summary report
amount-columns-reconcile-with-Total-Commission sanity check
(`test_topup_base_and_reports.py`), session auth - sliding-window
revalidation, revocation on logout, the server-side inactivity backstop,
and that logging out one session doesn't touch another
(`test_session_auth.py`), and the DSA/DTL Bulk Update matcher - case-
insensitive/whitespace-trimmed-not-collapsed name+branch matching, never
creating a record on an unmatched row, code-collision and malformed-
account-number rejection, and the stray-tab/quote sanitization
(`test_bulk_details.py`).

## Deployment / CI-CD

Production runs on `102.204.1.22` (`dsa.miracore.co.tz`), under `/opt/dsa`.
That host is a **shared, live server** - it already runs an unrelated
"MiraCore" stack (Apache Fineract + Keycloak in k3s, its own Postgres
instance for that stack) - so DSA was deliberately kept isolated from it:

- **Own Postgres cluster**: a separate PostgreSQL 16 cluster
  (`postgresql@16-dsa.service`, port 5433, `listen_addresses=localhost`),
  not the existing MiraCore instance. Nothing else on the box shares this
  database.
- **Plain systemd service**, not a k3s pod: `dsa.service` runs
  `uvicorn app.main:app` on `127.0.0.1:8000` under a dedicated, unprivileged
  `dsa` system user with `ProtectSystem=strict` / `ReadWritePaths=/opt/dsa`.
  Decoupled from the k3s cluster the other apps here run in.
- **Own nginx vhost + TLS**: `dsa.miracore.co.tz`, cert via
  `certbot --webroot`, auto-renewing. Reverse-proxies to the uvicorn
  service above.

### Pipeline (`.github/workflows/deploy.yml`)

Triggers on push to `master` (the repo's actual default branch - PRs into
`master` run tests only, via the `pull_request` trigger, without deploying):

1. **test** - installs deps, runs `pytest` (in-memory SQLite, no DB service
   needed). Deploy only runs if this passes.
2. **deploy** (push to `master` only) - `rsync`s the working tree to
   `/opt/dsa` over SSH, then over the same connection: `pip install`,
   `alembic upgrade head`, `systemctl restart dsa.service`, then polls
   `/api/health` for up to ~20s and **fails the job** (dumping
   `journalctl -u dsa.service`) if the service doesn't come back healthy.
   Only once that health check has actually passed, it runs
   `scripts/deploy_summary.py` (as the `dsa` user, against the DB directly -
   no new credentials/service account needed) and prints "Total Branches"
   (with names), "Total DSAs", and "Total DTLs" straight into the job log,
   so a deploy's data state is visible without logging into the app
   separately. Deliberately **read-only and non-gating**: a failure here
   (`|| echo ... non-fatal`) never fails an otherwise-healthy deploy - it's
   for a human to sanity-check the numbers, not an automated threshold.
   A final step re-checks `https://dsa.miracore.co.tz/api/health` from
   outside the box.

All deploy credentials live in GitHub Actions secrets on this repo
(`DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`, `DEPLOY_HOST`, `DEPLOY_USER`) -
never committed. The CI deploy key is a dedicated keypair (not the
engineer's own SSH key used for manual server access), added as its own
line in the server's `authorized_keys` so it can be revoked independently.

`.env` on the server (DB URL, JWT secret, etc.) is deploy-target-local and
excluded from the rsync (`--exclude='.env'`) - it's provisioned once during
setup, not shipped by the pipeline.

`tests/conftest.py` seeds the same role/permission catalog into the
in-memory test DB that the RBAC migration seeds in production (reusing
`app.services.permissions`, not the migration's frozen copy - tests should
track current app behavior).
