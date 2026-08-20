"""配信ソースとスケジュールの定義。

ソースを増減させたい場合はこのファイルだけを触れば済むようにしている。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# 曜日（Monday=0）とテーマの対応。月水金＝生成AI、火木＝業務技術。
THEME_BY_WEEKDAY = {
    0: "ai",
    1: "work",
    2: "ai",
    3: "work",
    4: "ai",
}

THEME_LABEL = {
    "ai": "生成AI",
    "work": "業務技術",
}

# 選定対象とする記事の最大経過日数。これより古い記事は配信しない。
MAX_AGE_DAYS = 21

# 1日の経過ごとにスコアへ掛ける減衰率。新しい記事ほど選ばれやすくする。
RECENCY_DECAY = 0.85

# 直近何回分の配信を「同一ソースの連続」とみなすか。
SOURCE_COOLDOWN = 4

# 本人にとって読む価値が低い記事のタイトルパターン。
# (1) 技術的な中身を伴わないニュース（人事・寄付・助成金・提携）
# (2) 入門・初学者向け記事（本人は現役エンジニアのため対象外）
# (3) 広告・PR記事
# Anthropic News の実データ13件で検証し、意図した4件だけに一致することを確認済み。
# カテゴリ（Product / Announcements 等）は Announcements に当たり外れが混在するため
# 判別に使えず、タイトルで判定している。
NOISE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bto join\b.{0,40}\bas\b",  # 「〜として入社」
        r"\bappoint(?:s|ed|ment)\b",
        r"\bdonat(?:e|es|ed|ing|ion)\b",
        r"\bresearch grants?\b|\bgrant program\b|\bapply for\b",
        r"\bpartnership\b|\bpartners with\b",
        r"(?:業務|資本)提携|人事異動|新役員|寄付",
        # --- 入門・初学者向け記事（2026-08-20 追加）---
        # Zenn のトピックフィードは初学者記事と実務記事が同じ流れに混ざる。
        # Zenn Java は20件中5件が初学者向けで、8/18 に「Java言語について2
        # (HelloWorld編)」を配信してしまった。ソース単位では分離できないため
        # タイトルで判定する（Anthropic の人事ニュースと同じ方針）。
        # 全14ソース228件で検証し、マッチ8件・誤検出0件を確認済み。
        r"初学者|初心者|入門|ゼロから(?:は|始|学)|基礎から",
        r"hello\s?world",
        # 括弧は全角・半角の両方が使われる（実データで両方確認）。
        # 「（基礎編）」は上級記事にも付くため対象にしない
        r"[（(](?:環境構築|導入|準備|インストール)編[）)]",
        # 「〜とは？」で始まる用語解説。前置きが長いものは解説記事ではないので除く
        r"^.{1,18}とは[？?]",
        # --- 広告・PR記事 ---
        r"［PR］|【PR】|\[PR\]|sponsored",
    )
]

# ノイズ判定に一致した記事へ掛ける係数。除外ではなく減点にとどめ、
# 他に候補が無い日は配信されるようにしている。
NOISE_PENALTY = 0.3

# Discord のリアクション絵文字と Notion のタグ名の対応。
# Bot が配信直後に事前付与し、週次でどれが押されたかを読んで転記する。
# 押す側の操作を1タップに保つため、選択肢は3つまでに絞っている。
REACTIONS = {
    "🔥": "🔥 深掘りしたい",
    "🛠": "🛠 業務で試す",
    "📚": "📚 保管",
}

# 週次転記の対象期間。土曜に走らせて月〜金の5本を拾う。取りこぼした週を
# 翌週に回収できるよう、1週間分ではなく余裕を持たせている。
SYNC_WINDOW_DAYS = 10


@dataclass(frozen=True)
class Source:
    """1つの情報源。

    Attributes:
        name: Discord に表示する名前。
        url: RSS/Atom のURL。fetcher="anthropic" の場合はHTMLページのURL。
        theme: "ai" または "work"。
        weight: 選定スコアの重み。読む価値が高いソースほど大きくする。
        fetcher: "feed"（RSS/Atom）または "anthropic"（HTMLパース）。
    """

    name: str
    url: str
    theme: str
    weight: float = 1.0
    fetcher: str = "feed"


SOURCES: list[Source] = [
    # --- 生成AI（月・水・金） ---
    # Anthropic は RSS を提供していないため HTML をパースする（2026-08-05 確認）
    Source("Anthropic News", "https://www.anthropic.com/news", "ai", 1.3, fetcher="anthropic"),
    # /atom/everything/ はリンク集・引用メモを含み中身が薄い記事が混ざるため、
    # 長文記事だけを流す /atom/entries/ を使う（2026-08-05 に everything から変更）
    Source("Simon Willison", "https://simonwillison.net/atom/entries/", "ai", 1.2),
    Source("OpenAI News", "https://openai.com/news/rss.xml", "ai", 1.1),
    Source("Zenn 生成AI", "https://zenn.dev/topics/生成ai/feed", "ai", 1.0),
    Source("Zenn LLM", "https://zenn.dev/topics/llm/feed", "ai", 0.9),
    Source("Hugging Face Blog", "https://huggingface.co/blog/feed.xml", "ai", 0.8),
    # --- 業務技術（火・木） ---
    Source("Publickey", "https://www.publickey1.jp/atom.xml", "work", 1.2),
    Source("Martin Fowler", "https://martinfowler.com/feed.atom", "work", 1.1),
    Source("InfoQ Japan", "https://feed.infoq.com/jp/", "work", 1.0),
    Source("Zenn アーキテクチャ", "https://zenn.dev/topics/architecture/feed", "work", 1.0),
    Source("Zenn Java", "https://zenn.dev/topics/java/feed", "work", 0.9),
    Source("Zenn PostgreSQL", "https://zenn.dev/topics/postgresql/feed", "work", 0.9),
    Source("PostgreSQL News", "https://www.postgresql.org/news.rss", "work", 0.8),
    Source("はてブ テクノロジー", "https://b.hatena.ne.jp/hotentry/it.rss", "work", 0.7),
]


def sources_for(theme: str) -> list[Source]:
    return [s for s in SOURCES if s.theme == theme]
