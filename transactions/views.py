from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from .forms import StatementUploadForm
from .importer import StatementImportError, import_statement
from .models import Transaction
from .stats import totals, monthly_totals, top_merchants, totals_by_type


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
    }
    return render(request, "transactions/dashboard.html", context)
