import os
import csv
import argparse
from typing import List, Dict, Any
import statistics

from src.embedding import get_embedding
from src.db import DB

EVAL_QUERIES_CSV = os.environ.get("EVAL_QUERIES_CSV")
CSV_DATA_DIR = "/" + os.environ["CSV_DATA_DIR"]
EVAL_QUERIES_CSV_PATH = os.path.join(CSV_DATA_DIR, EVAL_QUERIES_CSV) if EVAL_QUERIES_CSV else None

def load_queries(csv_path: str) -> List[Dict[str, str]]:
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader]
    return rows


def detect_fields(row: Dict[str, str]):
    text_fields = [k for k in row.keys() if k.lower() in ("text", "query", "question")]
    qa_fields = [k for k in row.keys() if k.lower() in ("qa_id", "qid", "correct_qa_id", "qaid")]
    text_field = text_fields[0] if text_fields else list(row.keys())[0]
    qa_field = qa_fields[0] if qa_fields else (list(row.keys())[1] if len(row.keys())>1 else None)
    return text_field, qa_field


def compute_mrr(
    db: DB,
    rows: List[Dict[str, str]],
    embed_url: str,
    embed_model: str,
    top_k: int = 10,
):
    reciprocal_ranks = []
    details = []

    if not rows:
        return 0.0, details

    text_field, qa_field = detect_fields(rows[0])

    for r in rows:
        query_text = r.get(text_field, "").strip()
        correct_qa = r.get(qa_field, "").strip() if qa_field else ""

        emb = get_embedding(embed_url, embed_model, query_text)

        results = db.search_similar(emb, top_k)

        # search_similar now returns tuples: (question, answer, question_original, qa_id)
        rank = 0
        for i, rec in enumerate(results, start=1):
            returned_qa = str(rec[3]) if len(rec) > 3 else ""
            if returned_qa == correct_qa:
                rank = i
                break

        rr = 1.0 / rank if rank > 0 else 0.0
        reciprocal_ranks.append(rr)
        details.append({"query": query_text, "correct_qa": correct_qa, "rank": rank, "reciprocal_rank": rr})

    mrr = statistics.mean(reciprocal_ranks) if reciprocal_ranks else 0.0
    return mrr, details


def main():
    parser = argparse.ArgumentParser(description="Evaluate DB.search_similar with MRR metric")
    parser.add_argument("--csv", default=EVAL_QUERIES_CSV_PATH, help="CSV file with queries and correct qa_id")
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL"), help="Database URL (env DATABASE_URL)")
    parser.add_argument("--embed-url", default=os.environ.get("LMSTUDIO_EMBEDDING_URL"), help="Embedding endpoint URL (env LMSTUDIO_EMBEDDING_URL)")
    parser.add_argument("--embed-model", default=os.environ.get("MODEL_EMBEDDING"), help="Embedding model name (env MODEL_EMBEDDING)")
    parser.add_argument("--top-k", type=int, default=10, help="Number of nearest neighbors to consider")
    parser.add_argument("--output", default=None, help="Optional CSV path to write per-query results")

    args = parser.parse_args()


    if not args.db_url:
        raise SystemExit("DATABASE_URL not provided via --db-url or environment")
    if not args.embed_url or not args.embed_model:
        raise SystemExit("Embedding endpoint and model must be provided via --embed-url/--embed-model or environment")

    rows = load_queries(args.csv)

    with DB(args.db_url) as db:
        mrr, details = compute_mrr(db, rows, args.embed_url, args.embed_model, args.top_k)

    print(f"MRR: {mrr:.6f} (n={len(details)})")

    if args.output:
        with open(args.output, "w", newline='', encoding='utf-8') as f:
            fieldnames = ["query", "correct_qa", "rank", "reciprocal_rank"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for d in details:
                writer.writerow(d)


if __name__ == "__main__":
    main()
