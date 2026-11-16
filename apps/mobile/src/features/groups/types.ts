/**
 * Hand-written mirrors of the FastAPI response models (apps/api/src/split_ranch/schemas).
 * TODO: replace with generated types from packages/api-client once OpenAPI codegen exists.
 */

export interface Membership {
  group_id: string;
  group_name: string;
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
  /** Active memberships only, oldest first. */
  memberships: Membership[];
}

export type MemberStatus = 'active' | 'left';

export interface Member {
  id: string;
  user_id: string;
  display_name: string | null;
  role: 'admin' | 'member' | string;
  status: MemberStatus | string;
  sort_key: number;
  joined_at: string;
  left_at: string | null;
}

export interface Group {
  id: string;
  name: string;
  timezone: string;
  created_at: string;
  members: Member[];
  my_member_id: string;
  /** Every member has the same rights; only the admin removes members and deletes the group. */
  my_role: string;
}

/** The group's join code: one per group, valid 7 days, typed by hand by the invitee. */
export interface Invitation {
  code: string;
  expires_at: string;
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
  weight?: number | null;
  basis_points?: number | null;
  exact_cents?: number | null;
}

export interface Expense {
  id: string;
  group_id: string;
  version: number;
  category_id: string | null;
  payer_member_id: string;
  amount_cents: number;
  description: string;
  notes: string | null;
  expense_date: string;
  split_type: string;
  split_origin: string;
  participant_mode: 'all' | 'subset' | string;
  shares: Share[];
  created_by_user_id: string | null;
  updated_by_user_id: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  can_edit: boolean;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

/** Inclusive date range in the group's time zone ("YYYY-MM-DD"); undefined = open end. */
export interface DateRange {
  from?: string;
  to?: string;
}

export interface Summary {
  count: number;
  total_cents: number;
  by_category: { category_id: string | null; total_cents: number }[];
  by_payer: { member_id: string; total_cents: number }[];
}

export interface Balance {
  member_id: string;
  paid_cents: number;
  owed_cents: number;
  /** Confirmed balance: expenses plus confirmed payments. */
  net_cents: number;
  pending_out_cents: number;
  pending_in_cents: number;
}

export interface Suggestion {
  from_member_id: string;
  to_member_id: string;
  amount_cents: number;
}

export interface GroupBalance {
  balances: Balance[];
  /** Computed after counting payments already sent, so nobody is told to pay twice. */
  suggestions: Suggestion[];
}

export type PaymentStatus = 'sent' | 'confirmed' | 'disputed' | 'cancelled';

export interface Payment {
  id: string;
  group_id: string;
  from_member_id: string;
  to_member_id: string;
  amount_cents: number;
  status: PaymentStatus;
  note: string | null;
  created_by_user_id: string;
  confirmed_at: string | null;
  version: number;
  created_at: string;
}

export interface ExpenseCreateInput {
  id: string;
  amount_cents: number;
  description: string;
  category_id: string | null;
  payer_member_id: string;
  expense_date: string;
  /** Omitted = group/category rule; otherwise an equal split between these members. */
  participants?: string[];
}

/** Fields sent change; sending `participants` re-splits with today's members. */
export interface ExpenseUpdateInput {
  amount_cents?: number;
  description?: string;
  category_id?: string | null;
  payer_member_id?: string;
  expense_date?: string;
  participants?: string[];
}

export interface PaymentCreateInput {
  id: string;
  from_member_id: string;
  to_member_id: string;
  amount_cents: number;
  note?: string;
}
