import datetime
from decimal import Decimal

import pytest

from transactions.models import Transaction
from transactions.parsers.barclays import PAYMENT_CODE_MAP, TRANSACTION_TYPE_MAP, BarclaysCSVParser
from transactions.parsers.base import ParsedTransaction, ParseResult, UnknownStatementFormatError
from transactions.parsers.registry import get_parser


def find(result: ParseResult, merchant: str) -> ParsedTransaction:
    """Find a transaction by merchant name."""
    for transaction in result.transactions:
        if transaction.merchant == merchant:
            return transaction

    pytest.fail(f"Transaction with merchant '{merchant}' not found in parse result.")


def find_all(result: ParseResult, merchant: str) -> list[ParsedTransaction]:
    """Find every transaction with the given merchant name."""
    return [t for t in result.transactions if t.merchant == merchant]


def test_parses_twelve_transactions(parse_result):
    assert len(parse_result.transactions) == 12


def test_parses_no_errors(parse_result):
    assert len(parse_result.errors) == 0


def test_parses_sort_code_and_account_number(parse_result):
    assert parse_result.sort_code == "112233"
    assert parse_result.account_number == "12345678"


def test_identical_transactions_are_both_kept(parse_result):
    """Two genuinely separate purchases of the same thing on the same day."""
    coffees = find_all(parse_result, "COFFEE SHOP A")

    assert len(coffees) == 2
    assert coffees[0].amount == coffees[1].amount == Decimal("-3.20")
    assert coffees[0].posted_date == coffees[1].posted_date


def test_unquoted_comma_in_merchant_is_repaired(parse_result):
    """Barclays does not quote a comma inside a merchant name."""
    transaction = find(parse_result, "VENDOR E, INC.")

    assert transaction.amount == Decimal("-7.77")
    assert "AMOUNT IN USD" in transaction.description
    assert parse_result.errors == []


def test_positive_card_purchase_is_not_reclassified_as_credit(parse_result):
    """A refund is a positive Card Purchase -- sign must not drive the type."""
    transaction = find(parse_result, "RETAILER C")

    assert transaction.amount > 0
    assert transaction.transaction_type == "CARD_PURCHASE"


def test_unmapped_subcategory_falls_back_to_other(parse_result):
    """'Unpaid' is deliberately absent from the map, so it must land in OTHER."""
    transaction = find(parse_result, "04191000000021")

    assert transaction.transaction_type == "OTHER"


@pytest.mark.parametrize(
    ("merchant", "expected_type"),
    [
        ("CASH MACHINE G", "CASH_WITHDRAWAL"),
        ("LANDLORD H", "STANDING_ORDER"),
    ],
)
def test_payment_code_beats_subcategory(parse_result, merchant, expected_type):
    """ATM and STO are more specific than the 'Debit' the Subcategory reports."""
    assert find(parse_result, merchant).transaction_type == expected_type


def test_subcategory_used_when_no_specific_payment_code(parse_result):
    assert find(parse_result, "TELECOM D").transaction_type == "DIRECT_DEBIT"
    assert find(parse_result, "A PERSON").transaction_type == "CREDIT"


def test_transaction_date_recovered_from_reference(parse_result):
    transaction = find(parse_result, "SAMPLE GYM")

    assert transaction.posted_date == datetime.date(2026, 7, 31)
    assert transaction.transaction_date == datetime.date(2026, 7, 30)


@pytest.mark.parametrize("merchant", ["TELECOM D", "A PERSON", "04191000000021"])
def test_transaction_date_is_none_without_an_on_date(parse_result, merchant):
    """Credits, direct debits and transfers settle same-day, so there is no
    second date to record. None means 'same as posted', not 'unknown'."""
    assert find(parse_result, merchant).transaction_date is None


@pytest.mark.parametrize(
    ("reference", "posted", "expected"),
    [
        # Ordinary case: a few days before the posting date.
        ("ON 30 JUL CPM", datetime.date(2026, 7, 31), datetime.date(2026, 7, 30)),
        # Year rollover: posted in January, spent the previous December.
        ("ON 31 DEC CPM", datetime.date(2027, 1, 2), datetime.date(2026, 12, 31)),
        # Same day.
        ("ON 06 JUL BCC", datetime.date(2026, 7, 6), datetime.date(2026, 7, 6)),
        # No ON date present.
        ("JANE TUTORING BGC", datetime.date(2026, 7, 13), None),
        ("", datetime.date(2026, 7, 6), None),
        # 29 Feb in a non-leap year must not raise.
        ("ON 29 FEB CPM", datetime.date(2026, 3, 2), None),
        # Unknown month abbreviation.
        ("ON 12 XXX CPM", datetime.date(2026, 7, 13), None),
    ],
)
def test_transaction_date_inference(reference, posted, expected):
    assert BarclaysCSVParser._transaction_date(reference, posted) == expected


def test_registry_matches(sample_bytes):
    assert get_parser(sample_bytes).name == "barclays_csv"


def test_registry_tolerates_a_byte_order_mark(sample_bytes):
    """Windows-generated CSVs often start with a BOM; detection must survive it."""
    with_bom = "\ufeff".encode() + sample_bytes

    assert get_parser(with_bom).name == "barclays_csv"


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"Foo,Bar,Baz\n1,2,3\n", id="unknown-header"),
        pytest.param(b"", id="empty-file"),
    ],
)
def test_registry_rejects_unrecognised_files(data):
    with pytest.raises(UnknownStatementFormatError):
        get_parser(data)


def test_parser_rejects_a_file_it_cannot_read(parser):
    """A parser stays safe to call directly, without going via the registry."""
    with pytest.raises(UnknownStatementFormatError):
        parser.parse(b"Foo,Bar,Baz\n1,2,3\n")


def test_parser_maps_only_emit_valid_model_choices():
    valid = set(Transaction.TransactionType.values)

    assert set(TRANSACTION_TYPE_MAP.values()) <= valid
    assert set(PAYMENT_CODE_MAP.values()) <= valid
