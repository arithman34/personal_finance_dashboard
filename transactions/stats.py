import datetime
from decimal import Decimal

from django.db.models import DecimalField, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from .models import Transaction


_MONEY = DecimalField(max_digits=12, decimal_places=2)
_ZERO = Value(Decimal("0.00"), output_field=_MONEY)
_TYPE_LABELS = dict(Transaction.TransactionType.choices)


def totals(transactions: QuerySet) -> dict[str, Decimal]:
    """Money in, money out and net for `transactions`."""
    figures = transactions.aggregate(
        money_in=Coalesce(
            Sum("amount", filter=Q(amount__gt=0)), _ZERO, output_field=_MONEY
        ),
        money_out=Coalesce(
            Sum("amount", filter=Q(amount__lt=0)), _ZERO, output_field=_MONEY
        ),
    )

    money_in = figures["money_in"]
    money_out = -figures["money_out"]

    return {
        "money_in": money_in,
        "money_out": money_out,
        "net": money_in - money_out,
    }


def monthly_totals(transactions: QuerySet) -> dict[datetime.date, dict[str, Decimal]]:
    """Money in, money out and net for each month in `transactions`."""
    figures = transactions.annotate(month=TruncMonth("posted_date")).values("month").annotate(
        money_in=Coalesce(
            Sum("amount", filter=Q(amount__gt=0)), _ZERO, output_field=_MONEY
        ),
        money_out=Coalesce(
            Sum("amount", filter=Q(amount__lt=0)), _ZERO, output_field=_MONEY
        ),
    ).order_by("month")

    result = {}
    for figure in figures:
        money_in = figure["money_in"]
        money_out = -figure["money_out"]
        result[figure["month"]] = {
            "money_in": money_in,
            "money_out": money_out,
            "net": money_in - money_out,
        }
    return result


def top_merchants(transactions: QuerySet, limit: int = 10) -> dict[str, Decimal]:
    """The `limit` merchants with the highest spend, biggest first."""
    figures = (
        transactions.filter(amount__lt=0)
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
