"""tech-reader Phase 1: RSS/HTML から「今日の1本」を選び Discord へ配信する。

使い方:
    python -m tech_reader.main                # 配信（DISCORD_WEBHOOK_URL が必要）
    python -m tech_reader.main --dry-run      # 配信せず選定結果だけ表示
    python -m tech_reader.main --theme work   # 曜日を無視してテーマを指定
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from . import discord, feeds
from .config import JST, MAX_AGE_DAYS, SOURCE_COOLDOWN, THEME_BY_WEEKDAY, THEME_LABEL, sources_for
from .history import History
from .selector import select

HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "history.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("tech_reader")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="今日の1本を Discord へ配信する")
    parser.add_argument("--dry-run", action="store_true", help="Discord へ投稿せず結果を表示する")
    parser.add_argument("--theme", choices=["ai", "work"], help="曜日による自動判定を上書きする")
    parser.add_argument("--force", action="store_true", help="同日に配信済みでも再配信する")
    args = parser.parse_args(argv)

    now = datetime.now(JST)
    theme = args.theme or THEME_BY_WEEKDAY.get(now.weekday())
    if theme is None:
        logger.info("土日のため配信しない (%s)", now.strftime("%Y-%m-%d %a"))
        return 0

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url and not args.dry_run:
        logger.error("DISCORD_WEBHOOK_URL が未設定")
        return 1

    history = History(HISTORY_PATH)
    today = now.strftime("%Y-%m-%d")
    already = history.delivered_on(today)
    if already and not args.force:
        logger.info("本日は配信済みのためスキップ: %s", already["title"])
        return 0

    sources = sources_for(theme)
    logger.info("%s テーマ / ソース %d件を取得", THEME_LABEL[theme], len(sources))
    pairs, warnings = feeds.collect(sources, now, MAX_AGE_DAYS)
    for warning in warnings:
        logger.warning("取得失敗: %s", warning)
    logger.info("候補記事 %d件", len(pairs))

    candidate = select(pairs, now, history.delivered_urls, history.recent_sources(SOURCE_COOLDOWN))

    if candidate is None:
        message = (
            f"{today} の配信対象が見つかりませんでした（テーマ: {THEME_LABEL[theme]}）。"
            + (" 取得失敗: " + " / ".join(warnings) if warnings else "")
        )
        logger.error(message)
        if not args.dry_run:
            discord.post_notice(webhook_url, message)
        return 1

    article = candidate.article
    logger.info("選定: [%s] %s (score=%.3f, %s)", article.source, article.title, candidate.score, article.url)

    # 一覧に概要が無いソース向けの補完。配信する1件だけを対象にする。
    if not article.summary:
        article.summary = feeds.backfill_summary(article)
        logger.info("概要を記事ページから補完: %s", "成功" if article.summary else "取得できず")

    if args.dry_run:
        print(f"\nテーマ : {THEME_LABEL[theme]}")
        print(f"ソース : {article.source}" + (f"（{article.category}）" if article.category else ""))
        print(f"タイトル: {article.title}")
        print(f"URL    : {article.url}")
        print(f"公開日 : {article.published:%Y-%m-%d}（{candidate.age_days}日前）")
        print(f"概要   : {article.summary}")
        return 0

    discord.post_article(webhook_url, article, theme, candidate.age_days)
    history.add(article.to_record(theme, now))
    history.save()
    logger.info("配信完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
