from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


class CustomUserAdmin(UserAdmin):
    list_select_related = ("accounts",)


admin.site.register(User, CustomUserAdmin)
