/**
 * Hand-written mirrors of the FastAPI response models (apps/api/src/split_ranch/schemas).
 * TODO: replace with generated types from packages/api-client once OpenAPI codegen exists.
 */

export interface Membership {
  household_id: string;
  household_name: string;
  member_id: string;
  role: string;
  status: string;
}

export interface Me {
  id: string;
  email: string | null;
  display_name: string | null;
  avatar_url: string | null;
  locale: string;
  memberships: Membership[];
}

export interface Member {
  id: string;
  user_id: string;
  display_name: string | null;
  role: string;
  status: string;
  sort_key: number;
  /** Period numbers the member takes part in (left = null while still a member). */
  joined_period_seq: number;
  left_period_seq: number | null;
}

export interface Household {
  id: string;
  name: string;
  timezone: string;
  currency: string;
  version: number;
  created_at: string;
  members: Member[];
  my_member_id: string;
  my_role: string;
}

export interface Invitation {
  id: string;
  code: string;
  url: string;
  expires_at: string;
  max_uses: number;
  uses: number;
}

export interface Category {
  id: string;
  name: string;
  icon: string | null;
  color: string | null;
  is_default: boolean;
  sort_key: number;
  archived_at: string | null;
}

export interface Share {
  member_id: string;
  amount_cents: number;
}

export interface Expense {
  id: string;
  version: number;
  period: { id: string; seq: number; status: string };
  category_id: string | null;
  payer_member_id: string;
  amount_cents: number;
  description: string;
  expense_date: string;
  split_type: string;
  status: string;
  shares: Share[];
  created_at: string;
  deleted_at: string | null;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export type PeriodStatus = 'open' | 'closed' | 'settled';

/** A period number, or "current" for the latest period (open or not). */
export type PeriodKey = number | 'current';

/** Members close a period and start the next one by hand: periods are numbered, not months. */
export interface Period {
  id: string;
  seq: number;
  status: PeriodStatus;
  started_at: string;
  closed_at: string | null;
  settled_at: string | null;
  version: number;
  total_cents: number;
  /** True once any transfer was sent or confirmed: the period can no longer be reopened. */
  locked: boolean;
}

export type TransferStatus = 'pending' | 'sent' | 'confirmed' | 'disputed' | 'cancelled';

export interface Transfer {
  id: string;
  from_member_id: string;
  to_member_id: string;
  amount_cents: number;
  status: TransferStatus;
  note: string | null;
  sent_at: string | null;
  confirmed_at: string | null;
}

export interface Settlement {
  period: Period;
  transfers: Transfer[];
}

export interface Balance {
  member_id: string;
  paid_cents: number;
  owed_cents: number;
  net_cents: number;
}

export interface PeriodBalance {
  period: Period;
  balances: Balance[];
  drift: boolean;
}

export interface ExpenseCreateInput {
  id: string;
  amount_cents: number;
  description: string;
  category_id: string | null;
  payer_member_id: string;
  expense_date: string;
  /** Omitted = household rule; otherwise equal split between these members. */
  participants?: string[];
}
