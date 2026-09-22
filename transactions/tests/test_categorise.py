from decimal import Decimal

import pytest
from django.urls import reverse

from transactions import views
from transactions.models import Category, CategoryRule, Transaction
from transactions.suggester import Suggestion, SuggestionError

pytestmark = pytest.mark.django_db

URL = "/transactions/categorise/"


@pytest.fixture
def backlog(client, user, make_category, make_transaction):
    """Two Tesco transactions and one Nandos, none of them categorised."""
    make_category(name="Groceries")
    make_category(name="Eating Out")

    make_transaction(amount="-30.00", merchant="TESCO STORES 3298")
    make_transaction(amount="-12.50", merchant="TESCO STORES 3298")
    make_transaction(amount="-25.00", merchant="NANDOS 441")

    client.force_login(user)


@pytest.fixture
def stub_suggestions(monkeypatch):
    """Replace the API call with a fixed answer, or an error."""

    def _stub(suggestions=None, error=None):
        def fake(user):
            if error is not None:
                raise error
            return suggestions or []

        monkeypatch.setattr(views, "suggest_rules", fake)

    return _stub


def test_anonymous_is_redirected_to_login(client):
    response = client.get(reverse("transactions:categorise"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_uncategorised_merchants_are_listed_once_each(backlog, client):
    """Two Tesco rows are one decision, not two."""
    rows = client.get(URL).context["rows"]

    assert [row["merchant"] for row in rows] == ["TESCO STORES 3298", "NANDOS 441"]


def test_each_merchant_shows_how_much_it_accounts_for(backlog, client):
    rows = {row["merchant"]: row for row in client.get(URL).context["rows"]}

    assert rows["TESCO STORES 3298"]["count"] == 2
    assert rows["TESCO STORES 3298"]["total"] == Decimal("-42.50")


def test_a_categorised_merchant_drops_off_the_list(backlog, client):
    groceries = Category.objects.get(name="Groceries")
    Transaction.objects.filter(merchant__startswith="TESCO").update(category=groceries)

    rows = client.get(URL).context["rows"]

    assert [row["merchant"] for row in rows] == ["NANDOS 441"]


def test_always_saves_a_rule_and_applies_it(backlog, client):
    groceries = Category.objects.get(name="Groceries")

    client.post(
        URL,
        {
            "action": "rule",
            "merchant": "TESCO STORES 3298",
            "pattern": "TESCO",
            "category": groceries.pk,
        },
    )

    assert CategoryRule.objects.filter(pattern="TESCO").exists()
    assert Transaction.objects.filter(category=groceries).count() == 2


def test_once_categorises_without_saving_a_rule(backlog, client):
    """The point of Once is that nothing is remembered for next time."""
    eating_out = Category.objects.get(name="Eating Out")

    client.post(
        URL,
        {
            "action": "assign",
            "merchant": "NANDOS 441",
            "pattern": "NANDOS 441",
            "category": eating_out.pk,
        },
    )

    assert not CategoryRule.objects.exists()
    assert Transaction.objects.get(merchant="NANDOS 441").category == eating_out


def test_once_marks_the_transactions_as_yours(backlog, client):
    """A hand categorisation must survive the next recategorise."""
    eating_out = Category.objects.get(name="Eating Out")

    client.post(
        URL,
        {
            "action": "assign",
            "merchant": "NANDOS 441",
            "pattern": "NANDOS 441",
            "category": eating_out.pk,
        },
    )

    nandos = Transaction.objects.get(merchant="NANDOS 441")
    assert nandos.category_source == Transaction.CategorySource.MANUAL


def test_an_unknown_action_changes_nothing(backlog, client):
    groceries = Category.objects.get(name="Groceries")

    client.post(
        URL,
        {
            "action": "something-else",
            "merchant": "TESCO STORES 3298",
            "pattern": "TESCO",
            "category": groceries.pk,
        },
    )

    assert not CategoryRule.objects.exists()
    assert Transaction.objects.filter(category__isnull=False).count() == 0


def test_a_form_without_a_category_is_rejected(backlog, client):
    client.post(URL, {"action": "rule", "merchant": "TESCO STORES 3298"})

    assert not CategoryRule.objects.exists()


def test_you_cannot_use_another_users_category(
    backlog, client, make_user, make_category
):
    stranger = make_user(username="stranger")
    theirs = make_category(name="Theirs", user=stranger)

    client.post(
        URL,
        {
            "action": "rule",
            "merchant": "TESCO STORES 3298",
            "pattern": "TESCO",
            "category": theirs.pk,
        },
    )

    assert not CategoryRule.objects.exists()


def test_asking_for_suggestions_remembers_them(backlog, client, stub_suggestions):
    groceries = Category.objects.get(name="Groceries")
    stub_suggestions(
        [Suggestion(merchant="TESCO STORES 3298", pattern="TESCO", category=groceries)]
    )

    client.post(URL, {"action": "suggest"})

    assert client.session["suggestions"] == {
        "TESCO STORES 3298": {"pattern": "TESCO", "category": groceries.pk}
    }


def test_a_suggestion_fills_the_form_in(backlog, client, stub_suggestions):
    groceries = Category.objects.get(name="Groceries")
    stub_suggestions(
        [Suggestion(merchant="TESCO STORES 3298", pattern="TESCO", category=groceries)]
    )
    client.post(URL, {"action": "suggest"})

    rows = {row["merchant"]: row for row in client.get(URL).context["rows"]}
    tesco = rows["TESCO STORES 3298"]

    assert tesco["suggested"] is True
    assert tesco["form"].initial["pattern"] == "TESCO"
    assert tesco["form"].initial["category"] == groceries.pk


def test_a_merchant_with_no_suggestion_is_left_alone(
    backlog, client, stub_suggestions
):
    groceries = Category.objects.get(name="Groceries")
    stub_suggestions(
        [Suggestion(merchant="TESCO STORES 3298", pattern="TESCO", category=groceries)]
    )
    client.post(URL, {"action": "suggest"})

    rows = {row["merchant"]: row for row in client.get(URL).context["rows"]}
    nandos = rows["NANDOS 441"]

    assert nandos["suggested"] is False
    assert nandos["form"].initial["pattern"] == "NANDOS 441"


def test_a_failure_is_shown_rather_than_raised(backlog, client, stub_suggestions):
    stub_suggestions(error=SuggestionError("no api key"))

    response = client.post(URL, {"action": "suggest"}, follow=True)

    assert response.status_code == 200
    assert "no api key" in [str(m) for m in response.context["messages"]]
    assert "suggestions" not in client.session


def test_accepting_a_suggestion_unchanged_is_credited_to_the_model(
    backlog, client, stub_suggestions
):
    groceries = Category.objects.get(name="Groceries")
    stub_suggestions(
        [Suggestion(merchant="TESCO STORES 3298", pattern="TESCO", category=groceries)]
    )
    client.post(URL, {"action": "suggest"})

    client.post(
        URL,
        {
            "action": "rule",
            "merchant": "TESCO STORES 3298",
            "pattern": "TESCO",
            "category": groceries.pk,
        },
    )

    assert (
        CategoryRule.objects.get(pattern="TESCO").source
        == CategoryRule.RuleSource.LLM
    )


def test_editing_a_suggestion_first_makes_it_yours(
    backlog, client, stub_suggestions
):
    """Changing the pattern means the stored judgement is no longer the model's."""
    groceries = Category.objects.get(name="Groceries")
    stub_suggestions(
        [Suggestion(merchant="TESCO STORES 3298", pattern="TESCO", category=groceries)]
    )
    client.post(URL, {"action": "suggest"})

    client.post(
        URL,
        {
            "action": "rule",
            "merchant": "TESCO STORES 3298",
            "pattern": "TESCO STORES",
            "category": groceries.pk,
        },
    )

    assert (
        CategoryRule.objects.get(pattern="TESCO STORES").source
        == CategoryRule.RuleSource.MANUAL
    )


def test_a_rule_written_without_a_suggestion_is_yours(backlog, client):
    groceries = Category.objects.get(name="Groceries")

    client.post(
        URL,
        {
            "action": "rule",
            "merchant": "TESCO STORES 3298",
            "pattern": "TESCO",
            "category": groceries.pk,
        },
    )

    assert (
        CategoryRule.objects.get(pattern="TESCO").source
        == CategoryRule.RuleSource.MANUAL
    )


def test_another_users_backlog_is_not_shown(
    backlog, client, make_user, make_account, make_transaction
):
    stranger = make_user(username="stranger")
    make_transaction(
        amount="-99.00",
        merchant="NOT MINE",
        account=make_account(user=stranger),
    )

    rows = client.get(URL).context["rows"]

    assert "NOT MINE" not in [row["merchant"] for row in rows]
