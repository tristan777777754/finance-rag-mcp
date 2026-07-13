# -*- coding: utf-8 -*-
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
_CLIENT = OpenAI()

FEW_SHOT = """
The query may be in any language. Translate it to English internally, then classify.

Classify into one of: RAG_ONLY, MCP_ONLY, HYBRID.

RAG_ONLY  = needs SEC filing content: historical revenue, earnings, gross margin, operating income,
            risk factors, business description, MD&A, management commentary, annual/quarterly financials.
            KEY RULE: any question about a SPECIFIC YEAR's financials (revenue, profit, income) -> RAG_ONLY.
MCP_ONLY  = needs live/real-time market data ONLY: current stock price, current P/E, upcoming earnings date.
HYBRID    = needs both filing content AND live market data simultaneously.

Examples:
Q: "What were Apple's risk factors in 2024?"                           -> RAG_ONLY
Q: "What was Apple's revenue in 2024?"                                 -> RAG_ONLY
Q: "What was Microsoft's annual revenue?"                              -> RAG_ONLY
Q: "What is Apple's current stock price?"                              -> MCP_ONLY
Q: "What is Apple's current P/E ratio?"                               -> MCP_ONLY
Q: "Compare Apple's reported revenue with its current valuation"       -> HYBRID
Q: "What did management say about AI in the 10-K?"                    -> RAG_ONLY
Q: "Who are Apple's competitors per their 10-K and what is its price?" -> HYBRID

Return JSON only: {"query_type": "...", "reasoning": "..."}
"""

VALID_QUERY_TYPES = frozenset({"RAG_ONLY", "MCP_ONLY", "HYBRID"})


def _validate_classification(payload: object) -> dict:
    """Validate the router contract before the analyst uses the result."""
    if not isinstance(payload, dict):
        raise ValueError("Router response must be a JSON object.")

    query_type = payload.get("query_type")
    reasoning = payload.get("reasoning")
    if query_type not in VALID_QUERY_TYPES:
        raise ValueError(f"Router returned invalid query_type: {query_type!r}")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise ValueError("Router response must include non-empty reasoning.")

    return {"query_type": query_type, "reasoning": reasoning.strip()}


def classify_query(query: str) -> dict:
    response = _CLIENT.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": FEW_SHOT},
            {"role": "user", "content": f"Query: {query}"},
        ],
    )
    try:
        payload = json.loads(response.choices[0].message.content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Router returned invalid JSON.") from exc
    return _validate_classification(payload)


if __name__ == "__main__":
    queries = [
        "What was Apple's revenue in 2025?",
        "What is Apple's current stock price?",
        "Compare Apple's gross margin with its current P/E ratio",
    ]
    for q in queries:
        result = classify_query(q)
        print(f"{result['query_type']} | {q}")
