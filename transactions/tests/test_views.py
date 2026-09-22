import datetime
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from transactions.importer import import_statement
from transactions.models import Category, StatementUpload, Transaction

pytestmark = pytest.mark.django_db


def test_anonymous_is_redirected_to_login(client):
    response = client.get(reverse("transactions:transaction_list"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_authenticated_user_sees_their_transactions(
    client, user, account, make_upload, sample_bytes
):
    import_statement(make_upload(account, sample_bytes))
    client.force_login(user)

    response = client.get(reverse("transactions:transaction_list"))

    assert response.status_code == 200
    assert response.context["page_obj"].paginator.count == 12
    assert "COFFEE SHOP A" in response.content.decode()


def test_a_user_cannot_see_another_users_transactions(
    client, make_user, make_account, make_upload, sample_bytes
):
    alice = make_user("alice")
    bob = make_user("bob")

    import_statement(make_upload(make_account(user=alice), sample_bytes))
    Transaction.objects.create(
        account=make_account(user=bob, account_number="87654321"),
        fingerprint="bob_only_fingerprint",
        posted_date=datetime.date(2026, 7, 15),
        amount=Decimal("-12.34"),
        description="BOB SECRET SHOP",
        merchant="BOB SECRET SHOP",
        transaction_type=Transaction.TransactionType.CARD_PURCHASE,
    )

    client.force_login(alice)
    body = client.get(reverse("transactions:transaction_list")).content.decode()

    assert "COFFEE SHOP A" in body
    assert "BOB SECRET SHOP" not in body


# Uploading a statement


def csv_file(data, name="statement.csv"):
    return SimpleUploadedFile(name, data, content_type="text/csv")


def test_uploading_a_statement_imports_it(client, user, account, sample_bytes):
    client.force_login(user)

    response = client.post(
        reverse("transactions:upload"),
        {"account": account.pk, "file": csv_file(sample_bytes)},
        follow=True,
    )

    assert Transaction.objects.filter(account=account).count() == 12
    assert "Imported 12 of 12 transactions." in [
        str(m) for m in response.context["messages"]
    ]


def test_uploading_the_same_statement_twice_adds_nothing(
    client, user, account, sample_bytes
):
    """Idempotency has to hold through the view, not just the importer."""
    client.force_login(user)
    url = reverse("transactions:upload")

    client.post(url, {"account": account.pk, "file": csv_file(sample_bytes)})
    response = client.post(
        url, {"account": account.pk, "file": csv_file(sample_bytes)}, follow=True
    )

    assert Transaction.objects.filter(account=account).count() == 12
    assert "Imported 0 of 12 transactions." in [
        str(m) for m in response.context["messages"]
    ]


def test_a_failed_import_is_explained(client, user, account):
    """A silent failure would leave the dashboard quietly wrong."""
    client.force_login(user)
    broken = (
        b"Number,Date,Account,Amount,Subcategory,Memo\n"
        b"0,03/07/2026,11-22-33 12345678,-35.28,Debit,"
        b"GOOD ROW              \tON 01 JUL CPM\t\n"
        b"0,03/07/2026,11-22-33 12345678\n"
    )

    response = client.post(
        reverse("transactions:upload"),
        {"account": account.pk, "file": csv_file(broken)},
        follow=True,
    )

    assert Transaction.objects.count() == 0
    assert "Row 3" in " ".join(str(m) for m in response.context["messages"])


def test_an_unrecognised_format_is_rejected(client, user, account):
    client.force_login(user)

    response = client.post(
        reverse("transactions:upload"),
        {"account": account.pk, "file": csv_file(b"Foo,Bar,Baz\n1,2,3\n")},
        follow=True,
    )

    assert Transaction.objects.count() == 0
    assert "No registered parser" in " ".join(
        str(m) for m in response.context["messages"]
    )


def test_only_csv_files_are_accepted(client, user, account):
    client.force_login(user)

    client.post(
        reverse("transactions:upload"),
        {
            "account": account.pk,
            "file": SimpleUploadedFile("statement.pdf", b"%PDF-1.4"),
        },
    )

    assert not StatementUpload.objects.exists()


def test_you_cannot_upload_to_another_users_account(
    client, user, make_user, make_account, sample_bytes
):
    stranger = make_user(username="stranger")
    theirs = make_account(user=stranger)
    client.force_login(user)

    client.post(
        reverse("transactions:upload"),
        {"account": theirs.pk, "file": csv_file(sample_bytes)},
    )

    assert not StatementUpload.objects.exists()


# Changing a category from the transaction list


@pytest.fixture
def one_transaction(client, user, account, make_category, make_transaction):
    make_category(name="Groceries")
    transaction = make_transaction(amount="-30.00", merchant="TESCO")
    client.force_login(user)
    return transaction


def test_setting_a_category_marks_it_as_yours(one_transaction, client):
    """recategorise skips manual rows, so this is what makes a fix stick."""
    groceries = Category.objects.get(name="Groceries")

    client.post(
        reverse("transactions:transaction_list"),
        {"transaction": one_transaction.pk, "category": groceries.pk},
    )
    one_transaction.refresh_from_db()

    assert one_transaction.category == groceries
    assert one_transaction.category_source == Transaction.CategorySource.MANUAL


def test_clearing_a_category_clears_the_source_too(one_transaction, client):
    """Leaving MANUAL behind would stop rules ever touching the row again."""
    groceries = Category.objects.get(name="Groceries")
    url = reverse("transactions:transaction_list")

    client.post(url, {"transaction": one_transaction.pk, "category": groceries.pk})
    client.post(url, {"transaction": one_transaction.pk, "category": ""})
    one_transaction.refresh_from_db()

    assert one_transaction.category is None
    assert one_transaction.category_source == ""


def test_you_cannot_change_another_users_transaction(
    one_transaction, client, make_user, make_account, make_transaction
):
    stranger = make_user(username="stranger")
    theirs = make_transaction(
        amount="-5.00", merchant="NOT MINE", account=make_account(user=stranger)
    )
    groceries = Category.objects.get(name="Groceries")

    client.post(
        reverse("transactions:transaction_list"),
        {"transaction": theirs.pk, "category": groceries.pk},
    )
    theirs.refresh_from_db()

    assert theirs.category is None


def test_you_cannot_use_another_users_category(
    one_transaction, client, make_user, make_category
):
    stranger = make_user(username="stranger")
    theirs = make_category(name="Theirs", user=stranger)

    client.post(
        reverse("transactions:transaction_list"),
        {"transaction": one_transaction.pk, "category": theirs.pk},
    )
    one_transaction.refresh_from_db()

    assert one_transaction.category is None


def test_an_id_that_is_not_a_number_does_not_crash(one_transaction, client):
    """Both ids arrive from a form, so anything at all can be posted."""
    response = client.post(
        reverse("transactions:transaction_list"),
        {"transaction": "not-a-number", "category": "also-not"},
        follow=True,
    )

    assert response.status_code == 200


def test_the_page_you_were_on_is_kept(one_transaction, client):
    groceries = Category.objects.get(name="Groceries")

    response = client.post(
        reverse("transactions:transaction_list") + "?page=2",
        {"transaction": one_transaction.pk, "category": groceries.pk},
    )

    assert response.url.endswith("?page=2")
