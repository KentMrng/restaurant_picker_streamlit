from __future__ import annotations

import random
from io import StringIO
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, urlparse

import pandas as pd
import streamlit as st


APP_TITLE = "天王洲ランチ ランダムピッカー"
DEFAULT_CACHE_TTL_SECONDS = 300
REQUIRED_COLUMNS = {"name", "category"}
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
TRUE_VALUES = {"1", "true", "t", "yes", "y", "on", "active", "公開", "有効", "はい", "○", "〇"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "off", "inactive", "非公開", "無効", "いいえ", "×"}


st.set_page_config(page_title=APP_TITLE, page_icon="🍽️", layout="wide")


class DataLoadError(RuntimeError):
    """Raised when the restaurant source cannot be loaded."""


def normalize_column_name(value: object) -> str:
    """Normalize a CSV/Sheet header name for internal processing."""
    return str(value).strip().lower().replace(" ", "_")


def normalize_bool(value: object, default: bool = True) -> bool:
    """Convert common spreadsheet values into booleans."""
    if pd.isna(value):
        return default
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return default


def split_values(value: object) -> list[str]:
    """Split comma-like spreadsheet cells into clean string values."""
    if pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []

    normalized = text.replace("、", ",").replace("，", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def get_secret_or_empty(key: str) -> str:
    """Read a Streamlit secret without raising when secrets are unavailable."""
    try:
        value = st.secrets.get(key, "")
    except Exception:
        return ""
    return str(value).strip()


def google_sheet_url_to_csv_url(url: str) -> str:
    """Convert common Google Sheets URLs into a CSV export URL.

    Supported inputs:
    - https://docs.google.com/spreadsheets/d/<sheet_id>/edit#gid=0
    - https://docs.google.com/spreadsheets/d/<sheet_id>/edit?gid=0#gid=0
    - https://docs.google.com/spreadsheets/d/e/<published_id>/pub?output=csv
    - Any direct CSV URL
    """
    clean_url = url.strip()
    if not clean_url:
        raise DataLoadError("Google Sheets URL is empty.")

    lowered = clean_url.lower()
    if "output=csv" in lowered or "format=csv" in lowered:
        return clean_url

    parsed = urlparse(clean_url)
    if "docs.google.com" not in parsed.netloc or "/spreadsheets/" not in parsed.path:
        return clean_url

    # Published-to-web URL, e.g. /spreadsheets/d/e/<id>/pubhtml -> /pub?output=csv
    if "/spreadsheets/d/e/" in parsed.path:
        base = clean_url.split("/pub", maxsplit=1)[0]
        return f"{base}/pub?output=csv"

    parts = parsed.path.split("/")
    try:
        sheet_id = parts[parts.index("d") + 1]
    except (ValueError, IndexError) as exc:
        raise DataLoadError("Could not parse the Google Sheet ID from the URL.") from exc

    query_params = parse_qs(parsed.query)
    fragment_params = parse_qs(parsed.fragment)
    gid = "0"
    if "gid" in query_params and query_params["gid"]:
        gid = query_params["gid"][0]
    elif "gid" in fragment_params and fragment_params["gid"]:
        gid = fragment_params["gid"][0]

    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


@st.cache_data(ttl=DEFAULT_CACHE_TTL_SECONDS, show_spinner=False)
def load_restaurants_from_url(source_url: str) -> pd.DataFrame:
    """Load restaurant data from a Google Sheets CSV export URL."""
    csv_url = google_sheet_url_to_csv_url(source_url)
    try:
        df = pd.read_csv(csv_url)
    except Exception as exc:
        raise DataLoadError(
            "Could not load the Google Sheet. Make sure it is shared as viewable by link "
            "or published to the web as CSV."
        ) from exc
    return normalize_restaurant_frame(df)


@st.cache_data(ttl=DEFAULT_CACHE_TTL_SECONDS, show_spinner=False)
def load_restaurants_from_uploaded_csv(csv_text: str) -> pd.DataFrame:
    """Load restaurant data from an uploaded CSV file."""
    try:
        df = pd.read_csv(StringIO(csv_text))
    except Exception as exc:
        raise DataLoadError("Could not read the uploaded CSV file.") from exc
    return normalize_restaurant_frame(df)


def normalize_restaurant_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate restaurant records from a spreadsheet-like table."""
    normalized = df.copy()
    normalized.columns = [normalize_column_name(column) for column in normalized.columns]

    missing = sorted(REQUIRED_COLUMNS - set(normalized.columns))
    if missing:
        joined = ", ".join(missing)
        raise DataLoadError(f"Required columns are missing: {joined}")

    for column in OPTIONAL_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = ""

    normalized["name"] = normalized["name"].astype(str).str.strip()
    normalized["category"] = normalized["category"].astype(str).str.strip()
    normalized = normalized[(normalized["name"] != "") & (normalized["category"] != "")]

    if "active" in normalized.columns:
        normalized = normalized[normalized["active"].map(lambda value: normalize_bool(value, default=True))]

    if normalized.empty:
        raise DataLoadError("No active restaurant records were found.")

    return normalized.reset_index(drop=True)


def get_categories(df: pd.DataFrame) -> list[str]:
    """Return sorted unique categories."""
    values: set[str] = set()
    for value in df["category"].dropna():
        for item in split_values(value):
            values.add(item)
    return sorted(values)


def get_tags(df: pd.DataFrame) -> list[str]:
    """Return sorted unique tags."""
    values: set[str] = set()
    if "tags" not in df.columns:
        return []
    for value in df["tags"].dropna():
        for item in split_values(value):
            values.add(item)
    return sorted(values)


def row_has_any_value(cell_value: object, selected_values: Iterable[str]) -> bool:
    """Return True when a comma-like cell contains any selected value."""
    selected = set(selected_values)
    if not selected:
        return False
    return bool(set(split_values(cell_value)) & selected)


def make_maps_search_url(row: pd.Series) -> str:
    """Return the stored map URL or a Google Maps search URL."""
    map_url = str(row.get("map_url", "")).strip()
    if map_url and map_url.lower() != "nan":
        return map_url

    query_parts = [str(row.get("name", "")).strip(), str(row.get("area", "")).strip()]
    query = " ".join(part for part in query_parts if part and part.lower() != "nan")
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def filter_restaurants(
    df: pd.DataFrame,
    selected_categories: list[str],
    selected_tags: list[str],
    keyword: str,
) -> pd.DataFrame:
    """Filter restaurants by category, tags, and keyword."""
    filtered = df.copy()

    if selected_categories:
        filtered = filtered[
            filtered["category"].map(lambda value: row_has_any_value(value, selected_categories))
        ]
    else:
        filtered = filtered.iloc[0:0]

    if selected_tags:
        filtered = filtered[filtered["tags"].map(lambda value: row_has_any_value(value, selected_tags))]

    stripped_keyword = keyword.strip().lower()
    if stripped_keyword:
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
        existing_columns = [column for column in search_columns if column in filtered.columns]
        haystack = filtered[existing_columns].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
        filtered = filtered[haystack.str.contains(stripped_keyword, regex=False)]

    return filtered.reset_index(drop=True)


def render_category_checkboxes(categories: list[str]) -> list[str]:
    """Render category checkboxes and return selected categories."""
    st.sidebar.subheader("カテゴリ")

    if "selected_categories" not in st.session_state:
        st.session_state.selected_categories = categories.copy()

    col_a, col_b = st.sidebar.columns(2)
    if col_a.button("すべてON", use_container_width=True):
        st.session_state.selected_categories = categories.copy()
    if col_b.button("すべてOFF", use_container_width=True):
        st.session_state.selected_categories = []

    selected: list[str] = []
    columns = st.sidebar.columns(2)
    for index, category in enumerate(categories):
        key = f"category::{category}"
        default_value = category in st.session_state.selected_categories
        is_checked = columns[index % 2].checkbox(category, value=default_value, key=key)
        if is_checked:
            selected.append(category)

    st.session_state.selected_categories = selected
    return selected


def render_restaurant_card(row: pd.Series, title: str = "今日の候補") -> None:
    """Render a selected restaurant."""
    map_url = make_maps_search_url(row)

    st.markdown(f"### {title}: {row.get('name', '')}")
    st.markdown(f"[Google Mapsで開く]({map_url})")

    meta_items = []
    for label, column in [
        ("カテゴリ", "category"),
        ("エリア", "area"),
        ("価格帯", "price_range"),
        ("営業時間", "open_hours"),
    ]:
        value = str(row.get(column, "")).strip()
        if value and value.lower() != "nan":
            meta_items.append(f"**{label}:** {value}")

    if meta_items:
        st.markdown("  ".join(meta_items))

    address = str(row.get("address", "")).strip()
    if address and address.lower() != "nan":
        st.caption(address)

    tags = str(row.get("tags", "")).strip()
    if tags and tags.lower() != "nan":
        st.write(f"🏷️ {tags}")

    note = str(row.get("note", "")).strip()
    if note and note.lower() != "nan":
        st.info(note)


def render_setup_help() -> None:
    """Render setup instructions when no Google Sheets URL is configured."""
    st.warning("Google Sheets URLが未設定です。")
    st.markdown(
        """
        `streamlit_app.py` と同じリポジトリをStreamlit Cloudへデプロイし、Secretsに以下を設定してください。

        ```toml
        GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/xxxxxxxx/edit#gid=0"
        ```

        Google Sheets側には、最低限この2列が必要です。

        ```csv
        name,category
        ```

        推奨列は以下です。

        ```csv
        name,category,area,map_url,address,price_range,open_hours,tags,note,active
        ```
        """
    )


def main() -> None:
    """Run the Streamlit application."""
    st.title(APP_TITLE)
    st.caption("Google Sheetsの店舗リストから、カテゴリ条件に合うランチ候補をランダムに選びます。")

    configured_url = get_secret_or_empty("GOOGLE_SHEET_URL") or get_secret_or_empty("GOOGLE_SHEET_CSV_URL")

    with st.sidebar:
        st.header("データソース")
        manual_url = st.text_input(
            "Google Sheets URL",
            value=configured_url,
            placeholder="https://docs.google.com/spreadsheets/d/1ZrXZcY-Fr4My0aoj8VCT6VxG_SN6czrvLa7xT8pw1U4/edit?gid=0#gid=0",
            help="Streamlit CloudではSecretsのGOOGLE_SHEET_URLに設定するのがおすすめです。",
        )
        uploaded_file = st.file_uploader("一時確認用CSV", type=["csv"])
        if st.button("データを再読み込み", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    try:
        if uploaded_file is not None:
            csv_text = uploaded_file.getvalue().decode("utf-8-sig")
            df = load_restaurants_from_uploaded_csv(csv_text)
            source_label = "アップロードCSV"
        elif manual_url.strip():
            df = load_restaurants_from_url(manual_url.strip())
            source_label = "Google Sheets"
        else:
            render_setup_help()
            return
    except DataLoadError as exc:
        st.error(str(exc))
        st.stop()

    categories = get_categories(df)
    selected_categories = render_category_checkboxes(categories)

    st.sidebar.subheader("追加フィルター")
    tags = get_tags(df)
    selected_tags = st.sidebar.multiselect("タグ", options=tags)
    keyword = st.sidebar.text_input("キーワード", placeholder="例: カレー / テラス / 一人OK")
    avoid_previous = st.sidebar.checkbox("前回と同じ店を避ける", value=True)

    filtered = filter_restaurants(df, selected_categories, selected_tags, keyword)

    metric_col_1, metric_col_2, metric_col_3 = st.columns(3)
    metric_col_1.metric("データソース", source_label)
    metric_col_2.metric("登録店舗", len(df))
    metric_col_3.metric("現在の候補", len(filtered))

    if filtered.empty:
        st.error("条件に合う店舗がありません。カテゴリやフィルターを緩めてください。")
        st.stop()

    if "last_selected_name" not in st.session_state:
        st.session_state.last_selected_name = ""

    button_col_1, button_col_2 = st.columns([2, 1])
    pick_clicked = button_col_1.button("ランダムで選ぶ", type="primary", use_container_width=True)
    show_candidates = button_col_2.toggle("候補一覧を表示", value=False)

    if pick_clicked:
        choices = filtered
        if avoid_previous and len(filtered) > 1 and st.session_state.last_selected_name:
            choices = filtered[filtered["name"] != st.session_state.last_selected_name]
            if choices.empty:
                choices = filtered

        selected_row = choices.sample(n=1, random_state=random.randint(0, 10_000_000)).iloc[0]
        st.session_state.last_selected_name = str(selected_row["name"])
        st.session_state.selected_row = selected_row.to_dict()

    if "selected_row" in st.session_state:
        render_restaurant_card(pd.Series(st.session_state.selected_row))
    else:
        st.info("条件を確認してから「ランダムで選ぶ」を押してください。")

    if show_candidates:
        display_columns = [
            column
            for column in ["name", "category", "area", "price_range", "open_hours", "tags", "note"]
            if column in filtered.columns
        ]
        st.dataframe(filtered[display_columns], use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
