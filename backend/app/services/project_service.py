from __future__ import annotations

import asyncio
from uuid import UUID

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, HnswConfigDiff, VectorParams
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import ChatSession, Document, Project, User


qdrant_client = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


def _minio_client():
    scheme = "https" if settings.MINIO_USE_SSL else "http"
    endpoint_url = f"{scheme}://{settings.MINIO_ENDPOINT}"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.MINIO_ROOT_USER,
        aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
        use_ssl=settings.MINIO_USE_SSL,
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )


async def get_project_or_403(project_id: str, user: User, db: AsyncSession) -> Project:
    project = await db.get(Project, UUID(project_id))
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return project


class ProjectService:
    @staticmethod
    async def list_projects(db: AsyncSession, user: User) -> list[Project]:
        stmt = select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create_project(db: AsyncSession, user: User, name: str, description: str | None) -> Project:
        project = Project(
            user_id=user.id,
            name=name,
            description=description,
            qdrant_namespace="pending",
        )
        db.add(project)
        await db.flush()

        project.qdrant_namespace = f"project_{project.id}"

        try:
            await qdrant_client.create_collection(
                collection_name=project.qdrant_namespace,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
                hnsw_config=HnswConfigDiff(m=16, ef_construct=200),
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

        await db.refresh(project)
        return project

    @staticmethod
    async def get_project(db: AsyncSession, user: User, project_id: str) -> Project:
        return await get_project_or_403(project_id, user, db)

    @staticmethod
    async def update_project(
        db: AsyncSession,
        user: User,
        project_id: str,
        name: str | None,
        description: str | None,
    ) -> Project:
        project = await get_project_or_403(project_id, user, db)

        if name is not None:
            project.name = name
        if description is not None:
            project.description = description

        await db.commit()
        await db.refresh(project)
        return project

    @staticmethod
    async def delete_project(db: AsyncSession, user: User, project_id: str) -> None:
        project = await get_project_or_403(project_id, user, db)

        stmt = select(Document.original_path).where(Document.project_id == project.id)
        doc_keys = list((await db.execute(stmt)).scalars().all())

        prefix = f"uploads/{user.id}/{project.id}/"
        await _delete_project_minio_objects(prefix=prefix, extra_keys=doc_keys)

        try:
            await qdrant_client.delete_collection(collection_name=project.qdrant_namespace)
        except Exception:
            pass

        await _delete_project_cache_keys(str(project.id))

        await db.execute(delete(Document).where(Document.project_id == project.id))
        await db.execute(delete(ChatSession).where(ChatSession.project_id == project.id))
        await db.delete(project)
        await db.commit()


async def _delete_project_minio_objects(prefix: str, extra_keys: list[str]) -> None:
    client = _minio_client()

    def _list_and_delete() -> None:
        token = None
        while True:
            kwargs = {"Bucket": settings.MINIO_BUCKET, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            contents = response.get("Contents", [])
            if contents:
                objects = [{"Key": obj["Key"]} for obj in contents]
                client.delete_objects(Bucket=settings.MINIO_BUCKET, Delete={"Objects": objects})

            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")

        for key in extra_keys:
            try:
                client.delete_object(Bucket=settings.MINIO_BUCKET, Key=key)
            except ClientError:
                continue

    await asyncio.to_thread(_list_and_delete)


async def _delete_project_cache_keys(project_id: str) -> None:
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        ask_pattern = f"ask:{project_id}:*"
        ask_keys: list[str] = []
        async for key in redis.scan_iter(match=ask_pattern):
            ask_keys.append(str(key))
        if ask_keys:
            await redis.delete(*ask_keys)

        await redis.delete(f"extract:{project_id}")
    finally:
        await redis.aclose()
