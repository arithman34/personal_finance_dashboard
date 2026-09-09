import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import DecimalField, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from .models import Category, Transaction


_MONEY = DecimalField(max_digits=12, decimal_places=2)
_ZERO = Value(Decimal("0.00"), output_field=_MONEY)
_TYPE_LABELS = dict(Transaction.TransactionType.choices)
_UNCATEGORISED = "Uncategorised"
_NO_COLOUR = "6c757d"
_NON_SPEND = [
    Category.KindType.TRANSFER,
    Category.KindType.SAVING,
    Category.KindType.INCOME,
]
_SPEND = ~Q(category__kind__in=_NON_SPEND)
_INCOME = Q(category__kind=Category.KindType.INCOME)
_SAVING = Q(category__kind=Category.KindType.SAVING)


@dataclass(frozen=True)
class CategoryTotal:
    name: str
    colour: str
    kind: str
    money_in: Decimal
    money_out: Decimal
    net: Decimal


def totals(transactions: QuerySet) -> dict[str, Decimal]:
    """Money in, money out, saved and net for `transactions`."""
    figures = transactions.aggregate(
        money_in=Coalesce(Sum("amount", filter=_INCOME), _ZERO, output_field=_MONEY),
        money_out=Coalesce(Sum("amount", filter=_SPEND), _ZERO, output_field=_MONEY),
        saved=Coalesce(Sum("amount", filter=_SAVING), _ZERO, output_field=_MONEY),
    )

    money_in = figures["money_in"]
    money_out = -figures["money_out"]

    return {
        "money_in": money_in,
        "money_out": money_out,
        "saved": -figures["saved"],
        "net": money_in - money_out,
    }


def monthly_totals(transactions: QuerySet) -> dict[datetime.date, dict[str, Decimal]]:
    """Money in, money out and net for each month in `transactions`."""
    figures = transactions.annotate(month=TruncMonth("posted_date")).values("month").annotate(
        money_in=Coalesce(Sum("amount", filter=_INCOME), _ZERO, output_field=_MONEY),
        money_out=Coalesce(Sum("amount", filter=_SPEND), _ZERO, output_field=_MONEY),
        saved=Coalesce(Sum("amount", filter=_SAVING), _ZERO, output_field=_MONEY),
    ).order_by("month")

    result = {}
    for figure in figures:
        money_in = figure["money_in"]
        money_out = -figure["money_out"]
        result[figure["month"]] = {
            "money_in": money_in,
            "money_out": money_out,
            "saved": -figure["saved"],
            "net": money_in - money_out,
        }
    return result


def top_merchants(transactions: QuerySet, limit: int = 10) -> dict[str, Decimal]:
    """The `limit` merchants with the highest spend, biggest first."""
    figures = (
        transactions.filter(amount__lt=0)
        .exclude(category__kind__in=_NON_SPEND)
        .values("merchant")
        .annotate(money_spent=Sum("amount"))
        .order_by("money_spent")[:limit]
    )

    return {figure["merchant"]: -figure["money_spent"] for figure in figures}


def totals_by_type(transactions: QuerySet) -> dict[str, dict[str, Decimal]]:
    """Money in, money out and net for each transaction type in `transactions`."""
    figures = transactions.values("transaction_type").annotate(
        money_in=Coalesce(
            Sum("amount", filter=Q(amount__gt=0)), _ZERO, output_field=_MONEY
        ),
        money_out=Coalesce(
            Sum("amount", filter=Q(amount__lt=0)), _ZERO, output_field=_MONEY
        ),
    ).order_by("transaction_type")

    result = {}
    for figure in figures:
        money_in = figure["money_in"]
        money_out = -figure["money_out"]
        raw_type = figure["transaction_type"]
        label = _TYPE_LABELS.get(raw_type, raw_type)
        result[label] = {
            "money_in": money_in,
            "money_out": money_out,
            "net": money_in - money_out,
        }
    return result


def totals_by_category(transactions: QuerySet) -> list[CategoryTotal]:
    """Money in, money out and net for each category in `transactions`."""
    figures = transactions.values(
        "category__name", "category__colour", "category__kind"
    ).annotate(
        money_in=Coalesce(
            Sum("amount", filter=Q(amount__gt=0)), _ZERO, output_field=_MONEY
        ),
        money_out=Coalesce(
            Sum("amount", filter=Q(amount__lt=0)), _ZERO, output_field=_MONEY
        ),
    ).order_by("money_out")

    result = []
    for figure in figures:
        money_in = figure["money_in"]
        money_out = -figure["money_out"]
        result.append(
            CategoryTotal(
                name=figure["category__name"] or _UNCATEGORISED,
                colour=figure["category__colour"] or _NO_COLOUR,
                kind=figure["category__kind"] or Category.KindType.SPEND,
                money_in=money_in,
                money_out=money_out,
                net=money_in - money_out,
            )
        )
    return result
