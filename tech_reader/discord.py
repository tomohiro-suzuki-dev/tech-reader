"""Discord Webhook への投稿。"""

from __future__ import annotations

import requests

from .config import THEME_LABEL
from .models import Article

TIMEOUT = 20

THEME_COLOR = {
    "ai": 0x7C5CFF,  # 紫: 生成AI
    "work": 0x2E9E6B,  # 緑: 業務技術
}

REACTION_GUIDE = "🔥 深掘りしたい　🛠 業務で試す　📚 保管"


def post_article(webhook_url: str, article: Article, theme: str, age_days: int) -> str:
    parts = [article.source]
    if article.category:
        parts.append(article.category)
    parts.append(f"{article.published:%m/%d}")
    footer = "　|　".join(parts)
    if age_days > 0:
        footer += f"（{age_days}日前）"

    embed = {
        "title": article.title[:250],
        "url": article.url,
        "description": article.summary or "(概要なし)",
        "color": THEME_COLOR.get(theme, 0x5865F2),
        "footer": {"text": footer},
    }
    payload = {
        "content": f"**今日の1本 — {THEME_LABEL.get(theme, theme)}**\n{REACTION_GUIDE}",
        "embeds": [embed],
    }
    posted = _send(webhook_url, payload, wait=True)
    return (posted or {}).get("id", "")


def post_notice(webhook_url: str, message: str) -> None:
    """配信できなかった場合などの通知。無言で落ちる状態を作らないために使う。"""
    _send(webhook_url, {"content": f":warning: {message}"})


def _send(webhook_url: str, payload: dict, wait: bool = False) -> dict | None:
    """wait=True のとき、Discord は投稿したメッセージを返す。

    週次でリアクションを読むには message_id が要るため、配信時に受け取って
    履歴へ保存する。Webhook 自体は読み取りができないので、この機会を逃すと
    後からチャンネル全体を走査する羽目になる。
    """
    url = webhook_url + ("?wait=true" if wait else "")
    resp = requests.post(url, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    if not wait or not resp.content:
        return None
    return resp.json()
