"""Unit tests for runner/assertions.py."""
import pytest

from runner.assertions import run_assertions


@pytest.mark.parametrize("assertion,response,expected", [
    ({"type": "contains", "value": "Paris"}, "The capital is PARIS.", True),       # case-insensitive
    ({"type": "contains", "value": "Lyon"}, "The capital is Paris.", False),
    ({"type": "not_contains", "value": "sorry"}, "Here is the answer.", True),
    ({"type": "not_contains", "value": "Sorry"}, "sorry, I cannot.", False),
    ({"type": "max_length", "value": 5}, "12345", True),                           # boundary
    ({"type": "max_length", "value": 5}, "123456", False),
    ({"type": "min_length", "value": "3"}, "abc", True),                           # YAML may give a string
    ({"type": "min_length", "value": 3}, "ab", False),
])
def test_assertion_types(assertion, response, expected):
    assert run_assertions(response, [assertion])[0]["passed"] is expected


def test_unknown_assertion_type_fails_instead_of_passing_silently():
    assert run_assertions("anything", [{"type": "matches_regex", "value": ".*"}])[0]["passed"] is False


def test_no_assertions_gives_empty_result():
    assert run_assertions("anything", []) == []


def test_each_assertion_is_reported_separately():
    results = run_assertions("hello world", [
        {"type": "contains", "value": "hello"},
        {"type": "contains", "value": "missing"},
    ])
    assert [r["passed"] for r in results] == [True, False]
