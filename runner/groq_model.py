"""
groq_model.py — replaces dummy_model.py for Layer 3+
Calls Groq to generate actual model responses for test inputs.
"""

from judge.groq_client import call_groq


def get_response(input_text: str, model: str = None) -> str:
    if model is None:
        from judge.groq_client import MODEL
        model = MODEL
    """
    Get a real LLM response for a test input.
    Used as the 'model under test' in the eval pipeline.
    """
    return call_groq(input_text, model=model, temperature=0.7)
