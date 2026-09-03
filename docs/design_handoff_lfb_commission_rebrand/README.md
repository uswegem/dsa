# Handoff: LFB DSA/DTL Commission App — brand redesign

## Overview

A visual and UX redesign of the existing DSA/DTL Commission App (`github.com/uswegem/dsa`, branch `master`), rebranded to Letshego Faidika Bank. Structure and functionality are unchanged: same pages, same tables, same columns, same form fields, same copy. What changes is the visual layer, plus one navigational move — the horizontal tab bar becomes a persistent left sidebar.

Source of truth for the current app: `frontend/static/index.html`, `frontend/static/style.css`, `frontend/static/app.js` in that repo.

## About the design files

The files in this bundle are **design references created in HTML** — prototypes showing intended look and behavior, not production code to copy directly. The task is to **recreate these designs in the existing codebase's environment**: the app is a FastAPI backend serving a static vanilla-JS frontend (`frontend/static/`), so the natural implementation is to update `style.css` and the markup in `index.html` in place, keeping `app.js`'s element IDs and event wiring intact.

Every element ID in the current `index.html` still exists conceptually in these designs. Do not rename IDs — `app.js` depends on them.

## Fidelity

**High-fidelity.** Final colors, typography, spacing, radii and states. Recreate pixel-accurately with the values in the Design Tokens section below.

## Files in this bundle

| File | What it is |
| --- | --- |
| `LFB Commission App.dc.html` | All nine screens, navigable. Sidebar switches pages; "Sign out" goes to Login; clicking an upload row opens the upload detail. Demo states (empty, loading, form errors, login error) are toggles on the component's props. |
| `LFB Palette.dc.html` | The derived color system with rationale, ramps, and applied examples (nav, buttons, table headers, form fields, status badges). |
| `assets/lfb-logo.png` | The supplied LFB logo, cropped to its black field. 1729×476. Use as-is; do not redraw or recolor. |
| `_ds/modernist-.../styles.css` | The Modernist design-system token sheet the designs are built against (Archivo-based; type here is overridden to Poppins per client direction). |

Open the `.dc.html` files in a browser to interact with them.

## Design tokens

### Brand

Both brand colors are sampled from the supplied logo.

| Token | Value | Role |
| --- | --- | --- |
| `--lfb-yellow` | `#FECD07` | Primary action, active nav marker, focus ring, key emphasis |
| `--lfb-ink` | `#0B0B0B` | Table headers, LOCKED badge, active sidebar item |
| `--lfb-black` | `#000000` | Login hero background and app top bar **only** — matches the logo asset's own opaque field so the PNG shows no seam. Do not substitute `#0B0B0B` on surfaces carrying the logo. |
| `--lfb-charcoal` | `#1F1E1B` | Sidebar background |

**Labels on yellow are always ink (`#0B0B0B`), never white.** Yellow never fills a large surface.

### Yellow ramp

```
100 #FFFBE6   200 #FFF3B8   300 #FEE87F   400 #FEDA3E   500 #FECD07
600 #D8AC00   700 #A88300   800 #755B00   900 #44350A
```

100–300: tinted rows, hovers, highlight bands. 500: primary button. 600: primary hover. 700: primary pressed, and the only step usable for yellow **text** on paper (500 fails contrast).

### Neutral ramp (warmed toward the brand hue)

```
100 #FAF9F6   200 #F0EEE9   300 #DFDCD4   400 #C2BEB3   500 #9C978A
600 #7A756A   700 #5C574D   800 #3D3A33   900 #1C1B18
```

Ground `#F4F3F0`, panel surface `#FFFFFF`, body text `#141310`, section rule `rgba(20,19,16,0.4)` at 2px.

### Semantic

| Role | Base | Tint | Used for |
| --- | --- | --- | --- |
| Success | `#126B47` | `#E4F1EA` | PROCESSED, PAID, matched rows, accepted counts |
| Warning | `#A85F00` | `#FBEEDB` | REVIEWED, match warnings, warning counts |
| Error | `#B3271E` | `#FAE7E5` | FAILED, rejected rows, unmatched, duplicates, destructive actions |
| Info | `#1F5B7A` | `#E5EEF3` | Processing notices, informational flashes |

Warning amber is deliberately deeper than brand yellow so a status never reads as a call to action.

### Typography

Poppins (Google Fonts, weights 400/500/600/700), `font-family: 'Poppins', system-ui, sans-serif`.

| Use | Size | Weight | Other |
| --- | --- | --- | --- |
| Page title (h1) | 30px | 700 | `letter-spacing:-0.02em` |
| Login hero h1 | 40px | 700 | `letter-spacing:-0.02em`, `line-height:1.1` |
| Panel heading (h2) | 17px | 700 | |
| Body | 13.5–14px | 400 | `line-height:1.5` |
| Table cell | 13.5px | 400 | numbers `font-variant-numeric:tabular-nums` |
| Table header | 11px | 600 | `letter-spacing:0.06em`, uppercase |
| Field label | 11.5px | 600 | `letter-spacing:0.06em`, uppercase, `#5C574D` |
| Eyebrow / crumb | 11–11.5px | 600 | `letter-spacing:0.1em`, uppercase, `#7A756A` |
| Status badge | 10.5px | 600 | `letter-spacing:0.06em` |
| Sidebar item | 14px (13.5px admin) | 500 | |
| Hint / helper | 12.5px | 400 | `#7A756A` |
| Stat figure | 26px | 700 | tabular-nums |
| Mono (codes, account nos, permission keys) | 12.5px | — | `ui-monospace, monospace` |

### Radius

**6px** on buttons, inputs, selects, the avatar chip, the file-drop zone, and sidebar count pills (`20px`, fully rounded). **0px everywhere else** — panels, table headers, status badges, stat cards. The softening reads as interactive affordance, not decoration.

### Spacing

4 / 8 / 12 / 16 / 20 / 22 / 24 / 28 / 32px. Panel padding 22px. Table cell padding 12px. Content area padding `28px 32px 64px`. Grid gaps 16px (form fields), 20px (panels), 2px (stat card strips).

### Borders and rules

- Panel border: `1px solid #DFDCD4`
- Table row divider: `1px solid #F0EEE9`
- Section rule under the page header, and above a revealed inline form: `2px solid rgba(20,19,16,0.4)`
- Input border: `1px solid #C2BEB3`; disabled `1px solid #DFDCD4` on `#FAF9F6` with `#9C978A` text
- File drop zone: `1px dashed #C2BEB3` on `#FAF9F6`
- Stat cards on Exceptions: `border-top: 3px solid` in the relevant semantic color

### Elevation

None. Nothing floats — alignment and rule strength do the organising. No box-shadows anywhere except the focus ring.

## Component specs

### Buttons

All: `border-radius:6px`, Poppins 600, `cursor:pointer`.

| Variant | Default | Hover | Notes |
| --- | --- | --- | --- |
| Primary | bg `#FECD07`, text `#0B0B0B`, border `1px solid #FECD07`, padding `11px 22px`, 14px | bg + border `#D8AC00` | Pressed `#A88300` |
| Secondary | bg `#FFFFFF`, text `#141310`, border `1px solid #C2BEB3`, padding `8px 15px`, 13px | bg `#F0EEE9` | Refresh, Cancel, "+ New …", Choose file, downloads |
| Danger | bg `#B3271E`, text `#FFFFFF` | bg `#8E1F17` | Destructive only |
| Disabled | `opacity:0.45`, `cursor:not-allowed` | — | |
| Link action (in table Actions cells) | `#A88300`, 13px, 600, no underline | `#0B0B0B`, underlined | Separated by `·` in `#DFDCD4` |
| Login submit | full width, padding `13px 18px`, 15px | as Primary | |
| Sign out (on black bar) | transparent, text `#C2BEB3`, border `1px solid rgba(255,255,255,0.22)`, padding `7px 13px`, 12.5px | bg `rgba(255,255,255,0.08)`, text `#FFFFFF` | |

### Inputs and selects

`border:1px solid #C2BEB3`, `border-radius:6px`, `padding:10px 12px` (login: `11px 13px`, 14.5px), font-size 14px, bg `#FFFFFF`.

- Focus: `outline: 2px solid #FECD07; outline-offset: 2px` (via `:focus-visible`). Never the browser default.
- Error: border `#B3271E`, background `#FAE7E5`, label color `#B3271E`, and a 12.5px `#B3271E` message directly below.
- Checkbox: 16px, `accent-color:#FECD07`.
- Label sits above the field, 6px gap. Secondary qualifiers inside a label (e.g. "— admin only, leave blank if the sheet is named after the branch") render 400 weight, `text-transform:none`, `letter-spacing:0`, `#9C978A`.

### Tables

- Header row: bg `#0B0B0B`, text `#FFFFFF`, cells 11px/600/uppercase/`letter-spacing:0.06em`, padding 12px, left-aligned (numeric columns right-aligned).
- Body: `font-size:13.5px`, zebra `#FFFFFF` / `#FAF9F6`, row divider `1px solid #F0EEE9`, row hover `#FFFBE6`.
- Numeric cells: `font-variant-numeric: tabular-nums`. Rejected counts > 0 in `#B3271E`; warning counts > 0 in `#A85F00`; zeros and em-dashes in `#7A756A`.
- Codes and account numbers: monospace.
- **Wide tables must sit in a `overflow-x:auto` wrapper inside the panel** with a `min-width` on the table (Uploads 1030px, Exceptions 1080px, upload detail 760px) so the table scrolls within its panel rather than the page scrolling sideways.
- Optional footer strip below the table: `padding:14px 22px`, `border-top:1px solid #DFDCD4`, 12.5px `#7A756A`.

### Status badges

`font-size:10.5px; font-weight:600; letter-spacing:0.06em; padding:3px 9px`, square corners, 1px border.

| Status | Background | Text | Border |
| --- | --- | --- | --- |
| DRAFT | `#F0EEE9` | `#3D3A33` | `#DFDCD4` |
| PENDING | `#F0EEE9` | `#5C574D` | `#DFDCD4` |
| PROCESSING | `#E5EEF3` | `#1F5B7A` | `#1F5B7A` |
| REVIEWED | `#FBEEDB` | `#A85F00` | `#A85F00` |
| LOCKED | `#0B0B0B` | `#FECD07` | `#0B0B0B` |
| PROCESSED / PAID | `#E4F1EA` | `#126B47` | `#126B47` |
| FAILED | `#FAE7E5` | `#B3271E` | `#B3271E` |

Severity badges (upload detail): ERROR `#FAE7E5`/`#B3271E`; WARNING `#FBEEDB`/`#A85F00`.

Exception category badges: `MATCHED_WITH_WARNING` uses the warning pair; `UNMATCHED_IN_BUSINESS_FILE`, `UNMATCHED_IN_BRANCH_FILE` and `DUPLICATE` use the error pair. Missing account numbers render as `—` in `#B3271E`.

Role badges (Users table) are neutral: `#F0EEE9` / `#3D3A33` / `#DFDCD4`.

Permission chips (Roles table): monospace 10.5px, `#F0EEE9` bg, `#3D3A33` text, `1px solid #DFDCD4`, `padding:2px 7px`, laid out in a `flex-wrap` row with 4px gap.

### Flash / notice bands

`padding:11px 16px`, square, `1px solid` the semantic base, `border-left: 4px solid` the same, tint background, 13.5px text in the semantic base color. Lead phrase in weight 600.

The upsert hint inside upload panels is a yellow-tinted note instead: bg `#FFFBE6`, border `1px solid #FEE87F`, `padding:10px 12px`, 12.5px `#5C574D`, `line-height:1.5`.

## Screens

### 1. Login

Replaces the current centered 400px card. Two-up composition inside a `max-width:1120px` container with `1px solid rgba(255,255,255,0.10)` border, centered on a `#000000` page with one decorative `radial-gradient(circle at 26% 96%, rgba(254,205,7,0.10), transparent 42%)`.

**Left (flex 1.15), `padding:56px 52px`, `min-height:600px`, space-between:**
- Logo at `width:300px` (auto height), top.
- Middle block: 52×4px `#FECD07` rule, then h1 "DSA/DTL Commission" (40px/700, `#FFFFFF`), then 16px `#9C978A` body at `max-width:40ch`: "Branch and business manager uploads, matching, exceptions and monthly commission runs — in one reconciled ledger."
- Bottom: three stat pairs above a `1px solid rgba(255,255,255,0.12)` rule — Period / August 2026, Branches live / 28, Support / +255 754 730 813. Labels 11px/600/uppercase `#7A756A`, values 15px/600 `#FFFFFF`.

**Right (flex 1), `#FFFFFF`, `padding:48px 44px`, flex column:**
- Header row: h2 "Sign in" (26px/700) with sub "Commission administration portal" (14px `#7A756A`); language select on the right (English / Kiswahili).
- Error band (conditional) — see Error states.
- Email field, then Password field (20px apart).
- Row 22px below: "Remember me" checkbox (13.5px `#3D3A33`) left, "Forgot password?" link (13.5px/600 `#A88300`) right.
- Full-width primary "Sign in" 28px below.
- Footer pinned to the bottom above a `1px solid #F0EEE9` rule: "Letshego Faidika Bank · Internal use only" and "v2.4.0", 12px `#9C978A`.

The composition follows the reference the client supplied (branded panel beside the form, logo above the fields, footer strip). **No color, logo or wording from that reference is used.**

Backend note: the current API authenticates on email + password only. No organization-code field is present in these designs.

### 2. App shell

**Top bar** — `#000000`, `height:60px`, `padding:0 24px`, space-between. Logo at `height:30px` left. Right: name (13px/600 `#FFFFFF`) over role · branch (11.5px `#9C978A`); a 34px `#FECD07` avatar chip with 13px/700 `#0B0B0B` initials, `border-radius:6px`; the Sign out button.

**Sidebar** — `width:236px`, `#1F1E1B`, `padding:16px 0`, full height, flex column.
- Group label "Commission" (10.5px/600/uppercase `#7A756A`, `padding:0 20px 10px`), then Uploads, Commission Runs, Exceptions.
- `1px rgba(255,255,255,0.10)` divider inset 20px, 14px margin.
- Group label "Administration", then Users, Roles, Branches, DSAs, DTLs (13.5px).
- Items: `padding:11px 20px` (admin `9px 20px`), `border-left:3px solid transparent`, 14px/500, `#9C978A`.
- Active item: bg `#0B0B0B`, `border-left-color:#FECD07`, text `#FFFFFF`.
- Count pills, right-aligned in the item: `border-radius:20px`, `padding:1px 8px`, 11px/600 — Uploads yellow (`#FECD07` on `#0B0B0B` text), Exceptions error (`#FAE7E5` bg, `#B3271E` text).
- Bottom, above a `1px rgba(255,255,255,0.10)` top border: "Active period" label + "August 2026" (14px/600 `#FFFFFF`).

Sidebar items are shown/hidden by the same permission checks `app.js` already applies to the admin subnav buttons (`data-perm`).

**Page header** (top of every content area) — eyebrow crumb + h1 on the left; on the right a "Scope" pair (11px/600/uppercase `#9C978A` over 13.5px/600 `#3D3A33`, e.g. "All branches · 2026-08") and a secondary Refresh button. Closed by the 2px section rule, 24px above content.

Crumb / title pairs: Uploads → "Commission · Data intake"; Commission Runs → "Commission · Payouts"; Exceptions → "Commission · Review"; the five admin sections → "Administration".

### 3. Uploads

Two panels in `grid-template-columns: repeat(auto-fit, minmax(360px, 1fr))`, 20px gap — collapses to one column on narrow viewports. Each panel needs `min-width:0`.

Each panel: h2, a yellow 12.5px/600/uppercase `#A88300` kicker ("Roster" / "Payout report"), the yellow-tinted upsert hint (copy verbatim from the current app), then the fields, then a primary Upload button 18px below.

- **Branch Manager panel**: Branch select, Period (month + year selects side by side, 10px gap, `flex:1` each), File.
- **Business Manager panel**: Period, File. No branch.
- **File control**: dashed drop zone containing a secondary "Choose file" button (`flex:none`) and the filename. The filename span needs `min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap` so a long name truncates rather than widening the panel.

**Recent Uploads** panel below: header row (h2 + Refresh) over a `1px solid #DFDCD4` divider, then the 10-column table in an `overflow-x:auto` wrapper (`min-width:1030px`), then the footer strip. Columns exactly as today: ID, Type, Branch, Period, Filename, Status, Accepted, Rejected, Warnings, Uploaded — the three count columns right-aligned. Rows are clickable and open the upload detail.

### 4. Upload detail (row expansion)

A panel appended below Recent Uploads, 20px gap.

- Header: eyebrow "Upload #1043 · Branch Manager · Kariakoo · 2026-08", h2 with the filename (20px/700), secondary Close button right. Closed by the 2px rule.
- Four-up stat strip, `grid-template-columns:repeat(4,1fr)`, `padding:18px 22px` per cell, `1px solid #F0EEE9` between: Rows read (neutral), Accepted (`#126B47`), Rejected (`#B3271E`), Warnings (`#A85F00`). Label 11px/600/uppercase, figure 26px/700 tabular-nums in the same color.
- Tab strip (`padding:14px 22px 0`, 6px gap): "Rejected rows (44)" / "Warnings (14)" / "Accepted (1,802)". Active tab `#0B0B0B` bg with `#FECD07` text, `border-radius:6px`, `padding:8px 14px`, 13px/600. Inactive `#5C574D`, hover `#F0EEE9`.
- Table: Row, Severity, DSA, Client, Date, Reason (`min-width:760px` in a scroll wrapper).
- Footer strip: the explanatory line ("Rejected rows are not stored. Correct the sheet and re-upload — the period upserts, it will not duplicate.") left, "Download rejected rows (.xlsx)" secondary button right.

### 5. Commission Runs

- **Create Commission Run** panel: h2, a 13px `#7A756A` explainer at `max-width:70ch` ("A run snapshots matched sales for the period. Org-wide runs cover every branch; branch runs cover one. Runs move DRAFT → REVIEWED → LOCKED → PAID."), then a `grid-template-columns: repeat(3,1fr) auto` row, `align-items:end`: Type select, Branch select (disabled unless Type is BRANCH), Period text input (`YYYY-MM`, tabular-nums), primary "Create Run".
- **Commission Runs** table panel: ID, Type, Branch, Period, Status, Actions. Actions cell holds View · Export .xlsx · a status-dependent advance link (DRAFT → "Mark reviewed", REVIEWED → "Lock run", LOCKED → "Mark paid", PAID → "Reopen").
- Footer strip: "A run cannot be locked while its period has open exceptions."

### 6. Exceptions

- Filter panel: h2, the explainer verbatim from today ("Unmatched, duplicate, and match-quality-warning rows. These block nothing but must be reviewed before a run is locked."), then `grid-template-columns: 1fr 1fr auto auto`, `align-items:end`: Period input, Branch select, primary "Load", secondary "Download Exceptions (.xlsx)".
- Four stat cards, `grid-template-columns:repeat(4,1fr)`, 2px gap, each `border-top:3px solid` its semantic color: Unmatched in business file (error), Unmatched in branch file (error), Duplicates (error), Match warnings (warning). Label 11px/600/uppercase `#7A756A`, figure 26px/700.
- The 9-column table in an `overflow-x:auto` wrapper, `min-width:1080px`: Category, Branch, Client, Acct (Branch), Acct (Business), DSA, Loan Type, Disb. Date, Notes.

### 7. Admin — Users

Panel with header row (h2 + "+ New User" secondary). The form is collapsed by default and revealed by that button, as today.

Revealed form: `background:#FAF9F6`, `padding:22px`, closed below by the 2px rule, fields in `grid-template-columns:repeat(3,1fr)`, 16px gap — Email, Full name, Password, Role select, Branch select, then a cell holding primary "Create User" and secondary "Cancel".

Table: ID, Email, Name, Role (neutral badge), Branch.

### 8. Admin — Roles

Header row + "+ New Role". Revealed form: Name and Description in a 2-column grid, then the permission grid — `grid-template-columns:repeat(3,1fr)` with `gap:2px` over a `#DFDCD4` background and `1px solid #DFDCD4` border, so each cell reads as a tile. Each tile: `#FFFFFF`, `padding:11px 13px`, hover `#FFFBE6`, containing a 16px yellow-accent checkbox beside the monospace permission key (12.5px/600 `#141310`) over its description (11.5px `#7A756A`). Save Role primary + Cancel secondary.

Table: Name, Description, Permissions (chip row), System?, Actions (Edit link).

### 9. Admin — Branches

Panel capped at `max-width:720px`. Header row + "+ New Branch". Revealed form: `grid-template-columns:1fr 1fr auto` — Name, Code (monospace), primary "Create". Table: ID, Name, Code (monospace).

### 10. Admin — DSAs

Header row carries the h2 plus the full explanatory paragraph verbatim from today (12.5px `#7A756A`, `max-width:88ch`), with "+ New DSA" (`flex:none`, `white-space:nowrap`) to its right.

Revealed form, `repeat(3,1fr)`: DSA Code (monospace), DSA Name, DSA Account No (tabular-nums), Branch select, DTL select, then Save DSA primary + Cancel secondary.

Table: Code, Name, Branch, Current DTL, Actions (Edit · History).

### 11. Admin — DTLs

Panel capped at `max-width:820px`. Header row + "+ New DTL". Revealed form: `1fr 1fr 1fr auto` — DTL Code (monospace), DTL Name, Branch select, primary "Create". Table: Code, Name, Branch.

## Interactions and behavior

- **Sidebar navigation** replaces the current `#tabs` buttons; `#admin-subnav` is absorbed into the sidebar's Administration group. Keep `app.js`'s tab-switch and permission-gating logic, retargeted at the sidebar items.
- **Row click** on Recent Uploads opens the upload detail panel; Close dismisses it. In the current app this is the `#upload-detail` container — same behavior, new presentation.
- **Inline forms** ("+ New User/Role/Branch/DSA/DTL") toggle open and closed, unchanged from today's `.collapsible` pattern; the revealed form is tinted `#FAF9F6` and separated by the 2px rule.
- **Sign in** navigates to Uploads; **Sign out** returns to Login.
- **Hover states**: table rows `#FFFBE6`; secondary buttons `#F0EEE9`; primary buttons `#D8AC00`; permission tiles `#FFFBE6`; sidebar inactive items lift toward `#FFFFFF` text.
- **Focus**: `:focus-visible { outline: 2px solid #FECD07; outline-offset: 2px; }` on every interactive element. No browser-default rings.
- **Transitions**: none specified; if the codebase has a standard, a 120–150ms ease on background-color is in keeping. Nothing animates position or size.
- **Responsive**: the upload panel grid is the only fluid grid (`auto-fit`, `minmax(360px,1fr)`). Wide tables scroll horizontally inside their panels. The sidebar is fixed at 236px; below roughly 900px it would need to collapse to a drawer — not designed, flag if needed.

## States

| State | Where | Treatment |
| --- | --- | --- |
| **Loading / processing** | Uploads | Info band above the panels: spinning 16px `#1F5B7A` ring (`border-top-color:transparent`, 0.8s linear), bold filename + progress ("1,204 of 1,860 rows matched"), and the reassurance that processing continues if the user leaves. |
| **Empty** | Recent Uploads | Replaces the table: `padding:64px 24px`, centered. 44px square `2px solid #DFDCD4` glyph, 17px/600 headline ("No uploads for August 2026 yet"), 13.5px `#7A756A` body at `max-width:46ch` explaining the roster-then-payout order, primary "Upload roster file". |
| **Validation error** | Any form field | Label, border and message all `#B3271E`; field background `#FAE7E5`; 12.5px message below the field. Example copy: "Select an .xlsx or .xls file before uploading." / "Enter a valid @lfb.co.tz address." |
| **Login error** | Login | Error band above the fields: `#FAE7E5` bg, `1px solid #B3271E`, `border-left:4px`, "**Sign-in failed.** Email or password is incorrect. Two attempts remain before this account is locked." |

In the prototype these are props on the root component (`emptyState`, `loadingState`, `formErrors`, `loginError`) so any screen can be flipped into its state. In production they are driven by the API responses `app.js` already handles.

## State management

Only what the current app already tracks: authenticated user + permissions, active page, active admin section, open/closed inline form, selected upload for detail, filter values (period, branch), and the fetched collections (uploads, runs, exceptions, users, roles, branches, DSAs, DTLs). No new state is introduced by this redesign.

## Assets

- `assets/lfb-logo.png` — the client-supplied LFB logo, cropped to its black field, 1729×476. Used at `width:300px` on Login and `height:30px` in the top bar. Use as-is: do not redraw, recolor, or place on a light surface (the wordmark is white). Surfaces carrying it must be `#000000`.
- Icons: none of the designs depend on an icon set. If the codebase adds one, Lucide matches the system's geometry.
- Fonts: Poppins 400/500/600/700 from Google Fonts.

## Sample data

Branch, DSA and DTL names in the prototype are realistic Tanzanian placeholders (Kariakoo, Mwanza, Arusha, Mbeya, Dodoma, Tanga, Morogoro, Zanzibar; Amina Mwakyusa, Joseph Kimaro, Neema Shirima, Baraka Mwenda, Grace Mollel, Fatuma Juma, Hamisi Bakari, Salma Kibwana). Permission keys and role names are plausible reconstructions from the repo's RBAC models — reconcile them with `app/models/rbac.py` and `scripts/seed.py` rather than adopting them verbatim.

## Notes for implementation

1. **Do not change `app.js`'s element IDs.** Every field and table in these designs corresponds to an existing ID in `frontend/static/index.html`.
2. **Copy text is verbatim** from the current app wherever the current app has copy (upsert hints, the exceptions explainer, the DSA paragraph, field labels). New copy exists only where the redesign adds surface: the login hero, empty states, the run-lifecycle explainer, footer strips.
3. **Column sets are unchanged.** If a column looks reordered, it isn't — check against `index.html`.
4. The only structural change is tabs → sidebar. Everything else keeps its current place in the page.
