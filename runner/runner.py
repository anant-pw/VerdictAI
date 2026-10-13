"""
runner.py — Layer 3 version

Orchestrates:
- load YAML suite
- get model response
- run heuristic assertions
- run LLM-as-judge
- check regression
- persist results
"""

from __future__ import annotations

import os
import time

from runner.loader import load_suite
from runner.assertions import run_assertions
from runner.groq_model import get_response
from runner.retry_utils import inter_case_sleep
from judge.llm_judge import judge_response
from memory.regression import evaluate_regression
from memory.store import init_db, save_result, get_history
from runner.verdict import compute_verdict as _compute_verdict
from memory.self_heal import check_and_heal
from judge.multi_judge import multi_judge_response
from runner.logger import eval_logger
from database.models import DatabaseManager
from reports.allure_writer import AllureWriter
from judge.relevance_scorer import get_relevance_score
from judge.hallucination_detector import detect_hallucination

def run_suite(suite_path: str, use_judge: bool = True) -> list[dict]:
    suite = load_suite(suite_path)
    suite_name = os.path.basename(suite_path).replace(".yaml", "")

    # Initialize DB + logger
    db = DatabaseManager()
    run_id = f"{suite_name}_{int(time.time())}"
    
    eval_logger.eval_start(run_id, {"suite": suite_name, "use_judge": use_judge})
    db.create_run(run_id, {"suite_path": suite_path, "use_judge": use_judge})
    # ADD THIS: Create entry in test_runs for dashboard
    db.create_test_run(run_id=run_id, suite_name=suite_name)

    init_db()  # Keep existing memory store
    allure = AllureWriter()
    allure.write_environment({
        "Suite": suite_name,
        "Framework": "VerdictAI",
        "Python": "3.10+"
    })
    allure.write_categories()
    results: list[dict] = []
    passed = 0
    failed = 0
    inconclusive = 0

    # Tickets (Jira / GitHub issue) are raised only after this many consecutive
    # FAILs of the same case. 0 disables ticket creation.
    ticket_after = int(os.getenv("VERDICTAI_TICKET_AFTER_FAILS", "3"))

    cases = suite if isinstance(suite, list) else suite.get("test_cases", [])

    for case in cases:
        result = _run_case(case, use_judge=use_judge, run_id=run_id, db=db)
        
        # Track pass/fail
        verdict_str = result["verdict"].get("verdict") if isinstance(result["verdict"], dict) else result["verdict"]
        if verdict_str == "PASS":
            passed += 1
        elif verdict_str == "INCONCLUSIVE":
            inconclusive += 1
        else:
            failed += 1

        # Regression check: compare the judge score with the previous run of
        # the same case (case_id is stable across runs; result["id"] is not).
        case_id = result.get("case_id", result["id"])
        judge_score = (result.get("judge") or {}).get("score")
        if judge_score is not None:
            previous = get_history(case_id, limit=1)
            result["regression"] = evaluate_regression(
                previous[0]["score"] if previous else None, judge_score
            )
            if result["regression"]["regressed"]:
                print(f"   {result['regression']['message']}")

        # Persist result
        save_result(suite_name, result)

        # Jira / self-heal trigger on repeated FAIL
        if verdict_str == "FAIL" and ticket_after > 0:
            reason_str = result["verdict"].get("reason", "") if isinstance(result["verdict"], dict) else ""
            try:
                check_and_heal(
                    test_id=case_id,
                    suite_name=suite_name,
                    reason=reason_str,
                    n=ticket_after,
                )
            except Exception as _jira_err:
                print(f"   ⚠️  Jira/self-heal error (non-fatal): {_jira_err}")

        results.append(result)
        allure.write_test_result(result)
        _print_result(result)
        inter_case_sleep(2.0)   # 2s buffer — keeps all providers within rate limits

    # End run
    summary = {
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "inconclusive": inconclusive,
        "pass_rate": passed / len(cases) if cases else 0
    }
    
    db.update_run(
        run_id,
        ended_at=time.time(),
        status="completed",
        total_tests=len(cases),
        passed_tests=passed,
        failed_tests=failed
    )
    # ADD THIS: Update test_run summary for dashboard
    db.update_test_run_summary(run_id)
    
    eval_logger.eval_end(run_id, summary)
    # ADD THIS LINE TO FORCE SYNC TO DASHBOARD TABLES
    db.sync_from_eval_tables(run_id)  # Sync only this run
    db.close()

    return results


def _run_case(case: dict, use_judge: bool = True, run_id: str = None, db: DatabaseManager = None) -> dict:
    case_id = case.get("id", "unknown")        # stable across runs
    test_id = f"{case_id}_{run_id}"            # unique per run, used by the dashboard DB
    input_text = case.get("input", "")
    expected_behavior = case.get("expected_behavior", "")
    threshold = case.get("judge_threshold", 70)

    eval_logger.test_case_start(test_id, {"input": input_text[:100]})

    print(f"\n{'=' * 60}")
    print(f"TEST: {test_id}")
    print(f"INPUT: {input_text[:80]}...")

    t0 = time.time()
    response, token_usage = get_response(input_text)   # unpack tuple
    latency_ms = int((time.time() - t0) * 1000)

    # Log LLM call
    eval_logger.llm_call(
        model=str(os.getenv("GROQ_MODEL", "groq/llama3-8b")),
        prompt=input_text,
        response=response,
        latency=latency_ms
    )

    if db:
        db.save_llm_call(
            test_id=test_id,
            model=str(os.getenv("GROQ_MODEL", "groq/llama3-8b")),
            prompt=input_text,
            response=response,
            latency_ms=latency_ms,
            tokens_input=token_usage["tokens_input"],
            tokens_output=token_usage["tokens_output"],
        )

    print(f"RESPONSE ({latency_ms}ms): {response[:120]}...")

    # ... existing assertion logic ...
    
    # scoring_mode controls which scorers run:
    #   "full"       — judge + relevance + hallucination (default, good for factual suites)
    #   "judge_only" — judge only, skip relevance + hallucination
    #                  use for safety/format/behaviour suites where cosine similarity is meaningless
    scoring_mode = case.get("scoring_mode", "full")

    assertions = case.get("assertions", [])
    heuristic_results = run_assertions(response, assertions)
    heuristic_pass = all(item["passed"] for item in heuristic_results)

    if not heuristic_pass:
        judge_result = None
        relevance = None
        hallucination = None
    else:
        if use_judge and expected_behavior:
            print(f"JUDGING against: '{expected_behavior}'")
            judge_result = multi_judge_response(
                input_text=input_text,
                response=response,
                expected_behavior=expected_behavior,
                threshold=threshold,
            )

            if judge_result and judge_result.get("score"):
                eval_logger.score_calculated(
                    test_id=test_id,
                    metric="judge_score",
                    score=judge_result["score"],
                    details={"reason": judge_result.get("reason")}
                )
                if db:
                    db.save_score(
                        test_id=test_id,
                        metric_name="judge_score",
                        score_value=judge_result["score"],
                        details=judge_result.get("reason")
                    )

            print(f"JUDGE → score={judge_result['score']} | verdict={judge_result['verdict']}")
            print(f"GROQ:      {judge_result['groq']['score']} — {judge_result['groq']['reason']}")
            second = judge_result.get('cerebras') or judge_result.get('sambanova') or judge_result.get('gemini') or {}
            print(f"JUDGE-2:   {second.get('score','N/A')} — {second.get('reason','N/A')}")

            if scoring_mode == "full":
                # Relevance scoring — compares response to expected via cosine similarity
                # Only meaningful for factual suites where response and expected share vocabulary
                relevance = get_relevance_score(response, expected_behavior)
                eval_logger.score_calculated(
                    test_id=test_id,
                    metric="relevance_score",
                    score=relevance["score"],
                    details={"cosine_similarity": relevance["cosine_similarity"]}
                )
                if db:
                    db.save_score(
                        test_id=test_id,
                        metric_name="relevance_score",
                        score_value=relevance["score"],
                        details=f"cosine_sim={relevance['cosine_similarity']}"
                    )
                print(f"RELEVANCE → score={relevance['score']} (cosine={relevance['cosine_similarity']})")

                # Hallucination detection — uses expected_behavior as source context
                # Only meaningful for factual suites where expected contains ground truth content
                source_context = case.get("source_context", expected_behavior)
                hallucination = detect_hallucination(response, source_context)
                eval_logger.score_calculated(
                    test_id=test_id,
                    metric="hallucination_score",
                    score=hallucination["score"],
                    details={
                        "claims_total": hallucination["claims_total"],
                        "supported": hallucination["claims_supported"],
                        "contradicted": hallucination["claims_contradicted"]
                    }
                )
                if db:
                    db.save_score(
                        test_id=test_id,
                        metric_name="hallucination_score",
                        score_value=hallucination["score"],
                        details=f"claims={hallucination['claims_total']}, supported={hallucination['claims_supported']}"
                    )
                print(f"HALLUCINATION → score={hallucination['score']}% ({hallucination['claims_supported']}/{hallucination['claims_total']} claims supported)")
            else:
                relevance = None
                hallucination = None
                print(f"   ℹ️  scoring_mode=judge_only — relevance + hallucination skipped")
        else:
            judge_result = None
            relevance = None
            hallucination = None

    final_verdict = _compute_verdict(
        heuristic_pass=heuristic_pass,
        heuristic_results=heuristic_results,
        judge_result=judge_result,
        relevance=relevance,
        hallucination=hallucination,
        scoring_mode=scoring_mode,
    )
    
    
    result = {
        "id": test_id,
        "case_id": case_id,
        "input": input_text,
        "response": response,
        "latency_ms": latency_ms,
        "heuristic_pass": heuristic_pass,
        "heuristic_results": heuristic_results,
        "judge": judge_result,
        "relevance": relevance,
        "hallucination": hallucination,
        "verdict": final_verdict,
    }
    
    # Save test case to DB
    if db and run_id:
        # Extract verdict fields FIRST before any usage
        verdict_label = final_verdict.get("verdict") if isinstance(final_verdict, dict) else final_verdict
        verdict_reason = final_verdict.get("reason") if isinstance(final_verdict, dict) else None
        verdict_details = final_verdict.get("details") if isinstance(final_verdict, dict) else None

        db.save_test_case(
            test_id=test_id,
            run_id=run_id,
            test_name=test_id,
            input_data=input_text,
            expected_output=expected_behavior,
            actual_output=response,
            passed=(verdict_label == "PASS"),
            error_message=(judge_result.get("reason") if judge_result and verdict_label == "FAIL" else None)
        )


        metadata = {
            "input": input_text,
            "expected_output": expected_behavior,
            "actual_output": response,
            "heuristic_results": heuristic_results,
            "hallucination_claims": hallucination.get("details", []) if hallucination else [],
            "verdict_details": verdict_details  # ✅ move details here
        }

        db.save_test_result(
            run_id=run_id,
            test_id=test_id,
            verdict=verdict_label,  # ✅ string only
            score=judge_result.get("score") if judge_result else None,
            relevance_score=relevance.get("score") if relevance else None,
            hallucination_score=hallucination.get("score") if hallucination else None,
            reason=verdict_reason,  # ✅ use YOUR verdict reason (not judge)
            latency_ms=latency_ms,
            metadata=metadata  # will be json.dumps inside DB layer
        )
    
    verdict_label = final_verdict.get("verdict") if isinstance(final_verdict, dict) else final_verdict

    eval_logger.test_case_end(
        test_id,
        {
            "verdict": verdict_label,
            "passed": verdict_label == "PASS"
        }
    )

    return result


def _print_result(result: dict) -> None:
    """
    Print final result summary for a test case.
    """
    verdict = result.get("verdict", "FAIL")
    if isinstance(verdict, dict):
        verdict = verdict.get("verdict", "FAIL")
    icon = {"PASS": "✅", "INCONCLUSIVE": "⚠️"}.get(verdict, "❌")
    print(f"{icon} FINAL VERDICT: {verdict}")