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

    # Append live MCP data as a context string so faithfulness can score it
    for mcp_item in result.get("mcp_data", []):
        contexts.append(json.dumps(mcp_item))

    return {
        "answer": result["answer"],
        "contexts": contexts,
        "query_type": result["query_type"],
    }


def _build_samples(
    eval_set: list[dict],
    pipeline_outputs: dict[int, dict],
) -> tuple[list[SingleTurnSample], list[SingleTurnSample], list[SingleTurnSample]]:
    """
    Split pipeline outputs into three RAGAS sample lists by metric coverage.

    Returns:
        rag_with_gt  - RAG_ONLY samples that have ground truth
        rag_no_gt    - RAG_ONLY / HYBRID samples without ground truth
        mcp_only     - MCP_ONLY samples
    """
    rag_with_gt: list[SingleTurnSample] = []
    rag_no_gt: list[SingleTurnSample] = []
    mcp_only: list[SingleTurnSample] = []

    for item in eval_set:
        output = pipeline_outputs.get(item["id"])
        if output is None:
            continue

        ground_truth = item.get("expected_answer", "").strip()
        query_type = item["query_type"]

        if query_type == "MCP_ONLY":
            mcp_only.append(
                SingleTurnSample(
                    user_input=item["query"],
                    response=output["answer"],
                    retrieved_contexts=output["contexts"] or ["(no RAG context)"],
                )
            )
        elif ground_truth:
            rag_with_gt.append(
                SingleTurnSample(
                    user_input=item["query"],
                    response=output["answer"],
                    retrieved_contexts=output["contexts"],
                    reference=ground_truth,
                )
            )
        else:
            rag_no_gt.append(
                SingleTurnSample(
                    user_input=item["query"],
                    response=output["answer"],
                    retrieved_contexts=output["contexts"] or ["(no RAG context)"],
                )
            )

    return rag_with_gt, rag_no_gt, mcp_only


def _safe_score(result_df, col: str) -> float | None:
    """Extract mean score from RAGAS result, return None if column missing."""
    if col in result_df.columns:
        return round(float(result_df[col].mean()), 4)
    return None


def _is_multi_company_sample(sample: dict) -> bool:
    """Return True when the eval sample asks for multiple tickers."""
    return "," in str(sample.get("ticker", ""))


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

    # --- Step 2: Build RAGAS sample groups ---
    rag_with_gt, rag_no_gt, mcp_only = _build_samples(eval_set, pipeline_outputs)

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

    # --- Step 3: Evaluate each group ---
    if rag_with_gt:
        print(f"Evaluating {len(rag_with_gt)} RAG samples (with ground truth)...")
        ds = EvaluationDataset(samples=rag_with_gt)
        res = evaluate(ds, metrics=metrics_full)
        df = res.to_pandas()
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
        if "faithfulness" in df.columns:
            all_faithfulness.extend(df["faithfulness"].dropna().tolist())
        if "answer_relevancy" in df.columns:
            all_relevancy.extend(df["answer_relevancy"].dropna().tolist())

    if mcp_only:
        print(f"Evaluating {len(mcp_only)} MCP_ONLY samples...")
        ds = EvaluationDataset(samples=mcp_only)
        res = evaluate(ds, metrics=metrics_mcp)
        df = res.to_pandas()
        if "answer_relevancy" in df.columns:
            all_relevancy.extend(df["answer_relevancy"].dropna().tolist())

    # --- Step 4: Aggregate scores ---
    scores = {
        "faithfulness":     round(sum(all_faithfulness) / len(all_faithfulness), 4) if all_faithfulness else None,
        "answer_relevancy": round(sum(all_relevancy) / len(all_relevancy), 4)     if all_relevancy     else None,
        "context_recall":   round(sum(all_recall) / len(all_recall), 4)           if all_recall        else None,
        "n_evaluated":      len(pipeline_outputs),
        "n_failed":         n_failed,
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
    print(f"  Skipped Multi-Co : {scores['n_skipped_multi_company']}")
    print("=" * 50)

    # --- Step 6: Save results ---
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    result_path = Path(output_dir) / f"ragas_{timestamp}.json"
    result_path.write_text(json.dumps(scores, indent=2))
    print(f"Results saved to {result_path}\n")

    return scores


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_evaluation()
