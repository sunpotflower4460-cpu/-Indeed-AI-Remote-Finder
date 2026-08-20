# AI Remote Finder

**完全リモート × デジタル定型業務 × 新しい求人**を優先し、仕事内容を技術的にAI/RPAへ大きく寄せやすいIndeed求人候補だけを先に確認するためのiPhone対応PWAです。

> このアプリが判定するのは主に「技術的な自動化適性」です。求人本文に生成AI・AIツール・外部AIの**明示的な利用禁止**がある候補は除外します。一方、禁止が書かれていないことを利用許可とはみなしません。機密情報や個人情報を外部AIへ入力してよいこと、応募者本人の稼働を代替してよいことも求人票だけでは断定しないため、許可が明記されていない場合は応募後・業務開始前に必ず確認してください。

## 現在の品質方針

候補は、広めに探してから**厳しく公開判定する**構成です。検索語に一般的な「在宅」「リモート」を含めることはありますが、それだけで掲載対象にはしません。

公開候補には原則として次を要求します。

1. **Indeed個別求人URLが確認できること**
   - Google Jobsの構造化データにある `apply_options` からIndeedの個別 `viewjob?jk=...` URLを確認します。
   - Indeed求人ページそのものをbotで直接巡回する設計ではありません。
2. **求人本文に無条件の完全リモート根拠があること**
   - 「完全在宅」「フルリモート」「完全リモート」「100% remote」などを明示的に確認します。
   - 一部在宅、ハイブリッド、月/週の出社、研修のみ出社、相談可、将来フルリモート等は除外します。
3. **AI/RPAへ寄せやすい構造化作業であること**
   - データ入力、転記、アノテーション、分類、評価、文字起こし、校正、商品登録、データ検証、OCR確認などを中心に評価します。
4. **人間本人の同期対応・張り付きが本質ではないこと**
   - 電話、常時チャット対応、会議、顧客折衝、進行管理、継続的な調整などを除外します。
   - カメラ常時ON、Zoom/Teams常時接続、画面共有常時、PC前待機、在席確認、離席不可、ランダムな本人確認なども除外します。
   - 一方、ソフトウェアの常時ログイン、自動監視、機械による高速応答だけなら、それ自体を人間張り付きとはみなしません。
5. **鮮度が一定範囲内であること**
   - 高確度は原則14日以内。
   - 最新検索で再検出できなかった予備候補は最大14日までに限定します。
   - 明示的な掲載日時が30日を超える求人は通常候補から外します。
6. **求人本文にAI利用禁止が明記されていないこと**
   - 「生成AI使用禁止」「AIツール利用不可」「must not use generative AI」などの明示禁止は決定論的に除外します。
   - 「AI利用可」が明記されている場合はその状態を記録します。
   - 許可も禁止も書かれていない場合は候補を残しますが、PWA上で**AI利用可否確認**として表示し、許可を推測しません。

品質契約の詳細は [`docs/QUALITY_POLICY.md`](docs/QUALITY_POLICY.md) を参照してください。

## 2段階 + 最終ゲート

### 1. 決定論的な厳格ゲート

外部LLMが使えない時でも必ず動く一次判定です。

- AI代替性
- 完全リモート確度
- 鮮度
- 人間依存リスク
- 部分/条件付きリモートの矛盾
- 同期的人間対応
- 全文ベースの人間在席要件
- 求人本文の明示的なAI/外部AI利用禁止

`review` 候補にも、現在は次の最低条件を要求します。

- `automation_confidence >= 64`
- `human_dependency_risk <= 18`
- 異なる自動化根拠が2つ以上

### 2. 任意のLLM二次審査

`OPENAI_API_KEY` を設定すると、一次判定を通過した候補を第二の審査官として追加確認します。

LLMは固定JSON形式で、主に次を返します。

- 技術的に自動化できそうな割合
- 判定の確信度
- 人間依存の強さ
- 物理的な出社・作業が本質的に必要か
- 同期的な人とのやり取りの頻度
- データ機密性の注意度
- 自動化レシピ
- 技術的ブロッカー
- 応募後に確認すべきこと

現在の共有LLM予算は、**1回の更新で最大8 paid attempts**です。高確度候補を先に監査し、余った同じ8回枠を `review` 候補に使用します。月間安全上限は現在700 attemptsです。

LLMが明確な不一致を確認した候補は最終公開前に除外します。たとえば、物理出社、頻繁な同期対応、中〜高い人間依存、高確信度で75%未満のend-to-end自動化、人間在席を示すブロッカーなどです。

`review` tierの候補でも、**現行v2の決定論的品質・全文presence screen・presence gateを保ったままLLM strict passまで通過した場合**は、PWA上で「◎ LLM二重審査通過」として表示・絞り込みできます。ただし決定論的な `tier` 自体を `high` へ昇格させるわけではありません。

LLMが利用できないことだけを理由に、決定論的に通過した候補を削除することはありません。

## 候補数の考え方

- **ユーザー向け未応募目標:** 100件
- **サーバー側品質予備枠:** 最大150件
- **端末表示:** 最初は30件ずつ
- **1日の応募目安UI:** 10件

150件は品質基準を緩めるための枠ではありません。応募済み・辞退済みが増えても100件を切りにくくするための余剰在庫です。

最新スキャンで見つからなかった求人は、**現行の品質ポリシー・全文在席チェック・presence gate・AI利用ポリシーgateまで通過済みであることを証明できる候補だけ**、最大14日まで低順位の予備候補として保持できます。PWAでは「予備・今回未再検出」と未再検出日数を表示します。リンク先で募集継続を確認してから応募してください。

## データ取得と検索予算

本番更新の入口は `scripts/acquisition_precision.py` です。これは既存の `scripts/acquisition_supply_yield.py` を包み、供給量・source recovery・provider予算保護を維持したまま、過去の最終成果から検索プロフィール順を最適化します。

- SerpApi Google Jobs APIを利用
- 日本向け、既定検索起点は `Tokyo, Japan`
- 通常アンカー + Indeed寄りアンカー + 多数のタスク別検索をローテーション
- 検索プロフィールはIndeed導線・決定論通過・最終掲載・下流落ち・粗い拒否理由から減衰付きで学習
- 同系統familyが少ない検索枠を独占しないよう分散
- 実績トップの完全一致プロフィールを条件付きchampion枠へ入れ、同じ求人の再発見だけだった場合は次回休ませるfatigue guardを使用
- 候補が少ない時の深掘り上限は**1回7検索**
- 通常の1日1回運用なら 7 × 31日 = 217検索として、既定の月220検索安全上限内に収まる設計
- 手動更新やコード変更後の追加更新で月間使用量が通常ペースを上回った場合は、残り月間枠を残りUTC日数へ配分し、**実効検索数を7未満へ自動ペーシング**する
- ペーシングは検索回数を減らすだけで、公開品質基準や月間ハード上限を緩めない
- SerpApi Account APIの利用量も確認し、プロバイダ側の残量が少ない時は追加消費を止める
- 取得失敗時はlast-known-good feedを消さない

検索は広めでも、公開基準は常に同じ厳格ゲートです。

## 自動更新

`.github/workflows/update-jobs.yml` の本番スケジュールは現在、**毎日 08:25 JST（23:25 UTC）**です。

更新時は概ね次の順で処理します。

1. 回帰テスト
2. 前回feed保存
3. SerpApi候補取得 + 安全な供給量テレメトリ + 適応型検索順
4. provider / acquisition状態の安全な診断スタンプ
5. 重複除去・14日以内の予備候補統合
6. LLM一次監査
7. 余った同一予算でreview候補監査
8. 公開用LLMエラー情報を安全化
9. LLM / 人間在席の最終品質veto
10. 明示的AI利用禁止の最終veto + AI利用可否stamp
11. feed validator + remote validator
12. 検証を通った `data/jobs.json` のみcommit

本番更新の自動トリガーは、定期実行に加えて、候補パイプラインの `scripts/**` または `.github/workflows/update-jobs.yml` を変更する**trusted `main` push**です。関連PRをマージすると通常のmain pushが発生するため、これが唯一の自動post-merge refresh経路です。二重にAPI予算を消費しないため、別のmerged-PR dispatcherは使用しません。

詳しくは [`docs/REFRESH_CONTRACT.md`](docs/REFRESH_CONTRACT.md) を参照してください。

## 古い・不確かな求人を残しすぎない仕組み

- 高確度は14日以内を要求
- 明示的な掲載日時が30日超の求人は通常候補から除外
- 未再検出のサーバー予備候補は14日以内のみ
- 予備候補へ戻せるのは、現行品質・全文presence screen・presence gate・AI利用ポリシーgateの証明が残るものだけ
- 求人本文に明示的AI利用禁止があればlive/予備とも除外
- 同じ会社・同じ職種は重複圧縮
- ブラウザ側は `candidateCacheV5` で、最終検出14日以内 + 現行quality/presence/AI-policy stampを再確認してからローカル予備へ入れる
- 旧V4以前の候補キャッシュは再利用しない
- PWAの求人JSONはnetwork-firstで取得し、通信失敗時だけService Workerキャッシュへフォールバック

## 主な機能

- おすすめ候補 / 高確度 / ◎ LLM二重審査 / 次点候補
- ★お気に入り / ✓応募済み / ×応募しない
- AI代替・完全在宅・新しさの別スコア
- `AI利用可明記` / `AI利用可否確認` の求人単位表示
- live再検出 / 予備未再検出と未確認日数の表示
- LLM技術代替率・確信度・人間依存
- 求人ごとの自動化レシピ
- 応募後確認事項
- 総合 / 新しさ / AI代替 / LLM代替率で並べ替え
- キーワード絞り込み
- iPhoneのホーム画面に追加できるPWA
- ローカルに応募・保存・辞退履歴を保持
- ワンタップでIndeed個別求人へ移動
- 生成feedの自動品質検査
- Python回帰テスト + Python/JavaScript構文チェック

## 自動求人更新を有効にする

GitHubリポジトリの `Settings > Secrets and variables > Actions` に次を設定します。

- `SERPAPI_KEY` — 本番候補取得に必要
- `OPENAI_API_KEY` — LLM二次審査を使う場合のみ必要

設定後、`Actions > Update job candidates > Run workflow` を実行できます。以後は定期更新も動きます。

検索起点を実験的に変える場合は `SERPAPI_SEARCH_ORIGIN`、月間検索安全上限を変える場合は `SERPAPI_MONTHLY_REQUEST_CAP` を環境変数として利用できます。品質ゲートそのものを弱める設定ではありません。

## iPhoneに入れる

1. `Settings > Pages > Build and deployment > Source` をGitHub Actionsにする
2. Pages URLをSafariで開く
3. 共有 → **ホーム画面に追加**

## 品質検査

ローカル/CIで主に次を実行します。

```bash
python -m unittest discover -s tests -q
python -m compileall -q scripts
python scripts/validate_feed.py
python scripts/validate_remote_feed.py
node --check app.js
node --check sw.js
```

validatorは、たとえば次を確認します。

- canonical Indeed `viewjob?jk=...` URL
- ID重複
- スコア範囲
- high/reviewの閾値整合
- 掲載日時の未来値・鮮度
- LLM JSONとstrict passの整合
- LLM最終vetoが残っていないこと
- 明示的な完全リモート根拠
- 部分/ハイブリッド表現の混入
- 人間在席要件の混入
- presence gate stamp
- **サーバー予備枠150件上限**

AI利用禁止はvalidator直前の必須 `apply_ai_tool_policy_gate.py` で最終vetoされます。このステップが失敗した場合、検証・feed commitへ進まないため、明示禁止候補を「技術的に自動化できるから」という理由だけで公開しません。

## 主要ファイル

- `scripts/acquisition.py` — 適応型Google Jobs取得の基盤
- `scripts/acquisition_remote.py` — リモート/人間同期リスクとprovider予算の保護層
- `scripts/acquisition_quality.py` — 現行v2品質・全文presence判定
- `scripts/acquisition_supply.py` — 多様な検索テーマと日次検索量
- `scripts/acquisition_supply_yield.py` — Indeed供給量の安全な測定とsource recovery
- `scripts/acquisition_precision.py` — 本番入口、profile learning / family diversity / guarded championを接続
- `scripts/profile_precision.py`〜`profile_precision_v4.py` — 減衰付き検索学習・最終結果学習・family分散・champion fatigue guard
- `scripts/postprocess_feed.py` — 重複圧縮、現行ゲート通過済み14日予備候補の統合
- `scripts/llm_review.py` — 高確度候補の任意LLM監査
- `scripts/llm_review_quality.py` — 同一run予算の余りでreview候補を監査
- `scripts/apply_llm_quality_gate.py` — LLM/人間在席の最終公開veto
- `scripts/apply_ai_tool_policy_gate.py` — 明示的AI利用禁止のveto、許可明記/未記載stamp
- `scripts/validate_feed.py` — 一般feed整合性検査
- `scripts/validate_remote_feed.py` — 完全リモート/AI代替/presence品質検査
- `scripts/stamp_provider_health.py` — 公開して安全なprovider診断
- `scripts/stamp_refresh_outcome.py` — acquisition成否とlast-known-good保持状態
- `data/jobs.json` — 現在の公開候補feed
- `index.html`, `app.js`, `sw.js` — PWA
- `tests/` — 回帰テスト
- `.github/workflows/update-jobs.yml` — 本番更新
- `.github/workflows/check.yml` — PR/main検証
- `.github/workflows/pages.yml` — GitHub Pages公開