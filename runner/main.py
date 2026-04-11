"""
main.py — Sentinel Eval entry point (Layer 3)
Usage: python -m runner.main [--suite path/to/suite.yaml] [--no-judge]
"""

import argparse
import sys
from runner.runner import run_suite


def main():
    parser = argparse.ArgumentParser(description="Sentinel Eval — LLM Testing Framework")
    parser.add_argument(
        "--suite",
        default="tests/suites/hallucination.yaml",
        help="Path to YAML test suite",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip LLM-as-judge (heuristics only)",
    )
    args = parser.parse_args()

    print(f"\n🚀 Sentinel Eval — Running suite: {args.suite}")
    print(f"   LLM Judge: {'DISABLED' if args.no_judge else 'ENABLED (Groq llama3-8b)'}")

    results = run_suite(args.suite, use_judge=not args.no_judge)

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    failed = total - passed

    print(f"\n{'='*60}")
    print(f"SUMMARY: {passed}/{total} passed | {failed} failed")

    if failed > 0:
        print("FAILED TESTS:")
        for r in results:
            if r["verdict"] == "FAIL":
                judge_score = r["judge"]["score"] if r["judge"] else "N/A"
                print(f"  ❌ {r['id']} (judge_score={judge_score})")

    # Exit 1 if any failures (for CI gate)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
