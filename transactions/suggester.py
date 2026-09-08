import json
from dataclasses import dataclass

from django.conf import settings
from openai import OpenAI

from .categoriser import uncategorised_merchants
from .models import Category, Transaction


_MODEL = "gpt-5.6-luna"
_MAX_MERCHANTS = 100


class SuggestionError(Exception):
    """Raised when there is a suggestion error."""


@dataclass(frozen=True)
class Suggestion:
    merchant: str
    pattern: str
    category: Category


def _build_schema(category_names: list[str]) -> dict:
    return {
        "type": "json_schema",
        "name": "rule_suggestions",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "merchant": {"type": "string"},
                            "pattern": {"type": "string"},
                            "category": {"type": "string", "enum": category_names},
                        },
                        "required": ["merchant", "pattern", "category"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["suggestions"],
            "additionalProperties": False,
        },
    }


def _build_prompt(merchants: list[str], category_names: list[str]) -> str:
    return (
        "Propose one rule per merchant below, mapping it to one of the categories.\n"
        "The category must be copied exactly from the category list.\n"
        "The pattern is the shortest substring that identifies the merchant, and it "
        "must appear inside the merchant string exactly as written there.\n\n"
        "Merchants:\n"
        + "\n".join(merchants)
        + "\n\nCategories:\n"
        + "\n".join(category_names)
    )


def _parse_response(payload: dict, categories: dict[str, Category]) -> list[Suggestion]:
    suggestions = []

    for item in payload.get("suggestions", []):
        merchant = item.get("merchant", "").strip()
        pattern = item.get("pattern", "").strip()
        category = categories.get(item.get("category", ""))

        if not merchant or not pattern or category is None:
            continue

        if pattern.lower() not in merchant.lower():
            continue

        suggestions.append(
            Suggestion(merchant=merchant, pattern=pattern, category=category)
        )

    return suggestions


def suggest_rules(user) -> list[Suggestion]:
    categories = {c.name: c for c in Category.objects.filter(user=user)}
    if not categories:
        return []

    rows = uncategorised_merchants(Transaction.objects.filter(account__user=user))
    merchants = [row["merchant"] for row in rows[:_MAX_MERCHANTS]]
    if not merchants:
        return []

    if not settings.OPENAI_API_KEY:
        raise SuggestionError("OPENAI_API_KEY not set in environment variables.")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        response = client.responses.create(
            model=_MODEL,
            input=_build_prompt(merchants, list(categories)),
            text={"format": _build_schema(list(categories))},
        )
    except Exception as e:
        raise SuggestionError(f"Could not fetch suggestions: {e}") from e

    return _parse_response(json.loads(response.output_text), categories)
