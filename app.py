import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io

# =========================================================
# PAGE CONFIG & AUTHENTICATION
# =========================================================
st.set_page_config(page_title="Lab Data Analyzer", page_icon="🔬", layout="wide")

def check_password():
    if st.session_state.get("authenticated"):
        return True
    pwd = st.text_input("Enter Lab Dashboard Password", type="password")
    if pwd:
        if pwd == st.secrets["APP_PASSWORD"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password")
    return False

if not check_password():
    st.stop()

# =========================================================
# CONFIGURATION & DATA LOADING
# =========================================================
COL_SAMPLE_ID = 'SampleID'
COL_TEST_NAME = 'TestName'
COL_MATERIAL = 'Material'
COL_ACN = 'ACN'
COL_INSTRUMENT = 'InstrumentName' 

COL_REG_DATE = 'TestRegistrationDate'
COL_REG_TIME = 'TestRegistrationTime'
COL_FIRST_SCAN_DATE = 'FirstScanDate'
COL_FIRST_SCAN_TIME = 'FirstScanTime'
COL_RESULT_DATE = 'ResultDate'
COL_RESULT_TIME = 'ResultTime'
COL_VAL_DATE = 'ValidationDate'
COL_VAL_TIME = 'ValidationTime'

@st.cache_data(show_spinner=False)
def load_and_parse_data(file_bytes, file_name):
    if file_name.endswith('.csv') or file_name.endswith('.txt'):
        df_raw = pd.read_csv(io.BytesIO(file_bytes), low_memory=False)
    else:
        df_raw = pd.read_excel(io.BytesIO(file_bytes))
        
    df_raw['RegistrationDateTime'] = pd.to_datetime(df_raw[COL_REG_DATE].astype(str) + ' ' + df_raw[COL_REG_TIME].astype(str), errors='coerce', dayfirst=False)
    df_raw['FirstScanDateTime'] = pd.to_datetime(df_raw[COL_FIRST_SCAN_DATE].astype(str) + ' ' + df_raw[COL_FIRST_SCAN_TIME].astype(str), errors='coerce', dayfirst=False)
    df_raw['ResultDateTime'] = pd.to_datetime(df_raw[COL_RESULT_DATE].astype(str) + ' ' + df_raw[COL_RESULT_TIME].astype(str), errors='coerce', dayfirst=False)
    df_raw['ValidationDateTime'] = pd.to_datetime(df_raw[COL_VAL_DATE].astype(str) + ' ' + df_raw[COL_VAL_TIME].astype(str), errors='coerce', dayfirst=False)

    df_raw['Arrival_Date'] = df_raw['FirstScanDateTime'].dt.date
    df_raw['Unique_Tube_ID'] = df_raw[COL_FIRST_SCAN_DATE].astype(str) + "_" + df_raw[COL_SAMPLE_ID].astype(str)

    # Classify Assay Type based on ACN (10000 to 20000 = IM, otherwise CC)
    acn_numeric = pd.to_numeric(df_raw[COL_ACN], errors='coerce')
    df_raw['Assay_Category'] = acn_numeric.apply(
        lambda x: 'Immunoassay (IM)' if pd.notna(x) and (10000 <= x <= 20000) else 'Clinical Chemistry (CC)'
    )
    
    return df_raw

# =========================================================
# MAIN UI
# =========================================================
st.title("🔬 Laboratory Data Analyzer Dashboard")
st.markdown("Upload your raw lab data (Excel or CSV) to explore daily analytics, peak test/sample days, CC/IM assay distributions, TAT metrics, and instrument usage.")

uploaded_file = st.file_uploader("Drag and drop your Excel or CSV file here", type=['xlsx', 'csv', 'txt'])

if uploaded_file is not None:
    with st.spinner("Loading and parsing dataset..."):
        df_raw = load_and_parse_data(uploaded_file.getvalue(), uploaded_file.name)

    # 1. Daily Volume & Peak Calculation (Tests & Samples)
    valid_df = df_raw.dropna(subset=['Arrival_Date'])
    if valid_df.empty:
        st.error("No valid arrival dates found in the uploaded file. Please check your date columns.")
        st.stop()

    daily_stats = valid_df.groupby('Arrival_Date').agg(
        Test_Count=(COL_TEST_NAME, 'count'),
        Sample_Count=('Unique_Tube_ID', 'nunique')
    ).sort_index(ascending=False)

    peak_test_date = daily_stats['Test_Count'].idxmax()
    peak_sample_date = daily_stats['Sample_Count'].idxmax()
    sorted_dates = daily_stats.index.tolist()

    def format_date_label(d):
        t_cnt = daily_stats.loc[d, 'Test_Count']
        s_cnt = daily_stats.loc[d, 'Sample_Count']
        tags = []
        if d == peak_test_date and d == peak_sample_date:
            tags.append("⭐ Peak Tests & Samples")
        else:
            if d == peak_test_date:
                tags.append("🧪 Peak Tests")
            if d == peak_sample_date:
                tags.append("🧫 Peak Samples")
        tag_str = f" [{' | '.join(tags)}]" if tags else ""
        return f"{d} — {t_cnt:,} tests | {s_cnt:,} samples{tag_str}"

    # Quick Peak Filter + Date Dropdown
    col_filter, col_select = st.columns([1.2, 1.8])
    with col_filter:
        peak_mode = st.radio(
            "🎯 Quick Peak Filter:",
            options=["Peak Test Day", "Peak Sample Day", "All Dates (Manual)"],
            horizontal=True
        )

    if peak_mode == "Peak Test Day":
        default_date = peak_test_date
    elif peak_mode == "Peak Sample Day":
        default_date = peak_sample_date
    else:
        default_date = peak_test_date

    with col_select:
        selected_date = st.selectbox(
            "📅 Select Date to Analyze:",
            options=sorted_dates,
            index=sorted_dates.index(default_date),
            format_func=format_date_label
        )

    # Summary callout banner for both peaks
    st.info(
        f"**Peak Test Volume Day:** `{peak_test_date}` ({daily_stats.loc[peak_test_date, 'Test_Count']:,} tests, {daily_stats.loc[peak_test_date, 'Sample_Count']:,} samples)  |  "
        f"**Peak Sample Volume Day:** `{peak_sample_date}` ({daily_stats.loc[peak_sample_date, 'Sample_Count']:,} samples, {daily_stats.loc[peak_sample_date, 'Test_Count']:,} tests)"
    )

    with st.expander("📊 View All Dates Overview (Test & Sample Counts)"):
        daily_overview_display = daily_stats.reset_index().copy()
        daily_overview_display['Peak Status'] = daily_overview_display['Arrival_Date'].apply(
            lambda d: "⭐ Peak Tests & Samples" if (d == peak_test_date and d == peak_sample_date)
            else ("🧪 Peak Tests" if d == peak_test_date
                  else ("🧫 Peak Samples" if d == peak_sample_date else ""))
        )
        daily_overview_display.columns = ['Date', 'Total Tests', 'Total Samples', 'Peak Status']
        st.dataframe(daily_overview_display, use_container_width=True, hide_index=True)
