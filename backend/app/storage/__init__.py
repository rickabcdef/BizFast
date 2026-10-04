"""对象存储适配。

- `s3`：S3 兼容（MinIO 本地 / 云 OSS 生产）。
- `local`：本地磁盘（无 MinIO 时本地调试用），由 `app.routers.files` 提供下载。

启动包文件（ZIP/PDF/Excel 等）云端永久保存，多端下载（M4-05）。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import resolved_storage_backend, settings


class LocalStorage:
    """本地磁盘存储：key 形如 `packages/<order>/D01.pdf`。"""

    backend = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.replace("\\", "/").lstrip("/")
        path = (self.root / safe).resolve()
        if not str(path).startswith(str(self.root)):
            raise ValueError("illegal storage key")
        return path

    def save_bytes(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.public_url(key)

    def save_file(self, local_path: str, key: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, path)
        return self.public_url(key)

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def public_url(self, key: str) -> str:
        return f"{settings.local_storage_base_url.rstrip('/')}/{key.lstrip('/')}"

    def local_path(self, key: str) -> str:
        return str(self._path(key))


class S3Storage:
    """S3 兼容对象存储。"""

    backend = "s3"

    def __init__(self) -> None:
        import boto3

        self.bucket = settings.storage_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
        )

    def save_bytes(self, key: str, data: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return self.public_url(key)

    def save_file(self, local_path: str, key: str) -> str:
        self.client.upload_file(local_path, self.bucket, key)
        return self.public_url(key)

    def read_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def public_url(self, key: str) -> str:
        return f"{settings.storage_public_base.rstrip('/')}/{key.lstrip('/')}"

    def presigned(self, key: str, expires: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
        )


_storage = None


def get_storage():
    """返回存储单例（按配置选择 s3 / local，惰性初始化）。"""
    global _storage
    if _storage is None:
        if resolved_storage_backend() == "local":
            _storage = LocalStorage(settings.local_storage_dir)
        else:
            _storage = S3Storage()
    return _storage


# 兼容脚手架旧用法：`from app.storage import storage`
class _LazyStorage:
    def __getattr__(self, item):
        return getattr(get_storage(), item)


storage = _LazyStorage()
