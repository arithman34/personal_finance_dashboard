import csv
import datetime
import re
from decimal import Decimal, InvalidOperation

from .base import (
    BaseStatementParser,
    ParsedError,
    ParsedTransaction,
    ParseResult,
    UnknownStatementFormatError,
)

TRANSACTION_TYPE_MAP = {
    "Debit": "DEBIT",
    "Credit": "CREDIT",
    "Card Purchase": "CARD_PURCHASE",
    "Direct Debit": "DIRECT_DEBIT",
    "Funds Transfer": "TRANSFER",
    "Counter Credit": "CREDIT",
}

PAYMENT_CODE_MAP = {
    "ATM": "CASH_WITHDRAWAL",
    "STO": "STANDING_ORDER",
}

ON_DATE_RE = re.compile(r"\bON\s+(\d{1,2})\s+([A-Za-z]{3})\b")

MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


class BarclaysCSVParser(BaseStatementParser):
    name = "barclays_csv"
    header_signature = ("Number", "Date", "Account", "Amount", "Subcategory", "Memo")
    encoding = "cp1252"

    def parse(self, data: bytes) -> ParseResult:
        try:
            decoded_data = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded_data = data.decode(self.encoding)

        reader = csv.reader(decoded_data.splitlines())

        transactions = []
        errors = []
        sort_code = account_number = None
        expected_fields = len(self.header_signature)

        for row_number, row in enumerate(reader, start=1):
            if row_number == 1:
                if not self.can_parse(tuple(field.strip() for field in row)):
                    raise UnknownStatementFormatError(
                        "Header does not match Barclays CSV format."
                    )
                continue

            if not any(field.strip() for field in row):
                continue  # blank line

            if len(row) > expected_fields:
                row = row[: expected_fields - 1] + [
                    ",".join(row[expected_fields - 1 :])
                ]
            elif len(row) < expected_fields:
                errors.append(
                    ParsedError(
                        row_number=row_number,
                        error_message=(
                            f"Expected {expected_fields} fields, got {len(row)}"
                        ),
                    )
                )
                continue

            try:
                account = row[2]
                if sort_code is None and account_number is None:
                    sort_code = account.split()[0].replace("-", "")
                    account_number = account.split()[1]

                memo = row[5]
                merchant, bank_reference = self._split_memo(memo)
                posted_date = datetime.datetime.strptime(  # noqa: DTZ007
                    row[1], "%d/%m/%Y"
                ).date()

                transactions.append(
                    ParsedTransaction(
                        posted_date=posted_date,
                        amount=Decimal(row[3]),
                        merchant=merchant,
                        bank_reference=bank_reference,
                        description=memo,
                        transaction_type=self._transaction_type(row[4], bank_reference),
                        transaction_date=self._transaction_date(
                            bank_reference, posted_date
                        ),
                        external_id=None,
                    )
                )
            except (ValueError, IndexError, InvalidOperation) as e:
                errors.append(
                    ParsedError(
                        row_number=row_number,
                        error_message=f"Error parsing row {row_number}: {e}",
                    )
                )
                continue

        return ParseResult(
            transactions=transactions,
            errors=errors,
            sort_code=sort_code if sort_code is not None else "",
            account_number=account_number if account_number is not None else "",
        )

    @staticmethod
    def _split_memo(memo: str) -> tuple[str, str]:
        """Split a Barclays memo into (merchant, bank_reference)."""
        parts = memo.split("\t")
        bank_reference = parts[1].strip() if len(parts) > 1 else ""

        merchant = re.split(r"\s{2,}", parts[0].strip())[0]
        return merchant, bank_reference

    @staticmethod
    def _transaction_type(subcategory: str, bank_reference: str) -> str:
        """Resolve the bank-neutral transaction type for a row."""
        tokens = bank_reference.split()
        if tokens and tokens[-1] in PAYMENT_CODE_MAP:
            return PAYMENT_CODE_MAP[tokens[-1]]
        return TRANSACTION_TYPE_MAP.get(subcategory, "OTHER")

    @staticmethod
    def _transaction_date(
        bank_reference: str, posted_date: datetime.date
    ) -> datetime.date | None:
        """Recover the real transaction date from an "ON 30 JUL" reference.

        The bank omits the year, so it is inferred from the posting date: a
        transaction always occurs on or before the day it posts, so a candidate
        landing after the posting date belongs to the previous year.

        Returns None for rows carrying no such date (credits, direct debits,
        transfers), where the posting date is already the transaction date.
        """
        match = ON_DATE_RE.search(bank_reference)
        if match is None:
            return None

        month = MONTHS.get(match.group(2).upper())
        if month is None:
            return None

        day = int(match.group(1))
        for year in (posted_date.year, posted_date.year - 1):
            try:
                candidate = datetime.date(year, month, day)
            except ValueError:
                return None  # e.g. 29 FEB in a non-leap year
            if candidate <= posted_date:
                return candidate
        return None
