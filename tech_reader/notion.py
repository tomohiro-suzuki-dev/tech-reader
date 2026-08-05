"""Notion ナレッジDBへの転記。

「tech-reader ナレッジDB」に1記事＝1ページとして追加する。
人間の作業をゼロにするのが Phase 2 の目的なので、失敗しても静かに終わらせず
呼び出し側が Discord へ通知できるよう例外を投げる。
"""

from __future__ import annotations

import logging

import requests

API_BASE = "https://api.notion.com/v1"
# 2022-06-28 は長期にわたり提供されている安定版。新しい版は parent の指定方法が
# data_source_id に変わるため、意図せず壊れないようここで固定する。
NOTION_VERSION = "2022-06-28"
TIMEOUT = 20

# Notion のテキストプロパティは1つのリッチテキストあたり2000文字まで。
TEXT_LIMIT = 1900

logger = logging.getLogger(__name__)


class NotionError(RuntimeError):
    pass


def create_page(token: str, database_id: str, record: dict, tags: list[str], memo: str, link: str) -> str:
    """記事1件をDBへ追加し、作成されたページIDを返す。"""
    properties = {
        "記事名": {"title": [{"text": {"content": record["title"][:1900]}}]},
        "URL": {"url": record["url"]},
        "テーマ": _select(_theme_label(record.get("theme"))),
        "ソース": _select(record.get("source")),
        "カテゴリ": _select(record.get("category")),
        "概要": _rich_text(record.get("summary", "")),
        "メモ": _rich_text(memo),
        "タグ": {"multi_select": [{"name": tag} for tag in tags]},
        "公開日": _date(record.get("published")),
        "配信日": _date(record.get("delivered_at")),
        "状態": _select("未着手"),
        "Discord": {"url": link or None},
    }
    payload = {
        "parent": {"database_id": database_id},
        "properties": {k: v for k, v in properties.items() if v is not None},
    }

    resp = requests.post(
        f"{API_BASE}/pages",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise NotionError(f"ページ作成に失敗: {resp.status_code} {resp.text[:300]}")
    return resp.json().get("id", "")


_THEME_LABEL = {"ai": "生成AI", "work": "業務技術"}


def _theme_label(theme: str | None) -> str:
    return _THEME_LABEL.get(theme or "", "")


def _select(value: str | None) -> dict | None:
    """空文字のときはプロパティごと省く。空の select を送るとAPIが400を返すため。"""
    if not value:
        return None
    return {"select": {"name": value}}


def _rich_text(value: str) -> dict:
    return {"rich_text": [{"text": {"content": (value or "")[:TEXT_LIMIT]}}] if value else []}


def _date(iso: str | None) -> dict | None:
    if not iso:
        return None
    # history.json は ISO 8601（タイムゾーン付き）で保存している。日付だけを使う。
    return {"date": {"start": iso[:10]}}
