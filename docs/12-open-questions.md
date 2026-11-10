# 12 — Open questions

Each item has a **default** that the plan already assumes. Change the default by editing this file and the referenced doc.

## Already decided (2026-11-07)
| Question | Decision |
|---|---|
| Who closes the period? | Any member, by hand; any member starts the next period. No automatic close (changed 2026-11-09). Admins reopen the latest period |
| Who confirms a payment? | The receiver (creditor) |
| Joins/leaves during a period | Whole-period membership |
| Hosting | Supabase (Postgres + Auth, Frankfurt) + Render Frankfurt for the FastAPI web service and worker |
| Auth | Supabase Auth with native Google sign-in |
| Receipt photos | Out of scope (no file storage) |
| Docs language | English |

## Household and rules
1. **Retroactive re-split when someone joins an open period.** With whole-period membership, a member joining late changes earlier default-split expenses of the open period. **Default:** invitation asks "starts in the current period / the next one" (`current` by default). Re-resolution applies only to `participant_mode='all'` expenses of the open period.
2. **Leaving during a period.** The leaver pays their share of the whole current period, including expenses after they left. **Default:** yes (consistent, simple); admins can exclude them per expense with an override.
3. **Who can edit others' expenses?** **Default:** only admins (and the author).
4. **Can members (not only admins) change category rules?** **Default:** admins only.
5. **Should the payer default to "me"?** **Default:** yes.
6. **Cent tie-break fairness.** The leftover cent always goes to the earliest member in canonical order when remainders tie (max 1 cent per expense). **Default:** accept. Alternative: rotate the starting member by a hash of the expense id (still deterministic, needs vector updates).
7. **Optimal settlement solver** (bitmask DP) instead of greedy. **Default:** greedy in MVP; revisit if households complain about an extra transfer.
8. **Lock trigger.** Lock the closed period at the first `sent` or `confirmed` transfer (our proposal) vs only at `confirmed`. **Default:** first `sent` or `confirmed`.
9. ~~Grace days default~~ — obsolete: there is no automatic close.
10. **Expense date in a locked period** (forgotten expense). **Default:** create it in the current open period with a note; no recalculation of the locked one.
11. **Approval flow** (post-MVP): when enabled, do unapproved expenses count in the live balance? **Default:** no; they count once approved.

## Settlement and payments
12. **Disputed transfers at long durations** — escalate to admins after N days? **Default:** reminder to both after 7 days, no escalation.
13. **Cash settlements outside the app** (e.g. paid 50 € in cash mid-month). **Default:** creditor confirms the transfer with method `cash`; ad-hoc "reimbursement" entries are not supported in MVP. Consider a `transfer` expense type later.
14. **Payment handles visibility.** **Default:** phone/PayPal/Revolut handles visible only to members of the same household (or typed ad hoc in Quick splits).

## Quick splits
15. **Collaborative editing via link without account.** **Default:** later phase; v1 = single editor, read-only share. Requires conflict handling and abuse controls.
16. **Keep history of quick events?** **Default:** yes, locally (unlimited) and server-side only for saved events; user can delete.
17. **Link a participant to a real user** (`user_id`). **Default:** column exists; no UI in MVP.
18. **Convert a quick event into household expenses?** **Default:** not planned.

## Google Sheets
19. ~~Workspace subscription for the Shared Drive~~ **Decided 2026-11-09:** no paid services. The admin owns the spreadsheet and shares it with the service account as Editor (see [06](06-google-sheets.md)).
20. **Layout:** four tabs per period vs one tab with four blocks. **Default:** four tabs (`P3 Resumen`, …).
21. ~~Incremental sync of the open period~~ **Decided 2026-11-09:** never. Only closed periods are exported (at close, and again after an edit to a closed period).

## Technical
22. **Google Sign-In library**: paid Universal Sign-In vs free Credential-Manager library. **Default:** decide in spike T-0.4; abstraction either way.
23. **NativeWind 4.2 (Tailwind 3) now vs wait for v5 / use Uniwind (Tailwind 4).** **Default:** NativeWind 4.2 now; migrate when v5 is stable (est. small effort thanks to tokens in CSS variables).
24. **Job queue**: Procrastinate (Postgres) vs Celery + Redis. **Default:** Procrastinate.
25. **SQLAlchemy 2.1** just reached release-candidate/final. **Default:** pin 2.0.x for MVP; upgrade in a dedicated task.
26. **Analytics** (product usage). **Default:** none in MVP; if needed, a privacy-friendly EU tool with consent.
27. **App name/domain/package id** (`com.splitranch.app`?). **Default:** placeholder until branding; must be fixed before the first Play upload (package id is permanent).
28. **App UI language**: Spanish first, English second. **Default:** yes.

## Supabase
29. **Where to run FastAPI and the worker.** Supabase cannot host Python services. **Decided 2026-11-09:** one Render **Free** web service in Frankfurt, with the worker inside the API process; we accept the ~1 min cold start after 15 min idle. Revisit (Render Starter, or a separate worker) only if more households join.
30. **Supabase anonymous sign-ins** to let Quick-split users save/share events without a Google account. **Default:** disabled in MVP (saving requires Google); revisit with the share-link feature.
31. ~~PITR add-on for prod~~ **Decided 2026-11-09:** Supabase Free plan (no backups, no PITR). A weekly encrypted `supabase db dump` runs in GitHub Actions (`.github/workflows/db-backup.yml`), so the worst case is losing up to a week of data (run the workflow by hand before risky changes).
32. **Use Supabase Realtime** for live balance updates between members. **Default:** no; TanStack Query refetch on focus + push notifications are enough, and Realtime on our private schema would require exposing it.
33. **Access-token lifetime.** **Default:** Supabase's 1 h; revocation is not instant for that window (see [08](08-security-and-privacy.md)).
