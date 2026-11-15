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
    return df_raw

# =========================================================
# MAIN UI
# =========================================================
st.title("🔬 Laboratory Data Analyzer Dashboard")
st.markdown("Upload your raw lab data (Excel or CSV) to explore daily analytics, TAT metrics, and instrument distributions.")

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
    df_per_test_tat = df.groupby(COL_TEST_NAME)['TAT_Scan_to_Result'].agg(['count', 'mean']).round(2).reset_index()
    df_per_test_tat.columns = ['Test Name', 'Total Count', 'Avg Scan-to-Result TAT (Min)']
    df_per_test_tat = df_per_test_tat.sort_values('Total Count', ascending=False)

    sample_level_df = df.groupby('Unique_Tube_ID').agg(
        Sample_Type=(COL_MATERIAL, 'first'),
        Test_Combination=(COL_TEST_NAME, lambda x: ' + '.join(sorted(set(x.dropna())))),
        Instruments_Used=(COL_INSTRUMENT, lambda x: ' + '.join(sorted(set(x.dropna().astype(str)))))
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
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    avg_overall_tat = df['TAT_Scan_to_Result'].mean()
    
    kpi1.metric("Selected Date", f"{selected_date}", "Peak Day" if selected_date == peak_date else "Standard Day")
    kpi2.metric("Total Tests Run", f"{len(df):,}")
    kpi3.metric("Total Samples (Tubes)", f"{len(sample_level_df):,}")
    kpi4.metric("Overall Avg TAT", f"{avg_overall_tat:.1f} min" if pd.notna(avg_overall_tat) else "N/A")
    st.markdown("---")

    # --- GRAPHICAL DASHBOARD SECTIONS ---
    col1, col2 = st.columns(2)
    
    with col1:
        # Section 1: Test & Instrument Combinations
        st.subheader("🧪 Top Test & Instrument Combinations")
        top_combos = test_combo_freq.head(12).iloc[::-1] # Reverse for top-down horizontal bar
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
        
        # Section 2: Overall Instrument Usage
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
        # Section 3: Top Tests by Volume & TAT
        st.subheader("⏱️ Top Tests by Volume & Avg TAT")
        top_tat = df_per_test_tat.head(12).iloc[::-1]
        fig_tat = px.bar(
            top_tat,
            x='Total Count',
            y='Test Name',
            color='Avg Scan-to-Result TAT (Min)',
            orientation='h',
            text='Total Count',
            hover_data=['Avg Scan-to-Result TAT (Min)'],
            color_continuous_scale='YlOrRd',
            labels={'Test Name': '', 'Avg Scan-to-Result TAT (Min)': 'Avg TAT (min)'},
            height=420
        )
        fig_tat.update_layout(margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_tat, use_container_width=True)
        with st.expander("View Test Volume & TAT Data Table"):
            st.dataframe(df_per_test_tat, use_container_width=True, hide_index=True)
        
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

    # --- HOURLY ARRIVAL PATTERN (INTERACTIVE DUAL-AXIS) ---
    st.subheader(f"📈 Hourly Arrival Pattern ({selected_date})")
    df['Arrival_Hour'] = df['FirstScanDateTime'].dt.hour
    hr_tubes = df.drop_duplicates(subset=['Unique_Tube_ID'])['Arrival_Hour'].value_counts().reindex(range(24), fill_value=0)
    hr_tests = df['Arrival_Hour'].value_counts().reindex(range(24), fill_value=0)
    hours_labels = [f"{h:02d}:00" for h in range(24)]

    fig_hourly = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig_hourly.add_trace(
        go.Scatter(
            x=hours_labels, y=hr_tubes.values, name="Tube Volume",
            mode='lines+markers', line=dict(color='teal', width=3), marker=dict(size=8)
        ),
        secondary_y=False,
    )
    fig_hourly.add_trace(
        go.Scatter(
            x=hours_labels, y=hr_tests.values, name="Test Volume",
            mode='lines+markers', line=dict(color='darkorange', width=3, dash='dash'), marker=dict(size=8, symbol='square')
        ),
        secondary_y=True,
    )

    fig_hourly.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=30, b=10),
        height=380
    )
    fig_hourly.update_xaxes(title_text="Hour of Day (00:00 - 23:59)")
    fig_hourly.update_yaxes(title_text="Number of Tubes", title_font=dict(color="teal"), secondary_y=False)
    fig_hourly.update_yaxes(title_text="Number of Tests", title_font=dict(color="darkorange"), secondary_y=True)

    st.plotly_chart(fig_hourly, use_container_width=True)

    # --- EXPORT TO EXCEL ---
    st.markdown("---")
    st.subheader("📥 Export Formatted Results")
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        test_combo_freq.to_excel(writer, sheet_name='Test & Inst Combos', index=False)
        inst_combo_freq.to_excel(writer, sheet_name='Overall Inst Combos', index=False)
        df_per_test_tat.to_excel(writer, sheet_name='Test TAT Details', index=False)
        df.drop(columns=['Unique_Tube_ID', 'Arrival_Date', 'Arrival_Hour'], errors='ignore').to_excel(writer, sheet_name='Raw Selected Date Data', index=False)
    
    excel_data = output.getvalue()
    
    st.download_button(
        label=f"📥 Download Excel Report for {selected_date}",
        data=excel_data,
        file_name=f"Lab_Report_{selected_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
