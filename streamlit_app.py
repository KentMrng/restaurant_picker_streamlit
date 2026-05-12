from __future__ import annotations

import random
from pathlib import Path

import pandas as pd
import streamlit as st


APP_TITLE = "周辺ランチ・飲食店ランダムピッカー"
CSV_PATH = Path("restaurants.csv")
REQUIRED_COLUMNS = {"name", "category"}
OPTIONAL_COLUMNS = {
    "area",
    "map_url",
    "address",
    "price_range",
    "open_hours",
    "tags",
    "note",
    "active",
}


@st.cache_data(show_spinner=False)
def load_restaurants(csv_path: str) -> pd.DataFrame:
    """Load restaurant candidates from a CSV file."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file was not found: {path}")

    df = pd.read_csv(path).fillna("")
    df.columns = [str(column).strip() for column in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        missing_columns = ", ".join(sorted(missing))
        raise ValueError(f"restaurants.csv is missing required columns: {missing_columns}")

    df["name"] = df["name"].astype(str).str.strip()
    df["category"] = df["category"].astype(str).str.strip()
    df = df[df["name"] != ""]
    df = df[df["category"] != ""]

    if "active" in df.columns:
        active_values = df["active"].astype(str).str.strip().str.lower()
        inactive_values = {"0", "false", "no", "n", "off", "inactive", "非表示", "無効"}
        df = df[~active_values.isin(inactive_values)]

    return df.reset_index(drop=True)


def build_google_maps_search_url(name: str, area: str = "") -> str:
    """Build a fallback Google Maps search URL when map_url is not provided."""
    query = f"{name} {area}".strip().replace(" ", "+")
    return f"https://www.google.com/maps/search/?api=1&query={query}"


def get_categories(df: pd.DataFrame) -> list[str]:
    """Return sorted category names from the CSV data."""
    return sorted(category for category in df["category"].dropna().unique() if str(category).strip())


def filter_restaurants(
    df: pd.DataFrame,
    selected_categories: list[str],
    keyword: str,
    include_tags: list[str],
) -> pd.DataFrame:
    """Filter restaurants by selected categories, keyword, and tags."""
    filtered = df[df["category"].isin(selected_categories)].copy()

    if keyword:
        keyword_lower = keyword.lower().strip()
        searchable_columns = [
            column
            for column in ["name", "category", "area", "address", "price_range", "open_hours", "tags", "note"]
            if column in filtered.columns
        ]
        mask = pd.Series(False, index=filtered.index)
        for column in searchable_columns:
            mask = mask | filtered[column].astype(str).str.lower().str.contains(keyword_lower, na=False)
        filtered = filtered[mask]

    if include_tags and "tags" in filtered.columns:
        tag_mask = pd.Series(False, index=filtered.index)
        for tag in include_tags:
            tag_mask = tag_mask | filtered["tags"].astype(str).str.contains(tag, case=False, na=False)
        filtered = filtered[tag_mask]

    return filtered.reset_index(drop=True)


def pick_random_restaurant(df: pd.DataFrame, avoid_previous: bool) -> dict[str, str] | None:
    """Pick one restaurant from the filtered candidates."""
    if df.empty:
        return None

    records = df.to_dict(orient="records")
    previous_name = st.session_state.get("picked_restaurant", {}).get("name")

    if avoid_previous and previous_name and len(records) > 1:
        records = [record for record in records if record.get("name") != previous_name]

    return random.choice(records)


def render_restaurant_card(restaurant: dict[str, str]) -> None:
    """Render the selected restaurant."""
    name = str(restaurant.get("name", "")).strip()
    category = str(restaurant.get("category", "")).strip()
    area = str(restaurant.get("area", "")).strip()
    map_url = str(restaurant.get("map_url", "")).strip()

    if not map_url:
        map_url = build_google_maps_search_url(name, area)

    st.subheader(name)
    st.caption(" / ".join(value for value in [category, area] if value))

    detail_rows = []
    for label, column in [
        ("住所", "address"),
        ("価格帯", "price_range"),
        ("営業時間", "open_hours"),
        ("タグ", "tags"),
        ("メモ", "note"),
    ]:
        value = str(restaurant.get(column, "")).strip()
        if value:
            detail_rows.append((label, value))

    if detail_rows:
        for label, value in detail_rows:
            st.markdown(f"**{label}:** {value}")

    st.link_button("Google Mapsで開く", map_url)


def render_candidates_table(df: pd.DataFrame) -> None:
    """Render the filtered candidates as a compact table."""
    display_columns = [
        column
        for column in ["name", "category", "area", "price_range", "tags", "note"]
        if column in df.columns
    ]
    if display_columns:
        st.dataframe(
            df[display_columns],
            use_container_width=True,
            hide_index=True,
        )


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🍽️", layout="wide")
    st.title("🍽️ 周辺ランチ・飲食店ランダムピッカー")
    st.caption("restaurants.csv のリストから、カテゴリ条件に合うお店をランダムに選びます。")

    try:
        df = load_restaurants(str(CSV_PATH))
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    categories = get_categories(df)
    if not categories:
        st.error("restaurants.csv に有効な category がありません。")
        st.stop()

    all_tags: list[str] = []
    if "tags" in df.columns:
        tag_values = df["tags"].astype(str).str.split(",")
        all_tags = sorted(
            {
                tag.strip()
                for tags in tag_values
                for tag in tags
                if tag.strip()
            }
        )

    with st.sidebar:
        st.header("条件")
        st.write("カテゴリ")

        selected_categories = []
        for category in categories:
            checked = st.checkbox(category, value=True, key=f"category_{category}")
            if checked:
                selected_categories.append(category)

        st.divider()
        keyword = st.text_input("キーワード", placeholder="例: 駅近、安い、カレー")
        include_tags = st.multiselect("タグで絞り込み", all_tags) if all_tags else []
        avoid_previous = st.checkbox("前回と同じ店を避ける", value=True)
        show_candidates = st.checkbox("候補リストを表示", value=True)

    filtered = filter_restaurants(df, selected_categories, keyword, include_tags)

    left, right = st.columns([1, 1])
    with left:
        st.metric("候補数", len(filtered))
    with right:
        st.metric("登録店舗数", len(df))

    if filtered.empty:
        st.warning("条件に合うお店がありません。カテゴリやキーワードを調整してください。")
        if show_candidates:
            st.subheader("全登録リスト")
            render_candidates_table(df)
        st.stop()

    if "picked_restaurant" not in st.session_state:
        st.session_state["picked_restaurant"] = pick_random_restaurant(filtered, avoid_previous=False)

    if st.button("ランダムで選ぶ", type="primary", use_container_width=True):
        st.session_state["picked_restaurant"] = pick_random_restaurant(filtered, avoid_previous)

    picked_restaurant = st.session_state.get("picked_restaurant")
    if picked_restaurant:
        st.success("今日の候補")
        render_restaurant_card(picked_restaurant)

    if show_candidates:
        st.divider()
        st.subheader("現在の候補リスト")
        render_candidates_table(filtered)


if __name__ == "__main__":
    main()
