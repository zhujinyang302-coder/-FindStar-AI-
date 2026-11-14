"""数据库初始化脚本（显式命令执行迁移）。

用法：
    python scripts/init_db.py

不依赖应用启动时自动重建数据库；生产环境通过 Alembic 迁移受控变更。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.core.config import settings  # noqa: E402


def main() -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    print(f"[init_db] 迁移完成，数据库：{settings.database_url}")


if __name__ == "__main__":
    main()