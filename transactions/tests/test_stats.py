import datetime
from decimal import Decimal

import pytest

from transactions.models import Category, Transaction
from transactions.stats import (monthly_totals, top_merchants, totals,
                                totals_by_category, totals_by_type)

pytestmark = pytest.mark.django_db


@pytest.fixture
def spending(make_category, make_transaction):
    groceries = make_category(name="Groceries", kind=Category.KindType.SPEND)
    savings = make_category(name="Savings", kind=Category.KindType.SAVING)
    salary = make_category(name="Salary", kind=Category.KindType.INCOME)
    transfers = make_category(name="Transfers", kind=Category.KindType.TRANSFER)
    friends = make_category(name="Friends", kind=Category.KindType.TRANSFER)
    shopping = make_category(name="Shopping", kind=Category.KindType.SPEND)

    make_transaction(amount="-100.00", category=groceries, merchant="Supermarket A")
    make_transaction(amount="-200.00", category=shopping, merchant="Retailer B")
    make_transaction(amount="80.00", category=shopping, merchant="Retailer C")
    make_transaction(amount="2000.00", category=salary, merchant="Employer D")
    make_transaction(amount="-500.00", category=savings, merchant="Savings Account E")
    make_transaction(amount="-300.00", category=transfers, merchant="Bank Transfer F")
    make_transaction(amount="-120.00", category=friends, merchant="Friend G")
    make_transaction(amount="90.00", category=friends, merchant="Friend H")
    make_transaction(amount="-45.00", category=None, merchant="Uncategorised I")

    return Transaction.objects.all()


@pytest.fixture
def two_months(make_category, make_transaction):
    """Spending in July and August, with August also moving money to savings."""
    groceries = make_category(name="Groceries", kind=Category.KindType.SPEND)
    savings = make_category(name="Savings", kind=Category.KindType.SAVING)

    make_transaction(
        amount="-100.00", category=groceries, posted_date=datetime.date(2026, 7, 4)
    )
    make_transaction(
        amount="-250.00", category=groceries, posted_date=datetime.date(2026, 8, 9)
    )
    make_transaction(
        amount="-500.00", category=savings, posted_date=datetime.date(2026, 8, 9)
    )
    make_transaction(
        amount="-45.00", category=None, posted_date=datetime.date(2026, 8, 20)
    )

    return Transaction.objects.all()


def test_uncategorised_transactions_count_as_spending(spending):
    """Uncategorised transactions should be counted as spending, not ignored."""
    total = totals(spending)
    assert total["money_out"] == Decimal("265.00")


def test_savings_transactions_excluded_from_spending(spending):
    """Transactions categorised as savings should not be counted as spending."""
    total = totals(spending)
    assert total["saved"] == Decimal("500.00")


def test_transfers_change_nothing(spending, make_transaction):
    """Moving money between your own accounts is neither spending nor income."""
    before = totals(spending)
    transfers = Category.objects.get(name="Transfers")

    make_transaction(amount="-750.00", category=transfers, merchant="Bank Transfer Z")

    assert totals(Transaction.objects.all()) == before


def test_a_refund_reduces_spending(spending):
    """A refund should cancel out part of what was spent in its category."""
    Transaction.objects.get(merchant="Retailer C").delete()

    assert totals(Transaction.objects.all())["money_out"] == Decimal("345.00")


def test_a_refund_is_not_income(spending):
    """Only income categories count as money in, so a refund must not inflate it."""
    total = totals(spending)
    assert total["money_in"] == Decimal("2000.00")


def test_net_is_what_is_left_over(spending):
    """Net is simply what came in less what went out."""
    total = totals(spending)

    assert total["net"] == total["money_in"] - total["money_out"]
    assert total["net"] == Decimal("1735.00")


def test_totals_of_nothing_are_zero(account):
    """An empty dashboard should show zeroes rather than blanks."""
    total = totals(Transaction.objects.all())

    assert total == {
        "money_in": Decimal("0.00"),
        "money_out": Decimal("0.00"),
        "saved": Decimal("0.00"),
        "net": Decimal("0.00"),
    }


def test_each_month_is_reported_separately(two_months):
    """Transactions should be grouped into the month they were posted."""
    assert list(monthly_totals(two_months)) == [
        datetime.date(2026, 7, 1),
        datetime.date(2026, 8, 1),
    ]


def test_months_run_oldest_first(two_months):
    """A month by month table reads best in the order the months happened."""
    months = list(monthly_totals(two_months))

    assert months == sorted(months)


def test_monthly_figures_follow_the_same_rules_as_the_headline(two_months):
    """Savings stay out of monthly spending and uncategorised rows stay in."""
    august = monthly_totals(two_months)[datetime.date(2026, 8, 1)]

    assert august["money_out"] == Decimal("295.00")
    assert august["saved"] == Decimal("500.00")


def test_monthly_totals_of_nothing_is_empty(account):
    """No transactions means no months, rather than a month of zeroes."""
    assert monthly_totals(Transaction.objects.all()) == {}


def test_money_moved_is_not_a_top_merchant(spending):
    """Your own savings provider is not somewhere you spent money."""
    merchants = top_merchants(spending)

    assert "Savings Account E" not in merchants
    assert "Bank Transfer F" not in merchants
    assert "Friend G" not in merchants


def test_merchants_are_ranked_by_spend(spending):
    """The biggest drain on the account belongs at the top."""
    assert list(top_merchants(spending)) == [
        "Retailer B",
        "Supermarket A",
        "Uncategorised I",
    ]


def test_only_the_requested_number_of_merchants_come_back(spending):
    """The limit caps the list without changing the order."""
    assert list(top_merchants(spending, limit=2)) == ["Retailer B", "Supermarket A"]


def test_a_refund_does_not_reduce_a_merchants_total(spending, make_transaction):
    """Only outgoings are ranked, so a refund leaves the merchant total alone."""
    shopping = Category.objects.get(name="Shopping")
    make_transaction(amount="150.00", category=shopping, merchant="Retailer B")

    assert top_merchants(Transaction.objects.all())["Retailer B"] == Decimal("200.00")


def test_unused_categories_are_left_out(spending, make_category):
    """A category nothing has ever been spent against has nothing to report."""
    make_category(name="Holidays")

    assert "Holidays" not in [row.name for row in totals_by_category(spending)]


def test_transactions_without_a_category_are_grouped_together(spending):
    """Uncategorised spending still has to appear somewhere on the dashboard."""
    rows = {row.name: row for row in totals_by_category(spending)}
    uncategorised = rows["Uncategorised"]

    assert uncategorised.money_out == Decimal("45.00")
    assert uncategorised.kind == Category.KindType.SPEND
    assert uncategorised.colour == "6c757d"


def test_each_row_knows_its_kind(spending):
    """The dashboard needs the kind to tell spending apart from everything else."""
    kinds = {row.name: row.kind for row in totals_by_category(spending)}

    assert kinds["Groceries"] == Category.KindType.SPEND
    assert kinds["Salary"] == Category.KindType.INCOME
    assert kinds["Savings"] == Category.KindType.SAVING
    assert kinds["Transfers"] == Category.KindType.TRANSFER


def test_categories_are_ranked_by_what_went_out(spending):
    """Biggest outgoings first, so the table opens on what matters."""
    assert [row.name for row in totals_by_category(spending)] == [
        "Savings",
        "Transfers",
        "Shopping",
        "Friends",
        "Groceries",
        "Uncategorised",
        "Salary",
    ]


def test_a_refund_nets_off_inside_its_category(spending):
    """Money in and money out are both reported, and net is the real cost."""
    shopping = {row.name: row for row in totals_by_category(spending)}["Shopping"]

    assert shopping.money_in == Decimal("80.00")
    assert shopping.money_out == Decimal("200.00")
    assert shopping.net == Decimal("-120.00")


def test_transaction_types_are_labelled_for_people(make_transaction):
    """Nobody wants to read DIRECT_DEBIT on a dashboard."""
    make_transaction(
        amount="-12.99", transaction_type=Transaction.TransactionType.DIRECT_DEBIT
    )

    assert "Direct Debit" in totals_by_type(Transaction.objects.all())


def test_another_users_money_is_never_counted(
    spending, user, make_user, make_account, make_category, make_transaction
):
    """Every figure is built from a queryset, so the scoping has to hold."""
    stranger = make_user(username="stranger")
    their_account = make_account(user=stranger)
    their_category = make_category(name="Theirs", user=stranger)

    make_transaction(
        amount="-9999.00",
        category=their_category,
        merchant="Not Mine",
        account=their_account,
    )

    mine = Transaction.objects.filter(account__user=user)

    assert totals(mine)["money_out"] == Decimal("265.00")
    assert "Not Mine" not in top_merchants(mine)
    assert "Theirs" not in [row.name for row in totals_by_category(mine)]
