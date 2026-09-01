from django.db import migrations


def forwards(apps, schema_editor):
    """Give every existing category an owner, and record how categories were set."""
    User = apps.get_model("accounts", "User")
    Category = apps.get_model("transactions", "Category")
    Transaction = apps.get_model("transactions", "Transaction")

    owner = User.objects.order_by("pk").first()
    if owner is None:
        # A fresh database has no users and no categories; nothing to backfill.
        return

    Category.objects.filter(user__isnull=True).update(user=owner)
    Transaction.objects.filter(category__isnull=False).update(category_source="RULE")
    Transaction.objects.filter(category__isnull=True).update(category_source="")


def backwards(apps, schema_editor):
    """Undo the backfill."""
    Category = apps.get_model("transactions", "Category")
    Transaction = apps.get_model("transactions", "Transaction")

    Category.objects.update(user=None)
    Transaction.objects.update(category_source="")


class Migration(migrations.Migration):
    dependencies = [
        ("transactions", "0004_add_category_user_and_source"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
