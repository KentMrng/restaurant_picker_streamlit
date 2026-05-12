# 天王洲ランチルーレット - Streamlit + Google Sheets版

Google Sheetsを店舗リストとして読み込み、Streamlit Cloudで公開するランチ抽選アプリです。

Apps Scriptは使いません。Google Maps APIも使いません。

## 構成

```text
tennozu_lunch_streamlit_gsheet/
├── streamlit_app.py
├── requirements.txt
├── README.md
├── sample_restaurants.csv
└── .streamlit/
    ├── config.toml
    └── secrets.toml.example
```

## データ元

デフォルトで以下のGoogle Spreadsheetを読み込みます。

```text
https://docs.google.com/spreadsheets/d/1ZrXZcY-Fr4My0aoj8VCT6VxG_SN6czrvLa7xT8pw1U4/edit?gid=0#gid=0
```

コード内の `DEFAULT_GOOGLE_SHEET_URL` に埋め込み済みです。

別シートに変える場合は、コードを編集するか、Streamlit CloudのSecretsで上書きできます。

```toml
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/xxxxxxxxxxxxxxxxxxxx/edit?gid=0#gid=0"
```

## Google Sheetの列

1行目に以下のヘッダーを置いてください。

```csv
name,category,area,map_url,address,price_range,open_hours,tags,note,active,source_url,last_checked
```

必須列:

```text
name
category
```

`active` は空欄なら有効です。以下の値なら非表示になります。

```text
false, 0, no, n, off, inactive, 無効
```

## ローカル起動

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Streamlit Cloud公開

1. このフォルダをGitHubリポジトリにアップロード
2. Streamlit Community CloudでNew app
3. Repositoryを選択
4. Main file pathに以下を指定

```text
streamlit_app.py
```

5. Deploy

Google Sheetは、アプリからCSVエクスポートURLで読むため、少なくとも「リンクを知っている人が閲覧可」にしてください。

## ユーザー設定の保存

この版は、サードパーティのlocalStorageコンポーネントを使わず、Streamlit公式の `st.query_params` を使います。

保存されるもの:

```text
カテゴリON/OFF
キーワード
前回と同じ店を避ける
候補一覧表示
前回選ばれた店
```

特徴:

```text
同じURLを開くと設定を復元できる
スマホでも同じURLなら同じ設定で開ける
ブラウザのlocalStorageやCookieには依存しない
```

厳密な「端末ごとの自動保存」ではありませんが、Streamlit Cloudではこの方が安定します。
