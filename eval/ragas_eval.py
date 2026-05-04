"""
RAGAS evaluation pipeline (Sprint 4).
Runs labelled queries from tests/query_eval_set.json and reports metrics.

Metric coverage by query type:
    RAG_ONLY  (with ground_truth)  -> Faithfulness + AnswerRelevancy + ContextRecall
    RAG_ONLY  (no ground_truth)    -> Faithfulness + AnswerRelevancy
    HYBRID                         -> Faithfulness + AnswerRelevancy
    MCP_ONLY                       -> AnswerRelevancy only (no RAG contexts)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).parent.parent))

from ragas import EvaluationDataset, evaluate
from ragas.dataset_schema import SingleTurnSample
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import llm_factory
from ragas.metrics import _Faithfulness, _LLMContextRecall, _ResponseRelevancy
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI

from agent.analyst import run as analyst_run


MAX_CONTEXT_PREVIEW_CHARS = 1200


def _make_openai_client() -> OpenAI:
    """Create a shared OpenAI client for RAGAS judge calls."""
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def _make_llm_judge(openai_client: OpenAI) -> Any:
    """Use GPT-4o-mini as the RAGAS judge LLM."""
    return llm_factory(
        "gpt-4o-mini",
        client=openai_client,
        max_tokens=4096,
    )


def _make_eval_embeddings() -> Any:
    """Use a LangChain-compatible embedding wrapper for legacy RAGAS metrics."""
    return LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
    )


def _primary_ticker(ticker_field: str) -> str:
    """Return the first ticker from a comma-separated list."""
    return ticker_field.split(",")[0].strip()


def _run_pipeline(sample: dict) -> dict | None:
    """
    Run the full analyst pipeline for one eval sample.

    Returns dict with answer, retrieved_contexts, or None on failure.
    """
    ticker = _primary_ticker(sample["ticker"])
    fiscal_year = sample.get("fiscal_year") or "2024"

    try:
        result = analyst_run(
            query=sample["query"],
            ticker=ticker,
            fiscal_year=fiscal_year,
            query_type_override=sample.get("query_type"),
        )
    except Exception as exc:
        print(f"  [WARN] Pipeline failed for id={sample['id']}: {exc}")
        return None

    # Extract text from RAG source chunks
    contexts = [r["text"] for r in result.get("sources", [])]
    retrieved_contexts = [
        {
            "rank": index,
            "ticker": source.get("metadata", {}).get("ticker"),
            "fiscal_year": source.get("metadata", {}).get("fiscal_year"),
            "filing_type": source.get("metadata", {}).get("filing_type"),
            "section": source.get("metadata", {}).get("section"),
            "section_type": source.get("metadata", {}).get("section_type"),
            "page_number": source.get("metadata", {}).get("page_number"),
            "score": source.get("score"),
            "rrf_score": source.get("rrf_score"),
            "text_preview": source.get("text", "")[:MAX_CONTEXT_PREVIEW_CHARS],
        }
        for index, source in enumerate(result.get("sources", []), start=1)
    ]

    # Append live MCP data as a context string so faithfulness can score it
    tool_outputs = result.get("mcp_data", [])
    for mcp_item in tool_outputs:
        contexts.append(json.dumps(mcp_item))

    return {
        "answer": result["answer"],
        "contexts": contexts,
        "query_type": result["query_type"],
        "router_decision": result.get("routing", {}),
        "retrieved_contexts": retrieved_contexts,
        "tool_outputs": tool_outputs,
    }


def _context_preview(contexts: list[str]) -> str:
    """Return a compact context preview for per-question debugging files."""
    joined = "\n\n---\n\n".join(contexts)
    return joined[:MAX_CONTEXT_PREVIEW_CHARS]


def _build_samples(
    eval_set: list[dict],
    pipeline_outputs: dict[int, dict],
) -> tuple[
    list[SingleTurnSample],
    list[dict],
    list[SingleTurnSample],
    list[dict],
    list[SingleTurnSample],
    list[dict],
]:
    """
    Split pipeline outputs into three RAGAS sample lists by metric coverage.

    Returns:
        rag_with_gt  - RAG_ONLY samples that have ground truth
        rag_no_gt    - RAG_ONLY / HYBRID samples without ground truth
        mcp_only     - MCP_ONLY samples
    """
    rag_with_gt: list[SingleTurnSample] = []
    rag_with_gt_meta: list[dict] = []
    rag_no_gt: list[SingleTurnSample] = []
    rag_no_gt_meta: list[dict] = []
    mcp_only: list[SingleTurnSample] = []
    mcp_only_meta: list[dict] = []

    for item in eval_set:
        output = pipeline_outputs.get(item["id"])
        if output is None:
            continue

        ground_truth = item.get("expected_answer", "").strip()
        query_type = item["query_type"]
        metadata = {
            "id": item["id"],
            "query_type": query_type,
            "ticker": item.get("ticker"),
            "fiscal_year": item.get("fiscal_year"),
            "query": item["query"],
            "expected_answer": ground_truth,
            "answer": output["answer"],
            "n_contexts": len(output["contexts"]),
            "context_preview": _context_preview(output["contexts"]),
            "retrieved_contexts": output.get("retrieved_contexts", []),
            "router_decision": output.get("router_decision", {}),
            "tool_outputs": output.get("tool_outputs", []),
        }

        if query_type == "MCP_ONLY":
            mcp_only.append(
                SingleTurnSample(
                    user_input=item["query"],
                    response=output["answer"],
                    retrieved_contexts=output["contexts"] or ["(no RAG context)"],
                )
            )
            mcp_only_meta.append(metadata)
        elif ground_truth:
            rag_with_gt.append(
                SingleTurnSample(
                    user_input=item["query"],
                    response=output["answer"],
                    retrieved_contexts=output["contexts"],
                    reference=ground_truth,
                )
            )
            rag_with_gt_meta.append(metadata)
        else:
            rag_no_gt.append(
                SingleTurnSample(
                    user_input=item["query"],
                    response=output["answer"],
                    retrieved_contexts=output["contexts"] or ["(no RAG context)"],
                )
            )
            rag_no_gt_meta.append(metadata)

    return rag_with_gt, rag_with_gt_meta, rag_no_gt, rag_no_gt_meta, mcp_only, mcp_only_meta


def _safe_score(result_df, col: str) -> float | None:
    """Extract mean score from RAGAS result, return None if column missing."""
    if col in result_df.columns:
        return round(float(result_df[col].mean()), 4)
    return None


def _is_multi_company_sample(sample: dict) -> bool:
    """Return True when the eval sample asks for multiple tickers."""
    return "," in str(sample.get("ticker", ""))


def _unsupported_reason(item: dict, output: dict) -> str | None:
    """Explain samples that should not count toward RAGAS quality gates."""
    query_lower = item["query"].lower()
    query_type = item["query_type"]
    tool_outputs = output.get("tool_outputs", [])

    speculative_terms = [
        "pricing in",
        "priced in",
        "market imply",
        "market currently pricing",
        "adequately price",
        "sustainable",
        "future growth",
        "implied future growth",
        "pure-play",
        "aws and google cloud",
        "professional networking",
        "pipeline",
    ]
    if query_type == "HYBRID" and any(term in query_lower for term in speculative_terms):
        return (
            "unsupported_capability: requires valuation-model, peer/segment valuation, "
            "or forward-looking market-implied growth capability not implemented in MVP"
        )

    if query_type in {"MCP_ONLY", "HYBRID"} and tool_outputs:
        unavailable = [
            item
            for item in tool_outputs
            if item.get("data_source") == "unavailable" or item.get("error")
        ]
        if len(unavailable) == len(tool_outputs):
            return "data_unavailable: configured market-data APIs did not return the required fields"

    return None


def _merge_detail_rows(result_df, metadata_rows: list[dict]) -> list[dict]:
    """Merge RAGAS per-row scores with eval metadata."""
    rows: list[dict] = []
    records = result_df.to_dict(orient="records")
    for meta, scores in zip(metadata_rows, records):
        rows.append(
            {
                **meta,
                "faithfulness": scores.get("faithfulness"),
                "answer_relevancy": scores.get("answer_relevancy"),
                "context_recall": scores.get("context_recall"),
            }
        )
    return rows


def _sort_key_for_low_scores(row: dict) -> float:
    """Sort by the lowest available core metric score."""
    values = [
        row.get("answer_relevancy"),
        row.get("context_recall"),
        row.get("faithfulness"),
    ]
    numeric = [float(value) for value in values if value is not None]
    return min(numeric) if numeric else 1.0


def _print_low_score_examples(detail_rows: list[dict], limit: int = 10) -> None:
    """Print the lowest scoring questions for fast debugging."""
    if not detail_rows:
        return

    print("\nLowest scoring questions")
    print("-" * 50)
    for row in sorted(detail_rows, key=_sort_key_for_low_scores)[:limit]:
        print(
            f"id={row['id']:02d} [{row['query_type']}] "
            f"faith={row.get('faithfulness')} "
            f"rel={row.get('answer_relevancy')} "
            f"recall={row.get('context_recall')} | {row['query']}"
        )


def run_evaluation(
    eval_set_path: str = "tests/query_eval_set.json",
    output_dir: str = "eval/results",
) -> dict:
    """
    Run RAGAS evaluation over the full eval set.

    Args:
        eval_set_path: Path to the labelled query JSON file.
        output_dir:    Directory to write per-run result JSON.

    Returns:
        {
            "faithfulness":     float | None,
            "answer_relevancy": float | None,
            "context_recall":   float | None,
            "n_evaluated":      int,
            "n_failed":         int,
        }
    """
    raw_eval_set: list[dict] = json.loads(Path(eval_set_path).read_text())
    skipped_multi_company = [item for item in raw_eval_set if _is_multi_company_sample(item)]
    eval_set = [item for item in raw_eval_set if not _is_multi_company_sample(item)]

    print(f"Loaded {len(raw_eval_set)} samples from {eval_set_path}")
    print(f"Skipped {len(skipped_multi_company)} multi-company samples not supported by current agent")
    print(f"Evaluating {len(eval_set)} single-company samples")

    # --- Step 1: Run the full pipeline for every sample ---
    pipeline_outputs: dict[int, dict] = {}
    for item in eval_set:
        print(f"  Running id={item['id']:02d} [{item['query_type']}] {item['query'][:60]}...")
        output = _run_pipeline(item)
        if output:
            pipeline_outputs[item["id"]] = output

    n_failed = len(eval_set) - len(pipeline_outputs)
    print(f"\nPipeline complete: {len(pipeline_outputs)} OK, {n_failed} failed\n")

    openai_client = _make_openai_client()
    llm_judge = _make_llm_judge(openai_client)
    eval_embeddings = _make_eval_embeddings()
    metrics_full = [
        _Faithfulness(llm=llm_judge),
        _ResponseRelevancy(llm=llm_judge, embeddings=eval_embeddings),
        _LLMContextRecall(llm=llm_judge),
    ]
    metrics_no_gt = [
        _Faithfulness(llm=llm_judge),
        _ResponseRelevancy(llm=llm_judge, embeddings=eval_embeddings),
    ]
    metrics_mcp = [_ResponseRelevancy(llm=llm_judge, embeddings=eval_embeddings)]

    all_faithfulness: list[float] = []
    all_relevancy: list[float] = []
    all_recall: list[float] = []
    detail_rows: list[dict] = []
    unsupported_rows: list[dict] = []

    supported_eval_set: list[dict] = []
    supported_pipeline_outputs: dict[int, dict] = {}
    for item in eval_set:
        output = pipeline_outputs.get(item["id"])
        if output is None:
            continue
        unsupported_reason = _unsupported_reason(item, output)
        if unsupported_reason:
            unsupported_rows.append(
                {
                    "id": item["id"],
                    "query_type": item["query_type"],
                    "ticker": item.get("ticker"),
                    "fiscal_year": item.get("fiscal_year"),
                    "query": item["query"],
                    "expected_answer": item.get("expected_answer", ""),
                    "answer": output["answer"],
                    "n_contexts": len(output["contexts"]),
                    "context_preview": _context_preview(output["contexts"]),
                    "retrieved_contexts": output.get("retrieved_contexts", []),
                    "router_decision": output.get("router_decision", {}),
                    "tool_outputs": output.get("tool_outputs", []),
                    "faithfulness": None,
                    "answer_relevancy": None,
                    "context_recall": None,
                    "unsupported_reason": unsupported_reason,
                }
            )
        else:
            supported_eval_set.append(item)
            supported_pipeline_outputs[item["id"]] = output

    # --- Step 3: Evaluate each group ---
    rag_with_gt, rag_with_gt_meta, rag_no_gt, rag_no_gt_meta, mcp_only, mcp_only_meta = _build_samples(
        supported_eval_set,
        supported_pipeline_outputs,
    )

    if rag_with_gt:
        print(f"Evaluating {len(rag_with_gt)} RAG samples (with ground truth)...")
        ds = EvaluationDataset(samples=rag_with_gt)
        res = evaluate(ds, metrics=metrics_full)
        df = res.to_pandas()
        detail_rows.extend(_merge_detail_rows(df, rag_with_gt_meta))
        if "faithfulness" in df.columns:
            all_faithfulness.extend(df["faithfulness"].dropna().tolist())
        if "answer_relevancy" in df.columns:
            all_relevancy.extend(df["answer_relevancy"].dropna().tolist())
        if "context_recall" in df.columns:
            all_recall.extend(df["context_recall"].dropna().tolist())

    if rag_no_gt:
        print(f"Evaluating {len(rag_no_gt)} RAG/HYBRID samples (no ground truth)...")
        ds = EvaluationDataset(samples=rag_no_gt)
        res = evaluate(ds, metrics=metrics_no_gt)
        df = res.to_pandas()
        detail_rows.extend(_merge_detail_rows(df, rag_no_gt_meta))
        if "faithfulness" in df.columns:
            all_faithfulness.extend(df["faithfulness"].dropna().tolist())
        if "answer_relevancy" in df.columns:
            all_relevancy.extend(df["answer_relevancy"].dropna().tolist())

    if mcp_only:
        print(f"Evaluating {len(mcp_only)} MCP_ONLY samples...")
        ds = EvaluationDataset(samples=mcp_only)
        res = evaluate(ds, metrics=metrics_mcp)
        df = res.to_pandas()
        detail_rows.extend(_merge_detail_rows(df, mcp_only_meta))
        if "answer_relevancy" in df.columns:
            all_relevancy.extend(df["answer_relevancy"].dropna().tolist())

    # --- Step 4: Aggregate scores ---
    scores = {
        "faithfulness":     round(sum(all_faithfulness) / len(all_faithfulness), 4) if all_faithfulness else None,
        "answer_relevancy": round(sum(all_relevancy) / len(all_relevancy), 4)     if all_relevancy     else None,
        "context_recall":   round(sum(all_recall) / len(all_recall), 4)           if all_recall        else None,
        "n_evaluated":      len(pipeline_outputs),
        "n_failed":         n_failed,
        "n_supported_scored": len(supported_pipeline_outputs),
        "n_unsupported_or_data_unavailable": len(unsupported_rows),
        "n_skipped_multi_company": len(skipped_multi_company),
    }

    # --- Step 5: Print summary ---
    print("\n" + "=" * 50)
    print("RAGAS Evaluation Results")
    print("=" * 50)
    print(f"  Faithfulness     : {scores['faithfulness']}  (target >= 0.80)")
    print(f"  Answer Relevancy : {scores['answer_relevancy']}  (target >= 0.75)")
    print(f"  Context Recall   : {scores['context_recall']}  (RAG_ONLY w/ ground truth)")
    print(f"  Evaluated        : {scores['n_evaluated']} / {len(eval_set)}")
    print(f"  Supported Scored : {scores['n_supported_scored']}")
    print(f"  Unsupported/Data : {scores['n_unsupported_or_data_unavailable']}")
    print(f"  Skipped Multi-Co : {scores['n_skipped_multi_company']}")
    print("=" * 50)
    detail_rows.extend(unsupported_rows)
    _print_low_score_examples(detail_rows)

    # --- Step 6: Save results ---
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    result_path = Path(output_dir) / f"ragas_{timestamp}.json"
    details_json_path = Path(output_dir) / f"ragas_details_{timestamp}.json"
    details_csv_path = Path(output_dir) / f"ragas_details_{timestamp}.csv"
    result_path.write_text(json.dumps(scores, indent=2))
    details_json_path.write_text(json.dumps(detail_rows, indent=2))

    try:
        import pandas as pd

        pd.DataFrame(detail_rows).to_csv(details_csv_path, index=False)
        print(f"Per-question details saved to {details_csv_path}")
    except Exception as exc:
        print(f"[WARN] Could not save details CSV: {exc}")

    print(f"Per-question details saved to {details_json_path}")
    print(f"Results saved to {result_path}\n")

    return scores


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_evaluation()
