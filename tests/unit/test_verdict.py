"""Unit tests for runner/verdict.py - pure logic, no API calls."""
from runner.verdict import compute_verdict

HEURISTICS_OK = [{"type": "contains", "value": "paris", "passed": True}]
JUDGE_PASS = {"score": 90, "verdict": "PASS", "reason": "ok"}
JUDGE_FAIL = {"score": 30, "verdict": "FAIL", "reason": "wrong"}
JUDGE_INCONCLUSIVE = {"score": None, "verdict": "INCONCLUSIVE", "reason": "No judge returned a result."}


def test_heuristic_failure_is_fail_even_if_judge_would_pass():
    result = compute_verdict(False, [{"type": "contains", "value": "x", "passed": False}], judge_result=JUDGE_PASS)
    assert result["verdict"] == "FAIL"
    assert result["reason"] == "Heuristic checks failed"


def test_judge_not_requested_passes_on_heuristics_and_says_so():
    result = compute_verdict(True, HEURISTICS_OK, judge_result=None)
    assert result["verdict"] == "PASS"
    assert "judge not run" in result["reason"]


def test_all_checks_pass():
    result = compute_verdict(True, HEURISTICS_OK, judge_result=JUDGE_PASS,
                             relevance={"score": 80}, hallucination={"score": 95})
    assert result["verdict"] == "PASS"
    assert result["reason"] == "All checks passed"


def test_judge_fail_is_fail():
    result = compute_verdict(True, HEURISTICS_OK, judge_result=JUDGE_FAIL)
    assert result["verdict"] == "FAIL"
    assert "LLM judge failed" in result["reason"]


def test_no_judge_answered_is_inconclusive_not_pass_or_fail():
    result = compute_verdict(True, HEURISTICS_OK, judge_result=JUDGE_INCONCLUSIVE,
                             relevance={"score": 80}, hallucination={"score": 95})
    assert result["verdict"] == "INCONCLUSIVE"


def test_scorer_failure_outranks_inconclusive_judge():
    """Low relevance is real evidence of a failure even when no judge answered."""
    result = compute_verdict(True, HEURISTICS_OK, judge_result=JUDGE_INCONCLUSIVE,
                             relevance={"score": 10}, hallucination={"score": 95})
    assert result["verdict"] == "FAIL"
    assert "Low relevance" in result["reason"]


def test_relevance_threshold_boundary():
    at = compute_verdict(True, HEURISTICS_OK, judge_result=JUDGE_PASS, relevance={"score": 40})
    below = compute_verdict(True, HEURISTICS_OK, judge_result=JUDGE_PASS, relevance={"score": 39.9})
    assert at["verdict"] == "PASS"
    assert below["verdict"] == "FAIL"


def test_hallucination_fails_only_below_30_percent_support():
    at = compute_verdict(True, HEURISTICS_OK, judge_result=JUDGE_PASS, hallucination={"score": 30})
    below = compute_verdict(True, HEURISTICS_OK, judge_result=JUDGE_PASS, hallucination={"score": 29})
    assert at["verdict"] == "PASS"
    assert below["verdict"] == "FAIL"
    assert "High hallucination" in below["reason"]


def test_judge_only_mode_ignores_relevance_and_hallucination():
    result = compute_verdict(True, HEURISTICS_OK, judge_result=JUDGE_PASS,
                             relevance={"score": 0}, hallucination={"score": 0},
                             scoring_mode="judge_only")
    assert result["verdict"] == "PASS"


def test_multiple_failures_are_all_reported():
    result = compute_verdict(True, HEURISTICS_OK, judge_result=JUDGE_FAIL,
                             relevance={"score": 10}, hallucination={"score": 5})
    assert result["verdict"] == "FAIL"
    for expected in ("Low relevance", "High hallucination", "LLM judge failed"):
        assert expected in result["reason"]
