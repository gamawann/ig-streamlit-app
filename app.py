from io import BytesIO
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="IG Discovery Tool", layout="wide")
st.title("IG Discovery Tool")
st.markdown("Cari hasil Instagram via SerpApi Google Search.")

PAGE_SIZE = 50

# =========================
# CONFIG
# =========================
try:
    SERPAPI_KEY = st.secrets["SERPAPI_KEY"]
except Exception:
    SERPAPI_KEY = ""

# =========================
# HELPERS
# =========================
def build_query(keyword: str) -> str:
    return f"{keyword.strip()} instagram"

def extract_username_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if not path:
            return ""

        parts = path.split("/")
        reserved = {
            "p", "reel", "stories", "explore", "accounts",
            "about", "developer", "legal", "press", "directory"
        }

        if len(parts) == 1 and parts[0] not in reserved:
            return parts[0]

        if len(parts) >= 2 and parts[0] not in reserved:
            return parts[0]

        return ""
    except Exception:
        return ""

def infer_type(url: str) -> str:
    url_l = url.lower()
    if "/reel/" in url_l:
        return "Reel"
    elif "/p/" in url_l:
        return "Post"
    elif "/stories/" in url_l:
        return "Story"
    elif "/explore/tags/" in url_l:
        return "Hashtag"
    else:
        return "Other / Profile / Unknown"

def is_instagram_result(url: str) -> bool:
    if not url:
        return False

    url_l = url.lower()
    if "instagram.com" not in url_l:
        return False

    blocked = [
        "/accounts/",
        "/developer/",
        "/about/",
        "/legal/",
        "/press/",
        "/directory/",
    ]
    if any(x in url_l for x in blocked):
        return False

    return True

def serpapi_google_search(query: str, num_results: int = 10, start: int = 0):
    endpoint = "https://serpapi.com/search.json"
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": min(max(num_results, 1), 10),   # per request max 10
        "start": start,                        # pagination offset
        "hl": "id",
        "gl": "id",
    }

    resp = requests.get(endpoint, params=params, timeout=30)
    if resp.status_code != 200:
        st.subheader("API Error Debug")
        st.write("Status code:", resp.status_code)
        try:
            st.json(resp.json())
        except Exception:
            st.text(resp.text)
        resp.raise_for_status()

    return resp.json()

def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="results")
    return output.getvalue()

def fetch_instagram_results(query: str, total_target: int, show_raw: bool = False):
    all_items = []
    raw_pages = []
    seen_links = set()

    # ambil per 10 hasil sampai total_target
    for start in range(0, total_target, 10):
        data = serpapi_google_search(query=query, num_results=10, start=start)
        raw_pages.append(data)

        organic_results = data.get("organic_results", [])
        if not organic_results:
            break

        for item in organic_results:
            link = item.get("link", "").strip()
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            all_items.append(item)

    rows = []
    filtered_seen = set()

    for item in all_items:
        link = item.get("link", "").strip()
        title = item.get("title", "").strip()
        snippet = item.get("snippet", "").strip()

        if not is_instagram_result(link):
            continue

        if link in filtered_seen:
            continue
        filtered_seen.add(link)

        rows.append({
            "link": link,
            "username": extract_username_from_url(link),
            "caption": snippet or title,
            "type": infer_type(link),
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df[["link", "username", "caption", "type"]]

    return df, raw_pages

# =========================
# SESSION STATE
# =========================
if "search_keyword" not in st.session_state:
    st.session_state.search_keyword = ""

if "search_from" not in st.session_state:
    st.session_state.search_from = None

if "search_to" not in st.session_state:
    st.session_state.search_to = None

if "current_limit" not in st.session_state:
    st.session_state.current_limit = PAGE_SIZE

if "results_df" not in st.session_state:
    st.session_state.results_df = pd.DataFrame()

if "last_query" not in st.session_state:
    st.session_state.last_query = ""

# =========================
# INPUTS
# =========================
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    keyword = st.text_input("Keyword", value=st.session_state.search_keyword)

with col2:
    start_date = st.date_input("Dari tanggal")

with col3:
    end_date = st.date_input("Sampai tanggal")

show_raw = st.checkbox("Tampilkan raw API results", value=False)

col_btn1, col_btn2 = st.columns([1, 1])
with col_btn1:
    run_search = st.button("Search", use_container_width=True)
with col_btn2:
    load_more = st.button("Load more", use_container_width=True)

# =========================
# SEARCH ACTION
# =========================
if run_search:
    if not keyword.strip():
        st.warning("Masukkan keyword dulu.")
    elif start_date > end_date:
        st.warning("Tanggal awal tidak boleh lebih besar dari tanggal akhir.")
    elif not SERPAPI_KEY:
        st.error("Isi SERPAPI_KEY dulu di Streamlit secrets.")
    else:
        st.session_state.search_keyword = keyword.strip()
        st.session_state.search_from = str(start_date)
        st.session_state.search_to = str(end_date)
        st.session_state.current_limit = PAGE_SIZE
        st.session_state.last_query = build_query(keyword.strip())

        try:
            df, raw_pages = fetch_instagram_results(
                query=st.session_state.last_query,
                total_target=st.session_state.current_limit,
                show_raw=show_raw,
            )
            st.session_state.results_df = df

            if show_raw:
                st.subheader("Raw API Results")
                st.json(raw_pages)

        except Exception as e:
            st.error(f"Terjadi error saat search: {e}")

# =========================
# LOAD MORE ACTION
# =========================
if load_more:
    if not st.session_state.search_keyword:
        st.warning("Lakukan search dulu.")
    elif not SERPAPI_KEY:
        st.error("Isi SERPAPI_KEY dulu di Streamlit secrets.")
    else:
        st.session_state.current_limit += PAGE_SIZE

        try:
            df, raw_pages = fetch_instagram_results(
                query=st.session_state.last_query,
                total_target=st.session_state.current_limit,
                show_raw=show_raw,
            )
            st.session_state.results_df = df

            if show_raw:
                st.subheader("Raw API Results")
                st.json(raw_pages)

        except Exception as e:
            st.error(f"Terjadi error saat search: {e}")

# =========================
# RESULTS
# =========================
if st.session_state.last_query:
    st.subheader("Query")
    st.code(st.session_state.last_query)

if not st.session_state.results_df.empty:
    result_count = len(st.session_state.results_df)
    st.markdown(f"**Showing {result_count} results**")

    st.dataframe(st.session_state.results_df, use_container_width=True)

    excel_bytes = dataframe_to_excel_bytes(st.session_state.results_df)
    st.download_button(
        label=f"Download XLSX ({result_count})",
        data=excel_bytes,
        file_name="ig_results_serpapi.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
elif st.session_state.last_query:
    st.info("Tidak ada hasil Instagram yang lolos filter dari SerpApi.")
