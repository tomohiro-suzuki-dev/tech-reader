"""全ソースの疎通確認。

このパイプラインで最も壊れやすいのはソース側のURL変更・提供終了なので、
配信が止まる前に気づけるよう単体で実行できるようにしている。

    python -m tech_reader.check
"""

from __future__ import annotations

import sys
from datetime import datetime

from .config import JST, SOURCES, THEME_LABEL
from .feeds import fetch


def main() -> int:
    now = datetime.now(JST)
    failed = 0

    for source in SOURCES:
        articles, warning = fetch(source)
        if warning:
            failed += 1
            print(f"NG   {source.name:22} {warning}")
            continue

        latest = max(articles, key=lambda a: a.published)
        age = (now - latest.published).days
        status = "OK " if age <= 14 else "OLD"
        if status == "OLD":
            failed += 1
        print(
            f"{status}  {source.name:22} {THEME_LABEL[source.theme]:5} "
            f"{len(articles):3}件  最新 {latest.published:%Y-%m-%d}（{age}日前）"
        )

    print(f"\n{len(SOURCES)}ソース中 {failed}件が要確認")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
