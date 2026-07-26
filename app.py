import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
import os
import base64
import re

# 1. Page Configuration
st.set_page_config(page_title="Quant Dashboard", layout="wide", initial_sidebar_state="expanded")

# 2. Point Streamlit to your Custom HTML Folder
parent_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.join(parent_dir, "quant_frontend")
quant_ui = components.declare_component("quant_ui", path=frontend_dir)

# 3. Streamlit Native Sidebar
st.sidebar.header("🛡️ Daily Files Portal")
file_reg = st.sidebar.file_uploader("1. Registry CSV", type=['csv'])
file_broker = st.sidebar.file_uploader("2. Broker Statement", type=['csv', 'xlsx', 'xls'])
file_pngs = st.sidebar.file_uploader("3. Top 70 Chart Images (.jpg/.png)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

reg_data_dict = []
broker_data_dict = []
traded_images_b64 = {}
top_70_png_universe = [] # Store the exact symbols from the 70 PNGs

# 4. Ultra-Flexible Data Processing
if file_reg and file_broker:
    try:
        # --- PARSE REGISTRY ---
        df_reg = pd.read_csv(file_reg).fillna("")
        
        reg_map = {}
        for col in df_reg.columns:
            c = str(col).lower().strip()
            if 'symbol' in c or 'ticker' in c: reg_map[col] = 'Symbol'
            elif 'type' in c or 'zone' in c: reg_map[col] = 'Type'
            elif 'sl' in c or 'harmonic' in c or 'stop' in c: reg_map[col] = 'SL'
            elif 'tp' in c or 'kinetic' in c or 'target' in c: reg_map[col] = 'TP'
        
        df_reg = df_reg.rename(columns=reg_map)
        
        # 🚨 FIX 1: DEDUPLICATE REGISTRY SO SYMBOLS NEVER REPEAT 🚨
        if 'Symbol' in df_reg.columns:
            df_reg['Symbol'] = df_reg['Symbol'].astype(str).str.upper().str.strip()
            df_reg = df_reg.drop_duplicates(subset=['Symbol'], keep='first').reset_index(drop=True)
            
        if 'Rank' not in df_reg.columns:
            df_reg['Rank'] = range(1, len(df_reg) + 1)
            
        # --- PARSE BROKER KOTAK EXCEL ---
        df_broker_raw = pd.read_excel(file_broker, header=None).fillna("")
        
        header_idx = 0
        for i, row in df_broker_raw.head(30).iterrows():
            row_text = " ".join(row.astype(str).str.lower())
            if 'security name' in row_text or 'trade date' in row_text or 'quantity' in row_text:
                header_idx = i
                break
                
        df_broker = pd.read_excel(file_broker, skiprows=header_idx).fillna("")
        
        col_map = {}
        for col in df_broker.columns:
            c = str(col).lower().strip()
            if c in ['security name', 'scrip name', 'scrip']: col_map[col] = 'Name'
            elif c in ['trade time', 'time']: col_map[col] = 'Time'
            elif c in ['transaction type', 'buy/sell', 'type']: col_map[col] = 'Type'
            elif c in ['quantity', 'qty']: col_map[col] = 'Qty'
            elif c in ['market rate', 'price', 'rate']: col_map[col] = 'Price'
            elif c in ['total', 'value', 'net amount', 'net total']: col_map[col] = 'Value'
            
        df_broker = df_broker.rename(columns=col_map)
        df_broker = df_broker.loc[:, ~df_broker.columns.duplicated()]
        
        # --- SMART SYMBOL MATCHING ---
        if 'Symbol' not in df_broker.columns and 'Name' in df_broker.columns:
            df_broker['Symbol'] = df_broker['Name'].astype(str).str.split(' ').str[0].str.upper()
            
            reg_symbols = df_reg['Symbol'].unique() if 'Symbol' in df_reg.columns else []
            for idx, row in df_broker.iterrows():
                b_sym = str(row.get('Symbol', ''))
                if b_sym in reg_symbols: continue
                matches = [r for r in reg_symbols if str(r).startswith(b_sym) or b_sym.startswith(str(r))]
                if matches:
                    df_broker.at[idx, 'Symbol'] = matches[0]
        
        # --- BULLETPROOF MATH CASTING ---
        if 'Qty' in df_broker.columns:
            df_broker['Qty'] = pd.to_numeric(df_broker['Qty'], errors='coerce').fillna(0)
        else: df_broker['Qty'] = 0
            
        if 'Price' in df_broker.columns:
            df_broker['Price'] = pd.to_numeric(df_broker['Price'], errors='coerce').fillna(0)
        else: df_broker['Price'] = 0
        
        if 'Value' in df_broker.columns:
            df_broker['Value'] = pd.to_numeric(df_broker['Value'], errors='coerce').fillna(0)
        else: df_broker['Value'] = df_broker['Qty'] * df_broker['Price']
             
        if 'YieldVal' not in df_broker.columns:
            df_broker['YieldVal'] = df_broker['Value'] * 0.02 

        # --- 🚨 FIX 2: PARSE THE 70 PNG FILE NAMES FOR EXACT RANKS 🚨 ---
        if file_pngs and 'Symbol' in df_broker.columns:
            traded_unique_symbols = df_broker['Symbol'].astype(str).unique()
            
            for image_file in file_pngs:
                filename = image_file.name
                # Parse format: RANK_01_JSWENERGY_MOVE_5.37pct.jpg
                match = re.search(r'RANK_(\d+)_([A-Za-z0-9]+)_', filename, re.IGNORECASE)
                
                sym_str = ""
                rank_num = 0
                
                if match:
                    rank_num = int(match.group(1))
                    sym_str = match.group(2).upper()
                    
                    # Store this symbol in our master list of the 70 PNG universe
                    top_70_png_universe.append(sym_str)
                    
                    # Force the registry to use this exact real rank
                    if 'Symbol' in df_reg.columns:
                        df_reg.loc[df_reg['Symbol'] == sym_str, 'Rank'] = rank_num
                
                # Encode base64 image only if we successfully traded it
                if sym_str and sym_str in traded_unique_symbols:
                    bytes_data = image_file.getvalue()
                    mime_type = "image/jpeg" if filename.lower().endswith(('.jpg', '.jpeg')) else "image/png"
                    b64_str = base64.b64encode(bytes_data).decode()
                    traded_images_b64[sym_str] = f"data:{mime_type};base64,{b64_str}"

        # Clean Strings for JSON safety
        df_reg = df_reg.fillna("").astype(str)
        df_broker = df_broker.fillna("").astype(str)

        reg_data_dict = df_reg.to_dict(orient='records')
        broker_data_dict = df_broker.to_dict(orient='records')
        
        st.sidebar.success(f"✅ Extracted {len(top_70_png_universe)} symbols from PNGs & Processed {len(traded_images_b64)} charts!")
        
    except Exception as e:
        import traceback
        st.sidebar.error(f"Error parsing files: {str(e)}")
        st.sidebar.text(traceback.format_exc())

# 5. Render the Component & Pass Data
quant_ui(
    registry=reg_data_dict, 
    broker=broker_data_dict,
    images=traded_images_b64, 
    png_universe=top_70_png_universe, # Pass the exact 70 PNG symbols to UI
    key="quant_dashboard"
)