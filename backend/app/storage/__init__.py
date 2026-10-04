"""对象存储适配（S3 兼容：MinIO 本地 / 云 OSS 生产）。

启动包文件（ZIP/PDF/Excel 等）云端永久保存，多端下载（M4-05）。
"""
from __future__ import annotations

import boto3

from app.core.config import settings


class StorageClient:
    def __init__(self) -> None:
        self.bucket = settings.storage_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
        )

    def upload(self, local_path: str, key: str) -> str:
        self.client.upload_file(local_path, self.bucket, key)
        return f"{settings.storage_public_base}/{key}"

    def presigned(self, key: str, expires: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
        )


storage = StorageClient()
