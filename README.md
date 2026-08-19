# AI Remote Finder

**完全リモート × デジタル定型業務 × 新しい求人**を優先し、「技術的にAI/RPAへ大部分を寄せやすい」Indeed求人候補だけを先に確認するためのiPhone対応PWAです。

## 何を厳しく見るか

候補は1本の総合点だけではなく、次の4軸を別々に判定します。

1. **AI代替性** — データ入力、転記、アノテーション、分類、評価、文字起こし、校正、商品登録などの構造化しやすい作業
2. **完全リモート確度** — 「完全在宅」「フルリモート」「100% remote」を強く評価し、出社・常駐・ハイブリッドを除外
3. **新しさ** — 掲載から14日以内を高確度の必須条件にし、30日超は原則表示しない
4. **人間依存リスク** — 営業、接客、電話、訪問、講師、会議、マネジメント、現場作業などを減点・除外

**高確度**は4軸すべてを通過したものだけです。「総合点は高いけど出社あり」のような求人は入りません。惜しいものだけ**要確認候補**へ分離します。

## データ取得

Indeed求人ページをbotで直接巡回しません。自動更新の主経路は **SerpApi Google Jobs API** です。

- Google Jobsの構造化求人を取得
- `Working from home` フィルタを使用
- `apply_options` に **Indeedの個別応募URL** が実在する求人だけ残す
- そのうえで4軸スコアリング
- 2検索を8時間ごとに実行（最大約186検索/月）

SerpApi無料枠は現在250検索/月なので、通常運用では無料枠内に収まる設計です。

`SERPAPI_KEY` が未設定・一時障害の場合は、**既存の求人フィードを消さずにそのまま保持**します。初期状態には2026-08-19時点でIndeed上の個別求人ページを確認した候補を入れています。

## 主な機能

- 高確度 / 要確認 / 全候補 / ★保存 / 非表示
- AI代替・完全在宅・新しさを別スコア表示
- 人間依存リスク表示
- 総合 / 新しさ / AI代替の並べ替え
- キーワード絞り込み
- iPhone内に保存・非表示状態を保持
- ワンタップでIndeed個別求人へ移動
- Indeedの「7日以内・日付順」検索へのショートカット
- GitHub Actionsで8時間ごとの更新
- 判定ロジック19ケースの回帰テスト
- PWAキャッシュ更新対策

## 自動更新を有効にする（1回だけ）

1. SerpApiで無料アカウントを作りAPI Keyをコピー
2. このリポジトリの `Settings > Secrets and variables > Actions`
3. `New repository secret`
4. Nameを **`SERPAPI_KEY`**、SecretにAPI Keyを入れて保存
5. `Actions > Update job candidates > Run workflow` を1回実行

以後は8時間ごとに自動更新します。キーがなくても初期候補とIndeed検索ショートカットは使えます。

## iPhoneに入れる

1. `Settings > Pages > Build and deployment > Source` を **GitHub Actions** にする
2. Pages URLをSafariで開く
3. 共有 → **ホーム画面に追加**

## 「AI代替」の意味

ここで判定するのは**仕事内容が技術的に自動化しやすいか**です。雇用主が生成AI・自動化ツールの利用を許可していることまでは求人文だけでは断定できません。応募後・業務開始前に、AI利用可否、守秘義務、個人情報・機密データの外部サービス投入可否を確認してください。

## ファイル

- `scripts/fetch_jobs.py` — Google Jobs取得、Indeed応募URL確認、4軸判定、鮮度管理
- `data/jobs.json` — 現在の候補フィード
- `index.html`, `app.js`, `sw.js` — PWA
- `tests/test_scoring.py` — 判定ガード
- `.github/workflows/update-jobs.yml` — 定期更新
- `.github/workflows/pages.yml` — Pages公開
