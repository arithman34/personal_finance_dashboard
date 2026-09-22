from decimal import Decimal

import pytest
from django.urls import reverse

from transactions.models import CategoryRule
from transactions.templatetags.money import money, sign

pytestmark = pytest.mark.django_db

MINUS = "−"
POUND = "£"


def test_money_filter():
    """A hyphen after the symbol reads badly, so the sign goes in front of it."""
    assert money(Decimal("-53.29")) == f"{MINUS}{POUND}53.29"
    assert money(Decimal("1234.50")) == f"{POUND}1,234.50"
    assert money(Decimal("0.00")) == f"{POUND}0.00"
    assert money(None) == ""


def test_sign_filter():
    assert sign(Decimal("-1")) == "negative"
    assert sign(Decimal("1")) == "positive"
    assert sign(Decimal("0")) == ""
    assert sign(None) == ""


def test_every_page_renders(client, user, account, make_category, make_transaction):
    groceries = make_category(name="Groceries")
    make_transaction(amount="-53.29", merchant="TESCO", category=groceries)
    rule = CategoryRule.objects.create(pattern="TESCO", category=groceries)
    client.force_login(user)

    pages = [
        reverse("transactions:dashboard"),
        reverse("transactions:transaction_list"),
        reverse("transactions:categorise"),
        reverse("transactions:category_list"),
        reverse("transactions:category_create"),
        reverse("transactions:category_update", args=[groceries.pk]),
        reverse("transactions:category_delete", args=[groceries.pk]),
        reverse("transactions:rule_list"),
        reverse("transactions:rule_create"),
        reverse("transactions:rule_update", args=[rule.pk]),
        reverse("transactions:rule_delete", args=[rule.pk]),
        reverse("transactions:upload"),
    ]

    for url in pages:
        response = client.get(url)
        assert response.status_code == 200, url
        assert "css/app.css" in response.content.decode(), url

    client.logout()
    login = client.get(reverse("login"))

    assert login.status_code == 200
    assert "css/app.css" in login.content.decode()


def test_negative_amounts_reach_the_page_formatted(
    client, user, account, make_transaction
):
    make_transaction(amount="-53.29", merchant="TESCO")
    client.force_login(user)

    body = client.get(reverse("transactions:transaction_list")).content.decode()

    assert f"{MINUS}{POUND}53.29" in body
    assert f"{POUND}-53.29" not in body
