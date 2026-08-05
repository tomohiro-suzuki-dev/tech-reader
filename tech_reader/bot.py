"""Discord Bot Token を使った REST 操作。

Webhook では読み取りができないため、リアクションの事前付与と週次の読み取りは
Bot Token で行う。Gateway に常駐せず REST だけを使うのは、GitHub Actions の
実行時間内で完結させ、常駐サーバーの費用をゼロに保つため。

配信は引き続き Webhook が担当する（discord.py）。ここが失敗しても記事の配信自体は
止まらないよう、呼び出し側は例外を握りつぶしてよい設計にしている。
"""

from __future__ import annotations

import logging
import time
from urllib.parse import quote

import requests

API_BASE = "https://discord.com/api/v10"
TIMEOUT = 20
MAX_RETRIES = 3

logger = logging.getLogger(__name__)


class DiscordAPIError(RuntimeError):
    pass


def add_reactions(token: str, channel_id: str, message_id: str, emojis: list[str]) -> None:
    """メッセージに絵文字を事前付与する。押す側の操作を1タップにするため。"""
    for emoji in emojis:
        path = f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji)}/@me"
        _request(token, "PUT", path)


def get_message(token: str, channel_id: str, message_id: str) -> dict | None:
    """1件のメッセージを取得する。削除済みなら None。"""
    try:
        return _request(token, "GET", f"/channels/{channel_id}/messages/{message_id}")
    except DiscordAPIError as exc:
        if "404" in str(exc):
            logger.warning("メッセージが見つからない（削除済み?）: %s", message_id)
            return None
        raise


def list_messages(token: str, channel_id: str, limit: int = 100) -> list[dict]:
    """チャンネルの直近メッセージを取得する。message_id を持たない古い記録の
    遡及取込に使う。"""
    return _request(token, "GET", f"/channels/{channel_id}/messages?limit={limit}") or []


def get_thread_replies(token: str, message: dict) -> list[str]:
    """メッセージに紐づくスレッドの返信本文を古い順で返す。

    スレッドの開始メッセージ自体（＝配信した記事）は返信ではないので除く。
    """
    thread = message.get("thread")
    if not thread:
        return []

    replies = _request(token, "GET", f"/channels/{thread['id']}/messages?limit=50") or []
    texts = []
    for reply in reversed(replies):  # Discord は新しい順で返す
        if reply.get("id") == thread.get("id"):
            continue
        if reply.get("author", {}).get("bot"):
            continue
        content = (reply.get("content") or "").strip()
        if content:
            texts.append(content)
    return texts


def reacted_emojis(message: dict) -> list[str]:
    """1回以上押されたリアクションの絵文字名を返す。

    Bot が事前付与した分は count=1 かつ me=True になるため、それだけの
    リアクションは「押されていない」とみなす。
    """
    result = []
    for reaction in message.get("reactions") or []:
        name = reaction.get("emoji", {}).get("name") or ""
        count = reaction.get("count", 0)
        # 事前付与のみ（Bot の1件だけ）なら未押下
        if reaction.get("me") and count <= 1:
            continue
        if count >= 1 and name:
            result.append(name)
    return result


def message_link(guild_id: str, channel_id: str, message_id: str) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


def _request(token: str, method: str, path: str) -> dict | list | None:
    """レート制限（429）だけリトライする。それ以外の失敗は即例外にする。"""
    headers = {"Authorization": f"Bot {token}", "User-Agent": "tech-reader/1.0"}

    for attempt in range(MAX_RETRIES):
        resp = requests.request(method, API_BASE + path, headers=headers, timeout=TIMEOUT)

        if resp.status_code == 429:
            wait = float(resp.headers.get("Retry-After", resp.json().get("retry_after", 1)))
            logger.warning("レート制限。%.1f秒待機 (%d/%d)", wait, attempt + 1, MAX_RETRIES)
            time.sleep(min(wait, 10) + 0.1)
            continue

        if resp.status_code == 204 or not resp.content:
            return None
        if not resp.ok:
            raise DiscordAPIError(f"{method} {path} -> {resp.status_code} {resp.text[:200]}")
        return resp.json()

    raise DiscordAPIError(f"{method} {path} -> レート制限が解消しなかった")
