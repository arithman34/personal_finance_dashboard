import hashlib
from dataclasses import dataclass
from typing import NoReturn

from django.db import transaction as db_transaction

from .categoriser import active_rules, categorise
from .models import StatementUpload, Transaction
from .parsers.base import ParsedTransaction, UnknownStatementFormatError
from .parsers.registry import get_parser

_SEPARATOR = "\x1f"


class StatementImportError(Exception):
    """Raised when an upload cannot be imported."""


@dataclass(frozen=True)
class ImportResult:
    parsed: int
    created: int


def fingerprints(transactions: list[ParsedTransaction]) -> list[str]:
    """Return one fingerprint per transaction, in input order."""
    seen: dict[tuple, int] = {}
    digests: list[str] = []

    for transaction in transactions:
        key = (
            transaction.posted_date,
            transaction.amount,
            transaction.description,
        )

        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1

        raw = _SEPARATOR.join(
            [
                transaction.posted_date.isoformat(),
                str(transaction.amount),
                transaction.description,
                str(occurrence),
            ]
        )
        digests.append(hashlib.sha256(raw.encode("utf-8")).hexdigest())

    return digests


def _fail(upload: StatementUpload, message: str) -> NoReturn:
    """Record why an import failed on the upload, then raise."""
    upload.status = StatementUpload.StatusType.FAILED
    upload.error_message = message
    upload.save(update_fields=["status", "error_message"])
    raise StatementImportError(message)


def import_statement(upload: StatementUpload) -> ImportResult:
    """Parse an uploaded statement and insert its transactions.

    All-or-nothing: if any row cannot be interpreted, nothing is written. A
    partial import would leave the dashboard showing quietly wrong totals,
    which is worse than a visible failure.

    Idempotent: re-importing the same file, or a statement whose date range
    overlaps one already imported, inserts only the rows not already present.
    """
    with upload.file.open("rb") as f:
        data = f.read()

    try:
        parser = get_parser(data)
        result = parser.parse(data)
    except UnknownStatementFormatError as e:
        _fail(upload, str(e))

    account = upload.account

    if (result.sort_code, result.account_number) != (
        account.sort_code,
        account.account_number,
    ):
        _fail(
            upload,
            f"Statement is for {result.sort_code}/{result.account_number} "
            f"but the selected account is "
            f"{account.sort_code}/{account.account_number}.",
        )

    if result.errors:
        _fail(
            upload,
            "\n".join(
                f"Row {error.row_number}: {error.error_message}"
                for error in result.errors
            ),
        )

    digests = fingerprints(result.transactions)

    rules = active_rules(upload.user)

    existing = set(
        Transaction.objects.filter(
            account=account, fingerprint__in=digests
        ).values_list("fingerprint", flat=True)
    )

    new_transactions = []
    for parsed, digest in zip(result.transactions, digests, strict=True):
        if digest in existing:
            continue

        category = categorise(parsed.merchant, rules)
        new_transactions.append(
            Transaction(
                account=account,
                statement_upload=upload,
                category=category,
                category_source=Transaction.CategorySource.RULE if category else "",
                fingerprint=digest,
                posted_date=parsed.posted_date,
                transaction_date=parsed.transaction_date,
                amount=parsed.amount,
                description=parsed.description,
                merchant=parsed.merchant,
                bank_reference=parsed.bank_reference,
                transaction_type=parsed.transaction_type,
                external_id=parsed.external_id,
            )
        )

    with db_transaction.atomic():
        Transaction.objects.bulk_create(new_transactions, ignore_conflicts=True)

        upload.status = StatementUpload.StatusType.PROCESSED
        upload.rows = len(result.transactions)
        upload.parser = parser.name
        upload.error_message = ""
        upload.save(update_fields=["status", "rows", "parser", "error_message"])

    return ImportResult(
        parsed=len(result.transactions),
        created=len(new_transactions),
    )
