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
}

export interface QuickExpense {
  id: string;
  description: string;
  amountCents: number;
  payerId: string;
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
