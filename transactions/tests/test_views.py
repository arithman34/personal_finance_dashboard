import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from transactions.importer import import_statement
from transactions.models import Transaction

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
