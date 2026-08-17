# コミケ巡回プランナー：設計定義

## 1. 設計方針

uvで依存関係を固定したPython CLIとエージェント用SkillをMVPの中心にする。構造検証にはPydantic、HTML生成にはJinjaを使用する。取得、抽出、統合、表示を分離し、外部サービスや出力先を交換できるようにする。永続化の正本はローカルの構造化データとし、Notionなどは同期先として扱う。

設計上の優先順位は次のとおり。

1. 手動編集を失わない
2. 推定の根拠を追跡できる
3. 同じ入力から再実行できる
4. 当日の操作が少ない
5. 将来のリスク推定・ルート最適化へ拡張できる

## 2. 論理構成

```text
前回リスト ─┐
Xデータ ─────┼─> 取込・正規化 ─> 照合・統合 ─> イベント計画JSON ─> 当日用ビュー
お品書き ────┤                         ↑                    └─> 要確認レポート
公式PDF ─────┘                   ユーザー編集
```

### コンポーネント

| コンポーネント | 責務 |
|---|---|
| source adapters | CSV、JSON、PDF、画像、APIレスポンスを共通形式へ変換 |
| map indexer | 公式PDFをイベント単位の配置インデックスへ変換 |
| announcement finder | 参加告知・お品書き候補を抽出 |
| menu extractor | 画像や投稿からサークル名、商品、価格、区分を候補化 |
| entity resolver | Xアカウント、作家名、サークル名、前回レコードを照合 |
| merge engine | 優先順位と保護ルールに従って更新 |
| budget calculator | 確定額、最大額、価格不明を集計 |
| exporter | JSON、CSV、HTML、Notion等の当日用ビューを生成 |
| validator | 重複、矛盾、欠損、集計不整合、手動値の消失を検出 |

## 3. 推奨ディレクトリ

```text
comiket-route-planner/
├── SKILL.md
├── pyproject.toml
├── uv.lock
├── agents/openai.yaml
├── references/
│   ├── project-overview.md
│   └── design.md
├── scripts/
│   ├── import_previous.py
│   ├── import_x_data.py
│   ├── build_map_index.py
│   ├── extract_menus.py
│   ├── reconcile_plan.py
│   ├── export_event_view.py
│   └── validate_plan.py
├── src/comiket_planner/
├── tests/
├── config/
└── data/
    ├── raw/
    ├── derived/
    └── events/
```

`scripts/` 以下は薄いCLI入口にし、再利用可能な処理は `src/comiket_planner/` に置く。入力原本は `data/raw/` で不変として扱い、生成物は `derived/` と `events/` に分ける。実データや認証情報はSkill配布物へ含めない。

## 4. データモデル

### 4.1 EventPlan

```json
{
  "schema_version": "0.1.0",
  "event": {
    "event_id": "C110-day2",
    "name": "Comic Market 110",
    "day": 2,
    "event_date": null,
    "map_source_id": null
  },
  "circles": [],
  "budget": {
    "planned_total": 0,
    "max_total": 0,
    "unknown_price_buy_count": 0,
    "unknown_price_candidate_count": 0
  },
  "generated_at": null
}
```

### 4.2 CircleVisit

```json
{
  "visit_id": "stable-uuid",
  "circle_name": "Alice Garden",
  "creator_name": "Alice",
  "aliases": [],
  "x_user_id": null,
  "x_handle": null,
  "space_code": "東A34a",
  "hall": "東7",
  "placement_type": "wall",
  "priority": "A",
  "genre_short": "成人向けオリジナル",
  "visit_status": "unvisited",
  "notes": "",
  "items": [],
  "field_meta": {},
  "source_refs": []
}
```

列挙値の初期案：

- `placement_type`: `shutter_front | wall | island_end | island | unknown`
- `priority`: `A | B | C | unassigned`（将来設定可能にする）
- `visit_status`: `unvisited | purchased | sold_out | skipped`

### 4.3 PurchaseItem

```json
{
  "item_id": "stable-uuid",
  "name": "C110新刊",
  "variant": null,
  "price": 1000,
  "currency": "JPY",
  "purchase_state": "buy",
  "availability": "unknown",
  "age_rating": "adult",
  "bundle_components": [],
  "source_refs": []
}
```

- `purchase_state`: `buy | candidate | skip`
- `availability`: `unknown | available | sold_out`
- `price`: 不明なら `null`。0円で代用しない。
- セットと単品の構成が分かる場合は `bundle_components` で関連付け、二重計上警告に利用する。

### 4.4 FieldMetaとSourceRef

各推定値について、値そのものと判断材料を分離する。

```json
{
  "field_meta": {
    "circle_name": {
      "origin": "menu_ocr",
      "confidence": 0.91,
      "manually_confirmed": false,
      "updated_at": "2026-08-17T00:00:00+09:00"
    }
  },
  "source_refs": [
    {
      "source_id": "x-post-123",
      "type": "x_post",
      "locator": "https://example.invalid/post/123",
      "captured_at": null,
      "content_hash": null
    }
  ]
}
```

`confidence` はレビュー順を決める補助値であり、事実の保証として表示しない。

## 5. 統合ルール

### 5.1 値の優先順位

1. 今回イベントでの明示的なユーザー編集
2. 今回イベントでユーザー確認済みの抽出値
3. 前回リストの手動値
4. 公式情報または明示的な告知
5. お品書きOCR・画像理解
6. 一般投稿やプロフィールからの推定

フィールドごとに適用し、レコード全体を一括上書きしない。

### 5.2 イベント更新

- 新規イベント：`visit_status=unvisited` で作成し、購入選択は前回値を候補として提示しても自動確定しない。
- 同一イベント再同期：ユーザー編集済みの `priority`、`genre_short`、`visit_status`、`purchase_state`、`notes` を保護する。
- ソースから消えたレコード：即削除せず `source_missing=true` として確認対象にする。
- 同じ投稿・画像：`source_id` またはハッシュで重複取込を防ぐ。

### 5.3 エンティティ照合

決定的な識別子を優先する。

1. X user ID
2. 明示的なサークルIDやカタログID
3. 正規化済みハンドル
4. 過去にユーザー確認された別名
5. サークル名・作家名・配置・リンクの複合一致

曖昧一致だけで自動マージしない。候補をスコア付きでレビューへ出す。

## 6. 配置インデックス

公式PDFはイベントごとに一度解析し、次のような索引を保存する。

```json
{
  "event_id": "C110-day2",
  "map_sha256": "...",
  "spaces": {
    "東A34a": {
      "hall": "東7",
      "placement_type": "wall",
      "page": 1,
      "bbox": [0, 0, 0, 0],
      "confidence": 0.98
    }
  }
}
```

判定は固定のブロック名だけに依存させない。PDF上の座標、外周との接触、出入口・シャッター表記、ホール境界を組み合わせる。回次ごとの差異に対応するため、低信頼結果を可視化して人手修正できるようにする。

## 7. お品書き抽出

抽出処理は構造化JSONを返し、原文の長期保存を前提にしない。

必須候補フィールド：

- `circle_name`
- `creator_name`
- `space_code`
- `items[].name`
- `items[].price`
- `items[].age_rating`
- `items[].bundle_components`
- 各値の根拠領域またはソース参照

抽出後に次を検査する。

- 通貨記号・桁区切り・「各」「セット」の読み違い
- 新刊セットと新刊単品の二重計上
- 無料配布、購入特典、会場限定の価格扱い
- 売り子側メニューと委託品の混同
- 日付・スペースコードが別イベントの投稿ではないか

## 8. 金額計算

サークルごと、および全体で次を計算する。

```text
planned_total = sum(price where purchase_state == buy)
max_total     = sum(price where purchase_state in [buy, candidate])
```

ただし `price=null` は合計から除外し、別途件数とアイテム名を警告する。セットと構成品の重複選択は自動で片方を除外せず、ユーザー確認を要求する。将来、数量を追加する場合は `price * quantity` とする。

## 9. CLI設計案

```text
comiket-plan init EVENT_ID
comiket-plan import-previous EVENT_ID FILE
comiket-plan import-x EVENT_ID FILE
comiket-plan index-map EVENT_ID PDF
comiket-plan extract-menus EVENT_ID INPUT...
comiket-plan reconcile EVENT_ID
comiket-plan validate EVENT_ID
comiket-plan export EVENT_ID --format json|csv|html|notion
```

ローカル実行時は `uv run comiket-plan ...` を使用する。

各コマンドは原則として冪等にし、更新前後の差分と保護された手動フィールド数を表示する。破壊的な置換は明示フラグなしで行わない。

## 10. スクリプト責務

| スクリプト | 入力 | 出力 | 備考 |
|---|---|---|---|
| `import_previous.py` | CSV/JSON等 | 正規化済み過去レコード | 列マッピングを設定可能にする |
| `import_x_data.py` | 正規取得したJSON/CSV | アカウント・投稿候補 | 認証回避を実装しない |
| `build_map_index.py` | 公式PDF | map index JSON | PDFハッシュで再利用する |
| `extract_menus.py` | 画像・投稿 | 抽出候補JSON | 信頼度と根拠を必須にする |
| `reconcile_plan.py` | 全中間データ | EventPlan JSON | 手動値保護と差分を担当 |
| `export_event_view.py` | EventPlan | JSON/CSV/HTML等 | モバイル操作を優先する |
| `validate_plan.py` | EventPlan | 検証レポート | CIから利用可能にする |

実装開始時は、まず `reconcile_plan.py` と `validate_plan.py` の核となる純粋関数を作り、手動編集保護と金額計算をテストする。その後、外部入力アダプタを追加する。

## 11. 当日用ビュー

### 必須操作

- 訪問状態をワンタップで変更する
- 商品を `buy / candidate / skip` へ変更する
- 優先度、配置、購入予定、金額を一覧で確認する
- 優先度、ホール、未訪問、価格不明で絞り込む
- 同期後も現在の表示と進捗を維持する

### 推奨表示

- 上部：`確定額 / 候補込み最大額 / 価格不明件数`
- 一覧：優先度、状態、配置、サークル名、一言ジャンル、小計
- 詳細：商品選択、根拠リンク、メモ、抽出信頼度

巨大列の実際の最後尾は静的配置だけでは分からないため、MVPのルート表示は「スペース位置への移動支援」と明記する。

## 12. セキュリティとプライバシー

- APIトークン、Cookie、認証情報をデータファイルやログへ保存しない。
- 公開範囲を越えた投稿取得やアクセス制限の回避を行わない。
- 成人向け情報は分類に必要な最小限の派生メタデータへ縮約する。
- 元画像の保持期間と削除方針を設定可能にする。
- エクスポートに不要な個人情報を含めない。

## 13. テスト戦略

### 単体テスト

- 新規イベントでは進捗が初期化される
- 同一イベント再同期では手動状態が保持される
- ユーザー編集がAI推定より優先される
- `buy` と `candidate` の合計が正しい
- `null` 価格が0円扱いされず警告される
- 同一ソースの再取込が重複しない
- 曖昧な人物・サークル照合が自動マージされない

### 結合テスト

- 前回CSV、Xエクスポート、地図索引、お品書き抽出を統合できる
- 再同期前後の差分で手動編集が消えていない
- エクスポート値がEventPlanと一致する

### ゴールデンテスト

匿名化した小規模なPDFページ、メニュー画像、期待JSONを固定し、OCRや座標解析の回帰を検出する。実在作家の成人向け原文をテスト fixture に含めない。

## 14. 受け入れ条件

- 1イベント分の各入力を再現可能な手順で統合できる。
- 公式PDFから得た配置を根拠ページ・座標まで追跡できる。
- お品書きから複数商品と価格を抽出し、人手修正できる。
- 確定額、最大額、価格不明が正しく表示される。
- 同一イベントの再取込後も購入済み等の手動値が保持される。
- 当日用ビューで `未訪問 / 購入済 / 売切れ / 見送り` を更新できる。
- 入力不足や低信頼値を黙って確定せず、要確認として提示する。

## 15. 実装順序

1. JSON Schemaとサンプルデータを確定する。
2. 統合ルール、金額計算、検証処理をテスト駆動で実装する。
3. 前回リストの取込を実装する。
4. 当日用の静的HTMLまたは選定した第一出力先を実装する。
5. お品書き抽出を追加する。
6. 公式PDFの配置インデックスを追加する。
7. Xデータ取込を追加する。
8. 実データの匿名化サンプルで一連の流れを検証する。
9. 必要に応じてNotion同期、売切れリスク、経路提案を追加する。

## 16. 将来拡張

- 過去の完売報告、販売開始・終了時刻、搬入言及を使った売切れリスク
- ホール移動コスト、優先度、予想待ち時間を使った巡回順提案
- 複数人での担当分割とリアルタイム共有
- 現金・カード・QR決済別の予算
- 実績ログから次回の優先度・購入候補を提案

売切れリスクは `人気度 × 搬入傾向 × 販売速度` の不確実な推定として扱い、搬入数が未公表なら断定しない。
