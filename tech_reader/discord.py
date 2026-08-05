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


def post_article(webhook_url: str, article: Article, theme: str, age_days: int) -> None:
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
    _send(webhook_url, payload)


def post_notice(webhook_url: str, message: str) -> None:
    """配信できなかった場合などの通知。無言で落ちる状態を作らないために使う。"""
    _send(webhook_url, {"content": f":warning: {message}"})


def _send(webhook_url: str, payload: dict) -> None:
    resp = requests.post(webhook_url, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
