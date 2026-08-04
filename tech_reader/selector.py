"""その日に配信する「今日の1本」を選ぶ。

選定の方針:
  1. 未配信であること（必須）
  2. 新しいほど高スコア（RECENCY_DECAY で日数減衰）
  3. ソースの重み（config.Source.weight）を掛ける
  4. 直近の配信で使ったソースは減点し、同じソースの連続を避ける
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .config import RECENCY_DECAY, SOURCE_COOLDOWN, Source
from .models import Article


@dataclass
class Candidate:
    article: Article
    score: float
    age_days: int


def select(
    pairs: list[tuple[Source, Article]],
    now: datetime,
    delivered_urls: set[str],
    recent_sources: list[str],
) -> Candidate | None:
    """スコア最大の1件を返す。候補がなければ None。"""
    penalties = _source_penalties(recent_sources)

    best: Candidate | None = None
    for source, article in pairs:
        if article.url in delivered_urls:
            continue

        age_days = max((now - article.published).days, 0)
        score = source.weight * (RECENCY_DECAY**age_days) * penalties.get(source.name, 1.0)

        if best is None or score > best.score:
            best = Candidate(article, score, age_days)
    return best


def _source_penalties(recent_sources: list[str]) -> dict[str, float]:
    """直近に配信したソースほど強く減点する係数を作る。

    recent_sources は新しい順。直前の配信ソースは 0.25 倍、以降 0.5, 0.7… と回復する。
    """
    ladder = [0.25, 0.5, 0.7, 0.85]
    penalties: dict[str, float] = {}
    for index, name in enumerate(recent_sources[:SOURCE_COOLDOWN]):
        factor = ladder[index] if index < len(ladder) else 1.0
        # 同一ソースが複数回現れた場合は最も強い減点を採用する
        penalties[name] = min(penalties.get(name, 1.0), factor)
    return penalties
