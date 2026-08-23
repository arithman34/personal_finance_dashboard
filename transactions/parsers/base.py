import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


class UnknownStatementFormatError(Exception):
    """Raised when no registered parser recognises a file's header."""


@dataclass(frozen=True)
class ParsedError:
    """A row in the bank statement that could not be parsed."""

    row_number: int
    error_message: str


@dataclass(frozen=True)
class ParsedTransaction:
    """Successfully parsed transaction from a bank statement."""

    posted_date: datetime.date
    amount: Decimal
    merchant: str
    bank_reference: str
    description: str
    transaction_type: str
    transaction_date: datetime.date | None = None
    external_id: str | None = None


@dataclass(frozen=True)
class ParseResult:
    """Represents the result of parsing a bank statement."""

    transactions: list[ParsedTransaction]
    errors: list[ParsedError]
    sort_code: str
    account_number: str


class BaseStatementParser(ABC):
    """
    Base class for bank statement parsers. One subclass per bank and format.
    """

    name: str
    header_signature: tuple[str, ...]
    encoding: str = "utf-8"

    @classmethod
    def can_parse(cls, header: tuple[str, ...]) -> bool:
        return header == cls.header_signature

    @abstractmethod
    def parse(self, data: bytes) -> ParseResult: ...
