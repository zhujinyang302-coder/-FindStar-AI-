"""图片上传服务：校验类型、大小、数量与文件签名。

- 文件名由服务端生成（UUID），绝不沿用用户文件名。
- 拒绝可执行文件与伪装格式（扩展名与实际签名不符）。
- 图片通过后端代理访问，禁止暴露底层存储直连地址。
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.response import (
    PayloadTooLargeError,
    ValidationError,
    UnsupportedMediaTypeError,
)

# 文件签名（magic bytes）
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),  # 需进一步校验 WEBP 标记
}

# 可执行文件签名（拒绝）
_EXECUTABLE_SIGNATURES = (b"MZ", b"\x7fELF", b"#!", b"\xca\xfe\xba\xbe")

_EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _sniff_mime(head: bytes) -> str | None:
    if head.startswith(_EXECUTABLE_SIGNATURES):
        return None
    for mime, sigs in _SIGNATURES.items():
        for sig in sigs:
            if head.startswith(sig):
                if mime == "image/webp" and head[8:12] != b"WEBP":
                    continue
                return mime
    return None


def _upload_root() -> Path:
    root = Path(settings.upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_image(file: UploadFile) -> tuple[str, str, int, str | None]:
    """校验并保存图片，返回 (object_key, mime_type, size_bytes, thumb_key)。"""
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in settings.allowed_image_extensions:
        raise UnsupportedMediaTypeError("不支持的图片格式（仅支持 JPG/JPEG/PNG/WebP）")

    content = file.file.read()
    size = len(content)
    if size == 0:
        raise ValidationError("上传文件为空")
    if size > settings.max_image_size_bytes:
        raise PayloadTooLargeError("图片过大，单张不得超过 5 MB")

    declared = (file.content_type or "").lower()
    if declared and declared not in settings.allowed_image_types:
        raise UnsupportedMediaTypeError("文件类型不支持")

    sniffed = _sniff_mime(content[:32])
    if sniffed is None:
        raise UnsupportedMediaTypeError("文件类型不支持（疑似可执行文件或伪装格式）")
    if sniffed != _EXT_TO_MIME.get(extension):
        raise UnsupportedMediaTypeError("文件扩展名与实际内容不符")

    object_key = f"{uuid.uuid4().hex}{extension}"
    target = _upload_root() / object_key
    target.write_bytes(content)

    thumb_key = None
    try:
        from app.services.thumbnail_service import generate_thumbnail

        thumb_key = generate_thumbnail(target)
    except Exception:  # noqa: BLE001
        thumb_key = None
    return object_key, sniffed, size, thumb_key


def resolve_path(object_key: str) -> Path:
    """解析 object_key 对应的受控路径，防止目录穿越。"""
    safe_name = Path(object_key).name
    if safe_name != object_key or not object_key:
        raise ValidationError("非法的图片标识")
    root = _upload_root()
    target = (root / safe_name).resolve()
    if root not in target.parents and target != root:
        raise ValidationError("非法的图片标识")
    return target


def stat_image(object_key: str) -> tuple[str, int]:
    """返回已保存图片的 (mime_type, size_bytes)，若不存在则抛错。"""
    path = resolve_path(object_key)
    if not path.is_file():
        raise ValidationError(f"图片不存在：{object_key}")
    mime = _EXT_TO_MIME.get(path.suffix.lower())
    if mime is None:
        raise UnsupportedMediaTypeError("图片类型不支持")
    return mime, path.stat().st_size