from django.db import migrations


KINDS = {
    "INCOME": ["Salary", "Business Income", "Other Income"],
    "SAVING": ["Savings & Investments"],
    "TRANSFER": ["Transfers", "Friends & Family"],
}


def forwards(apps, schema_editor):
    """Mark the categories that must not count as spending."""
    Category = apps.get_model("transactions", "Category")

    for kind, names in KINDS.items():
        Category.objects.filter(name__in=names).update(kind=kind)


def backwards(apps, schema_editor):
    """Undo the backfill."""
    Category = apps.get_model("transactions", "Category")

    Category.objects.update(kind="SPEND")


class Migration(migrations.Migration):
    dependencies = [
        ("transactions", "0008_category_kind"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
