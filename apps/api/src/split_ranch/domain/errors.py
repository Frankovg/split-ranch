"""Domain errors. Codes are stable and shared with the TypeScript implementation."""

from typing import Literal

DomainErrorCode = Literal[
    "invalid_ratios",
    "invalid_amount",
    "invalid_split",
    "split_mismatch",
    "unbalanced_nets",
]


class DomainError(Exception):
    """Error raised by pure domain functions."""

    def __init__(self, code: DomainErrorCode, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code: DomainErrorCode = code
        self.message: str = message or code
