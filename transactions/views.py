from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import StatementUploadForm
from .importer import StatementImportError, import_statement


@login_required
def upload(request):
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
