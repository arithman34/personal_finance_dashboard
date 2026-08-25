from django import forms

from .models import Account, StatementUpload


class StatementUploadForm(forms.ModelForm):
    class Meta:
        model = StatementUpload
        fields = ["account", "file"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = Account.objects.filter(user=user)

    def clean_file(self):
        file = self.cleaned_data.get("file")

        if not file:
            raise forms.ValidationError("No file uploaded.")

        if not file.name.endswith(".csv"):
            raise forms.ValidationError("Only CSV files are supported.")

        return file
