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
st.markdown("Upload your raw lab data (Excel or CSV) to explore daily analytics, CC/IM assay distributions, TAT metrics, and instrument usage.")

uploaded_file = st.file_uploader("Drag and drop your Excel or CSV file here", type=['xlsx', 'csv', 'txt'])

if uploaded_file is not None:
    with st.spinner("Loading and parsing dataset..."):
        df_raw = load_and_parse_data(uploaded_file.getvalue(), uploaded_file.name)

    # 1. Date Dropdown Setup (Defaults to Peak Day)
    valid_dates_counts = df_raw['Arrival_Date'].dropna().value_counts()
    if valid_dates_counts.empty:
        st.error("No valid arrival dates found in the uploaded file. Please check your date columns.")
        st.stop()

    peak_date = valid_dates_counts.idxmax()
    sorted_dates = sorted(valid_dates_counts.index.tolist(), reverse=True)
    default_index = sorted_dates.index(peak_date)

    col_select, col_info = st.columns([1, 2])
    with col_select:
        selected_date = st.selectbox(
            "📅 Select Date to Analyze:",
            options=sorted_dates,
            index=default_index,
            format_func=lambda d: f"{d} ⭐ (Peak Day - {valid_dates_counts[d]:,} tests)" if d == peak_date else f"{d} ({valid_dates_counts[d]:,} tests)"
        )

    # Filter data for the selected date
    df = df_raw[df_raw['Arrival_Date'] == selected_date].copy()
    df['Unique_Tube_ID'] = df[COL_FIRST_SCAN_DATE].astype(str) + "_" + df[COL_SAMPLE_ID].astype(str)

    # 2. Calculate Metrics & Summaries
    df['TAT_Scan_to_Result'] = (df['ResultDateTime'] - df['FirstScanDateTime']).dt.total_seconds() / 60
    
    total_tests = len(df)
    cc_count = len(df[df['Assay_Category'] == 'Clinical Chemistry (CC)'])
    im_count = len(df[df['Assay_Category'] == 'Immunoassay (IM)'])
    cc_pct = (cc_count / total_tests * 100) if total_tests > 0 else 0.0
    im_pct = (im_count / total_tests * 100) if total_tests > 0 else 0.0
    
    # CC to IM Ratio (%)
    cc_to_im_pct_ratio = (cc_count / im_count * 100) if im_count > 0 else None
    cc_to_im_split_str = f"{cc_pct:.1f}% : {im_pct:.1f}%"
    cc_to_im_rel_str = f"{cc_to_im_pct_ratio:.1f}%" if cc_to_im_pct_ratio is not None else "N/A (0 IM)"

    # Per-Test TAT & Assay Category
    df_per_test_tat = df.groupby([COL_TEST_NAME, 'Assay_Category'])['TAT_Scan_to_Result'].agg(['count', 'mean']).round(2).reset_index()
    df_per_test_tat.columns = ['Test Name', 'Assay Category', 'Total Count', 'Avg Scan-to-Result TAT (Min)']
    df_per_test_tat = df_per_test_tat.sort_values('Total Count', ascending=False)

    # Assay Category Summary (CC vs IM)
    assay_summary_df = df.groupby('Assay_Category').agg(
        Test_Count=(COL_TEST_NAME, 'count'),
        Unique_Samples=('Unique_Tube_ID', 'nunique'),
        Avg_TAT_Min=('TAT_Scan_to_Result', 'mean')
    ).round(2).reset_index()
    assay_summary_df['Share of Total Tests (%)'] = ((assay_summary_df['Test_Count'] / total_tests) * 100).round(2) if total_tests > 0 else 0.0
    assay_summary_df.columns = ['Assay Category', 'Total Tests', 'Unique Samples', 'Avg TAT (Min)', 'Share of Total Tests (%)']

    # Excel-ready Assay Summary including CC-to-IM Ratio rows
    ratio_rows = pd.DataFrame([
        {
            'Assay Category': 'CC : IM Split (%)',
            'Total Tests': f"{cc_count} : {im_count}",
            'Unique Samples': '-',
            'Avg TAT (Min)': '-',
            'Share of Total Tests (%)': cc_to_im_split_str
        },
        {
            'Assay Category': 'CC to IM Ratio (CC / IM %)',
            'Total Tests': '-',
            'Unique Samples': '-',
            'Avg TAT (Min)': '-',
            'Share of Total Tests (%)': cc_to_im_rel_str
        }
    ])
    assay_summary_excel = pd.concat([assay_summary_df, ratio_rows], ignore_index=True)

    # Sample-Level Aggregation
    sample_level_df = df.groupby('Unique_Tube_ID').agg(
        Sample_Type=(COL_MATERIAL, 'first'),
        Test_Combination=(COL_TEST_NAME, lambda x: ' + '.join(sorted(set(x.dropna())))),
        Instruments_Used=(COL_INSTRUMENT, lambda x: ' + '.join(sorted(set(x.dropna().astype(str))))),
        Assay_Combination=('Assay_Category', lambda x: ' + '.join(sorted(set(x.dropna()))))
    ).reset_index()

    test_combo_totals = sample_level_df['Test_Combination'].value_counts().reset_index()
    test_combo_totals.columns = ['Test_Combination', 'Total_Freq']
    
    test_combo_freq = sample_level_df.groupby(['Test_Combination', 'Instruments_Used']).size().reset_index(name='Frequency')
    test_combo_freq = test_combo_freq.merge(test_combo_totals, on='Test_Combination')
    test_combo_freq = test_combo_freq.sort_values(by=['Total_Freq', 'Frequency'], ascending=[False, False])
    test_combo_freq = test_combo_freq[['Test_Combination', 'Instruments_Used', 'Frequency']]
    test_combo_freq.columns = ['Test Combination', 'Instrument Combination', 'Frequency']

    inst_combo_freq = sample_level_df['Instruments_Used'].value_counts().reset_index()
    inst_combo_freq.columns = ['Instrument Combination', 'Sample Count']

    sample_type_freq = sample_level_df['Sample_Type'].value_counts().reset_index()
    sample_type_freq.columns = ['Sample Type', 'Count']

    # --- KPI METRIC CARDS ---
    st.markdown("---")
    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6, kpi7 = st.columns(7)
    avg_overall_tat = df['TAT_Scan_to_Result'].mean()
    
    kpi1.metric("Selected Date", f"{selected_date}", "Peak Day" if selected_date == peak_date else "Standard Day")
    kpi2.metric("Total Tests", f"{total_tests:,}")
    kpi3.metric("Total Samples", f"{len(sample_level_df):,}")
    kpi4.metric("Clinical Chem (CC)", f"{cc_count:,}", f"{cc_pct:.1f}% of tests")
    kpi5.metric("Immunoassay (IM)", f"{im_count:,}", f"{im_pct:.1f}% of tests")
    kpi6.metric("CC : IM Ratio (%)", cc_to_im_split_str, f"CC/IM: {cc_to_im_rel_str}")
    kpi7.metric("Overall Avg TAT", f"{avg_overall_tat:.1f} min" if pd.notna(avg_overall_tat) else "N/A")
    st.markdown("---")

    # --- GRAPHICAL DASHBOARD SECTIONS ---
    col1, col2 = st.columns(2)
    
    with col1:
        # Section 1: Clinical Chemistry vs Immunoassay Breakdown
        st.subheader(f"🧬 Clinical Chemistry (CC) vs. Immunoassay (IM) — {cc_to_im_split_str}")
        fig_assay = px.pie(
            assay_summary_df,
            values='Total Tests',
            names='Assay Category',
            hole=0.45,
            color='Assay Category',
            color_discrete_map={
                'Clinical Chemistry (CC)': '#1f77b4',
                'Immunoassay (IM)': '#ff7f0e'
            },
            height=380
        )
        fig_assay.update_traces(textposition='inside', textinfo='percent+label+value')
        fig_assay.update_layout(margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_assay, use_container_width=True)
        with st.expander("View CC vs. IM Summary & Ratio Table"):
            st.dataframe(assay_summary_excel, use_container_width=True, hide_index=True)

        # Section 2: Test & Instrument Combinations
        st.subheader("🧪 Top Test & Instrument Combinations")
        top_combos = test_combo_freq.head(12).iloc[::-1]
        fig_combos = px.bar(
            top_combos,
            x='Frequency',
            y='Test Combination',
            color='Instrument Combination',
            orientation='h',
            text='Frequency',
            labels={'Frequency': 'Sample Count', 'Test Combination': ''},
            height=420
        )
        fig_combos.update_layout(
            barmode='stack',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=""),
            margin=dict(l=10, r=10, t=40, b=10)
        )
        st.plotly_chart(fig_combos, use_container_width=True)
        with st.expander("View Test & Instrument Data Table"):
            st.dataframe(test_combo_freq, use_container_width=True, hide_index=True)
        
        # Section 3: Overall Instrument Usage
        st.subheader("⚙️ Overall Instrument Usage")
        top_inst = inst_combo_freq.head(10).iloc[::-1]
        fig_inst = px.bar(
            top_inst,
            x='Sample Count',
            y='Instrument Combination',
            orientation='h',
            text='Sample Count',
            color='Sample Count',
            color_continuous_scale='Teal',
            labels={'Instrument Combination': ''},
            height=380
        )
        fig_inst.update_layout(coloraxis_showscale=False, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_inst, use_container_width=True)
        with st.expander("View Instrument Usage Data Table"):
            st.dataframe(inst_combo_freq, use_container_width=True, hide_index=True)

    with col2:
        # Section 4: Sample Material Distribution
        st.subheader("🩸 Sample Material Distribution")
        fig_mat = px.pie(
            sample_type_freq,
            values='Count',
            names='Sample Type',
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Set2,
            height=380
        )
        fig_mat.update_traces(textposition='inside', textinfo='percent+label')
        fig_mat.update_layout(margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_mat, use_container_width=True)
        with st.expander("View Sample Material Data Table"):
            st.dataframe(sample_type_freq, use_container_width=True, hide_index=True)

        # Section 5: Top Tests by Volume, Assay Category & TAT
        st.subheader("⏱️ Top Tests by Volume, Assay Type & Avg TAT")
        top_tat = df_per_test_tat.head(12).iloc[::-1]
        fig_tat = px.bar(
            top_tat,
            x='Total Count',
            y='Test Name',
            color='Assay Category',
            orientation='h',
            text=top_tat.apply(lambda r: f"{r['Total Count']} ({r['Avg Scan-to-Result TAT (Min)']}m)", axis=1),
            hover_data=['Assay Category', 'Avg Scan-to-Result TAT (Min)'],
            color_discrete_map={
                'Clinical Chemistry (CC)': '#1f77b4',
                'Immunoassay (IM)': '#ff7f0e'
            },
            labels={'Test Name': '', 'Avg Scan-to-Result TAT (Min)': 'Avg TAT (min)'},
            height=420
        )
        fig_tat.update_traces(textposition='outside')
        fig_tat.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=""),
            margin=dict(l=10, r=40, t=40, b=10)
        )
        st.plotly_chart(fig_tat, use_container_width=True)
        with st.expander("View Test Volume & TAT Data Table"):
            st.dataframe(df_per_test_tat, use_container_width=True, hide_index=True)

    # --- HOURLY ARRIVAL PATTERN (TUBES, CC TESTS, IM TESTS) ---
    st.subheader(f"📈 Hourly Arrival Pattern ({selected_date})")
    df['Arrival_Hour'] = df['FirstScanDateTime'].dt.hour
    hr_tubes = df.drop_duplicates(subset=['Unique_Tube_ID'])['Arrival_Hour'].value_counts().reindex(range(24), fill_value=0)
    hr_cc = df[df['Assay_Category'] == 'Clinical Chemistry (CC)']['Arrival_Hour'].value_counts().reindex(range(24), fill_value=0)
    hr_im = df[df['Assay_Category'] == 'Immunoassay (IM)']['Arrival_Hour'].value_counts().reindex(range(24), fill_value=0)
    hours_labels = [f"{h:02d}:00" for h in range(24)]

    fig_hourly = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig_hourly.add_trace(
        go.Scatter(
            x=hours_labels, y=hr_tubes.values, name="Total Tubes",
            mode='lines+markers', line=dict(color='teal', width=3), marker=dict(size=8)
        ),
        secondary_y=False,
    )
    fig_hourly.add_trace(
        go.Scatter(
            x=hours_labels, y=hr_cc.values, name="Clinical Chemistry (CC) Tests",
            mode='lines+markers', line=dict(color='#1f77b4', width=2.5, dash='dash'), marker=dict(size=7, symbol='square')
        ),
        secondary_y=True,
    )
    fig_hourly.add_trace(
        go.Scatter(
            x=hours_labels, y=hr_im.values, name="Immunoassay (IM) Tests",
            mode='lines+markers', line=dict(color='#ff7f0e', width=2.5, dash='dot'), marker=dict(size=7, symbol='diamond')
        ),
        secondary_y=True,
    )

    fig_hourly.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=30, b=10),
        height=400
    )
    fig_hourly.update_xaxes(title_text="Hour of Day (00:00 - 23:59)")
    fig_hourly.update_yaxes(title_text="Number of Tubes", title_font=dict(color="teal"), secondary_y=False)
    fig_hourly.update_yaxes(title_text="Number of Tests (CC & IM)", title_font=dict(color="#1f77b4"), secondary_y=True)

    st.plotly_chart(fig_hourly, use_container_width=True)

    # --- EXPORT TO EXCEL ---
    st.markdown("---")
    st.subheader("📥 Export Formatted Results")
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        assay_summary_excel.to_excel(writer, sheet_name='Assay Summary (CC vs IM)', index=False)
        df_per_test_tat.to_excel(writer, sheet_name='Test TAT Details', index=False)
        test_combo_freq.to_excel(writer, sheet_name='Test & Inst Combos', index=False)
        inst_combo_freq.to_excel(writer, sheet_name='Overall Inst Combos', index=False)
        df.drop(columns=['Unique_Tube_ID', 'Arrival_Date', 'Arrival_Hour'], errors='ignore').to_excel(writer, sheet_name='Raw Selected Date Data', index=False)
    
    excel_data = output.getvalue()
    
    st.download_button(
        label=f"📥 Download Excel Report for {selected_date}",
        data=excel_data,
        file_name=f"Lab_Report_{selected_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
