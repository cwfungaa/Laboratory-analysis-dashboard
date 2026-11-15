import streamlit as st

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

import pandas as pd
import matplotlib.pyplot as plt
import io

# =========================================================
# CONFIGURATION
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

st.set_page_config(page_title="Lab Data Analyzer", page_icon="🔬", layout="wide")
st.title("🔬 Laboratory Data Analyzer Dashboard")
st.markdown("Upload your raw lab data (Excel or CSV) to automatically generate peak day analytics, TAT metrics, and instrument distributions.")

uploaded_file = st.file_uploader("Drag and drop your Excel or CSV file here", type=['xlsx', 'csv', 'txt'])

if uploaded_file is not None:
    with st.spinner("Processing data..."):
        # 1. Read Data
        if uploaded_file.name.endswith('.csv') or uploaded_file.name.endswith('.txt'):
            df_raw = pd.read_csv(uploaded_file, low_memory=False)
        else:
            df_raw = pd.read_excel(uploaded_file)
        
        # 2. Date Parsing & Peak Day Isolation
        df_raw['RegistrationDateTime'] = pd.to_datetime(df_raw[COL_REG_DATE].astype(str) + ' ' + df_raw[COL_REG_TIME].astype(str), errors='coerce', dayfirst=False)
        df_raw['FirstScanDateTime'] = pd.to_datetime(df_raw[COL_FIRST_SCAN_DATE].astype(str) + ' ' + df_raw[COL_FIRST_SCAN_TIME].astype(str), errors='coerce', dayfirst=False)
        df_raw['ResultDateTime'] = pd.to_datetime(df_raw[COL_RESULT_DATE].astype(str) + ' ' + df_raw[COL_RESULT_TIME].astype(str), errors='coerce', dayfirst=False)
        df_raw['ValidationDateTime'] = pd.to_datetime(df_raw[COL_VAL_DATE].astype(str) + ' ' + df_raw[COL_VAL_TIME].astype(str), errors='coerce', dayfirst=False)

        df_raw['Arrival_Date'] = df_raw['FirstScanDateTime'].dt.date
        peak_date = df_raw['Arrival_Date'].value_counts().idxmax()
        
        df = df_raw[df_raw['Arrival_Date'] == peak_date].copy()
        df['Unique_Tube_ID'] = df[COL_FIRST_SCAN_DATE].astype(str) + "_" + df[COL_SAMPLE_ID].astype(str)

        # 3. Calculate TAT
        df['TAT_Scan_to_Result'] = (df['ResultDateTime'] - df['FirstScanDateTime']).dt.total_seconds() / 60
        df_per_test_tat = df.groupby(COL_TEST_NAME)['TAT_Scan_to_Result'].agg(['count', 'mean']).round(2).reset_index()
        df_per_test_tat.columns = ['Test Name', 'Total Count', 'Avg Scan-to-Result TAT (Min)']
        df_per_test_tat = df_per_test_tat.sort_values('Total Count', ascending=False)

        # 4. Generate Summaries
        sample_level_df = df.groupby('Unique_Tube_ID').agg(
            Sample_Type=(COL_MATERIAL, 'first'),
            Test_Combination=(COL_TEST_NAME, lambda x: ' + '.join(sorted(set(x.dropna())))),
            Instruments_Used=(COL_INSTRUMENT, lambda x: ' + '.join(sorted(set(x.dropna().astype(str)))))
        ).reset_index()

        # Detailed Test & Instrument Combinations
        test_combo_totals = sample_level_df['Test_Combination'].value_counts().reset_index()
        test_combo_totals.columns = ['Test_Combination', 'Total_Freq']
        
        test_combo_freq = sample_level_df.groupby(['Test_Combination', 'Instruments_Used']).size().reset_index(name='Frequency')
        test_combo_freq = test_combo_freq.merge(test_combo_totals, on='Test_Combination')
        test_combo_freq = test_combo_freq.sort_values(by=['Total_Freq', 'Frequency'], ascending=[False, False])
        test_combo_freq = test_combo_freq[['Test_Combination', 'Instruments_Used', 'Frequency']]
        test_combo_freq.columns = ['Test Combination', 'Instrument Combination', 'Frequency']

        inst_combo_freq = sample_level_df['Instruments_Used'].value_counts().reset_index()
        inst_combo_freq.columns = ['Instrument Combination', 'Sample Count']

        # --- DASHBOARD UI ---
        st.success(f"**Peak Date Analyzed:** {peak_date} | **Total Tests Run:** {len(df)} | **Total Samples Processed:** {len(sample_level_df)}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Test & Instrument Combinations")
            st.dataframe(test_combo_freq.head(15), use_container_width=True, hide_index=True)
            
            st.subheader("Overall Instrument Usage")
            st.dataframe(inst_combo_freq.head(10), use_container_width=True, hide_index=True)

        with col2:
            st.subheader("Top Tests by Volume & Turnaround Time")
            st.dataframe(df_per_test_tat.head(15), use_container_width=True, hide_index=True)
            
            st.subheader("Sample Material Distribution")
            st.dataframe(sample_level_df['Sample_Type'].value_counts().reset_index(name='Count'), use_container_width=True, hide_index=True)

        # Hourly Arrival Chart
        st.subheader("Hourly Arrival Pattern")
        df['Arrival_Hour'] = df['FirstScanDateTime'].dt.hour
        hr_tubes = df.drop_duplicates(subset=['Unique_Tube_ID'])['Arrival_Hour'].value_counts().reindex(range(24), fill_value=0)
        hr_tests = df['Arrival_Hour'].value_counts().reindex(range(24), fill_value=0)

        fig, ax1 = plt.subplots(figsize=(12, 4))
        ax2 = ax1.twinx()
        ax1.plot(range(24), hr_tubes.values, marker='o', color='teal', linewidth=2, label='Tube Volume')
        ax2.plot(range(24), hr_tests.values, marker='s', color='darkorange', linewidth=2, linestyle='--', label='Test Volume')
        
        ax1.set_xlabel('Hour of Day (00:00 - 23:59)')
        ax1.set_ylabel('Number of Tubes', color='teal')
        ax2.set_ylabel('Number of Tests', color='darkorange')
        ax1.set_xticks(range(24))
        ax1.set_xticklabels([f"{h:02d}:00" for h in range(24)], rotation=45)
        ax1.grid(True, linestyle='--', alpha=0.5)
        lines_1, labels_1 = ax1.get_legend_handles_labels()
        lines_2, labels_2 = ax2.get_legend_handles_labels()
        ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left')
        
        st.pyplot(fig)

        # --- EXPORT TO EXCEL ---
        st.markdown("---")
        st.subheader("Export Formatted Results")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            test_combo_freq.to_excel(writer, sheet_name='Test & Inst Combos', index=False)
            inst_combo_freq.to_excel(writer, sheet_name='Overall Inst Combos', index=False)
            df_per_test_tat.to_excel(writer, sheet_name='Test TAT Details', index=False)
            df.drop(columns=['Unique_Tube_ID', 'Arrival_Date', 'Arrival_Hour'], errors='ignore').to_excel(writer, sheet_name='Raw Peak Data', index=False)
        
        excel_data = output.getvalue()
        
        st.download_button(
            label="📥 Download Full Excel Report",
            data=excel_data,
            file_name=f"Lab_Report_{peak_date}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )