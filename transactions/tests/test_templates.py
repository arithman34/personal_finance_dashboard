from decimal import Decimal

import pytest
from django.urls import reverse

from transactions.models import Category, CategoryRule
from transactions.templatetags.money import money, sign

pytestmark = pytest.mark.django_db


def test_money_filter():
    assert money(Decimal("-53.29")) == "−£53.29"
    assert money(Decimal("1234.50")) == "£1,234.50"
    assert money(Decimal("0.00")) == "£0.00"
    assert money(None) == ""
    assert sign(Decimal("-1")) == "negative"
    assert sign(Decimal("1")) == "positive"
    assert sign(Decimal("0")) == ""


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
        body = response.content.decode()
        assert "css/app.css" in body, url

    client.logout()
    assert client.get(reverse("login")).status_code == 200

    body = client.get(reverse("login")).content.decode()
    assert "css/app.css" in body


def test_negative_amount_is_rendered_properly(
    client, user, account, make_category, make_transaction
):
    make_transaction(amount="-53.29", merchant="TESCO")
    client.force_login(user)

    body = client.get(reverse("transactions:transaction_list")).content.decode()

    assert "-£53.29" in body
    assert "£-53.29" not in body
