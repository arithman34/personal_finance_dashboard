from django.conf import settings
from django.db import models


class Account(models.Model):
    name = models.CharField(max_length=100)
    institution = models.CharField(max_length=100)
    sort_code = models.CharField(max_length=6, null=True, blank=True)
    account_number = models.CharField(max_length=8, null=True, blank=True)
    currency = models.CharField(max_length=3, default="GBP")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="accounts"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"], name="unique_account_name_per_user"
            ),
            models.UniqueConstraint(
                fields=["user", "sort_code", "account_number"],
                name="unique_bank_account_per_user",
            ),
        ]

    def __str__(self):
        return self.name


class Transaction(models.Model):
    class TransactionType(models.TextChoices):
        CASH_WITHDRAWAL = "CASH_WITHDRAWAL", "Cash Withdrawal"
        STANDING_ORDER = "STANDING_ORDER", "Standing Order"
        DEBIT = "DEBIT", "Debit"
        CREDIT = "CREDIT", "Credit"
        CARD_PURCHASE = "CARD_PURCHASE", "Card Purchase"
        DIRECT_DEBIT = "DIRECT_DEBIT", "Direct Debit"
        TRANSFER = "TRANSFER", "Transfer"
        OTHER = "OTHER", "Other"

    account = models.ForeignKey(
        "Account", on_delete=models.CASCADE, related_name="transactions"
    )
    statement_upload = models.ForeignKey(
        "StatementUpload",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    merchant = models.CharField(max_length=100, blank=True)
    bank_reference = models.CharField(max_length=100, blank=True)
    transaction_type = models.CharField(
        max_length=50, choices=TransactionType.choices, default=TransactionType.OTHER
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    posted_date = models.DateField()
    transaction_date = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=255)
    fingerprint = models.CharField(max_length=64)
    external_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-posted_date", "-id"]
        indexes = [
            models.Index(fields=["account", "posted_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "fingerprint"],
                name="unique_transaction_fingerprint",
            ),
            models.UniqueConstraint(
                fields=["account", "external_id"],
                name="unique_transaction_external_id",
            ),
        ]

    @property
    def effective_date(self):
        """The date a human means: when it happened, else when it posted."""
        return self.transaction_date or self.posted_date

    def __str__(self):
        return f"{self.posted_date} - {self.description} ({self.amount})"


class StatementUpload(models.Model):
    class StatusType(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSED = "PROCESSED", "Processed"
        FAILED = "FAILED", "Failed"

    account = models.ForeignKey(
        "Account",
        on_delete=models.CASCADE,
        related_name="statement_uploads",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="statement_uploads",
    )
    status = models.CharField(
        max_length=20, default=StatusType.PENDING, choices=StatusType.choices
    )
    rows = models.IntegerField(null=True, blank=True)
    file = models.FileField(upload_to="statements/")
    error_message = models.TextField(blank=True)
    parser = models.CharField(max_length=100, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["account", "uploaded_at"]),
        ]

    def __str__(self):
        return f"{self.rows} rows - {self.status} - {self.uploaded_at}"
