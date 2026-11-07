/** Local-only Quick split data. Amounts are integer cents. Order of `participants` is canonical (creation order). */

export type QuickMode = 'total' | 'itemised';

export interface QuickParticipant {
  id: string;
  name: string;
  /** Optional ad-hoc payment handles (docs/03 §7). */
  paypalMe?: string;
  revolut?: string;
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
}
