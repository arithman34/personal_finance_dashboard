from django import forms

from .models import Account, StatementUpload, Category, CategoryRule


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


class CategoriseForm(forms.Form):
    """One decision about one merchant."""

    merchant = forms.CharField(widget=forms.HiddenInput)
    pattern = forms.CharField(
        required=False,
        help_text="Shorten to match variants. Defaults to the whole merchant.",
    )
    category = forms.ModelChoiceField(queryset=Category.objects.none())

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(user=user)

    def clean_pattern(self):
        """Fall back to the merchant when no pattern was typed."""
        return self.cleaned_data.get("pattern", "").strip()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("pattern"):
            cleaned["pattern"] = cleaned.get("merchant", "").strip()
        return cleaned


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "colour"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.user = user

    def validate_constraints(self):
        exclude = self._get_validation_exclusions()
        exclude.discard("user")
        try:
            self.instance.validate_constraints(exclude=exclude)
        except forms.ValidationError as e:
            self._update_errors(e)
