"""
Script to ingest all knowledge base markdown files into ChromaDB.
Run once to populate the vector database.

Usage: python seed_knowledge.py
"""

import os
import sys
from database.db import init_db, SessionLocal
from database.models import KnowledgeDocument
from rag.knowledge import knowledge_manager


def load_knowledge_files(kb_dir: str) -> list[dict]:
    documents = []
    if not os.path.exists(kb_dir):
        print(f"[WARN] Knowledge directory not found: {kb_dir}")
        return documents

    category_map = {
        "services": "services",
        "pricing": "pricing",
        "faq": "faq",
        "policies": "policies",
        "objections": "objections",
        "scripts": "scripts",
    }

    for filename in os.listdir(kb_dir):
        if not filename.endswith((".md", ".txt")):
            continue
        filepath = os.path.join(kb_dir, filename)
        name = os.path.splitext(filename)[0]
        category = category_map.get(name, "general")

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        title = f"المعرفة - {name}"
        documents.append({
            "title": title,
            "category": category,
            "content": content,
            "source": f"knowledge/{filename}",
        })
        print(f"  Loaded: {filename} -> {category}")

    return documents


def main():
    kb_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge")
    print(f"[SEED] Loading knowledge from: {kb_dir}")

    init_db()
    db = SessionLocal()

    try:
        docs = load_knowledge_files(kb_dir)
        if not docs:
            print("[SEED] No documents to ingest.")
            return

        print(f"[SEED] Ingesting {len(docs)} documents...")
        ingested = 0
        skipped = 0
        for doc in docs:
            existing = (
                db.query(KnowledgeDocument)
                .filter(KnowledgeDocument.source == doc["source"])
                .first()
            )
            if existing:
                print(f"  Skipping: {doc['source']} already exists.")
                skipped += 1
                continue

            print(f"  Ingesting: {doc['title']} ({doc['category']})...")
            knowledge_manager.ingest_document(
                db=db,
                title=doc["title"],
                category=doc["category"],
                content=doc["content"],
                source=doc["source"],
            )
            ingested += 1
            print(f"    Done.")

        print(f"\n[SEED] Ingested {ingested} documents, skipped {skipped} existing documents.")
        print(f"[SEED] The system is ready to answer questions based on this knowledge.")

    except Exception as e:
        print(f"[ERROR] {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
