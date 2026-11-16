# 06 — Google Sheets export

> **Status: not built, and pending redesign.** It was designed around closed periods; since 2026-11-16 there are no periods, so the export becomes one tab per calendar month (written on demand or when a month is over), still read-only. The layout below is the old period-based design. Nothing in the code or the database exists for it yet. When it is built, it adds only what it needs (see [Storage](#storage)).

The database is the source of truth. The spreadsheet is a **read-only mirror** for humans.

## Ownership: the service-account problem

Service accounts have **no Drive storage quota** of their own: creating spreadsheets in a service account's "My Drive" fails with `403 storageQuotaExceeded` (widely reported for service accounts since 2025). A file's owner is whoever creates it, and it counts against the owner's quota. So a service account *can* edit a file that a person owns and has shared with it. Options:

| Option | How | Pros | Cons |
|---|---|---|---|
| **A. User-owned spreadsheet shared with the service account (chosen)** | A group admin creates the spreadsheet in their own Drive and shares it with the service account's email as **Editor** (and with the other members as Viewer). The backend only gets the spreadsheet ID (`GOOGLE_SHEETS_SPREADSHEET_ID` while there is a single group) | Free; no Workspace; no end-user OAuth or tokens; data lives in the group's own Drive | The backend cannot create the file or manage sharing, so the admin does both by hand once; if the admin deletes the file or removes the share, sync fails until they fix it |
| B. Shared Drive | Project owns a Google Workspace account (Business Starter ≈ €7/month) with a Shared Drive; the service account is *Content manager* and creates one file per group | Fully automatic creation and sharing; scales to many groups | Paid subscription; external sharing must be allowed in the Workspace admin console |
| C. Admin's own Drive via OAuth (`drive.file`) | Admin connects their Google account; backend stores an encrypted refresh token and creates the file for them | Free and automatic | Token lifecycle (revocation, admin leaves), extra consent screen, more code |

**Decision (2026-11-09):** A. The app is for one group, and there is no budget for paid services. Keep the `integrations/google_sheets.py` interface (`ensure_spreadsheet`, `write_tab`) independent of ownership, so B or C can be added if more groups ever join.

## Quotas (Sheets API, current)
- 300 read + 300 write requests/min **per project**; **60 read + 60 write requests/min per user per project**. A service account counts as **one user** → effective budget ≈ **60 writes/min** for all groups.
- A `spreadsheets.batchUpdate` with many sub-requests counts as **one** request.
- `429` → exponential backoff; quotas refill every minute.

Design consequence: one tab sync = **2–3 requests** (structure batchUpdate + values batchUpdate + optional formatting). We only sync closed periods, so a group makes a handful of requests per month. Backoff on 429 is enough; rate limiting is only needed if many groups ever share one service account.

## Spreadsheet layout

One spreadsheet per group: `Split Ranch — <Group name>`.

| Tab | Content |
|---|---|
| `Léeme` | Explanation, "this file is generated, edits will be overwritten", last sync time, link to the app |
| `2026-03 Resumen` | Status (abierto/cerrado/liquidado), totals, total per member paid/owed/net, closed_at |
| `2026-03 Detalle` | One row per expense: date, description, category, payer, amount, split type, origin, one column per member with their share, source, last edited, flags (adjustment / edited after close) |
| `2026-03 Por categoría` | Category × member matrix + totals; budget vs actual when budgets exist |
| `2026-03 Liquidación` | Live transfers: from, to, amount, status, sent_at, confirmed_at |

The brief asked for "one tab per month with four sections". Four sections in one tab are hard to keep idempotent and to read on a phone; **four tabs per period** (prefixed by the period number, e.g. `P3`; periods are started by hand, not calendar months) is the recommended layout. A single tab with four stacked blocks is the fallback if the group prefers fewer tabs (it only changes the renderer).

Personal expenses are excluded. Amounts are written as numbers with currency format (`#,##0.00 €`), never formulas that depend on other cells (the file must be reproducible from the DB alone).

## Triggers

**Only closed periods are exported.** The open period is never written: it changes on every expense, and the app is where people look at it.

| Event | Sync |
|---|---|
| Period closed | The period's four tabs (the first sync also checks access and writes `Léeme`) |
| Edit in an already closed period (unlocked) | That period's tabs, since its transfers were recomputed |

Not synced: transfer status changes (the app shows their live status), member joins/leaves (sharing is managed by hand in Drive), the open period, and nightly reconciliation (nothing runs on a schedule while the free API instance sleeps).

**How it runs:** without a job queue. The sync starts after the close (or edit) has committed, as a FastAPI background task of that same request, so the instance is awake and the user does not wait for Google. If it fails, the stored hash stays old and the sync can be retried from the app.

## Storage

- The spreadsheet id: a column on `groups` (the backend never creates files, so duplicates cannot happen).
- A content hash per period (a column on `periods`, or a small table if per-tab state turns out to be needed).

## Idempotency

- Each tab is located by **title**; missing tab → `addSheet`; existing → `updateCells`/`values.batchUpdate` replacing the full range + clearing trailing rows. Never `append`.
- The renderer is a pure function `render_period(period_data) -> TabContent`; `content_hash = sha256(TabContent)`. If the hash equals the stored one, nothing is sent.

## Retries and failures
- Retry on 429/5xx/timeouts: exponential backoff with jitter, a few attempts within the background task; honour `Retry-After`.
- Non-retryable (403 permission removed, 404 file deleted): record the error and send a Sentry alert. The admin re-shares the file, or creates a new one and updates the ID; the next close (or a manual retry) syncs again.
- Sheets failures never block the business flow: the app shows "Sheets: actualizado / pendiente / error".

## Sharing
- Managed by the file's owner in Google Drive, not by the backend: the service account is **Editor**, and other members are **Viewer**.
- Sheets is disabled when no spreadsheet ID is configured.

## Read-only enforcement
- Members other than the owner have Viewer permission. The owner can still edit by hand; the `Léeme` tab warns that generated tabs are overwritten on the next sync.

## Testing
- Renderer tested with snapshot tests (pure function).
- Integration test against a sandbox spreadsheet shared with a test service account (manual or nightly CI job, not on every PR).
- Backoff unit-tested with a fake client.
