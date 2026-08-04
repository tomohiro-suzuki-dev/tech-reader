"""配信履歴の読み書き。

同じ記事を二度配信しないこと、同じソースが連続しないことの判定に使う。
DBを持たず、リポジトリ内のJSONをGitHub Actionsがコミットして永続化する。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

MAX_RECORDS = 500


class History:
    def __init__(self, path: Path):
        self.path = path
        self.records: list[dict] = []
        if path.exists():
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            self.records = data.get("delivered", [])

    @property
    def delivered_urls(self) -> set[str]:
        return {r["url"] for r in self.records}

    def recent_sources(self, count: int) -> list[str]:
        """直近 count 回の配信で使ったソース名を、新しい順で返す。"""
        return [r["source"] for r in self.records[-count:]][::-1]

    def delivered_on(self, date_str: str) -> dict | None:
        """指定日（YYYY-MM-DD）に配信済みならその記録を返す。"""
        for record in reversed(self.records):
            if record.get("delivered_at", "").startswith(date_str):
                return record
        return None

    def add(self, record: dict) -> None:
        self.records.append(record)
        self.records = self.records[-MAX_RECORDS:]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"updated_at": datetime.now().astimezone().isoformat(), "delivered": self.records}
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
