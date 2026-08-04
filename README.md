# tech-reader

技術トレンドのインプットを習慣化し、四半期ごとのアウトプット（技術記事）へ変換するための個人用パイプラインです。

## 解決する課題

「新技術をキャッチアップする」という目標は、以下の理由で継続に失敗します。

1. **起動コスト** — 読む対象を毎回自分で探すところから始まる
2. **出力コスト** — 読んだ内容を整理・記録する作業が重い
3. **意志依存** — 忙しい時期に真っ先に後回しになり、止まったことにも気づけない

本ツールは「意志が続かない前提で成立すること」を設計制約とし、上記3点を仕組みで潰します。

## 設計

| 段階 | 頻度 | 人間の操作 |
|---|---|---|
| インプット | 平日 5:00 自動配信 | 通勤時に3分読む |
| 記録 | 刺さった時のみ | 絵文字を1タップ（＋任意でスレッドに一言） |
| 蓄積 | 週次・全自動 | なし |
| 変換 | 四半期 | 1テーマを検証して記事化 |
| 自己点検 | 週次・自動 | なし（2週連続ゼロで警告） |

### インプット

GitHub Actions が平日 5:00 JST に RSS を取得し、Discord へ「今日の1本」を配信します。

- 生成AI領域: 月・水・金（週3本）
- 業務技術領域（Java / PostgreSQL / アーキテクチャ等）: 火・木（週2本）

読む対象を選ぶ工程を設計から排除するため、配信は1日1本に限定します。英語記事は翻訳せず原文のまま配信します。

### 記録

Discord のメッセージへのリアクションが、そのままメタデータになります。

| 絵文字 | 意味 |
|---|---|
| 🔥 | 深掘りしたい（記事化候補） |
| 🛠 | 業務で試す |
| 📚 | 知識として保管 |

着想が湧いた場合のみスレッドに一言残します。スレッド返信があるメッセージは、リアクションの有無に関わらず蓄積対象とします。

### 蓄積

週次で Discord Bot がリアクション付きメッセージを抽出し、Notion のナレッジDBへ自動転記します。人間の作業はゼロで、多忙期でも記録が途切れません。

### 変換

四半期に1回、🔥タグの中から1テーマを選んで実際に検証し、技術記事として公開します。

## 技術スタック

- Python 3.11
- GitHub Actions（定期実行）
- Discord Webhook（配信）／ Discord Bot API（リアクション取得）
- Notion API（蓄積）

## ロードマップ

- [x] Phase 1: RSS → Discord 配信
- [ ] Phase 2: Discord → Notion 週次自動転記
- [ ] Phase 3: 週次サマリー配信 + 2週連続ゼロ警告

Phase 2 は後から実装しても情報を失いません。Discord 上のリアクションは残り続けるため、遡って取り込めます。

## 構成（Phase 1）

```
tech_reader/
  config.py    配信ソース・曜日別テーマ・スコア係数の定義
  feeds.py     RSS/Atom 取得と Anthropic の HTML パース
  selector.py  「今日の1本」の選定
  discord.py   Webhook への投稿
  history.py   配信履歴（data/history.json）の読み書き
  main.py      エントリポイント
  check.py     全ソースの疎通確認
.github/workflows/daily.yml  平日 5:00 JST の定期実行
```

### 情報源

| テーマ | ソース |
|---|---|
| 生成AI（月・水・金） | Anthropic News / Simon Willison / OpenAI News / Zenn 生成AI / Zenn LLM / Hugging Face Blog |
| 業務技術（火・木） | Publickey / Martin Fowler / InfoQ Japan / Zenn アーキテクチャ / Zenn Java / Zenn PostgreSQL / PostgreSQL News / はてブ テクノロジー |

Anthropic のみ RSS が提供されていないため、ニュース一覧ページを HTML パースしています（2026-08-05 時点）。

### 選定ロジック

`スコア = ソース重み × 0.85^(経過日数) × 直近配信ソースの減点`

配信済みURL（`data/history.json`）は候補から除外します。直近4回に配信したソースは 0.25〜0.85 倍に減点し、同じソースが続かないようにしています。21日より古い記事は対象外です。

候補が1件も見つからない場合は、無言で終わらず Discord に警告を投稿します。ソースのURL変更に気づけないことが、このパイプラインの最大の故障モードだからです。

## セットアップ

1. Discord に `#tech-reader` と `#idea` の2チャンネルを作成する
2. `#tech-reader` のチャンネル設定 → 連携サービス → ウェブフックを作成し、URLをコピーする
3. GitHub リポジトリの Settings → Secrets and variables → Actions で `DISCORD_WEBHOOK_URL` を登録する
4. Actions タブから `Daily Delivery` を手動実行し、投稿を確認する

## ローカル実行

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python -m tech_reader.check                 # 全ソースの疎通確認
.venv/bin/python -m tech_reader.main --dry-run        # 選定結果のみ表示（投稿しない）
.venv/bin/python -m tech_reader.main --dry-run --theme work
DISCORD_WEBHOOK_URL=... .venv/bin/python -m tech_reader.main   # 実際に配信
```

## 既知の制約

- Webhook では投稿に絵文字を事前付与できません（Bot Token が必要）。Phase 1 の間、リアクションは手動で付けてください。Phase 2 で Bot を導入する際に事前付与へ切り替えます。
- 祝日は判定していません。設計上「未読は溜めずに捨てる」方針のため、Phase 1 では対応を見送っています。
- GitHub Actions の cron は 15〜30分の遅延が発生します。5:00 配信・6:20 出発で 80分の余裕を確保しています。
