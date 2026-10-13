"""Unit tests for judge/consensus.py - pure logic, no API calls."""
from judge.consensus import combine_judges, is_valid


def judge(name, score, reason="fine"):
    return {"judge": name, "score": score, "verdict": "PASS" if score >= 70 else "FAIL",
            "reason": reason, "raw": f"raw-{name}"}


def errored(name):
    return {"judge": name, "score": 0, "verdict": "FAIL", "reason": "Judge error: 429 rate limit", "raw": ""}


NOT_CONFIGURED = {"judge": "none", "score": 0, "verdict": "FAIL",
                  "reason": "No second judge configured", "raw": ""}


def test_two_judges_are_averaged():
    result = combine_judges([judge("groq", 90), judge("cerebras", 80), None])
    assert result["score"] == 85
    assert result["verdict"] == "PASS"
    assert result["judges_used"] == 2
    assert result["disagreement"] is False


def test_average_below_threshold_fails():
    result = combine_judges([judge("groq", 75), judge("cerebras", 55), None], threshold=70)
    assert result["score"] == 65
    assert result["verdict"] == "FAIL"


def test_disagreement_flag_uses_the_gap_threshold():
    assert combine_judges([judge("groq", 90), judge("cerebras", 70), None])["disagreement"] is False  # gap 20
    assert combine_judges([judge("groq", 90), judge("cerebras", 69), None])["disagreement"] is True   # gap 21


def test_one_errored_judge_leaves_the_other_score_untouched():
    result = combine_judges([judge("groq", 90), errored("cerebras"), None])
    assert result["score"] == 90
    assert result["judges_used"] == 1
    # an errored judge has a placeholder score of 0, which must not count as disagreement
    assert result["disagreement"] is False


def test_missing_second_judge_does_not_halve_the_score():
    result = combine_judges([judge("groq", 90), NOT_CONFIGURED, None])
    assert result["score"] == 90
    assert result["verdict"] == "PASS"
    assert result["judges_used"] == 1


def test_no_judge_answered_is_inconclusive_with_no_score():
    result = combine_judges([errored("groq"), errored("cerebras"), None])
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["score"] is None
    assert result["judges_used"] == 0
    assert "429" in result["reason"]


def test_is_valid():
    assert is_valid(judge("groq", 50))
    assert not is_valid(errored("groq"))
    assert not is_valid(NOT_CONFIGURED)
    assert not is_valid(None)
