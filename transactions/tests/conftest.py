from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from accounts.models import User
from transactions.models import Account, StatementUpload
from transactions.parsers.barclays import BarclaysCSVParser


@pytest.fixture(autouse=True)
def isolated_media(settings, tmp_path):
    """Write uploads to a temp directory instead of the project's media/."""
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def make_user():
    """Return a factory that creates a new User."""
    def _make(username: str = "test", password: str = "test-pass-123") -> User:
        return User.objects.create_user(username=username, password=password)

    return _make


@pytest.fixture
def make_account(make_user):
    """Return a factory that creates a new Account."""
    def _make(user=None, name: str = "Current Account", institution: str = "Barclays", sort_code: str = "112233", account_number: str = "12345678"):
        if user is None:
            user = make_user()

        return Account.objects.create(
            user=user,
            name=name,
            institution=institution,
            sort_code=sort_code,
            account_number=account_number,
        )

    return _make


@pytest.fixture
def user(make_user) -> User:
    """A single user."""
    return make_user()


@pytest.fixture
def account(make_account, user) -> Account:
    """A single account belonging to the `user` fixture."""
    return make_account(user=user)


@pytest.fixture
def make_upload():
    """Return a factory that saves `data` as a StatementUpload for `account`."""

    def _make(account: Account, data: bytes, filename: str = "statement.csv") -> StatementUpload:
        upload = StatementUpload(account=account, user=account.user)
        upload.file.save(filename, ContentFile(data), save=True)
        return upload

    return _make


@pytest.fixture
def sample_csv_path():
    return Path(__file__).parent.parent / "sample_data" / "barclays_sample.csv"


@pytest.fixture
def sample_bytes(sample_csv_path: Path) -> bytes:
    with open(sample_csv_path, "rb") as f:
        return f.read()


@pytest.fixture
def parser():
    return BarclaysCSVParser()


@pytest.fixture
def parse_result(parser, sample_bytes):
    return parser.parse(sample_bytes)
