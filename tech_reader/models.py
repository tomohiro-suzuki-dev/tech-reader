"""ソース間で形式が異なる記事データを1つの型に正規化する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    title: str
    url: str
    source: str
    published: datetime  # tz-aware (JST)
    summary: str = ""
    category: str = ""  # ソース側が付けている分類。取得できた場合のみ入る

    def to_record(self, theme: str, delivered_at: datetime) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "source": self.source,
            "category": self.category,
            "theme": theme,
            "published": self.published.isoformat(),
            "delivered_at": delivered_at.isoformat(),
        }
