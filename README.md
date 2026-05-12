# 周辺ランチ・飲食店ランダムピッカー

`restaurants.csv` に登録した飲食店リストから、カテゴリ条件に合うお店をランダムに選ぶ Streamlit アプリです。

Google Maps API は使用しません。APIキーも不要です。

## ファイル構成

```text
restaurant_picker_streamlit_csv/
├── streamlit_app.py
├── restaurants.csv
├── requirements.txt
└── README.md
```

## ローカル実行

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Streamlit Community Cloud で公開する手順

1. このフォルダの中身を GitHub リポジトリにアップロードする。
2. Streamlit Community Cloud で New app を作成する。
3. Repository / Branch / Main file path を指定する。
4. Main file path には `streamlit_app.py` を指定する。
5. Deploy する。

Google Maps API を使わないため、Secrets 設定は不要です。

## restaurants.csv の列

必須列は `name` と `category` です。

| 列名 | 必須 | 内容 |
|---|---:|---|
| `name` | yes | 店名 |
| `category` | yes | カテゴリ。例: 和食、洋食、中華、カレー、カフェ |
| `area` | no | エリア名。例: 天王洲、品川、港南 |
| `map_url` | no | Google Maps の店舗URL。空欄の場合は店名とエリアでGoogle Maps検索リンクを自動生成 |
| `address` | no | 住所 |
| `price_range` | no | 価格帯。例: ¥、¥¥、¥¥¥ |
| `open_hours` | no | 営業時間メモ |
| `tags` | no | タグ。カンマ区切り。例: ランチ,一人OK,安い |
| `note` | no | メモ |
| `active` | no | `false`, `0`, `off`, `非表示`, `無効` の場合は候補から除外 |

## CSV記入例

```csv
name,category,area,map_url,address,price_range,open_hours,tags,note,active
お店A,和食,天王洲,https://maps.app.goo.gl/xxxxx,東京都品川区...,¥¥,11:00-15:00,"ランチ,落ち着く",魚定食が良い,true
お店B,カレー,天王洲,,東京都品川区...,¥,11:30-14:30,"ランチ,一人OK",混みやすい,true
```

`map_url` が空欄でも動きます。その場合、アプリ側で Google Maps の検索リンクを作ります。

## カテゴリを増やす方法

`restaurants.csv` の `category` に新しいカテゴリ名を書くだけで、アプリのサイドバーにチェックボックスが自動追加されます。

例:

```csv
name,category,area,map_url,address,price_range,open_hours,tags,note,active
お店C,ラーメン,天王洲,,東京都品川区...,¥,11:00-22:00,"ランチ,早い",替え玉あり,true
```

## 店を一時的に候補から外す方法

`active` を `false` にすると候補から除外されます。

```csv
name,category,area,map_url,address,price_range,open_hours,tags,note,active
お店D,中華,天王洲,,東京都品川区...,¥¥,11:00-15:00,"ランチ",改装中,false
```

## 注意

同梱の `restaurants.csv` はサンプルです。実際の店舗リストに置き換えて使ってください。
