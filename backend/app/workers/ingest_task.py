from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.bm25_index import bm25_service
from app.core.chunker import chunker
from app.core.document_processor import document_processor
from app.core.embedder import embedder
from app.core.vector_store import vector_store
from app.models.database import AsyncSessionLocal, Document, Project
from app.utils.storage import storage
from app.workers.celery_app import celery


@dataclass
class IngestChunk:
    doc_id: str
    project_id: str
    user_id: str
    chunk_id: str
    text: str
    window_text: str
    context_prefix: str
    page_num: int | None
    chunk_index: int
    total_chunks: int
    doc_type: str
    source_filename: str


@celery.task(bind=True, max_retries=3)
def ingest_document(self, doc_id: str):
    try:
        return asyncio.run(_ingest_document_async(doc_id))
    except Exception as exc:
        asyncio.run(_mark_document_failed(doc_id=doc_id, error_message=str(exc)))
        raise self.retry(exc=exc, countdown=30)


async def _ingest_document_async(doc_id: str) -> dict[str, int | str]:
    async with AsyncSessionLocal() as db:
        document = await _get_document_or_raise(db=db, doc_id=doc_id)
        project = await _get_project_or_raise(db=db, project_id=document.project_id)

        # 1) Load document and mark processing.
        document.status = "processing"
        document.error_message = None
        await db.commit()
        await db.refresh(document)

        # 2) Download bytes from MinIO.
        raw_bytes = await storage.get(document.original_path)

        # 3) Parse.
        text_elements = document_processor.parse(raw=raw_bytes, mime_type=document.mime_type)

        # 4) Chunk.
        base_chunks = chunker.chunk(text_elements=text_elements, doc=document)
        if not base_chunks:
            raise ValueError("No chunks generated from document")

        ingest_chunks = _build_ingest_chunks(document=document, project=project, base_chunks=base_chunks)

        # 5) Embed.
        embeddings = embedder.embed_batch([chunk.text for chunk in ingest_chunks])

        # 6) Upsert vectors.
        await vector_store.upsert(
            collection_name=project.qdrant_namespace,
            chunks=ingest_chunks,
            embeddings=embeddings,
        )

        # 7) Build BM25.
        bm25_index = bm25_service.build(ingest_chunks)

        # 8) Save BM25 in DB + Redis.
        await bm25_service.save_to_db_and_cache(db=db, doc_id=document.id, index=bm25_index)

        # 9) Update document ready.
        chunk_count = len(ingest_chunks)
        document = await _get_document_or_raise(db=db, doc_id=doc_id)
        document.status = "ready"
        document.error_message = None
        document.num_chunks = chunk_count

        # 10) Increment project counts.
        project = await _get_project_or_raise(db=db, project_id=document.project_id)
        project.doc_count = int(project.doc_count or 0) + 1
        project.chunk_count = int(project.chunk_count or 0) + chunk_count

        await db.commit()

        return {
            "doc_id": str(document.id),
            "project_id": str(project.id),
            "chunk_count": chunk_count,
        }


async def _mark_document_failed(doc_id: str, error_message: str) -> None:
    async with AsyncSessionLocal() as db:
        try:
            document = await db.get(Document, UUID(str(doc_id)))
            if document is None:
                return
            document.status = "failed"
            document.error_message = error_message
            await db.commit()
        except Exception:
            await db.rollback()


def _build_ingest_chunks(document: Document, project: Project, base_chunks: list) -> list[IngestChunk]:
    out: list[IngestChunk] = []
    doc_type = str(document.doc_type or "unknown")

    for chunk in base_chunks:
        out.append(
            IngestChunk(
                doc_id=str(document.id),
                project_id=str(project.id),
                user_id=str(document.user_id),
                chunk_id=str(uuid4()),
                text=str(chunk.text),
                window_text=str(chunk.window_text),
                context_prefix=str(chunk.context_prefix),
                page_num=chunk.page_num,
                chunk_index=int(chunk.chunk_index),
                total_chunks=int(chunk.total_chunks),
                doc_type=doc_type,
                source_filename=str(document.filename),
            )
        )

    return out


async def _get_document_or_raise(db: AsyncSession, doc_id: str) -> Document:
    document = await db.get(Document, UUID(str(doc_id)))
    if document is None:
        raise ValueError(f"Document not found: {doc_id}")
    return document


async def _get_project_or_raise(db: AsyncSession, project_id: UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")
    return project
