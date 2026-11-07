import { DomainError } from './errors';
import { allocate } from './money';

export type SplitType = 'equal' | 'weights' | 'percentages' | 'exact' | 'single' | 'personal';

export const BASIS_POINTS_TOTAL = 10_000;

/** A participant of a split, in canonical order (sort_key ASC, id ASC). */
export interface SplitParticipant {
  id: string;
  /** Positive integer weight, required for `weights`. */
  weight?: number;
  /** Basis points (sum 10000), required for `percentages`. */
  basisPoints?: number;
  /** Exact cents, required for `exact`. */
  exactCents?: number;
}

export interface ResolveSharesInput {
  amountCents: number;
  payerId: string;
  splitType: SplitType;
  /** Ignored for `personal` (the payer owes everything). Exactly one entry for `single`. */
  participants: readonly SplitParticipant[];
}

export interface Share {
  id: string;
  amountCents: number;
}

function requireIntField(
  p: SplitParticipant,
  field: 'weight' | 'basisPoints' | 'exactCents',
  min: number,
): number {
  const v = p[field];
  if (v === undefined || !Number.isSafeInteger(v) || v < min) {
    throw new DomainError('invalid_split', `participant ${p.id}: ${field} must be an integer >= ${min}`);
  }
  return v;
}

/**
 * Resolve how much each participant owes for one expense.
 * Invariant: the returned amounts always sum to `amountCents`.
 * Mirrors `split_ranch.domain.split.resolve_shares` (Python).
 */
export function resolveShares(input: ResolveSharesInput): Share[] {
  const { amountCents, payerId, splitType, participants } = input;
  if (!Number.isSafeInteger(amountCents) || amountCents === 0) {
    throw new DomainError('invalid_amount', 'amount must be a non-zero integer');
  }

  if (splitType === 'personal') {
    return [{ id: payerId, amountCents }];
  }

  if (participants.length === 0) {
    throw new DomainError('invalid_split', 'at least one participant is required');
  }
  const ids = new Set(participants.map((p) => p.id));
  if (ids.size !== participants.length) {
    throw new DomainError('invalid_split', 'duplicate participant');
  }

  switch (splitType) {
    case 'equal': {
      const amounts = allocate(amountCents, participants.map(() => 1));
      return participants.map((p, i) => ({ id: p.id, amountCents: amounts[i]! }));
    }
    case 'weights': {
      const weights = participants.map((p) => requireIntField(p, 'weight', 0));
      const amounts = allocate(amountCents, weights);
      return participants.map((p, i) => ({ id: p.id, amountCents: amounts[i]! }));
    }
    case 'percentages': {
      const bps = participants.map((p) => requireIntField(p, 'basisPoints', 0));
      const sum = bps.reduce((a, b) => a + b, 0);
      if (sum !== BASIS_POINTS_TOTAL) {
        throw new DomainError('split_mismatch', `basis points must sum to ${BASIS_POINTS_TOTAL}, got ${sum}`);
      }
      const amounts = allocate(amountCents, bps);
      return participants.map((p, i) => ({ id: p.id, amountCents: amounts[i]! }));
    }
    case 'exact': {
      const exact = participants.map((p) => {
        const v = p.exactCents;
        if (v === undefined || !Number.isSafeInteger(v)) {
          throw new DomainError('invalid_split', `participant ${p.id}: exactCents must be an integer`);
        }
        return v;
      });
      const sum = exact.reduce((a, b) => a + b, 0);
      if (sum !== amountCents) {
        throw new DomainError('split_mismatch', `exact amounts sum to ${sum}, expected ${amountCents}`);
      }
      return participants.map((p, i) => ({ id: p.id, amountCents: exact[i]! }));
    }
    case 'single': {
      if (participants.length !== 1) {
        throw new DomainError('invalid_split', 'single split needs exactly one participant');
      }
      return [{ id: participants[0]!.id, amountCents }];
    }
    default: {
      const never: never = splitType;
      throw new DomainError('invalid_split', `unknown split type ${String(never)}`);
    }
  }
}
