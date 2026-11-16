# Consolidated review — Groups without periods

*   **Target:** [design_draft.md](design_draft.md) (FeatureRange 1–472, DetailedRange 473–659)
*   **Date:** 2026-11-16
*   **Flow:** EGM `egm-review`, consolidated preset (Stages 5 → 9, no checkpoints, no fixes applied yet)
*   **Stage reports:** zoom-out (S5), comprehension (S6), critic (S7), intermediate zoom-out (S8), implementation readiness (S9). The per-stage reports and the baseline drift report were working files and are not kept; their findings are consolidated here.

| Stage | Blocker | Major | Nit |
|---|---|---|---|
| S5 Zoom Out + Inventive Catalyst | 0 | 11 | 10 |
| S6 Comprehension | 0 | 6 | 7 |
| S7 Critic (design, structural, style) | 3 | 25 | 24 |
| S8 Intermediate Zoom Out | 0 | 7 | 5 |
| S9 Implementation Readiness | 4 | 24 | 19 |

Verdict: the direction (no periods, one running balance of expenses plus
confirmed payments, flat permissions) holds up under every reviewer. The draft
is **not ready to implement**: the money pipeline is described against the
wrong function, the payments table and the migration are not concrete, and
several rules contradict each other. Stage 8 also shows that later stages
added mechanism the problem does not need; its "reject / narrow" table is
applied below.

## Decisions the author must take

These have more than one defensible answer. The draft is not changed until
they are answered.

| # | Decision | Options | Raised by |
|---|---|---|---|
| D1 | Admin model | **A** keep the existing multi-admin code (`change_member_role`, `last_admin` guard); only the creator starts as admin. **B** exactly one admin; when the admin leaves, the role passes automatically to the next member. | S8 #2, S5 #20, S9 RD-M7 |
| D2 | Leaving / removal with a non-zero balance | **A** blocked until the net is 0 (no `force`, no admin-confirm exception; edits that would change a left member's balance get 409). **B** allowed, the balance stays with the left member, and they keep read access to the balance and their payments. | S8 #1, S5 #3, S7 M4/M5, S6 #5 |
| D3 | Existing data in the cloud DB (Q6) | **A** reset (only test data). **B** migrate, after counting rows; the migration fails loudly on data it does not expect (for example adjustment pairs). | S8 #6, S9 RD-B2, S5 #10/#11 |
| D4 | Invitations | **A** members type the code by hand (no App Links in this design). **B** add a `join/[code]` route and App Links. | S5 #6, S7 M25 |

### Recommendations rejected because they contradict the author's brief

*   **S8 #3 / S5 #5: defer group deletion and multiple groups per user.** The
    author asked for both ("un usuario puede crear grupos", "el admin es el
    único que puede eliminar el grupo"). They stay. The draft must add a
    Problem bullet that states this need, so later reviewers can see why they
    are there.

## Consolidated action items

### 🔴 Blockers

| ID | Action | Sources |
|---|---|---|
| C-B1 | Rewrite the balance pipeline so it uses the domain's real API: confirmed payments become ledger rows fed to `compute_balances` (`domain/settle.py`), then `settle()`. No SQL-aggregated nets. Name one function for it and use the same name everywhere. | S9 RD-B4, S7 M11, S5 #1, S8 #7, S6 #7 |
| C-B2 | Define the `payments` table in full (types, CHECKs, tenant-safe composite FKs, indexes) and its backfill: say where `created_by_user_id` comes from (it does not exist in `settlement_transfers`), drop `paid_on` or give it a source, and pick one of "rename" or "create, copy, drop". Accept a client `id` so payment creation is idempotent like expenses. | S9 RD-B1, S5 #8/#17, S7 M9 |
| C-B3 | Migration grants: after re-granting `split_api`, repeat `REVOKE UPDATE, DELETE ON app.history`, or append-only history breaks. | S9 RD-B3, S7 M10 |
| C-B4 | One rollout statement: Render runs `alembic upgrade head` on deploy, so the backup is taken **before the merge**, and restoring that backup is the production rollback. Remove the contradicting "the author runs it" line. | S7 B1, S7 M13, S9 RD-M23, S5 #10 |
| C-B5 | Record Q1–Q6 and D1–D4 as decisions (in the draft and in `docs/12`), and have each "Rejected by author" alternative link to its decision entry. | S9 RD-B2, S7 B2 |
| C-B6 | Add a short Risks & Mitigations table: flat edit rights with no undo (accepted; `history` + "edited by"), lossy downgrade (accepted; backup is the rollback), old APKs fail on removed routes (accepted; both phones are updated by hand), deleting a group that still has balances (409 guard). | S7 B3 |

### 🟡 Major

| ID | Action | Sources |
|---|---|---|
| C-M1 | Re-split rule: an amount-only edit re-allocates over the participants and rule already stored; only an explicit change of split or participants re-resolves against the current active members. Rule changes are forward-only (Q1). | S6 #1, S5 #2, S7 M16, S9 RD-M5 |
| C-M2 | Suggestions use the confirmed balance minus payments in `sent`, so nobody is told to pay twice; the card shows "X € pending confirmation". | S5 #7, S8 #9 |
| C-M3 | Split delivery into PRs: (1) the mechanical household → group rename; (2) period removal + payments + migration 0006; (3) mobile screens. Each PR gets its own checkpoint (tests that must pass). | S5 #4, S9 RD-M1 |
| C-M4 | Map each drift fix to a file and a test: full-payload idempotency check, a scoped replacement for `expense_exists_anywhere`, `If-Match` + history on payments. Drop the personal-expense redaction (post-MVP in 00 and 10) and list it under Non-Goals. | S9 RD-M3, S7 M3/M20, S8 #4, S5 #9 |
| C-M5 | Drop the `X-Min-App-Version` promise: the app does not read it and both phones are updated by hand. State that in Risks instead. | S6 #6, S7 M1, S5 #15, S8 #11, S9 RD-M17 |
| C-M6 | Make the migration concrete: list every rename (tables, columns, constraints, indexes), every CHECK, the `split_origin` value change, the downgrade order, and migration tests that seed 0005 data and assert the mapping. Name it by the convention `YYYYMMDD_HHMM_<slug>.py`. Do not rewrite old `history.entity` values (append-only): the API maps `household` → `group` when it reads them. | S9 RD-M8/M9/M10/M11/M15, S7 M15/M18 |
| C-M7 | Payments API contract: request and response bodies, `If-Match`, who may call each transition, and the status code for each error. Define `payment_state_changed` (invalid transition) vs 412 (stale version). Drop the `disputed → sent` resend route. | S9 RD-M4/M13, S6 #10, S8 #8 |
| C-M8 | Summary uses the same filters as the list (`from`, `to`, `category_id`, `payer_member_id`, `created_by_member_id`, `q`), or the Goals say exactly which subset it takes. | S6 #4, S7 M22, S9 RD-M12 |
| C-M9 | Fix wording that contradicts the code or itself: "minimal set of payments" → greedy, at most n−1; "one running balance per member"; the permissions table vs `require_admin`; the tenant-isolation claim; "Balance at a date" under edit-in-place; the "monthly ritual" sentence. | S6 #2/#12, S7 M17/M19/M21/M23/M24 |
| C-M10 | Error codes: list only those this design removes, renames or adds, with their HTTP status, in `core/errors.py` (where they actually live) and in the mobile handling. | S7 M14, S9 RD-M13/M14 |
| C-M11 | Mobile scope: only the screens the CUJs need, each with its i18n keys, route parameters and where `activeGroupId` persists (MMKV via the existing preferences store). | S8 #5, S9 RD-M18/M19/M20/M21 |
| C-M12 | List every file the plan touches, with no globs, and give the E2E check runnable steps. | S9 RD-M2/M22/M24 |
| C-M13 | Group use cases: spell out `delete_group` (409 while any net ≠ 0), `leave_group`, `remove_member` and rejoin (reactivate the row, reset `joined_at`). | S9 RD-M6/M16, S7 M6 |
| C-M14 | Add one alternative: automatic calendar-month periods. It fixes Problems 1 and 4 but not 2, 3 or 5. Fold `/v1` vs `/v2` into Alternative D. | S7 M2, S8 narrow |

### 🟢 Nits

Define repository terms or link them (S6 #8); use one word for the invite code
(S6 #9); say what happens to extra admins (S6 #11); rename `confirmed_totals`'s
"sent" to "paid out" (S6 #13); drop the duplicate date index and the premature
partial payments index (S5 #12/#13); move the existing payment and summary
logic instead of rewriting it (S5 #14); keep function signatures out of the
architecture sections (S8 #12); plus the Nits in the S7 and S9 reports.

## Traceability matrix

| Raw finding | Consolidated item |
|---|---|
| S5 #1, S6 #7, S7 M11, S8 #7, S9 RD-B4 | C-B1 |
| S5 #8, #17; S7 M9; S9 RD-B1 | C-B2 |
| S7 M10; S9 RD-B3 | C-B3 |
| S5 #10; S7 B1, M13; S9 RD-M23 | C-B4, D3 |
| S7 B2; S9 RD-B2 | C-B5 |
| S7 B3 | C-B6 |
| S5 #2, #18; S6 #1; S7 M16; S9 RD-M5 | C-M1 |
| S5 #7; S8 #9 | C-M2 |
| S5 #4; S9 RD-M1 | C-M3 |
| S5 #9; S7 M3, M8, M20; S8 #4; S9 RD-M3 | C-M4 |
| S5 #15; S6 #6; S7 M1; S8 #11; S9 RD-M17 | C-M5 |
| S5 #11, #16; S7 M15, M18; S9 RD-M8–M11, RD-M15 | C-M6, D3 |
| S6 #10; S8 #8; S9 RD-M4, RD-M13 | C-M7 |
| S6 #4; S7 M22; S9 RD-M12 | C-M8 |
| S6 #2, #12; S7 M17, M19, M21, M23, M24 | C-M9 |
| S7 M14; S9 RD-M13, RD-M14 | C-M10 |
| S8 #5; S9 RD-M18–M21 | C-M11 |
| S9 RD-M2, RD-M22, RD-M24 | C-M12 |
| S7 M6; S9 RD-M6, RD-M16 | C-M13 |
| S7 M2 | C-M14 |
| S5 #3; S6 #5; S7 M4, M5; S8 #1 | D2 |
| S5 #20; S8 #2; S9 RD-M7 | D1 |
| S5 #6; S7 M25 | D4 |
| S5 #5; S8 #3 | Rejected (author's brief) |
| S5 #19, #21; S7 M7, M12 | Rejected by S8 (accepted trade-off in C-B6) |

## Resolution (2026-11-16)

The author decided D1–D4 (one admin with automatic hand-over; zero balance to leave; reset the cloud test data; codes typed by hand). The draft was rewritten as v2 with every 🔴 and 🟡 item above applied, and Stage 9 was re-audited once (the EGM cap): the re-audit left 1 Blocker and 23 Majors, mostly missing detail in the plan's file list, tests and mobile copy. They were settled during implementation instead of in the document, and are recorded here as accepted trade-offs:

| Re-audit finding | How it was settled |
|---|---|
| NEW-B1 `alembic downgrade -1` in Checkpoint 1 would hit the cloud DB | Never run the Alembic CLI without an explicit local URL; the round trip runs in `tests/integration/test_migrations.py` against a local Postgres. Recorded in `CLAUDE.md` and `docs/02` |
| NEW-M2 / M5 edit rules for payer, category, exact splits; `member_left` scope | `docs/03 §4` table; `member_left` blocks edit and delete of any expense whose payer or shares include a former member |
| NEW-M3 group deletion | Soft delete (`deleted_at`), history kept |
| NEW-M4 pending payments outliving membership | Leaving / removal also requires no `sent`/`disputed` payment of that member |
| NEW-M6 idempotency comparison | Full normalised payload incl. re-resolved shares (expenses) and every field (payments); foreign ids → `409 id_conflict` via a savepoint, no unscoped query |
| NEW-M9 locks and hand-over order | The group row is locked `FOR UPDATE` in leave, remove, delete, rename and invitations; the leaver is demoted and flushed before the heir is promoted |
| NEW-M10 / M11 rollout order and data backup | Rollout: data+schema backup, reset, migrate, then deploy the API and install the APK the same day; the old API is down in between (accepted for two users) |
| NEW-M12 downgrade names | The downgrade rebuilds the 0005 tables from frozen definitions; the test downgrades to base and upgrades again |
| NEW-M13, RD-M24 docs | `docs/00`–`13`, `README.md` and `CLAUDE.md` updated; decisions G1–G10 in `docs/12` |
| Remaining mobile detail (RD-M19/M20/M21, NEW-M7/M8) | Implemented and covered by typecheck, eslint and unit tests; the manual CUJ check on two phones is still pending |
