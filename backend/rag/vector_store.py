import os
import logging

os.environ["POSTHOG_DISABLED"] = "true"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "true"
os.environ["DO_NOT_TRACK"] = "true"

import chromadb
from chromadb.config import Settings
from config import config

logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("posthog").setLevel(logging.WARNING)


class VectorStore:
    def __init__(self):
        os.makedirs(config.CHROMA_PERSIST_DIR, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=config.CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=config.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(self, documents: list[dict]):
        ids = [d["id"] for d in documents]
        texts = [d["text"] for d in documents]
        metadatas = [d.get("metadata", {}) for d in documents]
        embeddings = [d.get("embedding") for d in documents]

        batch_size = 100
        for i in range(0, len(ids), batch_size):
            end = min(i + batch_size, len(ids))
            kwargs = {
                "ids": ids[i:end],
                "documents": texts[i:end],
                "metadatas": metadatas[i:end],
            }
            if embeddings and embeddings[i]:
                kwargs["embeddings"] = embeddings[i:end]
            self.collection.add(**kwargs)

    def search(self, query_embedding: list[float], top_k: int = None) -> list[dict]:
        if top_k is None:
            top_k = config.RAG_TOP_K
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
        documents = []
        if results["documents"]:
            for i in range(len(results["documents"][0])):
                documents.append({
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                })
        return documents

    def delete_document(self, doc_id: str):
        try:
            self.collection.delete(ids=[doc_id])
        except Exception:
            pass

    def delete_by_metadata(self, source_id: str):
        try:
            results = self.collection.get(where={"source_id": source_id})
            if results and results["ids"]:
                self.collection.delete(ids=results["ids"])
        except Exception:
            pass

    def count(self) -> int:
        return self.collection.count()


vector_store = VectorStore()
