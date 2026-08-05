"""tech-reader Phase 2: Discord の反応を Notion へ週次転記する。

土曜 8:00 JST に GitHub Actions が実行する。リアクションかスレッド返信が
付いた記事だけを Notion のナレッジDBへ送り、無反応の記事は捨てる。
「読んだものを整理する作業」を人間から完全に外すのが目的。

使い方:
    python -m tech_reader.weekly              # 転記を実行
    python -m tech_reader.weekly --dry-run    # 転記せず対象だけ表示
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import bot, discord, notion
from .config import JST, REACTIONS, SYNC_WINDOW_DAYS
from .history import History

HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "history.json"

# 絵文字の異体字セレクタ。ソース上で見えないため定数にしている。
VARIATION_SELECTOR = "\ufe0f"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("tech_reader.weekly")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discord の反応を Notion へ転記する")
    parser.add_argument("--dry-run", action="store_true", help="Notion へ書き込まず対象を表示する")
    args = parser.parse_args(argv)

    env = _load_env(require_notion=not args.dry_run)
    if env is None:
        return 1

    history = History(HISTORY_PATH)
    now = datetime.now(JST)
    targets = _targets(history.records, now)
    logger.info("対象期間 %d日 / 未転記 %d件", SYNC_WINDOW_DAYS, len(targets))
    if not targets:
        logger.info("転記対象なし")
        return 0

    _backfill_message_ids(env["bot_token"], env["channel_id"], targets)

    synced, skipped, failed = 0, 0, []
    for record in targets:
        if not record.get("message_id"):
            logger.warning("message_id 不明のため転記できない: %s", record["title"][:40])
            failed.append(record["title"][:40])
            continue

        try:
            tags, memo = _read_reactions(env["bot_token"], env["channel_id"], record)
        except Exception as exc:
            logger.warning("Discord 読み取り失敗: %s (%s)", record["title"][:40], exc)
            failed.append(record["title"][:40])
            continue

        if not tags and not memo:
            skipped += 1
            continue

        label = f"[{'/'.join(tags) or 'メモのみ'}] {record['title'][:50]}"
        if args.dry_run:
            print(f"転記対象: {label}")
            if memo:
                print(f"    メモ: {memo[:120]}")
            synced += 1
            continue

        try:
            page_id = notion.create_page(
                env["notion_token"],
                env["database_id"],
                record,
                tags,
                memo,
                bot.message_link(env["guild_id"], env["channel_id"], record["message_id"])
                if env["guild_id"]
                else "",
            )
        except Exception as exc:
            logger.error("Notion 転記失敗: %s (%s)", record["title"][:40], exc)
            failed.append(record["title"][:40])
            continue

        record["notion_page_id"] = page_id
        record["synced_at"] = now.isoformat()
        synced += 1
        logger.info("転記: %s", label)

    if not args.dry_run:
        history.save()

    logger.info("転記 %d件 / 無反応 %d件 / 失敗 %d件", synced, skipped, len(failed))

    if failed and not args.dry_run and env["webhook_url"]:
        discord.post_notice(
            env["webhook_url"],
            f"週次転記で {len(failed)}件が失敗しました: " + " / ".join(failed[:5]),
        )
    return 1 if failed else 0


def _load_env(require_notion: bool) -> dict | None:
    """必要な認証情報を集める。足りなければ何を設定すべきか示して終わる。"""
    env = {
        "bot_token": os.environ.get("DISCORD_BOT_TOKEN", ""),
        "channel_id": os.environ.get("DISCORD_CHANNEL_ID", ""),
        "guild_id": os.environ.get("DISCORD_GUILD_ID", ""),
        "notion_token": os.environ.get("NOTION_TOKEN", ""),
        "database_id": os.environ.get("NOTION_DATABASE_ID", ""),
        "webhook_url": os.environ.get("DISCORD_WEBHOOK_URL", ""),
    }

    required = ["bot_token", "channel_id"] + (["notion_token", "database_id"] if require_notion else [])
    missing = [_ENV_NAME[key] for key in required if not env[key]]
    if missing:
        logger.error("環境変数が未設定: %s", ", ".join(missing))
        return None
    return env


_ENV_NAME = {
    "bot_token": "DISCORD_BOT_TOKEN",
    "channel_id": "DISCORD_CHANNEL_ID",
    "guild_id": "DISCORD_GUILD_ID",
    "notion_token": "NOTION_TOKEN",
    "database_id": "NOTION_DATABASE_ID",
}


def _targets(records: list[dict], now: datetime) -> list[dict]:
    """転記の対象を選ぶ。

    転記済み（notion_page_id あり）は除く。無反応の記事は「まだ押されていない
    だけ」の可能性があるため印を付けず、期間を過ぎたら自然に落とす。
    """
    cutoff = now - timedelta(days=SYNC_WINDOW_DAYS)
    targets = []
    for record in records:
        if record.get("notion_page_id"):
            continue
        delivered = record.get("delivered_at", "")
        try:
            if datetime.fromisoformat(delivered) >= cutoff:
                targets.append(record)
        except ValueError:
            continue
    return targets


def _backfill_message_ids(token: str, channel_id: str, targets: list[dict]) -> None:
    """message_id を持たない記録に、チャンネル走査で ID を埋める。

    Phase 1 で配信した分は message_id を保存していないため、この経路でのみ拾える。
    走査は1回きりで済ませ、対象がなければ実行しない。
    """
    pending = [r for r in targets if not r.get("message_id")]
    if not pending:
        return

    logger.info("message_id 未取得 %d件をチャンネル走査で補う", len(pending))
    try:
        messages = bot.list_messages(token, channel_id, limit=100)
    except Exception as exc:
        logger.warning("チャンネル走査に失敗: %s", exc)
        return

    by_url = {}
    for message in messages:
        for embed in message.get("embeds") or []:
            if embed.get("url"):
                by_url.setdefault(embed["url"], message["id"])

    for record in pending:
        message_id = by_url.get(record["url"])
        if message_id:
            record["message_id"] = message_id
            logger.info("  補完: %s", record["title"][:40])


def _read_reactions(token: str, channel_id: str, record: dict) -> tuple[list[str], str]:
    """1件分の反応を読む。

    Returns:
        (Notion のタグ名リスト, スレッド返信を連結したメモ)
    """
    message = bot.get_message(token, channel_id, record["message_id"])
    if message is None:
        return [], ""

    tags = []
    for emoji in bot.reacted_emojis(message):
        tag = REACTIONS.get(_normalize_emoji(emoji))
        if tag and tag not in tags:
            tags.append(tag)

    memo = "\n".join(bot.get_thread_replies(token, message))
    return tags, memo


def _normalize_emoji(name: str) -> str:
    """異体字セレクタ（U+FE0F）の有無で照合が外れるのを防ぐ。

    🛠 は 🛠️（U+1F6E0 U+FE0F）として送られることがあり、config.REACTIONS の
    表記と一致しなくなる。見えない文字なので定数で明示する。
    """
    return name.replace(VARIATION_SELECTOR, "")


if __name__ == "__main__":
    sys.exit(main())
