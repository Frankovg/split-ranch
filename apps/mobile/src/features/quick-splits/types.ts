/** Local-only Quick split data. Amounts are integer cents. Order of `participants` is canonical (creation order). */

export type QuickMode = 'total' | 'itemised';

export interface QuickParticipant {
  id: string;
  name: string;
}

export interface QuickTotal {
  amountCents: number | null;
  /** Participants left out of the split. */
  excludedIds: string[];
  /** Positive integer weights; missing means 1. */
  weights: Record<string, number>;
  /** Who paid the total, if known. Without a payer there are no transfers. */
  payerId: string | null;
  /**
   * Several payers: cents each participant put in (missing means 0). When set, `payerId` is
   * null and the amounts must add up to the total before there is a result.
   */
  payerAmounts: Record<string, number> | null;
}

export interface QuickExpense {
  id: string;
  description: string;
  amountCents: number;
  /** The one payer; ignored (empty) when `payerAmounts` is set. */
  payerId: string;
  /**
   * Several payers: cents each participant put in. They must add up to `amountCents`, or the
   * expense is skipped. Missing or null means `payerId` paid it all.
   */
  payerAmounts?: Record<string, number> | null;
  /** Subset of participant ids sharing this expense equally. */
  participantIds: string[];
}

export interface QuickEvent {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  mode: QuickMode;
  participants: QuickParticipant[];
  total: QuickTotal;
  expenses: QuickExpense[];
  /** The participant who is the phone's owner ("you"), if they marked one. */
  meId: string | null;
  /**
   * Participants marked by hand as "has paid" their part. Only the user changes it (a
   * button per person); edits to amounts never change it automatically.
   */
  paidIds: string[];
}
