from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

_MINUS = "−"


@register.filter
def money(amount) -> str:
    """Render an amount as sterling, with the sign before the symbol."""
    if amount is None or amount == "":
        return ""

    try:
        amount = Decimal(amount)
    except (TypeError, ValueError, InvalidOperation):
        return ""

    sign = _MINUS if amount < 0 else ""
    return f"{sign}£{abs(amount):,.2f}"


@register.filter
def sign(amount) -> str:
    """Return a CSS class describing whether an amount is up or down."""
    if amount is None or amount == "":
        return ""

    try:
        amount = Decimal(amount)
    except (TypeError, ValueError, InvalidOperation):
        return ""

    if amount == 0:
        return ""

    return "negative" if amount < 0 else "positive"
