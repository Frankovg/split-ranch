# @split-ranch/domain-vectors

Language-neutral test vectors (snake_case JSON) that **both** the TypeScript domain
(`packages/domain`) and the Python domain (`apps/api/src/split_ranch/domain`) must pass.

| File | Function |
|---|---|
| `allocate.json` | `allocate(total, ratios)` |
| `resolve_shares.json` | `resolve_shares(input)` / `resolveShares(input)` |
| `balances.json` | `compute_balances(member_order, expenses)` / `computeBalances(...)` |
| `settle.json` | `settle(nets)` |

Each vector has either `expected` or `error` (a `DomainError` code:
`invalid_ratios`, `invalid_amount`, `invalid_split`, `split_mismatch`, `unbalanced_nets`).

Changing an existing vector is a money-behaviour change and must be called out in the PR.
