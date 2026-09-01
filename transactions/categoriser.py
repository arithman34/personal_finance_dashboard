from django.db import transaction as db_transaction
from django.db.models import Count, Sum, QuerySet

from .models import Category, CategoryRule, Transaction


def active_rules(user) -> list[CategoryRule]:
    """Every active rule belonging to `user`, in priority order."""
    return list(
        CategoryRule.objects.filter(is_active=True, category__user=user)
        .select_related("category")
    )


def categorise(merchant: str, rules: list[CategoryRule]) -> Category | None:
    """Return the category for `merchant`, or None if no rule matches."""
    merchant = merchant.lower()

    for rule in rules:
        pattern = rule.pattern.lower().strip()
        if not pattern:
            continue

        if pattern in merchant:
            return rule.category

    return None


def recategorise(user, force: bool = False) -> tuple[int, int]:
    """Re-apply `user`'s rules to their transactions."""
    rules = active_rules(user)

    transactions = Transaction.objects.filter(account__user=user)
    if not force:
        transactions = transactions.exclude(
            category_source=Transaction.CategorySource.MANUAL
        )

    scanned = 0
    changed = []

    for transaction in transactions.iterator(chunk_size=1000):
        scanned += 1
        category = categorise(transaction.merchant, rules)

        category_id = category.pk if category else None
        source = Transaction.CategorySource.RULE if category else ""

        if (category_id, source) != (transaction.category_id, transaction.category_source):
            transaction.category_id = category_id
            transaction.category_source = source
            changed.append(transaction)

    with db_transaction.atomic():
        Transaction.objects.bulk_update(
            changed, ["category", "category_source"], batch_size=500
        )

    return scanned, len(changed)


def uncategorised_merchants(transactions: QuerySet) -> list[dict]:
    """The merchants still needing a category, biggest outgoing first."""
    return list(
        transactions.filter(category__isnull=True)
        .exclude(merchant="")
        .values("merchant")
        .annotate(count=Count("id"), total=Sum("amount"))
        .order_by("total")
    )
