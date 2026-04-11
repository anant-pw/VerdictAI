"""
tests/test_eval.py — pytest wrapper for Sentinel Eval
Generates one pytest test per YAML test case.
Run: pytest tests/test_eval.py -v
"""

import os
import glob
import pytest
from runner.runner import run_suite


def _get_suites() -> list[str]:
    """Auto-discover all YAML suites in tests/suites/."""
    return glob.glob("tests/suites/*.yaml")


def _collect_cases() -> list[tuple[str, str]]:
    """Return list of (suite_path, test_id) for parametrize."""
    cases = []
    from runner.loader import load_suite
    for suite_path in _get_suites():
        suite = load_suite(suite_path)
        items = suite if isinstance(suite, list) else suite.get("test_cases", [])
        for case in items:
            cases.append((suite_path, case["id"]))
    return cases


# Cache results per suite to avoid re-running
_results_cache: dict[str, dict] = {}


def _get_result(suite_path: str, test_id: str) -> dict:
    if suite_path not in _results_cache:
        results = run_suite(suite_path, use_judge=True)
        _results_cache[suite_path] = {r["id"]: r for r in results}
    return _results_cache[suite_path].get(test_id, {})


@pytest.mark.parametrize("suite_path,test_id", _collect_cases())
def test_eval_case(suite_path: str, test_id: str):
    result = _get_result(suite_path, test_id)

    assert result, f"No result found for {test_id} in {suite_path}"

    score = result.get("judge", {}).get("score", "N/A") if result.get("judge") else "N/A"
    reason = result.get("judge", {}).get("reason", "") if result.get("judge") else ""

    assert result["verdict"] == "PASS", (
        f"\n  test_id : {test_id}"
        f"\n  suite   : {suite_path}"
        f"\n  score   : {score}"
        f"\n  reason  : {reason}"
        f"\n  response: {result.get('response', '')[:200]}"
    )