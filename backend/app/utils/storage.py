from __future__ import annotations

import asyncio
from typing import Final

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import settings


class StorageClient:
    def __init__(self) -> None:
        scheme = "https" if settings.MINIO_USE_SSL else "http"
        endpoint_url = f"{scheme}://{settings.MINIO_ENDPOINT}"

        self._bucket: Final[str] = settings.MINIO_BUCKET
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.MINIO_ROOT_USER,
            aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
            use_ssl=settings.MINIO_USE_SSL,
            region_name="us-east-1",
            config=Config(signature_version="s3v4"),
        )
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchBucket", "NotFound"}:
                self._client.create_bucket(Bucket=self._bucket)
                return
            raise

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
        body = response["Body"]
        try:
            return await asyncio.to_thread(body.read)
        finally:
            body.close()

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise


storage = StorageClient()
