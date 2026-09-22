import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from transactions.models import Account, Category, CategoryRule, Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    call_command("seed_demo", months=3, verbosity=0)
    return get_user_model().objects.get(username="demo")


def test_it_creates_a_self_contained_demo_user(seeded):
    assert Account.objects.filter(user=seeded).count() == 1
    assert Category.objects.filter(user=seeded).count() == 15
    assert CategoryRule.objects.filter(category__user=seeded).exists()
    assert Transaction.objects.filter(account__user=seeded).exists()


def test_rules_categorise_most_of_the_transactions(seeded):
    """A demo with nothing categorised would show an empty dashboard."""
    transactions = Transaction.objects.filter(account__user=seeded)
    categorised = transactions.filter(category__isnull=False).count()

    assert categorised > transactions.count() * 0.8


def test_some_transactions_are_left_uncategorised(seeded):
    """The categorise page needs something to show."""
    assert Transaction.objects.filter(
        account__user=seeded, category__isnull=True
    ).exists()


def test_it_covers_every_kind(seeded):
    kinds = set(
        Category.objects.filter(
            user=seeded, transactions__isnull=False
        ).values_list("kind", flat=True)
    )

    assert kinds == {
        Category.KindType.SPEND,
        Category.KindType.INCOME,
        Category.KindType.SAVING,
        Category.KindType.TRANSFER,
    }


def test_both_rule_sources_are_represented(seeded):
    """The rules page should show the manual and suggested distinction."""
    sources = set(
        CategoryRule.objects.filter(category__user=seeded).values_list(
            "source", flat=True
        )
    )

    assert sources == {CategoryRule.RuleSource.MANUAL, CategoryRule.RuleSource.LLM}


def test_running_it_twice_does_not_duplicate(seeded):
    call_command("seed_demo", months=3, verbosity=0)

    assert get_user_model().objects.filter(username="demo").count() == 1


def test_reset_replaces_the_previous_run(seeded):
    before = Transaction.objects.filter(account__user=seeded).count()
    call_command("seed_demo", months=3, reset=True, verbosity=0)

    user = get_user_model().objects.get(username="demo")

    assert Transaction.objects.filter(account__user=user).count() == before
    assert Transaction.objects.exclude(account__user=user).count() == 0


def test_it_leaves_other_users_alone(seeded, make_user, make_account):
    stranger = make_user(username="stranger")
    make_account(user=stranger)

    call_command("seed_demo", months=3, reset=True, verbosity=0)

    assert get_user_model().objects.filter(username="stranger").exists()
    assert Account.objects.filter(user=stranger).exists()
