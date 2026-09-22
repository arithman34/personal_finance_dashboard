import datetime
import hashlib
import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction

from transactions.categoriser import recategorise
from transactions.models import Account, Category, CategoryRule, Transaction

USERNAME = "demo"
PASSWORD = "demo-password-123"

K = Category.KindType
T = Transaction.TransactionType
S = CategoryRule.RuleSource

CATEGORIES = [
    ("Groceries", K.SPEND, "2f9e44"),
    ("Eating Out & Takeaway", K.SPEND, "e8590c"),
    ("Transport", K.SPEND, "1971c2"),
    ("Bills & Utilities", K.SPEND, "5f3dc4"),
    ("Subscriptions", K.SPEND, "7048e8"),
    ("Entertainment", K.SPEND, "c2255c"),
    ("Health & Fitness", K.SPEND, "0c8599"),
    ("Shopping", K.SPEND, "f08c00"),
    ("Education", K.SPEND, "495057"),
    ("Rent or Mortgage", K.SPEND, "a61e4d"),
    ("Salary", K.INCOME, "2b8a3e"),
    ("Business Income", K.INCOME, "37b24d"),
    ("Savings & Investments", K.SAVING, "1864ab"),
    ("Transfers", K.TRANSFER, "868e96"),
    ("Friends & Family", K.TRANSFER, "adb5bd"),
]

# Merchants are deliberately meaningless codes. Several appear with more than
# one trailing branch number, so a rule matching the stable prefix picks up
# every variant - which is the whole point of matching on a substring.

# merchant, category, rule pattern, rule source
MERCHANTS = [
    ("MERCHANT-01 4471", "Groceries", "MERCHANT-01", S.MANUAL),
    ("MERCHANT-02 8820", "Groceries", "MERCHANT-02", S.MANUAL),
    ("MERCHANT-03 1194", "Groceries", "MERCHANT-03", S.LLM),
    ("MERCHANT-04 6602", "Eating Out & Takeaway", "MERCHANT-04", S.LLM),
    ("MERCHANT-05 3317", "Eating Out & Takeaway", "MERCHANT-05", S.LLM),
    ("MERCHANT-06", "Eating Out & Takeaway", "MERCHANT-06", S.MANUAL),
    ("MERCHANT-07", "Transport", "MERCHANT-07", S.MANUAL),
    ("MERCHANT-08", "Transport", "MERCHANT-08", S.LLM),
    ("MERCHANT-09 5540", "Transport", "MERCHANT-09", S.LLM),
    ("MERCHANT-10", "Bills & Utilities", "MERCHANT-10", S.MANUAL),
    ("MERCHANT-11", "Bills & Utilities", "MERCHANT-11", S.MANUAL),
    ("MERCHANT-12", "Bills & Utilities", "MERCHANT-12", S.LLM),
    ("MERCHANT-13", "Subscriptions", "MERCHANT-13", S.LLM),
    ("MERCHANT-14", "Subscriptions", "MERCHANT-14", S.LLM),
    ("MERCHANT-15", "Subscriptions", "MERCHANT-15", S.MANUAL),
    ("MERCHANT-16", "Subscriptions", "MERCHANT-16", S.MANUAL),
    ("MERCHANT-17 2290", "Entertainment", "MERCHANT-17", S.LLM),
    ("MERCHANT-18", "Health & Fitness", "MERCHANT-18", S.MANUAL),
    ("MERCHANT-19 7738", "Health & Fitness", "MERCHANT-19", S.LLM),
    ("MERCHANT-20 A4K2", "Shopping", "MERCHANT-20", S.MANUAL),
    ("MERCHANT-21 9915", "Shopping", "MERCHANT-21", S.LLM),
    ("MERCHANT-22", "Shopping", "MERCHANT-22", S.LLM),
    ("MERCHANT-23", "Education", "MERCHANT-23", S.MANUAL),
    ("MERCHANT-24", "Rent or Mortgage", "MERCHANT-24", S.MANUAL),
    ("MERCHANT-25", "Salary", "MERCHANT-25", S.MANUAL),
    ("ACCOUNT-40128866", "Savings & Investments", "ACCOUNT-4012", S.MANUAL),
    ("PAYEE-A3", "Business Income", "PAYEE-A3", S.LLM),
    ("PAYEE-B7", "Business Income", "PAYEE-B7", S.LLM),
    ("PAYEE-C1", "Business Income", "PAYEE-C1", S.LLM),
    ("PAYEE-D9", "Friends & Family", "PAYEE-D9", S.MANUAL),
]

# merchant, category, amount, day of month
MONTHLY = [
    ("MERCHANT-24", "Rent or Mortgage", "-925.00", 1),
    ("MERCHANT-10", "Bills & Utilities", "-31.40", 3),
    ("MERCHANT-11", "Bills & Utilities", "-78.12", 5),
    ("MERCHANT-12", "Bills & Utilities", "-18.00", 7),
    ("MERCHANT-13", "Subscriptions", "-11.99", 9),
    ("MERCHANT-14", "Subscriptions", "-8.99", 11),
    ("MERCHANT-15", "Subscriptions", "-3.40", 13),
    ("MERCHANT-16", "Subscriptions", "-4.51", 14),
    ("MERCHANT-18", "Health & Fitness", "-24.99", 15),
    ("MERCHANT-25", "Salary", "1680.00", 28),
    ("ACCOUNT-40128866", "Savings & Investments", "-300.00", 28),
]

# merchant, category, amount range, roughly how many a month
OCCASIONAL = [
    ("MERCHANT-01 4471", "Groceries", 18, 62, 3),
    ("MERCHANT-01 9063", "Groceries", 12, 40, 1),
    ("MERCHANT-02 8820", "Groceries", 9, 34, 2),
    ("MERCHANT-03 1194", "Groceries", 4, 17, 3),
    ("MERCHANT-04 6602", "Eating Out & Takeaway", 14, 28, 1),
    ("MERCHANT-05 3317", "Eating Out & Takeaway", 3, 9, 4),
    ("MERCHANT-06", "Eating Out & Takeaway", 12, 34, 2),
    ("MERCHANT-07", "Transport", 2, 12, 6),
    ("MERCHANT-08", "Transport", 11, 48, 1),
    ("MERCHANT-09 5540", "Transport", 35, 62, 1),
    ("MERCHANT-17 2290", "Entertainment", 9, 22, 1),
    ("MERCHANT-19 7738", "Health & Fitness", 4, 19, 1),
    ("MERCHANT-20 A4K2", "Shopping", 6, 74, 2),
    ("MERCHANT-20 B1P8", "Shopping", 6, 40, 1),
    ("MERCHANT-21 9915", "Shopping", 15, 95, 1),
    ("MERCHANT-22", "Shopping", 22, 68, 1),
    ("MERCHANT-23", "Education", 29, 39, 1),
]

# Payments to and from people, in both directions.
PEOPLE = [
    ("PAYEE-A3", "Business Income", 30, 45, 3),
    ("PAYEE-B7", "Business Income", 30, 45, 2),
    ("PAYEE-C1", "Business Income", 60, 90, 1),
    ("PAYEE-D9", "Friends & Family", -45, -12, 1),
    ("PAYEE-D9", "Friends & Family", 12, 40, 1),
]

UNCATEGORISED = [
    ("04191000000021", "-0.01"),
    ("UNKNOWN-7X42", "-16.79"),
    ("UNKNOWN-2B19", "-4.85"),
]


class Command(BaseCommand):
    help = "Create a demo user with invented transactions, for screenshots and trying the app."

    def add_arguments(self, parser):
        parser.add_argument(
            "--months",
            type=int,
            default=4,
            help="How many months of history to generate. Defaults to 4.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the existing demo user first.",
        )

    def handle(self, *args, **options):
        random.seed(42)
        User = get_user_model()

        if options["reset"]:
            User.objects.filter(username=USERNAME).delete()
            self.stdout.write("Removed the previous demo user.")

        if User.objects.filter(username=USERNAME).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"User '{USERNAME}' already exists. Re-run with --reset to replace it."
                )
            )
            return

        with db_transaction.atomic():
            user = User.objects.create_user(username=USERNAME, password=PASSWORD)
            account = Account.objects.create(
                user=user,
                name="Everyday Current Account",
                institution="Barclays",
                sort_code="204415",
                account_number="70113928",
            )
            categories = {
                name: Category.objects.create(
                    user=user, name=name, kind=kind, colour=colour
                )
                for name, kind, colour in CATEGORIES
            }
            self._make_rules(categories)
            count = self._make_transactions(account, categories, options["months"])

        recategorise(user)
        self._correct_one_by_hand(user, categories)

        self.stdout.write(
            self.style.SUCCESS(
                f"Created '{USERNAME}' with {count} transactions across "
                f"{options['months']} months.\n"
                f"Log in as {USERNAME} / {PASSWORD}"
            )
        )

    def _correct_one_by_hand(self, user, categories):
        """Leave one transaction categorised manually, as a real user would."""
        Transaction.objects.filter(
            account__user=user, merchant="UNKNOWN-7X42"
        ).update(
            category=categories["Entertainment"],
            category_source=Transaction.CategorySource.MANUAL,
        )

    def _make_rules(self, categories):
        seen = set()
        for _, category, pattern, source in MERCHANTS:
            if pattern in seen:
                continue
            seen.add(pattern)
            CategoryRule.objects.create(
                pattern=pattern, category=categories[category], source=source
            )

    def _make_transactions(self, account, categories, months):
        today = datetime.date.today()
        start = (today.replace(day=1) - datetime.timedelta(days=31 * (months - 1))).replace(day=1)

        rows = []
        for offset in range(months):
            month = self._add_months(start, offset)
            rows.extend(self._month(month, today))

        created = []
        for date, merchant, category, amount, kind in rows:
            created.append(
                Transaction(
                    account=account,
                    category=categories[category] if category else None,
                    category_source=(
                        Transaction.CategorySource.RULE if category else ""
                    ),
                    merchant=merchant,
                    bank_reference=f"ON {date:%d %b} CPM".upper(),
                    description=f"{merchant} ON {date:%d %b} CPM".upper(),
                    transaction_type=kind,
                    amount=Decimal(amount),
                    posted_date=date,
                    fingerprint=hashlib.sha256(
                        f"{date}{merchant}{amount}{len(created)}".encode()
                    ).hexdigest(),
                )
            )

        Transaction.objects.bulk_create(created)
        return len(created)

    def _month(self, month, today):
        rows = []

        for merchant, category, amount, day in MONTHLY:
            date = self._clamp(month, day)
            if date > today:
                continue
            kind = (
                T.DIRECT_DEBIT
                if Decimal(amount) < 0
                else T.CREDIT
            )
            rows.append((date, merchant, category, amount, kind))

        for merchant, category, low, high, roughly in OCCASIONAL:
            for _ in range(max(1, random.randint(roughly - 1, roughly + 1))):
                date = self._clamp(month, random.randint(1, 28))
                if date > today:
                    continue
                amount = f"-{random.uniform(low, high):.2f}"
                rows.append((date, merchant, category, amount, T.CARD_PURCHASE))

        for merchant, category, low, high, roughly in PEOPLE:
            for _ in range(roughly):
                date = self._clamp(month, random.randint(1, 28))
                if date > today:
                    continue
                amount = f"{random.uniform(low, high):.2f}"
                rows.append((date, merchant, category, amount, T.TRANSFER))

        for merchant, amount in UNCATEGORISED:
            if month.month % 2 == 0:
                date = self._clamp(month, random.randint(1, 28))
                if date <= today:
                    rows.append((date, merchant, None, amount, T.CARD_PURCHASE))

        rows.sort(key=lambda row: row[0])
        return rows

    @staticmethod
    def _add_months(date, offset):
        month = date.month - 1 + offset
        return datetime.date(date.year + month // 12, month % 12 + 1, 1)

    @staticmethod
    def _clamp(month, day):
        last = 28
        return month.replace(day=min(day, last))
