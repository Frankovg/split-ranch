export type DomainErrorCode =
  | 'invalid_ratios'
  | 'invalid_amount'
  | 'invalid_split'
  | 'split_mismatch'
  | 'unbalanced_nets';

/** Error raised by pure domain functions. `code` is stable and shared with the Python implementation. */
export class DomainError extends Error {
  readonly code: DomainErrorCode;

  constructor(code: DomainErrorCode, message?: string) {
    super(message ?? code);
    this.name = 'DomainError';
    this.code = code;
  }
}
