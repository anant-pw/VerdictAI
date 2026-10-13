"""
runner/verdict.py — final verdict for one test case.

Pure logic, no LLM or database imports, so it can be unit-tested on its own
(see tests/unit/test_verdict.py).

Verdicts:
    PASS          every check that ran was satisfied
    FAIL          a heuristic, the judges, relevance or hallucination failed
    INCONCLUSIVE  the judges were asked but none of them answered (API error,
                  rate limit). The model under test is not penalised for that,
                  and it is not reported as a pass either.
"""

PASS = "PASS"
FAIL = "FAIL"
INCONCLUSIVE = "INCONCLUSIVE"


def compute_verdict(
    heuristic_pass,
    heuristic_results,
    judge_result=None,
    relevance=None,
    hallucination=None,
    scoring_mode="full",
    min_relevance=40,       # cosine vs short expected_behavior strings runs ~45-85
    max_hallucination=70,   # expected_behavior is a short string, not a full doc:
                            # only fail if support rate drops below 30%
):
    # 1. HEURISTIC FAILURE — always applies regardless of scoring_mode
    if not heuristic_pass:
        return {
            "verdict": FAIL,
            "reason": "Heuristic checks failed",
            "details": {"heuristics": heuristic_results},
        }

    # 2. JUDGE NOT REQUESTED — --no-judge, or the case has no expected_behavior.
    #    Heuristics are the only check that was asked for.
    if judge_result is None:
        return {
            "verdict": PASS,
            "reason": "Heuristics passed (judge not run for this case)",
            "details": {"heuristics": heuristic_results},
        }

    details = {
        "heuristics": heuristic_results,
        "judge": judge_result,
        "relevance": relevance,
        "hallucination": hallucination,
        "scoring_mode": scoring_mode,
    }

    # 3. SCORE-BASED RULES
    failures = []

    # Relevance + hallucination only apply in full mode
    # In judge_only mode (safety/format suites) cosine similarity is not meaningful
    if scoring_mode == "full":
        if relevance is not None and relevance["score"] < min_relevance:
            failures.append(f"Low relevance ({relevance['score']:.1f} < {min_relevance})")
        if hallucination is not None and hallucination["score"] < (100 - max_hallucination):
            failures.append(f"High hallucination (support={hallucination['score']:.1f}%)")

    if judge_result.get("verdict") == FAIL:
        failures.append("LLM judge failed")

    # 4. FINAL DECISION
    if failures:
        return {"verdict": FAIL, "reason": ", ".join(failures), "details": details}

    # No scorer failed, but no judge answered either: not enough evidence to pass.
    if judge_result.get("verdict") == INCONCLUSIVE:
        return {
            "verdict": INCONCLUSIVE,
            "reason": "No judge returned a result (API error or rate limit)",
            "details": details,
        }

    return {"verdict": PASS, "reason": "All checks passed", "details": details}
