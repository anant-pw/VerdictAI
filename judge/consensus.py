"""
judge/consensus.py — combine individual judge results into one result.

Pure logic, no LLM imports, so it can be unit-tested on its own
(see tests/unit/test_consensus.py). judge/multi_judge.py calls the judges
and hands their results to combine_judges().
"""

ERROR_PREFIX = "Judge error:"
NOT_CONFIGURED = "No second judge configured"


def is_valid(result: dict | None) -> bool:
    """A judge result counts only if the judge actually answered."""
    if result is None:
        return False
    reason = str(result.get("reason", ""))
    return not reason.startswith(ERROR_PREFIX) and reason != NOT_CONFIGURED


def combine_judges(
    results: list[dict | None],
    threshold: int = 70,
    disagreement_threshold: int = 20,
) -> dict:
    """
    Average the scores of the judges that answered.

    Returns:
        {
            "score":        int | None  (None when no judge answered),
            "verdict":      "PASS" | "FAIL" | "INCONCLUSIVE",
            "reason":       str,
            "disagreement": bool  (only ever True when two judges answered),
            "judges_used":  int,
            "raw":          str,
        }
    """
    valid = [r for r in results if is_valid(r)]

    if not valid:
        errors = " | ".join(
            f"{r.get('judge', 'judge')}: {r.get('reason', '')}" for r in results if r is not None
        )
        return {
            "score":        None,
            "verdict":      "INCONCLUSIVE",
            "reason":       f"No judge returned a result. {errors}".strip(),
            "disagreement": False,
            "judges_used":  0,
            "raw":          "",
        }

    avg_score = int(sum(r["score"] for r in valid) / len(valid))

    scores = [r["score"] for r in valid]
    score_gap = max(scores) - min(scores)

    return {
        "score":        avg_score,
        "verdict":      "PASS" if avg_score >= threshold else "FAIL",
        "reason":       " | ".join(f"{r['judge'].capitalize()}: {r['reason']}" for r in valid),
        "disagreement": len(valid) > 1 and score_gap > disagreement_threshold,
        "score_gap":    score_gap,
        "judges_used":  len(valid),
        "raw":          " | ".join(f"{r['judge']}={r['raw']}" for r in valid),
    }
