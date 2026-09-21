import pytest
from django.urls import reverse

from transactions.categoriser import recategorise
from transactions.models import Category, CategoryRule, Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def suggested_rule(client, user, make_category, make_transaction):
    """A rule the LLM proposed, already applied to two of three transactions."""
    groceries = make_category(name="Groceries")
    make_category(name="Eating Out")

    make_transaction(amount="-30.00", merchant="TESCO STORES 3298")
    make_transaction(amount="-8.00", merchant="TESCO EXPRESS 881")
    make_transaction(amount="-25.00", merchant="NANDOS 441")

    rule = CategoryRule.objects.create(
        pattern="TESCO", category=groceries, source=CategoryRule.RuleSource.LLM
    )
    recategorise(user)

    client.force_login(user)
    return rule


@pytest.fixture
def stranger_rule(make_user, make_category):
    """A rule belonging to somebody else."""
    stranger = make_user(username="stranger")
    theirs = make_category(name="Theirs", user=stranger)

    return CategoryRule.objects.create(pattern="NOT YOURS", category=theirs)


def test_anonymous_is_redirected_to_login(client):
    response = client.get(reverse("transactions:rule_list"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_rules_are_listed_with_where_they_came_from(suggested_rule, client):
    """Knowing a rule was suggested rather than written matters when reviewing."""
    response = client.get(reverse("transactions:rule_list"))

    assert list(response.context["categoryrule_list"]) == [suggested_rule]
    assert "LLM" in response.content.decode()


def test_another_users_rules_are_not_listed(suggested_rule, stranger_rule, client):
    response = client.get(reverse("transactions:rule_list"))

    assert stranger_rule not in response.context["categoryrule_list"]
    assert "NOT YOURS" not in response.content.decode()


def test_only_your_own_categories_are_offered(suggested_rule, stranger_rule, client):
    """The dropdown is the first place a rule could be pointed at someone else."""
    response = client.get(reverse("transactions:rule_create"))
    offered = response.context["form"].fields["category"].queryset

    assert [c.name for c in offered] == ["Eating Out", "Groceries"]


def test_a_new_rule_is_applied_straight_away(suggested_rule, client):
    """Saving a rule that changes nothing until the next import is useless."""
    eating_out = Category.objects.get(name="Eating Out")

    client.post(
        reverse("transactions:rule_create"),
        {
            "pattern": "NANDOS",
            "category": eating_out.pk,
            "priority": 100,
            "is_active": "on",
        },
    )

    assert Transaction.objects.get(merchant="NANDOS 441").category == eating_out


def test_a_rule_you_write_yourself_is_marked_manual(suggested_rule, client):
    eating_out = Category.objects.get(name="Eating Out")

    client.post(
        reverse("transactions:rule_create"),
        {
            "pattern": "NANDOS",
            "category": eating_out.pk,
            "priority": 100,
            "is_active": "on",
        },
    )

    assert (
        CategoryRule.objects.get(pattern="NANDOS").source
        == CategoryRule.RuleSource.MANUAL
    )


def test_you_cannot_point_a_rule_at_someone_elses_category(
    suggested_rule, stranger_rule, client
):
    """The form scopes the dropdown, but the POST has to be checked too."""
    theirs = Category.objects.get(name="Theirs")

    client.post(
        reverse("transactions:rule_create"),
        {"pattern": "SNEAKY", "category": theirs.pk, "priority": 100},
    )

    assert not CategoryRule.objects.filter(pattern="SNEAKY").exists()


def test_a_pattern_of_only_spaces_is_rejected(suggested_rule, client):
    """A blank pattern would match every merchant, so it must never be saved."""
    groceries = Category.objects.get(name="Groceries")

    response = client.post(
        reverse("transactions:rule_create"),
        {"pattern": "   ", "category": groceries.pk, "priority": 100},
    )

    assert response.status_code == 200
    assert "pattern" in response.context["form"].errors


def test_editing_a_suggested_rule_makes_it_your_own(suggested_rule, client):
    """Once you have changed it, the model's judgement is no longer what is stored."""
    groceries = Category.objects.get(name="Groceries")

    client.post(
        reverse("transactions:rule_update", args=[suggested_rule.pk]),
        {
            "pattern": "TESCO EXPRESS",
            "category": groceries.pk,
            "priority": 100,
            "is_active": "on",
        },
    )
    suggested_rule.refresh_from_db()

    assert suggested_rule.source == CategoryRule.RuleSource.MANUAL


def test_narrowing_a_pattern_releases_what_no_longer_matches(suggested_rule, client):
    """Editing a rule has to reach the transactions it used to own."""
    groceries = Category.objects.get(name="Groceries")
    assert Transaction.objects.get(merchant="TESCO STORES 3298").category == groceries

    client.post(
        reverse("transactions:rule_update", args=[suggested_rule.pk]),
        {
            "pattern": "TESCO EXPRESS",
            "category": groceries.pk,
            "priority": 100,
            "is_active": "on",
        },
    )

    assert Transaction.objects.get(merchant="TESCO STORES 3298").category is None
    assert Transaction.objects.get(merchant="TESCO EXPRESS 881").category == groceries


def test_deleting_a_rule_uncategorises_what_it_owned(suggested_rule, client):
    client.post(reverse("transactions:rule_delete", args=[suggested_rule.pk]))

    assert not CategoryRule.objects.filter(pk=suggested_rule.pk).exists()
    assert Transaction.objects.get(merchant="TESCO STORES 3298").category is None


def test_a_manual_categorisation_survives_a_rule_change(
    suggested_rule, client, make_transaction
):
    """recategorise skips manual rows, so a correction must outlive its rule."""
    groceries = Category.objects.get(name="Groceries")
    corrected = make_transaction(amount="-12.00", merchant="TESCO METRO 12")
    corrected.category = groceries
    corrected.category_source = Transaction.CategorySource.MANUAL
    corrected.save()

    client.post(reverse("transactions:rule_delete", args=[suggested_rule.pk]))
    corrected.refresh_from_db()

    assert corrected.category == groceries


def test_another_users_rule_cannot_be_edited(suggested_rule, stranger_rule, client):
    response = client.get(
        reverse("transactions:rule_update", args=[stranger_rule.pk])
    )

    assert response.status_code == 404


def test_another_users_rule_cannot_be_deleted(suggested_rule, stranger_rule, client):
    response = client.post(
        reverse("transactions:rule_delete", args=[stranger_rule.pk])
    )

    assert response.status_code == 404
    assert CategoryRule.objects.filter(pk=stranger_rule.pk).exists()
