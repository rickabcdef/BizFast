"""本地 / 对象存储文件直出（system 路由）。

生产用对象存储（MinIO / 云 OSS）由 CDN 或预签名 URL 提供下载；
本地调试（STORAGE_BACKEND=local）时由本路由提供统一下载入口。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.storage import LocalStorage, get_storage

router = APIRouter(prefix="/api/files", tags=["system"])

_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
    "pdf": "application/pdf",
    "zip": "application/zip",
    "txt": "text/plain; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/{key:path}", summary="按存储 key 读取文件")
async def read_file(key: str):
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise HTTPException(status_code=404, detail="本地文件服务未启用")
    try:
        data = storage.read_bytes(key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    suffix = key.rsplit(".", 1)[-1].lower() if "." in key else "bin"
    return Response(content=data, media_type=_MIME.get(suffix, "application/octet-stream"))
