"""各ソースから記事一覧を取得する。

1つのソースが落ちても配信全体を止めないため、例外はソース単位で握りつぶし、
警告として呼び出し側に返す。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from .config import JST, Source
from .models import Article

logger = logging.getLogger(__name__)

USER_AGENT = "tech-reader/1.0 (+https://github.com/tomohiro-suzuki-dev/tech-reader)"
TIMEOUT = 20

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# 例: "Jul 24, 2026"
_DATE_RE = re.compile(r"\b([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})\b")
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1
    )
}


def clean_text(raw: str, limit: int = 220) -> str:
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", raw or "")).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def fetch(source: Source) -> tuple[list[Article], str | None]:
    """1ソース分の記事を取得する。

    Returns:
        (記事リスト, 警告メッセージ or None)
    """
    try:
        if source.fetcher == "anthropic":
            articles = _fetch_anthropic(source)
        else:
            articles = _fetch_feed(source)
    except Exception as exc:  # ソース障害で配信全体を止めない
        logger.warning("failed to fetch %s: %s", source.name, exc)
        return [], f"{source.name}: {type(exc).__name__} {exc}"

    if not articles:
        return [], f"{source.name}: 記事0件"
    return articles, None


def _fetch_feed(source: Source) -> list[Article]:
    resp = requests.get(source.url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)

    articles: list[Article] = []
    for entry in parsed.entries:
        url = (entry.get("link") or "").strip()
        title = clean_text(entry.get("title", ""), limit=200)
        if not url or not title:
            continue
        published = _entry_datetime(entry)
        if published is None:
            continue
        summary = clean_text(entry.get("summary", "") or entry.get("description", ""))
        articles.append(Article(title, url, source.name, published, summary))
    return articles


def _entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            # feedparser の *_parsed は UTC の time.struct_time
            return datetime(*value[:6], tzinfo=timezone.utc).astimezone(JST)
    return None


def _fetch_anthropic(source: Source) -> list[Article]:
    """Anthropic のニュース一覧をHTMLからパースする。

    RSSが提供されていないための代替手段。カード単位の <a> にタイトル・カテゴリ・
    日付がテキストとして並ぶため、日付とカテゴリを除いた残りをタイトル・概要とする。
    """
    resp = requests.get(source.url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    seen: set[str] = set()
    articles: list[Article] = []
    for anchor in soup.select('a[href^="/news/"]'):
        href = anchor.get("href", "")
        url = "https://www.anthropic.com" + href
        if url in seen:
            continue

        parts = [clean_text(t, limit=300) for t in anchor.stripped_strings]
        parts = [p for p in parts if p]
        published = _extract_date(parts)
        if published is None:
            continue

        texts, labels = _split_card(parts)
        if not texts:
            continue
        title = texts[0]
        rest = texts[1:]
        summary = clean_text(max(rest, key=len)) if rest else ""
        category = labels[0] if labels else ""

        seen.add(url)
        articles.append(Article(title, url, source.name, published, summary, category))
    return articles


def _split_card(parts: list[str]) -> tuple[list[str], list[str]]:
    """カード内のテキスト片を (本文系, カテゴリ系) に分ける。

    タイトルの出現位置はカードによってカテゴリの前後に揺れるため、長さや位置では
    判定できない。ラベルらしきものを取り除いた残りのDOM順先頭をタイトルとして扱う。

    Returns:
        (日付・ラベルを除いたテキスト片, カテゴリ候補)
    """
    body = [p for p in parts if not _DATE_RE.search(p)]
    texts = [p for p in body if not _is_label(p)]
    labels = [p for p in body if _is_label(p) and p.lower() not in _CTA_LABELS]

    if not texts:
        # タイトルが短すぎてラベルと区別できなかった場合の保険。
        # 既知のカテゴリ名だけを除いて拾い直し、タイトルを失わないようにする。
        texts = [p for p in body if p.lower() not in _KNOWN_LABELS]
        labels = [p for p in body if p.lower() in _KNOWN_LABELS and p.lower() not in _CTA_LABELS]
    return texts, labels


# Anthropic のカードに現れるカテゴリ表記。タイトルと区別するために除外する。
_KNOWN_LABELS = {
    "announcements",
    "product",
    "policy",
    "research",
    "societal impacts",
    "interpretability",
    "alignment",
    "company news",
    "economic research",
    "events",
    "featured",
    "news",
    "read more",
    "learn more",
}

# ラベルとして除外はするが、カテゴリではないもの（カード内のCTA文言）。
_CTA_LABELS = {"read more", "learn more", "featured"}


def _is_label(text: str) -> bool:
    """カテゴリ表記らしき短い文字列か判定する。"""
    if text.lower() in _KNOWN_LABELS:
        return True
    # 既知リスト外のカテゴリが増えても拾えるよう、2語以内かつ24文字以内を保険で除外する
    return len(text) <= 24 and len(text.split()) <= 2


def _extract_date(parts: list[str]) -> datetime | None:
    for part in parts:
        match = _DATE_RE.search(part)
        if match:
            month = _MONTHS.get(match.group(1))
            if not month:
                continue
            return datetime(int(match.group(3)), month, int(match.group(2)), tzinfo=JST)
    return None


# 記事ページのメタ情報にサイト共通の定型文が入るソースがある（Anthropic は13件中2件）。
# 定型文を概要として配信しないよう、この文で始まる場合は本文へフォールバックする。
# 「Anthropic is」だけで判定すると "Anthropic is sharing a focused call…" のような
# 正当な概要まで捨ててしまうため、フレーズ全体で一致を見る（実データで確認済み）。
_BOILERPLATE_PREFIXES = ("anthropic is an ai safety and research company",)

# 本文フォールバック時に概要とみなす段落の最小文字数。見出しや注記を拾わないための下限。
MIN_PARAGRAPH_LEN = 60


def backfill_summary(article: Article) -> str:
    """記事ページを1回だけ取得して概要を補う。取得できなければ空文字を返す。

    一覧に概要が載らないソース向け。配信する1件にだけ呼ぶ前提のため、
    増えるリクエストは1回で済む。
    """
    try:
        resp = requests.get(article.url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:  # 概要が無いだけで配信は続ける
        logger.warning("failed to backfill summary %s: %s", article.url, exc)
        return ""

    for attrs in ({"property": "og:description"}, {"name": "description"}):
        tag = soup.find("meta", attrs=attrs)
        text = clean_text(tag.get("content", "") if tag else "")
        if text and not _is_boilerplate(text):
            return text

    for paragraph in soup.find_all("p"):
        text = clean_text(paragraph.get_text(" "))
        if len(text) >= MIN_PARAGRAPH_LEN:
            return text
    return ""


def _is_boilerplate(text: str) -> bool:
    lowered = text.lower()
    return any(lowered.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES)


def collect(sources: list[Source], now: datetime, max_age_days: int) -> tuple[list[tuple[Source, Article]], list[str]]:
    """複数ソースをまとめて取得し、期間内の記事だけを返す。"""
    cutoff = now - timedelta(days=max_age_days)
    results: list[tuple[Source, Article]] = []
    warnings: list[str] = []

    for source in sources:
        articles, warning = fetch(source)
        if warning:
            warnings.append(warning)
        for article in articles:
            if article.published >= cutoff:
                results.append((source, article))
    return results, warnings
