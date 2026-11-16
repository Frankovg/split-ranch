/**
 * Names the group screens use for the API models. Every server type is an alias of the
 * types generated from the FastAPI OpenAPI document (packages/api-client); regenerate
 * them with `pnpm api:openapi` after any API schema change instead of editing them here.
 */
import type {
  BalanceRead,
  CategoryRead,
  ExpenseCreate,
  ExpenseRead,
  ExpenseUpdate,
  GroupBalanceRead,
  GroupRead,
  InvitationRead,
  MemberRead,
  MembershipRead,
  MeRead,
  PageExpenseRead,
  PagePaymentRead,
  PaymentCreate,
  PaymentRead,
  ShareRead,
  SuggestionRead,
  SummaryRead,
} from '@split-ranch/api-client';

export type Membership = MembershipRead;
export type Me = MeRead;
export type Member = MemberRead;
export type Group = GroupRead;
/** The group's join code: one per group, valid 7 days, typed by hand by the invitee. */
export type Invitation = InvitationRead;
export type Category = CategoryRead;
export type Share = ShareRead;
export type Expense = ExpenseRead;
export type ExpensePage = PageExpenseRead;
export type PaymentPage = PagePaymentRead;
export type Summary = SummaryRead;
export type Balance = BalanceRead;
export type Suggestion = SuggestionRead;
/** Suggestions are computed after counting payments already sent, so nobody pays twice. */
export type GroupBalance = GroupBalanceRead;
export type Payment = PaymentRead;
/** `participants` omitted = group/category rule; otherwise an equal split between them. */
export type ExpenseCreateInput = ExpenseCreate;
/** Fields sent change; sending `participants` re-splits with today's members. */
export type ExpenseUpdateInput = ExpenseUpdate;
export type PaymentCreateInput = PaymentCreate;

/** Inclusive date range in the group's time zone ("YYYY-MM-DD"); undefined = open end. */
export interface DateRange {
  from?: string;
  to?: string;
}
