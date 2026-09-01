from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from transactions.categoriser import recategorise


class Command(BaseCommand):
    help = "Re-apply category rules to a user's transactions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            help="Only this user. Defaults to every user.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Also overwrite categories that were set by hand.",
        )

    def handle(self, *args, **options):
        users = get_user_model().objects.all()
        if options["username"]:
            users = users.filter(username=options["username"])

        if not users.exists():
            self.stdout.write(self.style.WARNING("No matching users."))
            return

        for user in users:
            scanned, changed = recategorise(user, force=options["force"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"{user}: updated {changed} of {scanned} transactions."
                )
            )
