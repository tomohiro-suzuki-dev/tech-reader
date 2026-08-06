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
| インプット | 平日 4:00 自動配信 | 通勤時に3分読む |
| 記録 | 刺さった時のみ | 絵文字を1タップ（＋任意でスレッドに一言） |
| 蓄積 | 土曜 8:00 全自動 | なし |
| 変換 | 四半期 | 1テーマを検証して記事化 |
| 自己点検 | 週次・自動 | なし（2週連続ゼロで警告） |

### インプット

GitHub Actions が平日 4:00 JST に RSS を取得し、Discord へ「今日の1本」を配信します。

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

土曜 8:00 JST に GitHub Actions が Discord の反応を読み、Notion のナレッジDBへ自動転記します。人間の作業はゼロで、多忙期でも記録が途切れません。

リアクションもスレッド返信も無い記事は転記しません。DBを「自分が反応した記事」だけの状態に保つことが、四半期の記事執筆時に見返す価値を決めるためです。反応がまだの記事は10日間は対象に残り続けるため、週をまたいで押しても拾われます。

配信時に Discord のメッセージIDを履歴へ保存し、週次はそのIDを直接参照します。チャンネル全体を走査しないため、過去ログが増えても処理時間は変わりません。

### 変換

四半期に1回、🔥タグの中から1テーマを選んで実際に検証し、技術記事として公開します。

## 技術スタック

- Python 3.11
- GitHub Actions（定期実行）
- Discord Webhook（配信）／ Discord Bot API（リアクション取得）
- Notion API（蓄積）

## ロードマップ

- [x] Phase 1: RSS → Discord 配信
- [x] Phase 2: Discord → Notion 週次自動転記
- [ ] Phase 3: 週次サマリー配信 + 2週連続ゼロ警告

Phase 1 の期間に配信した記事（メッセージIDを保存していない分）も、チャンネルを走査して記事URLで突き合わせることで遡って取り込めます。

## 構成

```
tech_reader/
  config.py    配信ソース・曜日別テーマ・スコア係数・リアクション定義
  feeds.py     RSS/Atom 取得、Anthropic の HTML パース、概要の補完
  selector.py  「今日の1本」の選定
  discord.py   Webhook への投稿（配信）
  bot.py       Bot Token での REST 操作（リアクション付与・読み取り）
  notion.py    ナレッジDBへの転記
  history.py   配信履歴（data/history.json）の読み書き
  main.py      配信のエントリポイント
  weekly.py    週次転記のエントリポイント
  check.py     全ソースの疎通確認
.github/workflows/daily.yml   平日 4:00 JST の配信
.github/workflows/weekly.yml  土曜 8:00 JST の転記
```

Discord へは Webhook（配信）と Bot Token（リアクション・読み取り）の2経路でアクセスします。Bot 側が権限不足やトークン失効で落ちても記事の配信は止まらず、絵文字が事前付与されないだけに影響を抑えるためです。

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

### Phase 1（配信）

1. Discord に `#tech-reader` と `#idea` の2チャンネルを作成する
2. `#tech-reader` のチャンネル設定 → 連携サービス → ウェブフックを作成し、URLをコピーする
3. GitHub リポジトリの Settings → Secrets and variables → Actions で `DISCORD_WEBHOOK_URL` を登録する
4. Actions タブから `Daily Delivery` を手動実行し、投稿を確認する

### Phase 2（リアクション付与と Notion 転記）

**Discord Bot**

1. [Discord Developer Portal](https://discord.com/developers/applications) → New Application で `tech-reader` を作成
2. Bot タブ → Reset Token でトークンを取得する（再表示できないためこの場でコピーする）
3. 同じ Bot タブの Privileged Gateway Intents で **Message Content Intent** を ON にする（スレッド返信の本文取得に必要）
4. OAuth2 → URL Generator で scope に `bot`、権限に `View Channels` / `Read Message History` / `Add Reactions` を選び、生成されたURLで自分のサーバーへ招待する
5. Discord の設定 → 詳細設定 → 開発者モードを ON にし、`#tech-reader` を右クリック → チャンネルIDをコピー（サーバー名を右クリックすればサーバーIDも取得できる）

**Notion**

6. [My integrations](https://www.notion.so/my-integrations) → New integration で内部インテグレーションを作成し、シークレット（`ntn_` で始まる）を取得する
7. ナレッジDBのページを開き、右上の … → 接続 → 作成したインテグレーションを追加する（これを忘れるとAPIから見えない）
8. DBのURLの `/p/` 以降32桁がデータベースIDになる

**GitHub Secrets**

9. `DISCORD_BOT_TOKEN` / `DISCORD_CHANNEL_ID` / `DISCORD_GUILD_ID` / `NOTION_TOKEN` / `NOTION_DATABASE_ID` を登録する
10. Actions タブから `Weekly Sync` を手動実行し、転記を確認する

## ローカル実行

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python -m tech_reader.check                 # 全ソースの疎通確認
.venv/bin/python -m tech_reader.main --dry-run        # 選定結果のみ表示（投稿しない）
.venv/bin/python -m tech_reader.main --dry-run --theme work
DISCORD_WEBHOOK_URL=... .venv/bin/python -m tech_reader.main   # 実際に配信

# 週次転記（Notion へ書き込まず対象だけ確認する）
DISCORD_BOT_TOKEN=... DISCORD_CHANNEL_ID=... .venv/bin/python -m tech_reader.weekly --dry-run
```

## 既知の制約

- 祝日は判定していません。設計上「未読は溜めずに捨てる」方針のため対応を見送っています。
- 週次転記は Discord の直近100件を上限にメッセージIDを補完します。Phase 1 期間の記事を遡って取り込む場合、それ以前の投稿は対象外です。
- Notion API は `2022-06-28` に固定しています。新しいバージョンは転記先の指定方法が変わるため、意図せず壊れないようにするためです。
- GitHub Actions の cron は遅延します（2026-08-06 の実測で72分）。4:00 配信・6:20 出発で 140分の余裕を確保しています。
