# 06 — Google Sheets export

The database is the source of truth. The spreadsheet is a **read-only mirror** for humans.

## Ownership: the service-account problem

Service accounts have **no Drive storage quota** of their own: creating spreadsheets in a service account's "My Drive" fails with `403 storageQuotaExceeded` (widely reported for service accounts since 2025). Options:

| Option | How | Pros | Cons |
|---|---|---|---|
| **A. Shared Drive (recommended)** | Project owns a Google Workspace account (Business Starter ≈ €7/month) with one Shared Drive "Split Ranch Households". The service account is a *Content manager* of it. Spreadsheets are created there and shared (reader) with members' emails | No end-user OAuth; files survive member changes; central control; matches the "service account" design | Requires a Workspace subscription; external sharing must be allowed in the Workspace admin console; data processed under the project's Workspace account (DPA) |
| B. Admin's own Drive (`drive.file` scope) | A household admin connects their Google account once with the non-sensitive `drive.file` scope; backend stores an encrypted refresh token and creates/updates the file in the admin's Drive | Free; data lives in the household's own Drive | Token lifecycle (revocation, admin leaves), extra OAuth consent screen, more code |
| C. Domain-wide delegation | Service account impersonates a Workspace user | — | Same Workspace requirement as A with more risk; no benefit here |

**Decision:** A for MVP. Keep the `integrations/google_sheets.py` interface (`ensure_spreadsheet`, `write_tab`) independent of ownership so B can be added if a household wants the file in its own Drive.

## Quotas (Sheets API, current)
- 300 read + 300 write requests/min **per project**; **60 read + 60 write requests/min per user per project**. A service account counts as **one user** → effective budget ≈ **60 writes/min** for all households.
- A `spreadsheets.batchUpdate` with many sub-requests counts as **one** request.
- `429` → exponential backoff; quotas refill every minute.

Design consequence: one tab sync = **2–3 requests** (structure batchUpdate + values batchUpdate + optional formatting), so ~20 tab syncs/min. The worker uses a **dedicated queue `sheets` with concurrency 1** and a token bucket (50 writes/min) to stay under the limit.

## Spreadsheet layout

One spreadsheet per household: `Split Ranch — <Household name>`.

| Tab | Content |
|---|---|
| `Léeme` | Explanation, "this file is generated, edits will be overwritten", last sync time, link to the app |
| `2026-03 Resumen` | Status (abierto/cerrado/liquidado), totals, total per member paid/owed/net, snapshot seq, closed_at |
| `2026-03 Detalle` | One row per expense: date, description, category, payer, amount, split type, origin, one column per member with their share, source, last edited, flags (adjustment / edited after close) |
| `2026-03 Por categoría` | Category × member matrix + totals; budget vs actual when budgets exist |
| `2026-03 Liquidación` | Transfers: from, to, amount, status, sent_at, confirmed_at; previous snapshots summarised |

The brief asked for "one tab per month with four sections". Four sections in one tab are hard to keep idempotent and to read on a phone; **four tabs per month** (prefixed by month) is the recommended layout. A single tab with four stacked blocks is the fallback if the household prefers fewer tabs (it only changes the renderer).

Personal expenses are excluded. Amounts are written as numbers with currency format (`#,##0.00 €`), never formulas that depend on other cells (the file must be reproducible from the DB alone).

## Triggers

| Event | Job |
|---|---|
| Household created / first close | `ensure_household_spreadsheet` (create file, `Léeme`, share with members) |
| Period closed (auto or manual) | `sync_period_tab(period_id)` for all four tabs |
| Edit after close, adjustment, transfer status change | `sync_period_tab` for the affected period(s) (an adjustment touches the current period; its original stays untouched) |
| Member joined / left | update sharing (add reader / remove permission after `left`) |
| Optional incremental sync (setting, default **off**) | debounced `sync_period_tab` for the open period at most once every 10 min |
| Nightly reconciliation | re-sync any tab whose `content_hash` differs from the DB rendering (catches manual edits or missed jobs) |

All jobs are enqueued **inside the business transaction** (Procrastinate), so a close and its sync request commit or roll back together.

## Idempotency

- `household_spreadsheets` stores `spreadsheet_id`; `ensure_*` first checks the row, then searches the Shared Drive by an `appProperties` key (`split_ranch_household_id`) before creating, so a crash between "create" and "save id" doesn't create duplicates.
- Each tab is located by **title** and its `sheetId` saved in `sheet_tabs`; missing tab → `addSheet`; existing → `updateCells`/`values.batchUpdate` replacing the full range + clearing trailing rows. Never `append`.
- The renderer is a pure function `render_period(period_data) -> TabContent`; `content_hash = sha256(TabContent)`. If the hash equals `sheet_tabs.content_hash`, the job does nothing.
- Procrastinate `queueing_lock = f"sheets:{period_id}"` collapses duplicate pending jobs for the same period.

## Retries and failures
- Retry on 429/5xx/timeouts: exponential backoff with jitter (2 s, 4 s, 8 s … max 10 min), up to 8 attempts; honour `Retry-After`.
- Non-retryable (403 permission, 404 file deleted): mark `sheet_tabs.status = 'error'`, Sentry alert; a deleted file is recreated on the next run (new id saved).
- Sheets failures never block the business flow: the app shows "Sheets: actualizado hace 3 min / pendiente / error".

## Sharing
- Members are added as `reader` (`permissions.create`, `sendNotificationEmail=false` for re-shares, true on first share with a short message).
- `left` members are removed after their last period settles. Admins can disable Sheets for the household (file kept, sharing removed).
- Users can opt out of being shared (privacy setting); they still appear in the data.

## Read-only enforcement
- Members only have `reader` permission. A protected-range is unnecessary for readers; if a household asks for editor access (not offered in MVP) all generated ranges would be protected with a warning.

## Testing
- Renderer tested with snapshot tests (pure function).
- Integration test against a sandbox Shared Drive in staging (nightly CI job, not on every PR).
- Quota simulation: unit tests of the token bucket and backoff with a fake client.
