from __future__ import annotations

import random
import re
from io import BytesIO
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st


APP_TITLE = "天王洲ランチルーレット"

DEFAULT_GOOGLE_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1ZrXZcY-Fr4My0aoj8VCT6VxG_SN6czrvLa7xT8pw1U4/edit?gid=0#gid=0"
)

OPTIONAL_COLUMNS = [
    "area",
    "map_url",
    "address",
    "price_range",
    "open_hours",
    "tags",
    "note",
    "active",
    "source_url",
    "last_checked",
]

FALSE_VALUES = {"false", "0", "no", "n", "off", "inactive", "無効"}


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🍽️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()

    st.title(APP_TITLE)
    st.caption("Google Sheetsの店舗リストから、今日のランチ候補をランダムで選びます。")

    sheet_url = get_sheet_url()
    uploaded_csv = st.sidebar.file_uploader(
        "一時確認用CSV",
        type=["csv"],
        help="アップロードしたCSVはこのセッション中だけ使われます。Google Sheetは更新されません。",
    )

    with st.sidebar:
        st.markdown("### Data")
        st.link_button("Google Sheetを開く", sheet_url, use_container_width=True)
        if st.button("データを再読み込み", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    try:
        df = load_from_upload(uploaded_csv) if uploaded_csv else load_restaurants(sheet_url)
        df = normalize_restaurants(df)
    except Exception as exc:
        st.error("店舗データを読み込めませんでした。Google Sheetの共有設定と列名を確認してください。")
        st.exception(exc)
        return

    if df.empty:
        st.warning("有効な店舗データがありません。`name` と `category` を含む行を追加してください。")
        return

    categories = sorted(df["category"].dropna().astype(str).unique().tolist())
    restore_query_state(categories)

    selected_categories = render_sidebar_filters(categories)
    filtered_df = filter_restaurants(df, selected_categories)

    update_query_params(selected_categories)

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("全店舗", len(df))
    col_b.metric("現在の候補", len(filtered_df))
    col_c.metric("カテゴリ", len(categories))

    st.divider()

    left, right = st.columns([1.1, 0.9], gap="large")

    with left:
        render_picker(filtered_df)

    with right:
        render_candidates(filtered_df)

    st.caption(
        "カテゴリ、キーワード、前回の店などの状態はURL query paramsに保存されます。"
        "同じURLを開けばスマホでも同じ設定を復元できます。"
    )


def get_sheet_url() -> str:
    """Returns the configured Google Sheet URL."""

    secrets_url = ""
    try:
        secrets_url = str(st.secrets.get("GOOGLE_SHEET_URL", "")).strip()
    except Exception:
        secrets_url = ""

    return secrets_url or DEFAULT_GOOGLE_SHEET_URL


@st.cache_data(ttl=300, show_spinner="Google Sheetから店舗リストを読み込み中...")
def load_restaurants(sheet_url: str) -> pd.DataFrame:
    """Loads restaurant data from a public Google Sheet URL."""

    csv_url = to_google_sheet_csv_url(sheet_url)
    return pd.read_csv(csv_url)


def load_from_upload(uploaded_csv) -> pd.DataFrame:
    """Loads restaurant data from an uploaded CSV file."""

    data = uploaded_csv.getvalue()
    return pd.read_csv(BytesIO(data))


def to_google_sheet_csv_url(sheet_url: str) -> str:
    """Converts a Google Sheet edit URL to a CSV export URL."""

    url = sheet_url.strip()

    if "export?format=csv" in url:
        return url

    match = re.search(r"/spreadsheets/d/([^/]+)", url)
    if not match:
        raise ValueError("Google Sheet URLからspreadsheet idを取得できませんでした。")

    spreadsheet_id = match.group(1)
    gid_match = re.search(r"[?#&]gid=(\d+)", url)
    gid = gid_match.group(1) if gid_match else "0"

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"


def normalize_restaurants(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizes and validates restaurant rows."""

    df = df.copy()
    df.columns = [str(column).strip().lower() for column in df.columns]

    missing_columns = [column for column in ["name", "category"] if column not in df.columns]
    if missing_columns:
        raise ValueError(f"必須列がありません: {', '.join(missing_columns)}")

    for column in OPTIONAL_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    for column in ["name", "category", *OPTIONAL_COLUMNS]:
        df[column] = df[column].fillna("").astype(str).str.strip()

    df = df[(df["name"] != "") & (df["category"] != "")]

    active_normalized = df["active"].str.lower().str.strip()
    df = df[(active_normalized == "") | (~active_normalized.isin(FALSE_VALUES))]

    return df.reset_index(drop=True)


def restore_query_state(categories: list[str]) -> None:
    """Initializes Streamlit session state from URL query params."""

    if "initialized_from_query_params" in st.session_state:
        return

    params = st.query_params
    category_param = str(params.get("categories", "")).strip()
    if category_param:
        selected_categories = [category for category in category_param.split("|") if category in categories]
    else:
        selected_categories = categories

    st.session_state.selected_categories = selected_categories or categories
    st.session_state.keyword = str(params.get("keyword", "")).strip()
    st.session_state.avoid_previous = parse_bool(str(params.get("avoid_previous", "true")))
    st.session_state.show_candidates = parse_bool(str(params.get("show_candidates", "false")))
    st.session_state.last_picked_name = str(params.get("last", "")).strip()
    st.session_state.picked_restaurant = None
    st.session_state.initialized_from_query_params = True


def render_sidebar_filters(categories: list[str]) -> list[str]:
    """Renders filters and returns selected categories."""

    with st.sidebar:
        st.markdown("### Filter")

        st.text_input(
            "キーワード",
            key="keyword",
            placeholder="店名・住所・メモで検索",
        )

        st.checkbox("前回と同じ店を避ける", key="avoid_previous")
        st.checkbox("候補一覧を表示", key="show_candidates")

        st.markdown("### Category")

        button_col_1, button_col_2 = st.columns(2)
        if button_col_1.button("全ON", use_container_width=True):
            st.session_state.selected_categories = categories
            for category in categories:
                st.session_state[f"category__{stable_key(category)}"] = True
            st.rerun()
        if button_col_2.button("全OFF", use_container_width=True):
            st.session_state.selected_categories = []
            for category in categories:
                st.session_state[f"category__{stable_key(category)}"] = False
            st.rerun()

        selected_categories = []
        current = set(st.session_state.get("selected_categories", categories))

        for category in categories:
            key = f"category__{stable_key(category)}"
            if key not in st.session_state:
                st.session_state[key] = category in current

            if st.checkbox(category, key=key):
                selected_categories.append(category)

        if selected_categories != st.session_state.get("selected_categories", []):
            st.session_state.selected_categories = selected_categories

        if st.button("保存状態をリセット", use_container_width=True):
            st.query_params.clear()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    return selected_categories


def filter_restaurants(df: pd.DataFrame, selected_categories: list[str]) -> pd.DataFrame:
    """Filters restaurant records by UI state."""

    if not selected_categories:
        return df.iloc[0:0].copy()

    filtered = df[df["category"].isin(selected_categories)].copy()

    keyword = str(st.session_state.get("keyword", "")).strip().lower()
    if keyword:
        search_columns = [
            "name",
            "category",
            "area",
            "address",
            "price_range",
            "open_hours",
            "tags",
            "note",
        ]
        search_text = filtered[search_columns].agg(" ".join, axis=1).str.lower()
        filtered = filtered[search_text.str.contains(re.escape(keyword), na=False)]

    return filtered.reset_index(drop=True)


def render_picker(filtered_df: pd.DataFrame) -> None:
    """Renders the random picker result panel."""

    st.subheader("今日の候補")

    if st.button("🎲 今日のランチを選ぶ", type="primary", use_container_width=True):
        pick_restaurant(filtered_df)

    picked = st.session_state.get("picked_restaurant")
    if picked is None:
        st.info("カテゴリを選んでボタンを押してください。")
        return

    restaurant = dict(picked)
    st.markdown(f"### {restaurant.get('name', '')}")
    st.markdown(f"**カテゴリ:** {restaurant.get('category', '')}")

    info_rows = [
        ("エリア", restaurant.get("area", "")),
        ("住所", restaurant.get("address", "")),
        ("価格帯", restaurant.get("price_range", "")),
        ("営業時間", restaurant.get("open_hours", "")),
        ("タグ", restaurant.get("tags", "")),
        ("メモ", restaurant.get("note", "")),
    ]

    for label, value in info_rows:
        if value:
            st.write(f"**{label}:** {value}")

    map_url = get_map_url(restaurant)
    action_col_1, action_col_2 = st.columns(2)
    action_col_1.link_button("Google Mapsで開く", map_url, use_container_width=True)

    source_url = str(restaurant.get("source_url", "")).strip()
    if source_url:
        action_col_2.link_button("公式/参照元", source_url, use_container_width=True)


def pick_restaurant(filtered_df: pd.DataFrame) -> None:
    """Picks one restaurant from the filtered records."""

    if filtered_df.empty:
        st.session_state.picked_restaurant = None
        st.warning("条件に合う店舗がありません。")
        return

    candidates = filtered_df
    last_name = str(st.session_state.get("last_picked_name", "")).strip()

    if st.session_state.get("avoid_previous", True) and last_name and len(candidates) > 1:
        candidates = candidates[candidates["name"] != last_name]

    picked = candidates.sample(n=1, random_state=random.randint(0, 1_000_000)).iloc[0].to_dict()
    st.session_state.picked_restaurant = picked
    st.session_state.last_picked_name = str(picked.get("name", ""))

    update_query_params(st.session_state.get("selected_categories", []))


def render_candidates(filtered_df: pd.DataFrame) -> None:
    """Renders current candidate records."""

    st.subheader("現在の候補")

    if filtered_df.empty:
        st.warning("候補がありません。")
        return

    if not st.session_state.get("show_candidates", False):
        st.caption("候補一覧はサイドバーで表示できます。")
        return

    for _, row in filtered_df.iterrows():
        restaurant = row.to_dict()
        title = restaurant.get("name", "")
        category = restaurant.get("category", "")
        area = restaurant.get("area", "")
        price = restaurant.get("price_range", "")
        meta = " / ".join(value for value in [category, area, price] if value)

        with st.container(border=True):
            st.markdown(f"**{title}**")
            if meta:
                st.caption(meta)
            st.link_button("Map", get_map_url(restaurant))


def update_query_params(selected_categories: list[str]) -> None:
    """Writes current UI state into URL query params."""

    st.query_params["categories"] = "|".join(selected_categories)
    st.query_params["avoid_previous"] = "true" if st.session_state.get("avoid_previous") else "false"
    st.query_params["show_candidates"] = "true" if st.session_state.get("show_candidates") else "false"

    keyword = str(st.session_state.get("keyword", "")).strip()
    if keyword:
        st.query_params["keyword"] = keyword
    elif "keyword" in st.query_params:
        del st.query_params["keyword"]

    last_name = str(st.session_state.get("last_picked_name", "")).strip()
    if last_name:
        st.query_params["last"] = last_name
    elif "last" in st.query_params:
        del st.query_params["last"]


def get_map_url(restaurant: dict) -> str:
    """Returns a Google Maps URL for a restaurant."""

    map_url = str(restaurant.get("map_url", "")).strip()
    if map_url:
        return map_url

    query = " ".join(
        value
        for value in [
            str(restaurant.get("name", "")).strip(),
            str(restaurant.get("area", "")).strip() or "天王洲アイル",
        ]
        if value
    )
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def parse_bool(value: str) -> bool:
    """Parses a boolean-like string."""

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def stable_key(value: str) -> str:
    """Creates a stable Streamlit widget key fragment."""

    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_") or "category"


def inject_css() -> None:
    """Injects small UI refinements."""

    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(56, 189, 248, 0.15), transparent 32%),
                linear-gradient(180deg, #0f172a 0%, #020617 100%);
        }

        section[data-testid="stSidebar"] {
            background: rgba(15, 23, 42, 0.96);
            border-right: 1px solid rgba(148, 163, 184, 0.18);
        }

        div[data-testid="stMetric"] {
            padding: 1rem;
            border: 1px solid rgba(148, 163, 184, 0.20);
            border-radius: 1rem;
            background: rgba(15, 23, 42, 0.62);
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: rgba(148, 163, 184, 0.22);
            background: rgba(15, 23, 42, 0.62);
        }

        .stButton > button,
        .stLinkButton > a {
            border-radius: 999px;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
