"""
memory/regression.py — VerdictAI Regression Eval
Compares current score vs last run for same test_id.
Flags if score dropped > threshold (default 10 points).
"""


def evaluate_regression(prev_score, current_score: int, drop_threshold: int = 10) -> dict:
    """Pure comparison of the previous score with the current one.
    prev_score is None when the case has no earlier scored run."""
    if prev_score is None:
        return {
            "regressed": False,
            "prev_score": None,
            "drop": None,
            "message": "No previous run to compare.",
        }

    drop = prev_score - current_score
    if drop > drop_threshold:
        return {
            "regressed": True,
            "prev_score": prev_score,
            "drop": drop,
            "message": f"⚠️  Regression: score dropped {drop} pts ({prev_score} → {current_score})",
        }
    return {
        "regressed": False,
        "prev_score": prev_score,
        "drop": drop,
        "message": f"✅ No regression ({prev_score} → {current_score})",
    }


def check_regression(test_id: str, current_score: int, drop_threshold: int = 10) -> dict:
    """Compare current_score with the most recent stored score for test_id.
    Call this BEFORE saving the current result."""
    from memory.store import get_history
    history = get_history(test_id, limit=1)
    prev_score = history[0].get("score") if history else None
    return evaluate_regression(prev_score, current_score, drop_threshold)
