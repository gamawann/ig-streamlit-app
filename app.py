from io import BytesIO
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="IG Discovery Tool", layout="wide")
st.title("IG Discovery Tool")
st.markdown("Cari hasil Instagram via SerpApi Google Search.")

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

def serpapi_google_search(query: str, num_results: int = 10):
    endpoint = "https://serpapi.com/search.json"
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": min(max(num_results, 1), 10),
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

    data = resp.json()
    return data

def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="results")
    return output.getvalue()

# =========================
# INPUTS
# =========================
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    keyword = st.text_input("Keyword")

with col2:
    start_date = st.date_input("Dari tanggal")

with col3:
    end_date = st.date_input("Sampai tanggal")

max_results = st.slider("Jumlah hasil", min_value=1, max_value=10, value=10, step=1)
show_raw = st.checkbox("Tampilkan raw API results", value=False)

run_search = st.button("Search")

# =========================
# SEARCH
# =========================
if run_search:
    if not keyword.strip():
        st.warning("Masukkan keyword dulu.")
    elif start_date > end_date:
        st.warning("Tanggal awal tidak boleh lebih besar dari tanggal akhir.")
    elif not SERPAPI_KEY:
        st.error("Isi SERPAPI_KEY dulu di .streamlit/secrets.toml")
    else:
        query = build_query(keyword)
        st.subheader("Query")
        st.code(query)

        try:
            data = serpapi_google_search(query=query, num_results=max_results)

            if show_raw:
                st.subheader("Raw API Results")
                st.json(data)

            organic_results = data.get("organic_results", [])

            rows = []
            seen = set()

            for item in organic_results:
                link = item.get("link", "").strip()
                title = item.get("title", "").strip()
                snippet = item.get("snippet", "").strip()

                if not is_instagram_result(link):
                    continue

                if link in seen:
                    continue
                seen.add(link)

                rows.append({
                    "link": link,
                    "username": extract_username_from_url(link),
                    "caption": snippet or title,
                    "type": infer_type(link),
                    "keyword": keyword,
                    "date_from": str(start_date),
                    "date_to": str(end_date),
                })

            df = pd.DataFrame(rows)

            if df.empty:
                st.info("Tidak ada hasil Instagram yang lolos filter dari SerpApi.")
            else:
                st.subheader("Results")
                st.dataframe(df, use_container_width=True)

                excel_bytes = dataframe_to_excel_bytes(df)
                st.download_button(
                    label="Download XLSX",
                    data=excel_bytes,
                    file_name="ig_results_serpapi.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        except Exception as e:
            st.error(f"Terjadi error saat search: {e}")