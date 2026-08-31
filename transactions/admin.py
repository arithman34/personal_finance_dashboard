from django.contrib import admin

from .models import Account, Category, CategoryRule, StatementUpload, Transaction


class TransactionAdmin(admin.ModelAdmin):
    list_display = ("posted_date", "description", "amount", "account", "merchant", "category")
    list_filter = ("posted_date", "account", "transaction_type", "category")
    search_fields = ("description", "merchant")
    readonly_fields = ("fingerprint", "created_at")
    list_select_related = ("account", "category")


class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "colour")


class CategoryRuleAdmin(admin.ModelAdmin):
    list_display = ("pattern", "category", "priority", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("pattern",)
    list_select_related = ("category",)
    list_editable = ("priority", "is_active")


admin.site.register(Account)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(StatementUpload)
admin.site.register(Category, CategoryAdmin)
admin.site.register(CategoryRule, CategoryRuleAdmin)
