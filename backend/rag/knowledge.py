import hashlib
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database.models import KnowledgeDocument
from rag.vector_store import vector_store
from rag.embeddings import chunk_text, generate_embeddings_batch, generate_embedding


class KnowledgeManager:
    @staticmethod
    def ingest_document(
        db: Session,
        title: str,
        category: str,
        content: str,
        source: str = None,
    ) -> KnowledgeDocument:
        doc_id = str(uuid.uuid4())
        source_key = (source or f"manual/{title.strip()}").strip()
        latest = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.source == source_key)
            .order_by(KnowledgeDocument.version.desc())
            .first()
        )
        version = ((latest.version or 1) + 1) if latest else 1

        old_docs = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.source == source_key,
            KnowledgeDocument.is_active == True,
        ).all()

        doc = KnowledgeDocument(
            id=doc_id,
            title=title,
            category=category,
            content=content,
            source=source_key,
            version=version,
            content_hash=KnowledgeManager.content_hash(content),
            chunk_count=0,
            is_active=True,
        )
        db.add(doc)
        db.commit()

        try:
            KnowledgeManager.index_document(db, doc)
            for old_doc in old_docs:
                old_doc.is_active = False
                vector_store.delete_by_metadata(old_doc.id)
            db.commit()
        except Exception as e:
            if old_docs:
                doc.is_active = False
                db.commit()
            vector_store.delete_by_metadata(doc.id)
            print(f"  [WARN] Embeddings failed: {e}. Document saved without vectors.")
            print(f"  Set OPENAI_API_KEY in .env to enable vector search.")

        return doc

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256((content or "").encode("utf-8")).hexdigest()

    @staticmethod
    def index_document(db: Session, doc: KnowledgeDocument) -> bool:
        chunks = chunk_text(doc.content)
        doc.chunk_count = len(chunks)
        vector_store.delete_by_metadata(doc.id)
        if not chunks:
            doc.last_indexed_at = None
            db.commit()
            return False

        embeddings = generate_embeddings_batch(chunks)
        vector_docs = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            vector_docs.append({
                "id": f"{doc.id}_chunk_{i}",
                "text": chunk,
                "embedding": emb,
                "metadata": {
                    "source_id": doc.id,
                    "title": doc.title,
                    "category": doc.category,
                    "chunk_index": i,
                    "source": doc.source or "",
                    "version": doc.version or 1,
                },
            })
        vector_store.add_documents(vector_docs)
        doc.last_indexed_at = datetime.now(timezone.utc)
        db.commit()
        return True

    @staticmethod
    def reindex_document(db: Session, doc_id: str) -> bool:
        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
        if not doc or not doc.is_active:
            return False
        return KnowledgeManager.index_document(db, doc)

    @staticmethod
    def set_document_active(db: Session, doc_id: str, active: bool) -> bool:
        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
        if not doc:
            return False
        doc.is_active = active
        if active:
            for other in db.query(KnowledgeDocument).filter(
                KnowledgeDocument.source == doc.source,
                KnowledgeDocument.id != doc.id,
                KnowledgeDocument.is_active == True,
            ).all():
                other.is_active = False
                vector_store.delete_by_metadata(other.id)
            KnowledgeManager.index_document(db, doc)
        else:
            vector_store.delete_by_metadata(doc.id)
            db.commit()
        return True

    @staticmethod
    def delete_document(db: Session, doc_id: str) -> bool:
        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
        if not doc:
            return False
        vector_store.delete_by_metadata(doc_id)
        db.delete(doc)
        db.commit()
        return True

    @staticmethod
    def search_knowledge(query: str, top_k: int = None) -> list[dict]:
        try:
            query_embedding = generate_embedding(query)
            results = vector_store.search(query_embedding, top_k=top_k)
            return results
        except Exception as e:
            print(f"[RAG] Search skipped: {e}")
            return []

    @staticmethod
    def format_context(results: list[dict]) -> str:
        if not results:
            return "لا توجد معلومات متاحة."
        context_parts = []
        for i, r in enumerate(results, 1):
            metadata = r.get("metadata", {})
            title = metadata.get("title", "مصدر غير معروف")
            category = metadata.get("category", "عام")
            context_parts.append(
                f"[المصدر {i}] التصنيف: {category}\nالعنوان: {title}\nالمحتوى: {r['text']}\n"
            )
        return "\n---\n".join(context_parts)

    @staticmethod
    def get_categories(db: Session) -> list[str]:
        results = (
            db.query(KnowledgeDocument.category)
            .filter(KnowledgeDocument.is_active == True)
            .distinct()
            .all()
        )
        return [r[0] for r in results]

    @staticmethod
    def get_documents_by_category(db: Session, category: str) -> list[KnowledgeDocument]:
        return (
            db.query(KnowledgeDocument)
            .filter(
                KnowledgeDocument.category == category,
                KnowledgeDocument.is_active == True,
            )
            .all()
        )


knowledge_manager = KnowledgeManager()
