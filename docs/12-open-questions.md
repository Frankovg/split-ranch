# 12 — Open questions

Each item has a **default** that the plan already assumes. Change the default by editing this file and the referenced doc.

## Decided 2026-11-16: groups without periods

Design and EGM review: [egm/design_draft.md](egm/design_draft.md), [egm/consolidated_review_report.md](egm/consolidated_review_report.md). Built in migration 0006.

| # | Question | Decision |
|---|---|---|
| G1 | Periods? | **None.** One running balance per group from its creation; "last month" is a date filter on the list and `/summary` |
| G2 | How is debt settled? | Payments: the debtor records `sent`, the receiver confirms or disputes; a receiver can record cash directly as `confirmed`. Only confirmed payments count |
| G3 | Permissions | Every member has the same rights (expenses, categories, rules, invitations, group name). The admin (creator) is the only one who removes members and deletes the group |
| G4 | Admin model (D1) | Exactly one active admin; when the admin leaves the role passes to the next active member; the last member leaving deletes the group |
| G5 | Leaving with a balance (D2) | Leaving, removal and group deletion need zero balances and no payment waiting. Expenses involving a member who left cannot change (`member_left`) |
| G6 | Existing data (D3) | Test data only: the cloud app data is reset before 0006 |
| G7 | Invitations (D4) | The 8-character code is typed by hand; App Links later |
| G8 | Rule changes (Q1) | Apply only to expenses created or explicitly re-split afterwards |
| G9 | "Everyone" in a split (Q2) | The active members when the split is resolved; an amount-only edit re-allocates over the stored participants |
| G10 | Renaming (R2) | `household` → `group` in every layer, inside `/v1` |

Superseded by the above: the 2026-11-07/09 decisions on closing periods and whole-period membership, and questions 1, 2, 3, 4, 8 and 10 below.

## Already decided (2026-11-07)
| Question | Decision |
|---|---|
| ~~Who closes the period?~~ | Superseded 2026-11-16: there are no periods (G1) |
| Who confirms a payment? | The receiver (creditor) |
| ~~Joins/leaves during a period~~ | Superseded 2026-11-16 (G5, G9) |
| Hosting | Supabase (Postgres + Auth, Frankfurt) + Render Frankfurt for the FastAPI web service |
| Auth | Supabase Auth with native Google sign-in |
| Receipt photos | Out of scope (no file storage) |
| Docs language | English |

## Group and rules
1. ~~Retroactive re-split when someone joins.~~ **Decided (G9):** joining never re-splits existing expenses.
2. ~~Leaving during a period.~~ **Decided (G5):** leaving needs a zero balance.
3. ~~Who can edit others' expenses?~~ **Decided (G3):** any member.
4. ~~Can members change category rules?~~ **Decided (G3):** yes.
5. **Should the payer default to "me"?** **Default:** yes.
6. **Cent tie-break fairness.** The leftover cent always goes to the earliest member in canonical order when remainders tie (max 1 cent per expense). **Default:** accept. Alternative: rotate the starting member by a hash of the expense id (still deterministic, needs vector updates).
7. **Optimal settlement solver** (bitmask DP) instead of greedy. **Default:** greedy in MVP; revisit if groups complain about an extra payment.
8. ~~Lock trigger.~~ Obsolete: no periods, no locks.
9. ~~Grace days default~~ — obsolete: there is no automatic close.
10. ~~Expense date in a locked period.~~ Obsolete: any expense can be added with any date.
11. **Approval flow** (post-MVP): when enabled, do unapproved expenses count in the live balance? **Default:** no; they count once approved.

## Settlement and payments
12. **Disputed payments at long durations** — escalate to admins after N days? **Default:** reminder to both after 7 days, no escalation.
13. **Cash settlements outside the app** (e.g. paid 50 € in cash mid-month). **Default:** the receiver records the cash payment as confirmed (or the debtor records it sent with a note "en efectivo"); ad-hoc "reimbursement" entries are not supported in MVP. Consider a `transfer` expense type later.
14. ~~Payment handles visibility.~~ **Decided 2026-11-10:** no payment handles at all; the app never links to payment platforms.

## Quick splits
15. ~~Collaborative editing via link without account.~~ **Decided 2026-11-10:** no; Quick splits never leave the phone.
16. **Keep history of quick events?** **Decided:** yes, locally only (unlimited); user can delete.
17. ~~Link a participant to a real user.~~ Not applicable: no server data. The only link is "Soy yo" (the phone's owner).
18. **Convert a quick event into group expenses?** **Default:** not planned.

## Google Sheets
19. ~~Workspace subscription for the Shared Drive~~ **Decided 2026-11-09:** no paid services. The admin owns the spreadsheet and shares it with the service account as Editor (see [06](06-google-sheets.md)).
20. **Layout** (pending redesign: monthly tabs, see [06](06-google-sheets.md)): four tabs per period vs one tab with four blocks. **Default:** four tabs (`P3 Resumen`, …).
21. ~~Incremental sync of the open period~~ **Decided 2026-11-09 (obsolete with periods):** never. Only closed periods are exported (at close, and again after an edit to a closed period).

## Technical
22. ~~Google Sign-In library~~ **Decided 2026-11-12:** `react-native-nitro-google-signin` (MIT, free, Credential Manager on Android), because it embeds our nonce in the ID token. Paid Universal Sign-In stays the fallback behind the same abstraction in `src/features/auth/google.ts`.
23. **NativeWind 4.2 (Tailwind 3) now vs wait for v5 / use Uniwind (Tailwind 4).** **Default:** NativeWind 4.2 now; migrate when v5 is stable (est. small effort thanks to tokens in CSS variables).
24. **Job queue**: **Decided 2026-11-11:** none until a feature needs background work. Push notifications should first try Expo's own APIs or sending within the request.
25. **SQLAlchemy 2.1** just reached release-candidate/final. **Default:** pin 2.0.x for MVP; upgrade in a dedicated task.
26. **Analytics** (product usage). **Default:** none in MVP; if needed, a privacy-friendly EU tool with consent.
27. **App name/domain/package id** (`com.splitranch.app`?). **Default:** placeholder until branding; must be fixed before the first Play upload (package id is permanent).
28. **App UI language**: Spanish first, English second. **Default:** yes.

## Supabase
29. **Where to run FastAPI and the worker.** Supabase cannot host Python services. **Decided 2026-11-09:** one Render **Free** web service in Frankfurt (API only; no worker since 2026-11-11); we accept the ~1 min cold start after 15 min idle. Revisit (Render Starter, or a separate worker) only if more groups join.
30. ~~Supabase anonymous sign-ins for Quick splits.~~ Not needed: Quick splits are never saved on the server.
31. ~~PITR add-on for prod~~ **Decided 2026-11-09:** Supabase Free plan (no backups, no PITR). A weekly encrypted `supabase db dump` runs in GitHub Actions (`.github/workflows/db-backup.yml`), so the worst case is losing up to a week of data (run the workflow by hand before risky changes).
32. **Use Supabase Realtime** for live balance updates between members. **Default:** no; TanStack Query refetch on focus + push notifications are enough, and Realtime on our private schema would require exposing it.
33. **Access-token lifetime.** **Default:** Supabase's 1 h; revocation is not instant for that window (see [08](08-security-and-privacy.md)).
