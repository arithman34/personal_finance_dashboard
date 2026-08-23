import csv

from .barclays import BarclaysCSVParser
from .base import BaseStatementParser, UnknownStatementFormatError

PARSERS: list[type[BaseStatementParser]] = [
    BarclaysCSVParser,
]


def _decode(data: bytes) -> str:
    """Decode far enough to read the header row."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def read_header(data: bytes) -> tuple[str, ...]:
    """Return the file's first row as a tuple of stripped column names."""
    lines = _decode(data).splitlines()
    if not lines:
        raise UnknownStatementFormatError("File is empty.")

    fields = next(csv.reader([lines[0]]))
    return tuple(field.strip() for field in fields)


def get_parser(data: bytes) -> BaseStatementParser:
    """Return a parser instance able to read ``data``"""
    header = read_header(data)
    for parser_class in PARSERS:
        if parser_class.can_parse(header):
            return parser_class()

    raise UnknownStatementFormatError(f"No registered parser matches header: {header}")
