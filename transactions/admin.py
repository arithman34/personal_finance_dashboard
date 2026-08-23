from django.contrib import admin

from .models import Account, StatementUpload, Transaction


class TransactionAdmin(admin.ModelAdmin):
    list_display = ("posted_date", "description", "amount", "account", "merchant")
    list_filter = ("posted_date", "account", "transaction_type")
    search_fields = ("description", "merchant")
    readonly_fields = ("fingerprint", "created_at")


admin.site.register(Account)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(StatementUpload)
