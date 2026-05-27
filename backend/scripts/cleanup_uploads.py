#!/usr/bin/env python3
"""Удалить просроченные uploaded_files (extracted_text). Запуск: python scripts/cleanup_uploads.py"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workers.maintenance_tasks import _cleanup_expired_uploads_async


def main() -> None:
    n = asyncio.run(_cleanup_expired_uploads_async())
    print(f"Deleted {n} expired upload(s)")


if __name__ == "__main__":
    main()
