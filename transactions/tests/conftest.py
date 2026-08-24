from pathlib import Path

import pytest

from transactions.parsers.barclays import BarclaysCSVParser


@pytest.fixture
def sample_csv_path():
    return Path(__file__).parent.parent / "sample_data" / "barclays_sample.csv"


@pytest.fixture
def sample_bytes(sample_csv_path):
    with open(sample_csv_path, "rb") as f:
        return f.read()


@pytest.fixture
def parser():
    return BarclaysCSVParser()


@pytest.fixture
def parse_result(parser, sample_bytes):
    return parser.parse(sample_bytes)
