"""Unit tests for the pure comparison in memory/regression.py."""
from memory.regression import evaluate_regression


def test_no_previous_run():
    result = evaluate_regression(None, 80)
    assert result["regressed"] is False
    assert result["prev_score"] is None


def test_drop_larger_than_threshold_is_a_regression():
    result = evaluate_regression(90, 79)
    assert result["regressed"] is True
    assert result["drop"] == 11


def test_drop_equal_to_threshold_is_not_a_regression():
    assert evaluate_regression(90, 80)["regressed"] is False


def test_improvement_is_not_a_regression():
    result = evaluate_regression(60, 95)
    assert result["regressed"] is False
    assert result["drop"] == -35
