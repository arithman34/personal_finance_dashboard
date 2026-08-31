import datetime
from decimal import Decimal

import pytest

from transactions.importer import (ImportResult, StatementImportError,
                                   import_statement)
from transactions.models import StatementUpload, Transaction

pytestmark = pytest.mark.django_db


def test_import_creates_every_parsed_transaction(
    account, make_upload, sample_bytes
):
    upload = make_upload(account, sample_bytes)

    result = import_statement(upload)

    assert result == ImportResult(parsed=12, created=12)
    assert Transaction.objects.filter(account=account).count() == 12


def test_import_marks_the_upload_processed(
    account, make_upload, sample_bytes
):
    upload = make_upload(account, sample_bytes)

    import_statement(upload)
    upload.refresh_from_db()

    assert upload.status == StatementUpload.StatusType.PROCESSED
    assert upload.rows == 12
    assert upload.parser == "barclays_csv"
    assert upload.error_message == ""


def test_imported_transactions_link_back_to_their_upload(
    account, make_upload, sample_bytes
):
    upload = make_upload(account, sample_bytes)

    import_statement(upload)

    assert upload.transactions.count() == 12


def test_fields_are_mapped_onto_the_model(
    account, make_upload, sample_bytes
):
    import_statement(make_upload(account, sample_bytes))

    gym = Transaction.objects.get(account=account, merchant="SAMPLE GYM")

    assert gym.amount == Decimal("-1.00")
    assert gym.posted_date == datetime.date(2026, 7, 31)
    assert gym.transaction_date == datetime.date(2026, 7, 30)
    assert gym.transaction_type == Transaction.TransactionType.DEBIT
    assert gym.bank_reference == "ON 30 JUL CPM"
    assert gym.description.startswith("SAMPLE GYM")
    assert gym.external_id is None


def test_reimporting_the_same_file_creates_nothing(
    account, make_upload, sample_bytes
):
    import_statement(make_upload(account, sample_bytes))

    second = import_statement(make_upload(account, sample_bytes))

    assert second == ImportResult(parsed=12, created=0)
    assert Transaction.objects.filter(account=account).count() == 12


def test_identical_transactions_are_stored_separately(
    account, make_upload, sample_bytes
):
    """Two real £3.20 coffees on the same day must remain as two rows."""
    import_statement(make_upload(account, sample_bytes))

    coffees = Transaction.objects.filter(account=account, merchant="COFFEE SHOP A")

    assert coffees.count() == 2
    assert coffees.values("fingerprint").distinct().count() == 2
    assert {c.amount for c in coffees} == {Decimal("-3.20")}


def test_the_same_account_can_import_a_second_distinct_statement(
    account, make_upload, sample_bytes
):
    """An unrelated row must still import after an overlapping re-upload."""
    import_statement(make_upload(account, sample_bytes))

    extra = (
        b"Number,Date,Account,Amount,Subcategory,Memo\n"
        b"0,02/08/2026,11-22-33 12345678,-9.99,Debit,"
        b"NEW MERCHANT Z        \tON 01 AUG CPM\t\n"
    )
    result = import_statement(make_upload(account, extra, "august.csv"))

    assert result == ImportResult(parsed=1, created=1)
    assert Transaction.objects.filter(account=account).count() == 13


def test_unrecognised_format_fails_the_upload(account, make_upload):
    upload = make_upload(account, b"Foo,Bar,Baz\n1,2,3\n")

    with pytest.raises(StatementImportError):
        import_statement(upload)

    upload.refresh_from_db()
    assert upload.status == StatementUpload.StatusType.FAILED
    assert "No registered parser" in upload.error_message
    assert Transaction.objects.filter(account=account).count() == 0


def test_statement_for_a_different_account_is_rejected(
    account, make_upload, sample_bytes
):
    account.account_number = "99999999"
    account.save(update_fields=["account_number"])

    upload = make_upload(account, sample_bytes)

    with pytest.raises(StatementImportError):
        import_statement(upload)

    upload.refresh_from_db()
    assert upload.status == StatementUpload.StatusType.FAILED
    assert "99999999" in upload.error_message
    assert Transaction.objects.filter(account=account).count() == 0


def test_a_single_bad_row_prevents_the_whole_import(account, make_upload):
    """All-or-nothing: one uninterpretable row means zero rows written.

    A partial import would leave the dashboard quietly under-reporting.
    """
    data = (
        b"Number,Date,Account,Amount,Subcategory,Memo\n"
        b"0,03/07/2026,11-22-33 12345678,-35.28,Debit,"
        b"GOOD ROW              \tON 01 JUL CPM\t\n"
        b"0,03/07/2026,11-22-33 12345678\n"  # only 3 fields
    )
    upload = make_upload(account, data)

    with pytest.raises(StatementImportError):
        import_statement(upload)

    upload.refresh_from_db()
    assert upload.status == StatementUpload.StatusType.FAILED
    assert "Row 3" in upload.error_message
    assert Transaction.objects.filter(account=account).count() == 0
