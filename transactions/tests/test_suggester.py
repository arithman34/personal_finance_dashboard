import json
from types import SimpleNamespace

import pytest

from transactions import suggester
from transactions.suggester import (Suggestion, SuggestionError, _build_prompt,
                                    _build_schema, _parse_response,
                                    suggest_rules)

pytestmark = pytest.mark.django_db


def fake_openai(output_text="{}", error=None):
    """A stand-in for the OpenAI client that records what it was asked."""
    calls = []

    class Responses:
        def create(self, **kwargs):
            calls.append(kwargs)
            if error is not None:
                raise error
            return SimpleNamespace(output_text=output_text)

    class Client:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.responses = Responses()

    return Client, calls


@pytest.fixture
def categories(make_category):
    """The two categories a suggestion is allowed to name."""
    return {
        "Groceries": make_category(name="Groceries"),
        "Eating Out": make_category(name="Eating Out"),
    }


@pytest.fixture
def uncategorised(make_transaction):
    make_transaction(amount="-30.00", merchant="TESCO STORES 3298")
    make_transaction(amount="-25.00", merchant="NANDOS 441")


# The schema is what stops the model inventing a category, so its shape matters
# more than anything else here. Strict mode rejects a schema that breaks any of
# the rules below, which would take the whole feature down.


def test_the_schema_asks_for_strict_mode():
    assert _build_schema(["Groceries"])["strict"] is True


def test_the_root_of_the_schema_is_an_object():
    """Strict mode will not accept a bare array at the top level."""
    schema = _build_schema(["Groceries"])["schema"]

    assert schema["type"] == "object"
    assert "suggestions" in schema["properties"]


def test_nothing_beyond_the_named_properties_is_allowed():
    schema = _build_schema(["Groceries"])["schema"]
    item = schema["properties"]["suggestions"]["items"]

    assert schema["additionalProperties"] is False
    assert item["additionalProperties"] is False


def test_every_property_is_required():
    """Strict mode demands that required lists every property."""
    item = _build_schema(["Groceries"])["schema"]["properties"]["suggestions"]["items"]

    assert sorted(item["required"]) == sorted(item["properties"])


def test_the_category_is_limited_to_the_names_given():
    """This is what makes an invented category impossible rather than unlikely."""
    item = _build_schema(["Groceries", "Rent"])["schema"]["properties"]["suggestions"][
        "items"
    ]

    assert item["properties"]["category"]["enum"] == ["Groceries", "Rent"]


def test_the_schema_can_be_sent_as_json():
    assert json.loads(json.dumps(_build_schema(["Groceries"])))


def test_the_prompt_lists_the_merchants_and_the_categories():
    prompt = _build_prompt(["TESCO STORES 3298"], ["Groceries"])

    assert "TESCO STORES 3298" in prompt
    assert "Groceries" in prompt


def test_a_usable_suggestion_comes_back_resolved(categories):
    """The category is returned as a real object, not the name the model sent."""
    payload = {
        "suggestions": [
            {"merchant": "TESCO STORES 3298", "pattern": "TESCO", "category": "Groceries"}
        ]
    }

    assert _parse_response(payload, categories) == [
        Suggestion(
            merchant="TESCO STORES 3298",
            pattern="TESCO",
            category=categories["Groceries"],
        )
    ]


def test_a_category_that_does_not_exist_is_dropped(categories):
    """The enum should prevent this, but the response is still not trusted."""
    payload = {
        "suggestions": [
            {"merchant": "NANDOS 441", "pattern": "NANDOS", "category": "Takeaway"}
        ]
    }

    assert _parse_response(payload, categories) == []


def test_a_blank_pattern_is_dropped(categories):
    """An empty pattern would match every merchant there is."""
    payload = {
        "suggestions": [
            {"merchant": "TESCO STORES 3298", "pattern": "   ", "category": "Groceries"}
        ]
    }

    assert _parse_response(payload, categories) == []


def test_a_pattern_that_is_not_in_its_merchant_is_dropped(categories):
    """Matching is a substring test, so this rule could never fire."""
    payload = {
        "suggestions": [
            {
                "merchant": "AMAZON MKTP",
                "pattern": "Amazon.co.uk",
                "category": "Groceries",
            }
        ]
    }

    assert _parse_response(payload, categories) == []


def test_a_pattern_may_differ_in_case(categories):
    payload = {
        "suggestions": [
            {"merchant": "NANDOS 441", "pattern": "nandos", "category": "Eating Out"}
        ]
    }

    assert len(_parse_response(payload, categories)) == 1


def test_surrounding_whitespace_is_trimmed(categories):
    payload = {
        "suggestions": [
            {
                "merchant": "TESCO STORES 3298",
                "pattern": "  TESCO  ",
                "category": "Groceries",
            }
        ]
    }

    assert _parse_response(payload, categories)[0].pattern == "TESCO"


def test_a_response_with_nothing_in_it_is_not_an_error(categories):
    assert _parse_response({}, categories) == []


def test_no_categories_means_nothing_to_suggest(user, uncategorised):
    """With no categories the enum would be empty, so there is nothing to ask."""
    assert suggest_rules(user) == []


def test_nothing_uncategorised_means_nothing_to_suggest(user, categories):
    assert suggest_rules(user) == []


def test_a_missing_api_key_is_reported(user, categories, uncategorised, settings):
    settings.OPENAI_API_KEY = ""

    with pytest.raises(SuggestionError):
        suggest_rules(user)


def test_a_failing_request_becomes_a_suggestion_error(
    user, categories, uncategorised, settings, monkeypatch
):
    """Callers should handle one exception type, not the SDK's hierarchy."""
    settings.OPENAI_API_KEY = "test-key"
    client, _ = fake_openai(error=RuntimeError("upstream is down"))
    monkeypatch.setattr(suggester, "OpenAI", client)

    with pytest.raises(SuggestionError, match="Could not fetch suggestions"):
        suggest_rules(user)


def test_the_request_carries_the_schema_and_the_merchants(
    user, categories, uncategorised, settings, monkeypatch
):
    settings.OPENAI_API_KEY = "test-key"
    client, calls = fake_openai(output_text=json.dumps({"suggestions": []}))
    monkeypatch.setattr(suggester, "OpenAI", client)

    suggest_rules(user)

    sent = calls[0]
    schema = sent["text"]["format"]["schema"]
    enum = schema["properties"]["suggestions"]["items"]["properties"]["category"]["enum"]

    assert sorted(enum) == ["Eating Out", "Groceries"]
    assert "TESCO STORES 3298" in sent["input"]
    assert "NANDOS 441" in sent["input"]


def test_suggestions_are_returned_as_objects(
    user, categories, uncategorised, settings, monkeypatch
):
    settings.OPENAI_API_KEY = "test-key"
    client, _ = fake_openai(
        output_text=json.dumps(
            {
                "suggestions": [
                    {
                        "merchant": "TESCO STORES 3298",
                        "pattern": "TESCO",
                        "category": "Groceries",
                    },
                    {
                        "merchant": "NANDOS 441",
                        "pattern": "WRONG",
                        "category": "Eating Out",
                    },
                ]
            }
        )
    )
    monkeypatch.setattr(suggester, "OpenAI", client)

    suggestions = suggest_rules(user)

    assert [s.merchant for s in suggestions] == ["TESCO STORES 3298"]
    assert suggestions[0].category == categories["Groceries"]
