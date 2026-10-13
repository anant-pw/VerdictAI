"""
judge/multi_judge.py — VerdictAI Multi-Judge Consensus
Runs Groq + Gemini judges in parallel via asyncio.
Averages scores, flags disagreements, returns consensus verdict.
"""

import os
import asyncio
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from judge.llm_judge import _parse_judge_output
from judge.judge_cache import cache_key, get_cached, set_cached
from judge.consensus import combine_judges

def _compact(text: str, max_chars: int = 300) -> str:
    """Truncate long strings to keep prompt lean."""
    return text[:max_chars] + "..." if len(text) > max_chars else text

load_dotenv("config.env")

# TOKEN OPTIMISATION: prompt trimmed ~180 tokens -> ~90 tokens
JUDGE_PROMPT = ChatPromptTemplate.from_template(
    "QA evaluator. Score 0-100 how well RESPONSE satisfies EXPECTED."
    "90-100=fully|70-89=mostly|50-69=partial|0-49=fails. PASS if score>={threshold}"
    "INPUT: {input}"
    "RESPONSE: {response}"
    "EXPECTED: {expected_behavior}"
    'Reply ONLY valid JSON, no markdown: {{"score":<int>,"verdict":"PASS|FAIL","reason":"<15 words>"}}'
)

# ── Judge 1: Groq ────────────────────────────────────────────
_groq_chain = (
    JUDGE_PROMPT
    | ChatGroq(
        # Set GROQ_JUDGE_MODEL to judge with a different model than the one
        # under test (GROQ_MODEL); otherwise a model grades its own answers.
        model=os.getenv("GROQ_JUDGE_MODEL") or os.getenv("GROQ_MODEL"),
        temperature=0.0,
        api_key=os.getenv("GROQ_API_KEY"),
    )
    | StrOutputParser()
)

# ── Judge 2: Cerebras (primary second judge — generous free tier, fast) ──
# Falls back to SambaNova if CEREBRAS_API_KEY not set
_cerebras_key = os.getenv("CEREBRAS_API_KEY", "").strip()
_sambanova_key = os.getenv("SAMBANOVA_API_KEY", "").strip()

if _cerebras_key:
    _second_chain = (
        JUDGE_PROMPT
        | ChatOpenAI(
            model=os.getenv("CEREBRAS_MODEL", "llama3.1-8b"),
            temperature=0.0,
            api_key=_cerebras_key,
            base_url="https://api.cerebras.ai/v1",
        )
        | StrOutputParser()
    )
    _second_judge_name = "cerebras"
    print("[VerdictAI] Second judge: Cerebras")
elif _sambanova_key:
    _second_chain = (
        JUDGE_PROMPT
        | ChatOpenAI(
            model=os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct"),
            temperature=0.0,
            api_key=_sambanova_key,
            base_url="https://api.sambanova.ai/v1",
        )
        | StrOutputParser()
    )
    _second_judge_name = "sambanova"
    print("[VerdictAI] Second judge: SambaNova (fallback — Cerebras key not set)")
else:
    _second_chain = None
    _second_judge_name = "none"
    print("[VerdictAI] WARNING: No second judge configured. Set CEREBRAS_API_KEY in config.env")

# Backward-compat aliases
_sambanova_chain = _second_chain
_gemini_chain = _second_chain
_cerebras_chain = _second_chain
_cerebras_enabled = bool(_cerebras_key)




async def _call_judge(chain, inputs: dict, judge_name: str) -> dict:
    """Run a single judge chain asynchronously."""
    try:
        raw = await chain.ainvoke(inputs)
        result = _parse_judge_output(raw)
        result["judge"] = judge_name
        result["raw"] = raw
        return result
    except Exception as e:
        return {
            "judge":   judge_name,
            "score":   0,
            "verdict": "FAIL",
            "reason":  f"Judge error: {e}",
            "raw":     "",
        }


async def _run_both_judges(inputs: dict) -> tuple[dict, dict, None]:
    """Fire Groq + second judge (Cerebras or SambaNova) in parallel."""
    tasks = [_call_judge(_groq_chain, inputs, "groq")]
    if _second_chain is not None:
        tasks.append(_call_judge(_second_chain, inputs, _second_judge_name))

    results = await asyncio.gather(*tasks)
    groq_r = results[0]
    second_r = results[1] if len(results) > 1 else {
        "judge": _second_judge_name,
        "score": 0,
        "verdict": "FAIL",
        "reason": "No second judge configured",
        "raw": "",
    }
    return groq_r, second_r, None  # 3rd slot kept for compat


def multi_judge_response(
    input_text: str,
    response: str,
    expected_behavior: str,
    threshold: int = 70,
    disagreement_threshold: int = 20,
) -> dict:
    """
    Run Groq + Gemini judges in parallel, return consensus result.

    Args:
        input_text:              Test input prompt
        response:                Model response to evaluate
        expected_behavior:       Expected behavior criteria from YAML
        threshold:               Score threshold for PASS (default 70)
        disagreement_threshold:  Score gap that triggers disagreement flag (default 20)

    Returns:
        {
            "score":        int | None  (average of the judges that answered),
            "verdict":      "PASS" | "FAIL" | "INCONCLUSIVE"  (no judge answered),
            "reason":       str   (combined reason),
            "groq":         dict  (individual groq result),
            "gemini":       dict  (individual gemini result),
            "disagreement": bool  (True if two judges answered and differ by > threshold),
            "raw":          str
        }
    """
    _ckey = cache_key(input_text, response, expected_behavior)
    _hit  = get_cached(_ckey)
    if _hit:
        print(f"   💾 Judge cache HIT — skipping API calls")
        return _hit

    inputs = {
        "input":             input_text,
        "response":          response,
        "expected_behavior": expected_behavior,
        "threshold":         threshold,
    }

    import asyncio as _asyncio
    try:
        _loop = _asyncio.get_running_loop()
        try:
            import nest_asyncio as _nest
            _nest.apply()
        except ImportError:
            pass
        groq_result, samba_result, cerebras_result = _loop.run_until_complete(_run_both_judges(inputs))
    except RuntimeError:
        groq_result, samba_result, cerebras_result = _asyncio.run(_run_both_judges(inputs))

    consensus = combine_judges(
        [groq_result, samba_result, cerebras_result],
        threshold=threshold,
        disagreement_threshold=disagreement_threshold,
    )

    if consensus["judges_used"] == 1:
        print("   ⚠️  Only one judge succeeded — using its score alone")
    if consensus["disagreement"]:
        print(
            f"   ⚠️  JUDGE DISAGREEMENT: Groq={groq_result['score']} "
            f"{_second_judge_name.capitalize()}={samba_result['score']} (gap={consensus['score_gap']})"
        )

    final = {
        **consensus,
        "groq":         groq_result,
        "gemini":       samba_result,          # keep key name for dashboard compat
        "sambanova":    samba_result,
        "cerebras":     cerebras_result,
    }
    # A run where no judge answered must not be replayed from the cache.
    if consensus["verdict"] == "INCONCLUSIVE":
        return final
    set_cached(_ckey, final)
    return final
