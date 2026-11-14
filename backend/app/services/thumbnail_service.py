"""水印缩略图生成。

缩略图最长边 ≤ thumbnail_max_edge，叠加平台水印与候选公开标识，
绝不包含用户身份信息。原图 key 不进入候选响应。
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _thumb_root() -> Path:
    root = Path(settings.upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def generate_thumbnail(
    source: Path, *, watermark: str | None = None, suffix: str = ".jpg"
) -> str | None:
    """生成最长边受限的水印缩略图，返回缩略图 object_key；失败返回 None。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:  # noqa: BLE001
        logger.warning("pillow unavailable, skip thumbnail")
        return None

    try:
        with Image.open(source) as raw:
            image = raw.convert("RGB")
            image.thumbnail(
                (settings.thumbnail_max_edge, settings.thumbnail_max_edge)
            )
            draw = ImageDraw.Draw(image)
            text = watermark or settings.watermark_text
            try:
                font = ImageFont.load_default()
            except Exception:  # noqa: BLE001
                font = None
            width, height = image.size
            margin = 6
            draw.rectangle(
                [0, height - 22, width, height], fill=(0, 0, 0, 120)
            )
            draw.text((margin, max(0, height - 20)), text, fill=(255, 255, 255), font=font)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=82)
            key = f"thumb_{uuid.uuid4().hex}{suffix}"
            (_thumb_root() / key).write_bytes(buffer.getvalue())
            return key
    except Exception as exc:  # noqa: BLE001
        logger.warning("thumbnail generation failed: %s", type(exc).__name__)
        return None


def thumb_url(thumb_key: str | None) -> str | None:
    if not thumb_key:
        return None
    return f"/api/v1/images/{thumb_key}"