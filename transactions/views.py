from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models.query import QuerySet
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.list import ListView

from .categoriser import recategorise, uncategorised_merchants
from .forms import StatementUploadForm, CategoriseForm, CategoryForm
from .importer import StatementImportError, import_statement
from .models import Category, CategoryRule, Transaction
from .stats import (totals, monthly_totals, top_merchants, totals_by_type,
                    totals_by_category)


class CategoryMixin(LoginRequiredMixin):
    model = Category
    success_url = reverse_lazy("transactions:category_list")

    def get_queryset(self) -> QuerySet[Category]:
        return Category.objects.filter(user=self.request.user)


class CategoryFormMixin(CategoryMixin):
    form_class = CategoryForm

    def get_form_kwargs(self) -> dict[str, Any]:
        return super().get_form_kwargs() | {"user": self.request.user}


class CategoryListView(CategoryMixin, ListView):
    pass


class CategoryCreateView(CategoryFormMixin, CreateView):
    pass


class CategoryUpdateView(CategoryFormMixin, UpdateView):
    pass


class CategoryDeleteView(CategoryMixin, DeleteView):
    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["rule_count"] = self.object.rules.count()
        context["transaction_count"] = self.object.transactions.count()
        return context


@login_required
def statement_upload(request):
    if request.method == "POST":
        form = StatementUploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            upload = form.save(commit=False)
            upload.user = request.user
            upload.save()
            try:
                result = import_statement(upload)
                messages.success(
                    request,
                    f"Imported {result.created} of {result.parsed} transactions.",
                )
            except StatementImportError as e:
                messages.error(request, str(e))
            return redirect("transactions:upload")
    else:
        form = StatementUploadForm(user=request.user)

    return render(request, "transactions/upload.html", {"form": form})


@login_required
def transaction_list(request):
    transactions = Transaction.objects.filter(account__user=request.user).select_related("account")
    paginator = Paginator(transactions, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "transactions/transaction_list.html", {"page_obj": page_obj})


@login_required
def dashboard(request):
    transactions = Transaction.objects.filter(account__user=request.user)
    context = {
        "totals": totals(transactions),
        "monthly_totals": monthly_totals(transactions),
        "top_merchants": top_merchants(transactions),
        "totals_by_type": totals_by_type(transactions),
        "totals_by_category": totals_by_category(transactions),
    }
    return render(request, "transactions/dashboard.html", context)


@login_required
def categorise(request):
    transactions = Transaction.objects.filter(account__user=request.user)

    if request.method == "POST":
        form = CategoriseForm(request.POST, user=request.user)

        if form.is_valid():
            merchant = form.cleaned_data["merchant"]
            category = form.cleaned_data["category"]
            pattern = form.cleaned_data["pattern"]
            action = request.POST.get("action")

            if action == "rule":
                CategoryRule.objects.get_or_create(
                    pattern=pattern, category=category
                )
                _, changed = recategorise(request.user)
                messages.success(
                    request,
                    f"Rule '{pattern}' -> {category}. "
                    f"{changed} transactions recategorised.",
                )
            elif action == "assign":
                updated = transactions.filter(
                    merchant=merchant, category__isnull=True
                ).update(
                    category=category,
                    category_source=Transaction.CategorySource.MANUAL,
                )
                messages.success(
                    request, f"{updated} '{merchant}' transactions set to {category}."
                )
            else:
                messages.error(request, "Unknown action.")
        else:
            messages.error(request, "Could not categorise that merchant.")

        return redirect("transactions:categorise")

    rows = [
        {
            **merchant,
            "form": CategoriseForm(
                user=request.user,
                initial={
                    "merchant": merchant["merchant"],
                    "pattern": merchant["merchant"],
                },
            ),
        }
        for merchant in uncategorised_merchants(transactions)
    ]

    return render(
        request,
        "transactions/categorise.html",
        {"rows": rows, "category_count": Category.objects.filter(user=request.user).count()},
    )
