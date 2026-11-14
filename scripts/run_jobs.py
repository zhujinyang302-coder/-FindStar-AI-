"""调度任务 CLI。

用法：
    python scripts/run_jobs.py --once
    python scripts/run_jobs.py          # 常驻轮询（多实例部署时由外部 cron 调用 --once）
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.core.config import settings  # noqa: E402
from app.jobs import scheduler  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="只执行一轮")
    args = parser.parse_args()
    if args.once:
        print("[jobs]", scheduler.run_once())
        return
    print("[jobs] 常驻轮询，间隔", settings.match_job_scan_seconds, "秒")
    try:
        while True:
            print("[jobs]", scheduler.run_once())
            time.sleep(settings.match_job_scan_seconds)
    except KeyboardInterrupt:
        print("[jobs] stopped")


if __name__ == "__main__":
    main()