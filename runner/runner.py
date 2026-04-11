"""
runner.py — Layer 3 version
Orchestrates: load YAML → get response → heuristic assertions → LLM judge
"""

import os
import time
from unittest import suite
from runner.loader import load_suite
from runner.assertions import run_assertions
from runner.groq_model import get_response
from judge.llm_judge import judge_response
from memory.store import init_db, save_result


def run_suite(suite_path: str, use_judge: bool = True) -> list[dict]:
    """
    Run all test cases in a YAML suite.

    Args:
        suite_path: Path to YAML test suite file
        use_judge:  Enable LLM-as-judge scoring (Layer 3)

    Returns:
        List of result dicts, one per test case
    """
    suite = load_suite(suite_path)
    suite_name = os.path.basename(suite_path).replace(".yaml", "")
    init_db()
    results = []

    cases = suite if isinstance(suite, list) else suite.get("test_cases", [])
    for case in cases:
        result = _run_case(case, use_judge=use_judge)
        results.append(result)
        _print_result(result)
        save_result(suite_name, result)

    return results


def _run_case(case: dict, use_judge: bool) -> dict:
    test_id = case.get("id", "unknown")
    input_text = case.get("input", "")
    expected_behavior = case.get("expected_behavior", "")
    threshold = case.get("judge_threshold", 70)

    print(f"\n{'='*60}")
    print(f"TEST: {test_id}")
    print(f"INPUT: {input_text[:80]}...")

    # Step 1: Get model response
    t0 = time.time()
    response = get_response(input_text)
    latency_ms = int((time.time() - t0) * 1000)

    print(f"RESPONSE ({latency_ms}ms): {response[:120]}...")

    # Step 2: Heuristic assertions (Layer 2)
    assertions = case.get("assertions", [])
    heuristic_results = run_assertions(response, assertions)
    heuristic_pass = all(r["passed"] for r in heuristic_results)

    # Step 3: LLM-as-judge (Layer 3)
    judge_result = None
    if use_judge and expected_behavior:
        print(f"JUDGING against: '{expected_behavior}'")
        judge_result = judge_response(
            input_text=input_text,
            response=response,
            expected_behavior=expected_behavior,
            threshold=threshold,
        )
        print(f"JUDGE → score={judge_result['score']} | verdict={judge_result['verdict']}")
        print(f"REASON: {judge_result['reason']}")

    # Final verdict: both heuristic AND judge must pass
    final_verdict = _compute_verdict(heuristic_pass, judge_result)

    return {
        "id": test_id,
        "input": input_text,
        "response": response,
        "latency_ms": latency_ms,
        "heuristic_pass": heuristic_pass,
        "heuristic_results": heuristic_results,
        "judge": judge_result,
        "verdict": final_verdict,
    }


def _compute_verdict(heuristic_pass: bool, judge_result: dict | None) -> str:
    if not heuristic_pass:
        return "FAIL"
    if judge_result is None:
        return "PASS" if heuristic_pass else "FAIL"
    return judge_result["verdict"]


def _print_result(result: dict):
    verdict = result["verdict"]
    icon = "✅" if verdict == "PASS" else "❌"
    print(f"{icon} FINAL VERDICT: {verdict}")
