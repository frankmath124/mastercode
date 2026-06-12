import streamlit as st
import numpy as np
import copy
import itertools
import pandas as pd  # <-- Add this to fix the "pd is not defined" error
import json
import re
import easyocr
import gc  # <--- Added for explicit garbage collection flushing
import threading # <--- Added to prevent parallel memory spikes
from PIL import Image
from simulator_engine import kingshot_multirally_sim2, TroopSide, load_hero_db
# Establish a global threading lock for the OCR engine
if "ocr_lock" not in st.session_state:
    st.session_state["ocr_lock"] = threading.Lock()

# =========================================================================
# --- OCR BATTLE REPORT SCANNER ENGINE ---
# =========================================================================
@st.cache_resource
def load_ocr_reader():
    """Initializes the EasyOCR reader once and caches it in memory."""
    return easyocr.Reader(['en'], gpu=False)

def scan_battle_report_side_by_side(image_file):
    """Parses a side-by-side battle report using Y-coordinate row grouping and a thread lock."""
    reader = load_ocr_reader()
    
    # Acquire the lock. If another user is scanning, this thread waits nicely in line
    with st.session_state["ocr_lock"]:
        image = Image.open(image_file)
        image_np = np.array(image)
        midpoint = image_np.shape[1] / 2
        
        # Detail=1 gives coordinates so we can map rows precisely
        results = reader.readtext(image_np, detail=1) 
        
        blocks = []
        for bbox, text, prob in results:
            y_center = (bbox[0][1] + bbox[2][1]) / 2
            x_center = (bbox[0][0] + bbox[1][0]) / 2
            blocks.append({'text': text.lower().strip(), 'x': x_center, 'y': y_center})
            
        # Sort all text blocks top-to-bottom
        blocks.sort(key=lambda b: b['y'])
        
        # Group text blocks into horizontal rows
        rows = []
        current_row = []
        last_y = -100
        for b in blocks:
            if abs(b['y'] - last_y) > 20 and current_row:
                rows.append(current_row)
                current_row = []
            current_row.append(b)
            last_y = b['y']
        if current_row: rows.append(current_row)
            
        left_stats, right_stats = {}, {}
        
        # Map for keyword hunting
        labels_map = {
            'ia': ['infantry', 'attack'], 'id': ['infantry', 'defense'], 'il': ['infantry', 'lethality'], 'ih': ['infantry', 'health'],
            'ca': ['cavalry', 'attack'],  'cd': ['cavalry', 'defense'],  'cl': ['cavalry', 'lethality'],  'ch': ['cavalry', 'health'],
            'aa': ['archer', 'attack'],   'ad': ['archer', 'defense'],   'al': ['archer', 'lethality'],   'ah': ['archer', 'health']
        }
        
        # Scan row by row
        for row in rows:
            row_text = " ".join([b['text'] for b in row])
            matched_key = None
            
            # Check if the row contains a stat label
            for key, keywords in labels_map.items():
                if all(kw in row_text for kw in keywords):
                    matched_key = key
                    break
                    
            if matched_key:
                # Look at all text blocks inside this row
                for b in row:
                    # Extract clean numbers (ignoring +, %, and commas)
                    num_match = re.search(r'(\d+[\d\.]*)', b['text'].replace(',', ''))
                    if num_match:
                        try:
                            val = float(num_match.group(1))
                            # Assign to Left or Right based on physical screen location
                            if b['x'] < midpoint - 20: 
                                left_stats[matched_key] = val
                            elif b['x'] > midpoint + 20: 
                                right_stats[matched_key] = val
                        except: pass
        
        # Explicit Memory Cleanup right before releasing lock
        del image
        del image_np
        gc.collect() # Force free the RAM back to the host system
                        
    return left_stats, right_stats

# =========================================================================
# --- JSON FILE MANAGER ENGINE ---
# =========================================================================
# =========================================================================
# --- JSON FILE MANAGER ENGINE ---
# =========================================================================
def export_army_to_json(prefix, is_wave=False, wave_idx=0):
    """Packages a specific army slot into a standardized JSON string."""
    suffix = f"_{wave_idx}" if is_wave else ""
    mid = "w" if is_wave else "g"
    stat_mid = "" if is_wave else "g"

    preset = {
        'tier': st.session_state.get(f"{prefix}_{mid}tier{suffix}", 10),
        'tg': st.session_state.get(f"{prefix}_{mid}tg{suffix}", 5),
        'style': st.session_state.get(f"{prefix}_{mid}style{suffix}", "Raw Counts"),
        'inf': st.session_state.get(f"{prefix}_{mid}inf{suffix}", 600000),
        'cav': st.session_state.get(f"{prefix}_{mid}cav{suffix}", 200000),
        'arc': st.session_state.get(f"{prefix}_{mid}arc{suffix}", 200000),
        'cap': st.session_state.get(f"{prefix}_{mid}cap{suffix}", 1000000),
        'l1': st.session_state.get(f"{prefix}_{mid}l1{suffix}", "None"),
        'w1': st.session_state.get(f"{prefix}_{mid}w1{suffix}", 10),
        'l2': st.session_state.get(f"{prefix}_{mid}l2{suffix}", "None"),
        'w2': st.session_state.get(f"{prefix}_{mid}w2{suffix}", 10),
        'l3': st.session_state.get(f"{prefix}_{mid}l3{suffix}", "None"),
        'w3': st.session_state.get(f"{prefix}_{mid}w3{suffix}", 10),
        's1': st.session_state.get(f"{prefix}_{mid}s1{suffix}", "None"),
        's2': st.session_state.get(f"{prefix}_{mid}s2{suffix}", "None"),
        's3': st.session_state.get(f"{prefix}_{mid}s3{suffix}", "None"),
        's4': st.session_state.get(f"{prefix}_{mid}s4{suffix}", "None")
    }

    # Extract all 12 stat nodes
    for s in ["ia", "id", "il", "ih", "ca", "cd", "cl", "ch", "aa", "ad", "al", "ah"]:
        preset[s] = st.session_state.get(f"{prefix}_{stat_mid}{s}{suffix}", 1000.0)

    return json.dumps(preset, indent=4)

def import_army_from_json(json_str, target_prefix, is_wave=False, wave_idx=0):
    """Maps a standardized JSON string perfectly into the requested UI slot."""
    try:
        preset = json.loads(json_str)
        suffix = f"_{wave_idx}" if is_wave else ""
        mid = "w" if is_wave else "g"
        stat_mid = "" if is_wave else "g"

        keys_map = {
            'tier': f"{target_prefix}_{mid}tier{suffix}", 'tg': f"{target_prefix}_{mid}tg{suffix}",
            'style': f"{target_prefix}_{mid}style{suffix}", 'inf': f"{target_prefix}_{mid}inf{suffix}",
            'cav': f"{target_prefix}_{mid}cav{suffix}", 'arc': f"{target_prefix}_{mid}arc{suffix}",
            'cap': f"{target_prefix}_{mid}cap{suffix}", 'l1': f"{target_prefix}_{mid}l1{suffix}",
            'w1': f"{target_prefix}_{mid}w1{suffix}", 'l2': f"{target_prefix}_{mid}l2{suffix}",
            'w2': f"{target_prefix}_{mid}w2{suffix}", 'l3': f"{target_prefix}_{mid}l3{suffix}",
            'w3': f"{target_prefix}_{mid}w3{suffix}", 's1': f"{target_prefix}_{mid}s1{suffix}",
            's2': f"{target_prefix}_{mid}s2{suffix}", 's3': f"{target_prefix}_{mid}s3{suffix}",
            's4': f"{target_prefix}_{mid}s4{suffix}"
        }
        for s in ["ia", "id", "il", "ih", "ca", "cd", "cl", "ch", "aa", "ad", "al", "ah"]:
            keys_map[s] = f"{target_prefix}_{stat_mid}{s}{suffix}"

        for generic_key, val in preset.items():
            if generic_key in keys_map:
                st.session_state[keys_map[generic_key]] = val
        return True
    except Exception as e:
        return False

# =========================================================================
# --- UNIVERSAL CLIPBOARD SYNC ENGINE ---
# =========================================================================
SYNC_KEYS = [
    'waves_cnt', 'gtier', 'gtg', 'g_style', 'gi', 'gc', 'ga', 'gtot', 'g_ratio_editor',
    'gl1', 'gw1', 'gl2', 'gw2', 'gl3', 'gw3', 'gs1', 'gs2', 'gs3', 'gs4',
    'gia', 'gid', 'gil', 'gih', 'gca', 'gcd', 'gcl', 'gch', 'gaa', 'gad', 'gal', 'gah'
]
for i in range(5):
    SYNC_KEYS.extend([
        f'wtier_{i}', f'wtg_{i}', f'wstyle_{i}', f'winf_{i}', f'wcav_{i}', f'warc_{i}', f'wcap_{i}', f'w_ratio_editor_{i}',
        f'wl1_{i}', f'ww1_{i}', f'wl2_{i}', f'ww2_{i}', f'wl3_{i}', f'ww3_{i}', f'ws1_{i}', f'ws2_{i}', f'ws3_{i}', f'ws4_{i}',
        f'ia_{i}', f'id_{i}', f'il_{i}', f'ih_{i}', f'ca_{i}', f'cd_{i}', f'cl_{i}', f'ch_{i}', f'aa_{i}', f'ad_{i}', f'al_{i}', f'ah_{i}'
    ])

def copy_to_clipboard(prefix):
    if "clipboard" not in st.session_state:
        st.session_state["clipboard"] = {}
    for k in SYNC_KEYS:
        full_key = f"{prefix}_{k}"
        if full_key in st.session_state:
            st.session_state["clipboard"][k] = st.session_state[full_key]

def paste_from_clipboard(prefix):
    if "clipboard" in st.session_state and st.session_state["clipboard"]:
        for k, v in st.session_state["clipboard"].items():
            st.session_state[f"{prefix}_{k}"] = v
    else:
        st.warning("Clipboard is empty! Copy a profile first.")

# =========================================================================
# --- SECURITY GATEWAY ---
# =========================================================================
SECRET_PASSCODE = "Frank_BattleSimulator"

st.set_page_config(page_title="FRANK-Optimizer Master Suite", layout="wide")

st.title("FRANK-Optimizer: Kingshot Battle Simulator and Optimizer")
st.caption("Centralised Combat Logistics & Battle Math Matrix.")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔒 Security Access Required")
    user_input = st.text_input("Enter Alliance Passcode:", type="password")
    
    if st.button("Unlock Command Suite"):
        if user_input == SECRET_PASSCODE:
            st.session_state["authenticated"] = True
            st.session_state["joiner_filter_enabled"] = True 
            st.rerun()
        else:
            st.error("Invalid passcode. Access denied.")
else:
    # =========================================================================
    # --- MASTER MODULE CORE CONFIGURATIONS ---
    # =========================================================================
    hero_db = load_hero_db()
    hero_list = ["None"] + sorted(list(hero_db.keys()))
    
    infantry_heroes = ["None"] + sorted(["Eric", "Zoe", "Amadeus", "Helga", "Howard", "Alcar"])
    cavalry_heroes = ["None"] + sorted(["Gordon", "Fahd", "Chenko", "Petra", "Hilde", "Jabel", "Margot"])
    archer_heroes = ["None"] + sorted(["Jaegar", "Marlin", "Saul", "Yaenwoo", "Amane", "Quinn", "Rosa"])
    
    # --- SYSTEM PERFORMANCE OPTIMIZATION SIDEBAR ---
    st.sidebar.markdown("## ⚙️ Calculation Engine Controls")
    filter_duplicates = st.sidebar.toggle(
        "Condense Support Permanent Pools", 
        value=True, 
        help="Filters redundant support variants (e.g. keeping only Howard to represent identical Fahd/Quinn math loops). Massive grid search execution speed gains."
    )
    
    if filter_duplicates:
        joiner_pool_defaults = ["Howard", "Chenko", "Gordon", "Amane"]
    else:
        joiner_pool_defaults = [h for h in hero_list if h != "None" and not hero_db[h].get('widget', {}).get('has_widget', True)]
        if not joiner_pool_defaults:
            joiner_pool_defaults = ["Gordon", "Fahd", "Chenko", "Yaenwoo", "Howard", "Quinn", "Amane"]

    # --- ADDED: JSON LOGIC AND OCR CONTROLS TO SIDEBAR ---
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 💾 Local File Manager")
    
    io_tab = st.sidebar.selectbox("Target UI Tab", ["Simulator", "Optimizer", "Stat Engine"])
    io_tab_prefix_map = {"Simulator": "s", "Optimizer": "o", "Stat Engine": "r"}
    io_prefix = io_tab_prefix_map[io_tab]

    io_target = st.sidebar.selectbox("Target Slot", ["Garrison", "Wave 1", "Wave 2", "Wave 3", "Wave 4", "Wave 5"])
    is_w = io_target != "Garrison"
    w_idx = int(io_target.split(" ")[1]) - 1 if is_w else 0

    st.sidebar.caption(f"Export data currently in `{io_tab}` -> `{io_target}`")
    json_data = export_army_to_json(io_prefix, is_w, w_idx)
    st.sidebar.download_button(
        label="Download Active Profile (.json)",
        data=json_data,
        file_name=f"{io_target.replace(' ', '_').lower()}_profile.json",
        mime="application/json",
        use_container_width=True
    )

    st.sidebar.markdown("---")
    uploaded_file = st.sidebar.file_uploader("Upload Saved Profile", type="json")
    if uploaded_file is not None:
        if st.sidebar.button(f"Inject Upload into {io_target}", type="primary", use_container_width=True):
            file_content = uploaded_file.read().decode("utf-8")
            success = import_army_from_json(file_content, io_prefix, is_w, w_idx)
            if success:
                st.sidebar.success(f"Profile loaded into {io_target}!")
                st.rerun()
            else:
                st.sidebar.error("Failed to parse the uploaded file.")
                
# --- AUTO-SCAN BATTLE REPORT ---
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📸 Dual-Column Battle Scanner")
    
    # Added "None" option to ignore sides
    slot_options = ["None", "Garrison", "Wave 1", "Wave 2", "Wave 3", "Wave 4", "Wave 5"]
    
    left_mapping = st.sidebar.selectbox("Assign LEFT Side To:", slot_options, index=2) # Default Wave 1
    right_mapping = st.sidebar.selectbox("Assign RIGHT Side To:", slot_options, index=1) # Default Garrison
    
    ocr_upload = st.sidebar.file_uploader("Upload Screenshot", type=["png", "jpg", "jpeg"], key="dual_ocr_uploader")
    
    if ocr_upload is not None:
        if st.sidebar.button("Extract Data Columns", use_container_width=True, type="primary"):
            with st.spinner("Neural Engine mapping image rows..."):
                left_stats_found, right_stats_found = scan_battle_report_side_by_side(ocr_upload)
                
                def inject_side_data(scanned_pool, assignment_label):
                    if assignment_label == "None" or not scanned_pool: return 0
                    
                    is_wave = assignment_label.startswith("Wave")
                    # Force integer indexing to match your memory keys exactly
                    wave_idx = int(assignment_label.split(" ")[1]) - 1 if is_wave else 0
                    stat_mid = "" if is_wave else "g"
                    suffix = f"_{wave_idx}" if is_wave else ""
                    
                    # UNIVERSAL SYNC: Apply the scan to all 3 tabs at the exact same time
                    prefixes = ['s', 'o', 'r'] 
                    
                    count = 0
                    for k, v in scanned_pool.items():
                        for pref in prefixes:
                            target_key = f"{pref}_{stat_mid}{k}{suffix}"
                            st.session_state[target_key] = v
                        count += 1
                    return count

                # Process injections
                l_count = inject_side_data(left_stats_found, left_mapping)
                r_count = inject_side_data(right_stats_found, right_mapping)
                
                if l_count > 0 or r_count > 0:
                    st.sidebar.success(f"Mapped: {left_mapping} -> {l_count} stats | {right_mapping} -> {r_count} stats")
                    st.rerun()
                else:
                    st.sidebar.error("OCR ran, but failed to separate text nodes cleanly. Ensure you uploaded a stats page.")
    if st.sidebar.button("Lock Command Suite"):
        st.session_state["authenticated"] = False
        st.rerun()

    # =========================================================================
    # --- MASTER HEADERS & SYSTEM DESCRIPTIONS ---
    # =========================================================================
    with st.expander(" Module Descriptions", expanded=False):
        col_desc1, col_desc2, col_desc3 = st.columns(3)
        with col_desc1:
            st.markdown("### Multi-Rally Simulator")
            st.write("Simulate consecutive rally waves hitting a fixed structure. Evaluates sequential attrition, troop depletion curves, and step-by-step win conditions.")
        with col_desc2:
            st.markdown("### Tactical Optimizer")
            st.write("Run brute-force grid searches across continuous loops to calculate best performance for troop compositions or optimal joiner heroes.")
        with col_desc3:
            st.markdown("### Stat Optimizer Engine")
            st.write("Isolate variables by injecting small stat changes. Calculates exactly how many fewer troop deaths an upgrade prevents to provide upgrade guidance.")

# Replace your old tab layout row with this four-tab tuple:
tab_sim, tab_opt, tab_roi, tab_gear = st.tabs([
    "Multi-Rally Simulator", 
    "Battle Optimizer", 
    "Stat Improvement Optimizer", 
    "Gear & Charm Optimizer"
])

# =========================================================================
# GLOBAL GEAR OPTIMIZER DATABASE UTILITIES
# =========================================================================
def load_stat_atlases():
    """Compiles progression data arrays parsed from gear.xlsx and image formulas."""
    charm_costs_guides = [0, 5, 40, 60, 80, 100, 120, 140, 200, 300, 420]
    charm_costs_designs = [0, 5, 15, 40, 100, 200, 300, 400, 400, 400, 420]
    charm_stat_deltas = [0, 0.09, 0.03, 0.04, 0.03, 0.06, 0.05, 0.05, 0.05, 0.05, 0.05]

    gov_tier_names = ["None", "Green L1", "Green L2", "Blue L1", "Blue L2", "Blue L3", "Blue L4", "Purple L1", "Purple L2"]
    gov_costs_satin = [0, 1500, 3800, 7000, 9700, 1000, 1000, 1500, 1500]
    gov_costs_threads = [0, 15, 40, 70, 95, 10, 10, 15, 15]
    gov_costs_artisans = [0, 0, 0, 0, 0, 45, 50, 60, 70]
    gov_stat_deltas = [0, 0.0935, 0.0340, 0.0425, 0.0425, 0.0425, 0.0425, 0.0425, 0.0289]
    
    return {
        "charms": {"guides": charm_costs_guides, "designs": charm_costs_designs, "deltas": charm_stat_deltas},
        "gov": {"names": gov_tier_names, "satin": gov_costs_satin, "threads": gov_costs_threads, "artisans": gov_costs_artisans, "deltas": gov_stat_deltas}
    }

def get_hero_gear_stat(tier, level):
    """Applies formulas extracted directly from image_d96da4.png to calculate fluid stat steps."""
    if tier == "Epic":
        return 0.09 + (min(level, 80) * 0.0021)
    elif tier == "Mythic":
        return 0.15 + (min(level, 100) * 0.0035)
    elif tier == "Red":
        if level <= 100: return 0.50
        return 0.50 + (min(level, 200) - 100) * 0.005
    return 0.0

def calculate_hero_gear_xp_cost(current_level):
    """Simulates XP progression curve derived from gear.xlsx metadata."""
    if current_level >= 200: return 9999999
    return int(10 + (current_level * 5) + ((current_level ** 1.5) * 0.25))

    # =========================================================================
    # --- TAB 1: MULTI-RALLY SIMULATOR ---
    # =========================================================================
    with tab_sim:
        st.header("Sequential Multi-Rally Wave Simulation")
        
        c1, c2, _ = st.columns([1, 1, 2])
        if c1.button("📋 Copy Profile to Clipboard", key="s_copy"):
            copy_to_clipboard('s')
            st.success("Profile saved to clipboard!")
        if c2.button("📥 Paste Profile from Clipboard", key="s_paste"):
            paste_from_clipboard('s')
            st.rerun()
        st.markdown("---")
        
        sim_main, sim_side = st.columns([2, 1])
        
        with sim_side:
            st.subheader("Garrison Target Defenses")
            s_gc1, s_gc2 = st.columns(2)
            s_g_tier = s_gc1.selectbox("Garrison Troop Tier", range(1, 12), index=10, key="s_gtier") 
            s_g_tg = s_gc2.selectbox("Garrison Troop TG Level", range(0, 6), index=5, key="s_gtg")       
            
            s_g_input_style = st.radio("Garrison Troop Input Style", ("Raw Counts", "Capacity + Ratios"), key="s_g_style")
            if s_g_input_style == "Raw Counts":
                s_g_inf = st.number_input("Garrison Infantry Count", value=1500000, key="s_gi")
                s_g_cav = st.number_input("Garrison Cavalry Count", value=500000, key="s_gc")
                s_g_arc = st.number_input("Garrison Archer Count", value=800000, key=f"s_ga")
                s_g_valid = True
            else:
                s_g_total_troops = st.number_input("Total Garrison Capacity Target", value=2800000, step=100000, key="s_gtot")
                s_g_df = [{"Class": "Infantry", "Ratio %": 50}, {"Class": "Cavalry", "Ratio %": 20}, {"Class": "Archer", "Ratio %": 30}]
                s_edited_g_df = st.data_editor(s_g_df, column_config={"Class": st.column_config.TextColumn("Class", disabled=True), "Ratio %": st.column_config.NumberColumn("Ratio %", min_value=0, max_value=100, step=1, format="%d%%")}, disabled=["Class"], hide_index=True, key="s_g_ratio_editor")
                s_g_total_pct = sum(row["Ratio %"] for row in s_edited_g_df)
                s_g_valid = s_g_total_pct == 100
                if not s_g_valid: st.error(f"❌ Garrison ratios must sum to 100% (Current: {s_g_total_pct}%).")
                s_g_inf = int(s_g_total_troops * (s_edited_g_df[0]["Ratio %"] / 100.0))
                s_g_cav = int(s_g_total_troops * (s_edited_g_df[1]["Ratio %"] / 100.0))
                s_g_arc = int(s_g_total_troops * (s_edited_g_df[2]["Ratio %"] / 100.0))
                
            with st.expander("Garrison Command Heroes"):
                s_hc1, s_wc1 = st.columns([3, 1])
                s_g_lead1 = s_hc1.selectbox("Infantry Hero", infantry_heroes, index=infantry_heroes.index("Amadeus") if "Amadeus" in infantry_heroes else 0, key="s_gl1")
                s_g_wid1 = s_wc1.number_input("W1", 0, 10, 10, key="s_gw1")
                s_hc2, s_wc2 = st.columns([3, 1])
                s_g_lead2 = s_hc2.selectbox("Cavalry Hero", cavalry_heroes, index=cavalry_heroes.index("Hilde") if "Hilde" in cavalry_heroes else 0, key="s_gl2")
                s_g_wid2 = s_wc2.number_input("W2", 0, 10, 10, key="s_gw2")
                s_hc3, s_wc3 = st.columns([3, 1])
                s_g_lead3 = s_hc3.selectbox("Archer Hero", archer_heroes, index=archer_heroes.index("Marlin") if "Marlin" in archer_heroes else 0, key="s_gl3")
                s_g_wid3 = s_wc3.number_input("W3", 0, 10, 10, key="s_gw3")
                st.markdown("---")
                s_g_sup1 = st.selectbox("Supporter 1", hero_list, index=0, key="s_gs1")
                s_g_sup2 = st.selectbox("Supporter 2", hero_list, index=0, key="s_gs2")
                s_g_sup3 = st.selectbox("Supporter 3", hero_list, index=0, key="s_gs3")
                s_g_sup4 = st.selectbox("Supporter 4", hero_list, index=0, key="s_gs4")
                
            with st.expander("Garrison Combat Stats Baseline"):
                s_gia = st.number_input("Inf Atk %", value=850.0, key="s_gia")
                s_gid = st.number_input("Inf Def %", value=900.0, key="s_gid")
                s_gil = st.number_input("Inf Let %", value=1100.0, key="s_gil")
                s_gih = st.number_input("Inf HP %", value=1100.0, key="s_gih")
                st.markdown("---")
                s_gca = st.number_input("Cav Atk %", value=800.0, key="s_gca")
                s_gcd = st.number_input("Cav Def %", value=800.0, key="s_gcd")
                s_gcl = st.number_input("Cav Let %", value=1000.0, key="s_gcl")
                s_gch = st.number_input("Cav HP %", value=1000.0, key="s_gch")
                st.markdown("---")
                s_gaa = st.number_input("Arc Atk %", value=850.0, key="s_gaa")
                s_gad = st.number_input("Arc Def %", value=800.0, key="s_gad")
                s_gal = st.number_input("Arc Let %", value=1100.0, key="s_gal")
                s_gah = st.number_input("Arc HP %", value=1000.0, key="s_gah")

        with sim_main:
            s_num_waves = st.number_input("Number of Attacking Waves", min_value=1, max_value=5, value=2, step=1, key="s_waves_cnt")
            s_wave_tabs = st.tabs([f"🌊 Wave {i+1}" for i in range(s_num_waves)])
            s_wave_configs = {}
            
            for i, tab in enumerate(s_wave_tabs):
                with tab:
                    sw_col1, sw_col2 = st.columns(2)
                    with sw_col1:
                        st.markdown("**Wave Base Metrics**")
                        swc1, swc2 = st.columns(2)
                        sw_tier = swc1.selectbox("Troop Tier", range(1, 12), index=9, key=f"s_wtier_{i}") 
                        sw_tg = swc2.selectbox("Troop TG Level", range(0, 6), index=5, key=f"s_wtg_{i}")       
                        
                        sw_input_style = st.radio("Troop Input Type", ("Raw Counts", "Rally Size + Ratios"), key=f"s_wstyle_{i}")
                        if sw_input_style == "Raw Counts":
                            sa_inf = st.number_input("Infantry Count", value=600000, key=f"s_winf_{i}")
                            sa_cav = st.number_input("Cavalry Count", value=200000, key=f"s_wcav_{i}")
                            sa_arc = st.number_input("Archer Count", value=200000, key=f"s_warc_{i}")
                            st.session_state[f"s_wvalid_{i}"] = True
                        else:
                            sa_total_capacity = st.number_input("Rally Size Capacity Limit", value=1000000, step=50000, key=f"s_wcap_{i}")
                            sw_df = [{"Class": "Infantry", "Ratio %": 60}, {"Class": "Cavalry", "Ratio %": 20}, {"Class": "Archer", "Ratio %": 20}]
                            s_edited_w_df = st.data_editor(sw_df, column_config={"Class": st.column_config.TextColumn("Class", disabled=True), "Ratio %": st.column_config.NumberColumn("Ratio %", min_value=0, max_value=100, step=1, format="%d%%")}, disabled=["Class"], hide_index=True, key=f"s_w_ratio_editor_{i}")
                            sw_total_pct = sum(row["Ratio %"] for row in s_edited_w_df)
                            st.session_state[f"s_wvalid_{i}"] = sw_total_pct == 100
                            if sw_total_pct != 100: st.error(f"❌ Wave {i+1} ratios must equal 100%.")
                            sa_inf = int(sa_total_capacity * (s_edited_w_df[0]["Ratio %"] / 100.0))
                            sa_cav = int(sa_total_capacity * (s_edited_w_df[1]["Ratio %"] / 100.0))
                            sa_arc = int(sa_total_capacity * (s_edited_w_df[2]["Ratio %"] / 100.0))
                            
                    with sw_col2:
                        st.markdown("**Main Heroes**")
                        sahc1, sawc1 = st.columns([3, 1])
                        sa_l1 = sahc1.selectbox("Infantry Hero", infantry_heroes, index=0, key=f"s_wl1_{i}")
                        sa_w1 = sawc1.number_input("Widget 1", 0, 10, 10, key=f"s_ww1_{i}")
                        sahc2, sawc2 = st.columns([3, 1])
                        sa_l2 = sahc2.selectbox("Cavalry Hero", cavalry_heroes, index=0, key=f"s_wl2_{i}")
                        sa_w2 = sawc2.number_input("Widget 2", 0, 10, 10, key=f"s_ww2_{i}")
                        sahc3, sawc3 = st.columns([3, 1])
                        sa_l3 = sahc3.selectbox("Archer Hero", archer_heroes, index=0, key=f"s_wl3_{i}")
                        sa_w3 = sawc3.number_input("Widget 3", 0, 10, 10, key=f"s_ww3_{i}")
                        st.markdown("---")
                        sa_s1 = st.selectbox("Supporter 1", hero_list, index=0, key=f"s_ws1_{i}")
                        sa_s2 = st.selectbox("Supporter 2", hero_list, index=0, key=f"s_ws2_{i}")
                        sa_s3 = st.selectbox("Supporter 3", hero_list, index=0, key=f"s_ws3_{i}")
                        sa_s4 = st.selectbox("Supporter 4", hero_list, index=0, key=f"s_ws4_{i}")
                        
                    with st.expander(f"Wave {i+1} Core Combat Stats Override"):
                        ssc1, ssc2, ssc3 = st.columns(3)
                        with ssc1:
                            sa_inf_atk = st.number_input("Inf Atk %", value=1000.0, key=f"s_ia_{i}")
                            sa_inf_def = st.number_input("Inf Def %", value=800.0, key=f"s_id_{i}")
                            sa_inf_let = st.number_input("Inf Let %", value=1100.0, key=f"s_il_{i}")
                            sa_inf_hp  = st.number_input("Inf HP %", value=900.0, key=f"s_ih_{i}")
                        with ssc2:
                            sa_cav_atk = st.number_input("Cav Atk %", value=900.0, key=f"s_ca_{i}")
                            sa_cav_def = st.number_input("Cav Def %", value=750.0, key=f"s_cd_{i}")
                            sa_cav_let = st.number_input("Cav Let %", value=850.0, key=f"s_cl_{i}")
                            sa_cav_hp  = st.number_input("Cav HP %", value=700.0, key=f"s_ch_{i}")
                        with ssc3:
                            sa_arc_atk = st.number_input("Arc Atk %", value=900.0, key=f"s_aa_{i}")
                            sa_arc_def = st.number_input("Arc Def %", value=700.0, key=f"s_ad_{i}")
                            sa_arc_let = st.number_input("Arc Let %", value=1050.0, key=f"s_al_{i}")
                            sa_arc_hp  = st.number_input("Arc HP %", value=800.0, key=f"s_ah_{i}")
                            
                        s_wave_configs[i] = {
                            "troops": [sa_inf, sa_cav, sa_arc], "tier": sw_tier, "tg": sw_tg,
                            "leaders": [sa_l1, sa_l2, sa_l3], "supporters": [sa_s1, sa_s2, sa_s3, sa_s4],
                            "widgets": [sa_w1, sa_w2, sa_w3, 0, 0, 0, 0],
                            "stats": [[sa_inf_atk, sa_inf_def, sa_inf_let, sa_inf_hp], [sa_cav_atk, sa_cav_def, sa_cav_let, sa_cav_hp], [sa_arc_atk, sa_arc_def, sa_arc_let, sa_arc_hp]]
                        }
            
            st.markdown("---")
            s_runs = st.number_input("Monte Carlo Matrix Iterations", min_value=10, max_value=1000, value=200, step=50, key="s_runs_cnt")
            s_all_waves_valid = all(st.session_state.get(f"s_wvalid_{w_idx}", True) for w_idx in range(s_num_waves))
            
            if s_all_waves_valid and s_g_valid:
                if st.button("Run Multi-Rally Simulation Sequence", key="s_run_btn"):
                    with st.spinner("Processing continuous battlefield math blocks..."):
                        s_g_combat_stats = [[s_gia, s_gid, s_gil, s_gih], [s_gca, s_gcd, s_gcl, s_gch], [s_gaa, s_gad, s_gal, s_gah]]
                        s_g_widgets = [s_g_wid1, s_g_wid2, s_g_wid3, 0, 0, 0, 0]
                        
                        garrison_setup = TroopSide([s_g_inf, s_g_cav, s_g_arc], np.array(s_g_combat_stats), [s_g_lead1, s_g_lead2, s_g_lead3], [s_g_sup1, s_g_sup2, s_g_sup3, s_g_sup4], s_g_tier, s_g_tg, s_g_widgets)
                        
                        rally_waves_input = []
                        for wave_idx in range(s_num_waves):
                            sw_data = s_wave_configs[wave_idx]
                            rally_waves_input.append(TroopSide(sw_data["troops"], np.array(sw_data["stats"]), sw_data["leaders"], sw_data["supporters"], sw_data["tier"], sw_data["tg"], sw_data["widgets"]))
                            
                        g_surv_total = 0
                        g_breakdown_avg = np.zeros(3)
                        w_surv_tracking = {w: 0 for w in range(s_num_waves)}
                        w_win_counts = {w: 0 for w in range(s_num_waves)}
                        
                        for _ in range(int(s_runs)):
                            t_garrison = copy.deepcopy(garrison_setup)
                            t_waves = copy.deepcopy(rally_waves_input)
                            final_g, logs = kingshot_multirally_sim2(t_waves, t_garrison)
                            
                            g_surv_total += np.sum(final_g.troops)
                            g_breakdown_avg += final_g.troops
                            for step_idx, log in enumerate(logs):
                                att_surv = np.sum(log['attacker_surviving'])
                                w_surv_tracking[step_idx] += att_surv
                                if att_surv > 0: w_win_counts[step_idx] += 1
                                
                        avg_g_surv = g_surv_total / s_runs
                        avg_g_breakdown = g_breakdown_avg / s_runs
                        
                        st.success("Simulation Sequence Complete!")
                        if avg_g_surv <= 0: st.markdown("### STATUS: <span style='color:red'>GARRISON COMPLETELY BROKEN</span>", unsafe_allow_html=True)
                        else: st.markdown(f"### STATUS: <span style='color:green'>GARRISON HELD (Avg. {avg_g_surv:,.0f} Total Troops Left)</span>", unsafe_allow_html=True)
                        
                        out_col1, out_col2 = st.columns(2)
                        with out_col1:
                            st.markdown("#### Final Defense Status")
                            st.table({"Troop Class": ["Infantry", "Cavalry", "Archers", "Total Remaining"], "Remaining (Avg)": [f"{avg_g_breakdown[0]:,.0f}", f"{avg_g_breakdown[1]:,.0f}", f"{avg_g_breakdown[2]:,.0f}", f"{avg_g_surv:,.0f}"]})
                        with out_col2:
                            st.markdown("#### Attacker Wave Performance")
                            w_perf_display = []
                            for w_idx in range(s_num_waves):
                                avg_w_surv = w_surv_tracking[w_idx] / s_runs
                                win_pct = (w_win_counts[w_idx] / s_runs) * 100
                                w_perf_display.append({"Rally Wave": f"Wave #{w_idx + 1}", "T-Level": f"T{s_wave_configs[w_idx]['tier']} TG{s_wave_configs[w_idx]['tg']}", "Win Rate %": f"{win_pct:.1f}%", "Avg Retained Troops": f"{avg_w_surv:,.0f}"})
                            st.table(w_perf_display)
            else:
                st.button("Run Multi-Rally Simulation Sequence", disabled=True, key="s_run_disabled", help="Resolve validation errors to run.")

    # =========================================================================
    # --- TAB 2: TACTICAL OPTIMIZER ---
    # =========================================================================
    with tab_opt:
        st.header("Multi-Rally Optimization Engine")
        
        c1, c2, _ = st.columns([1, 1, 2])
        if c1.button("📋 Copy Profile to Clipboard", key="o_copy"):
            copy_to_clipboard('o')
            st.success("Profile saved to clipboard!")
        if c2.button("📥 Paste Profile from Clipboard", key="o_paste"):
            paste_from_clipboard('o')
            st.rerun()
        st.markdown("---")
        
        opt_main, opt_side_col = st.columns([2, 1])
        
        with opt_side_col:
            st.header("Garrison Setup")
            st.markdown("**Garrison Base Troop Level**")
            o_gc1, o_gc2 = st.columns(2)
            o_g_tier = o_gc1.selectbox("Garrison Troop Tier", range(1, 12), index=10, key="o_gtier") 
            o_g_tg = o_gc2.selectbox("Garrison Troop TG Level", range(0, 6), index=5, key="o_gtg")       
            st.markdown("---")
            
            st.markdown("### Select Optimization Options")
            opt_side = st.radio("Step 1: Choose strategy track:", ("Garrison (Defenders)", "Attacker Waves (Rallies)"), key="opt_side_sel")
            if opt_side == "Garrison (Defenders)":
                opt_mode = st.selectbox("Step 2: Choose target variable:", ["Troop Ratios (Fixed Total Count)", "Supporter Heroes (Fixed Troop Count)"], key="opt_mode_g")
            else:
                opt_mode = st.selectbox("Step 2: Choose target variable:", ["Attacker Wave #1 Troop Ratios", "Attacker Wave #1 Supporter Heroes"], key="opt_mode_a")
            st.markdown("---")
            
            if opt_side == "Garrison (Defenders)" and "Troop Ratios" in opt_mode:
                o_g_total_troops = st.number_input("Total Garrison Capacity", value=2800000, step=100000, key="o_gtot")
                o_g_inf, o_g_cav, o_g_arc = 0, 0, 0
                o_g_valid = True
            else:
                o_g_input_style = st.radio("Garrison Troop Input Type", ("Raw Counts", "Capacity + Ratios"), key="o_g_style")
                if o_g_input_style == "Raw Counts":
                    o_g_inf = st.number_input("Garrison Infantry Count", value=1500000, key="o_gi")
                    o_g_cav = st.number_input("Garrison Cavalry Count", value=500000, key="o_gc")
                    o_g_arc = st.number_input("Garrison Archer Count", value=800000, key="o_ga")
                    o_g_total_troops = o_g_inf + o_g_cav + o_g_arc
                    o_g_valid = True
                else:
                    o_g_total_troops = st.number_input("Total Garrison Capacity Target", value=2800000, step=100000, key="o_gtot")
                    o_g_df = [{"Class": "Infantry", "Ratio %": 50}, {"Class": "Cavalry", "Ratio %": 20}, {"Class": "Archer", "Ratio %": 30}]
                    o_edited_g_df = st.data_editor(o_g_df, column_config={"Class": st.column_config.TextColumn("Class", disabled=True), "Ratio %": st.column_config.NumberColumn("Ratio %", min_value=0, max_value=100, step=1, format="%d%%")}, disabled=["Class"], hide_index=True, key="o_g_ratio_editor")
                    o_g_total_pct = sum(row["Ratio %"] for row in o_edited_g_df)
                    o_g_valid = o_g_total_pct == 100
                    if not o_g_valid: st.error(f"❌ Garrison ratios must sum to 100%.")
                    o_g_inf = int(o_g_total_troops * (o_edited_g_df[0]["Ratio %"] / 100.0))
                    o_g_cav = int(o_g_total_troops * (o_edited_g_df[1]["Ratio %"] / 100.0))
                    o_g_arc = int(o_g_total_troops * (o_edited_g_df[2]["Ratio %"] / 100.0))

            with st.expander("Garrison Heroes and Joiners"):
                o_hc1, o_wc1 = st.columns([3, 1])
                o_g_lead1 = o_hc1.selectbox("Infantry Hero", infantry_heroes, index=infantry_heroes.index("Amadeus") if "Amadeus" in infantry_heroes else 0, key="o_gl1")
                o_g_wid1 = o_wc1.number_input("W1", 0, 10, 10, key="o_gw1")
                o_hc2, o_wc2 = st.columns([3, 1])
                o_g_lead2 = o_hc2.selectbox("Cavalry Hero", cavalry_heroes, index=cavalry_heroes.index("Hilde") if "Hilde" in cavalry_heroes else 0, key="o_gl2")
                o_g_wid2 = o_wc2.number_input("W2", 0, 10, 10, key="o_gw2")
                o_hc3, o_wc3 = st.columns([3, 1])
                o_g_lead3 = o_hc3.selectbox("Archer Hero", archer_heroes, index=archer_heroes.index("Marlin") if "Marlin" in archer_heroes else 0, key="o_gl3")
                o_g_wid3 = o_wc3.number_input("W3", 0, 10, 10, key="o_gw3")
                st.markdown("---")
                if opt_side == "Garrison (Defenders)" and "Supporter Heroes" in opt_mode:
                    opt_hero_pool = st.multiselect("Joiner Pool Options", hero_list, default=joiner_pool_defaults, key="o_pool")
                    o_g_sup_heroes = [] 
                else:
                    o_g_sup1 = st.selectbox("Supporter 1", hero_list, index=hero_list.index(joiner_pool_defaults[0]) if joiner_pool_defaults else 0, key="o_gs1")
                    o_g_sup2 = st.selectbox("Supporter 2", hero_list, index=hero_list.index(joiner_pool_defaults[0]) if joiner_pool_defaults else 0, key="o_gs2")
                    o_g_sup3 = st.selectbox("Supporter 3", hero_list, index=hero_list.index(joiner_pool_defaults[0]) if joiner_pool_defaults else 0, key="o_gs3")
                    o_g_sup4 = st.selectbox("Supporter 4", hero_list, index=hero_list.index(joiner_pool_defaults[0]) if joiner_pool_defaults else 0, key="o_gs4")
                    o_g_sup_heroes = [o_g_sup1, o_g_sup2, o_g_sup3, o_g_sup4]
                    
            with st.expander("Target Garrison Combat Stats"):
                o_gia = st.number_input("Inf Attack %", value=850.0, key="o_gia")
                o_gid = st.number_input("Inf Defense %", value=900.0, key="o_gid")
                o_gil = st.number_input("Inf Lethality %", value=1100.0, key="o_gil")
                o_gih = st.number_input("Inf Health %", value=1100.0, key="o_gih")
                st.markdown("---")
                o_gca = st.number_input("Cav Attack %", value=800.0, key="o_gca")
                o_gcd = st.number_input("Cav Defense %", value=800.0, key="o_gcd")
                o_gcl = st.number_input("Cav Lethality %", value=1000.0, key="o_gcl")
                o_gch = st.number_input("Cav Health %", value=1000.0, key="o_gch")
                st.markdown("---")
                o_gaa = st.number_input("Arc Attack %", value=850.0, key="o_gaa")
                o_gad = st.number_input("Arc Defense %", value=800.0, key="o_gad")
                o_gal = st.number_input("Arc Lethality %", value=1100.0, key="o_gal")
                o_gah = st.number_input("Arc Health %", value=1000.0, key="o_gah")

        with opt_main:
            o_num_waves = st.number_input("Number of Attacking Waves Context", min_value=1, max_value=5, value=2, step=1, key="o_waves_cnt")
            o_wave_tabs = st.tabs([f"Wave {i+1}" for i in range(o_num_waves)])
            o_wave_configs = {}
            
            for i, tab in enumerate(o_wave_tabs):
                with tab:
                    ow_col1, ow_col2 = st.columns(2)
                    with ow_col1:
                        owc1, owc2 = st.columns(2)
                        ow_tier = owc1.selectbox("Troop Tier", range(1, 12), index=9, key=f"o_wtier_{i}") 
                        ow_tg = owc2.selectbox("Troop TG Level", range(0, 6), index=5, key=f"o_wtg_{i}")       
                        st.markdown("---")
                        
                        if opt_side == "Attacker Waves (Rallies)" and "Troop Ratios" in opt_mode and i == 0:
                            st.info("**Wave 1 Troop Ratios are locked for continuous loop optimization.**")
                            ow_total_capacity = st.number_input("Rally Size Capacity Limit", value=1000000, step=50000, key=f"o_wcap_{i}")
                            oa_inf, oa_cav, oa_arc = 0, 0, 0
                            st.session_state[f"o_wvalid_{i}"] = True
                        else:
                            ow_input_style = st.radio("Troop Input Type", ("Raw Counts", "Rally Size + Ratios"), key=f"o_wstyle_{i}")
                            if ow_input_style == "Raw Counts":
                                oa_inf = st.number_input("Infantry Count", value=600000, key=f"o_winf_{i}")
                                oa_cav = st.number_input("Cavalry Count", value=200000, key=f"o_wcav_{i}")
                                oa_arc = st.number_input("Archer Count", value=200000, key=f"o_warc_{i}")
                                st.session_state[f"o_wvalid_{i}"] = True
                            else:
                                ow_total_capacity = st.number_input("Rally Size Capacity Limit", value=1000000, step=50000, key=f"o_wcap_{i}")
                                ow_df = [{"Class": "Infantry", "Ratio %": 60}, {"Class": "Cavalry", "Ratio %": 20}, {"Class": "Archer", "Ratio %": 20}]
                                o_edited_w_df = st.data_editor(ow_df, column_config={"Class": st.column_config.TextColumn("Class", disabled=True), "Ratio %": st.column_config.NumberColumn("Ratio %", min_value=0, max_value=100, step=1, format="%d%%")}, disabled=["Class"], hide_index=True, key=f"o_w_ratio_editor_{i}")
                                ow_total_pct = sum(row["Ratio %"] for row in o_edited_w_df)
                                st.session_state[f"o_wvalid_{i}"] = ow_total_pct == 100
                                if ow_total_pct != 100: st.error(f"❌ Wave {i+1} ratios must equal 100%.")
                                oa_inf = int(ow_total_capacity * (o_edited_w_df[0]["Ratio %"] / 100.0))
                                oa_cav = int(ow_total_capacity * (o_edited_w_df[1]["Ratio %"] / 100.0))
                                oa_arc = int(ow_total_capacity * (o_edited_w_df[2]["Ratio %"] / 100.0))
                                
                    with ow_col2:
                        st.markdown("**Attack Main Heroes & Joiners**")
                        oahc1, oawc1 = st.columns([3, 1])
                        oa_l1 = oahc1.selectbox("Infantry Hero", infantry_heroes, index=0, key=f"o_wl1_{i}")
                        oa_w1 = oawc1.number_input("W1", 0, 10, 10, key=f"o_ww1_{i}")
                        oahc2, oawc2 = st.columns([3, 1])
                        oa_l2 = oahc2.selectbox("Cavalry Hero", cavalry_heroes, index=0, key=f"o_wl2_{i}")
                        oa_w2 = oawc2.number_input("W2", 0, 10, 10, key=f"o_ww2_{i}")
                        oahc3, oawc3 = st.columns([3, 1])
                        oa_l3 = oahc3.selectbox("Archer Hero", archer_heroes, index=0, key=f"o_wl3_{i}")
                        oa_w3 = oawc3.number_input("W3", 0, 10, 10, key=f"o_ww3_{i}")
                        st.markdown("---")
                        if opt_side == "Attacker Waves (Rallies)" and "Supporter Heroes" in opt_mode and i == 0:
                            opt_hero_pool = st.multiselect("Wave 1 Option Pool", hero_list, default=joiner_pool_defaults, key="o_w1_pool_opt")
                            oa_s1, oa_s2, oa_s3, oa_s4 = "None", "None", "None", "None"
                        else:
                            osc1, osc2 = st.columns(2)
                            oa_s1 = osc1.selectbox("Sup 1", hero_list, index=0, key=f"o_ws1_{i}")
                            oa_s2 = osc2.selectbox("Sup 2", hero_list, index=0, key=f"o_ws2_{i}")
                            oa_s3 = osc1.selectbox("Sup 3", hero_list, index=0, key=f"o_ws3_{i}")
                            oa_s4 = osc2.selectbox("Sup 4", hero_list, index=0, key=f"o_ws4_{i}")
                            
                    with st.expander(f"Wave {i+1} Stats Override"):
                        osc1, osc2, osc3 = st.columns(3)
                        with osc1:
                            oa_inf_atk = st.number_input("Inf Atk %", value=1000.0, key=f"o_ia_{i}")
                            oa_inf_def = st.number_input("Inf Def %", value=800.0, key=f"o_id_{i}")
                            oa_inf_let = st.number_input("Inf Let %", value=1100.0, key=f"o_il_{i}")
                            oa_inf_hp  = st.number_input("Inf HP %", value=900.0, key=f"o_ih_{i}")
                        with osc2:
                            oa_cav_atk = st.number_input("Cav Atk %", value=900.0, key=f"o_ca_{i}")
                            oa_cav_def = st.number_input("Cav Def %", value=750.0, key=f"o_cd_{i}")
                            oa_cav_let = st.number_input("Cav Let %", value=850.0, key=f"o_cl_{i}")
                            oa_cav_hp  = st.number_input("Cav HP %", value=700.0, key=f"o_ch_{i}")
                        with osc3:
                            oa_arc_atk = st.number_input("Arc Atk %", value=900.0, key=f"o_aa_{i}")
                            oa_arc_def = st.number_input("Arc Def %", value=700.0, key=f"o_ad_{i}")
                            oa_arc_let = st.number_input("Arc Let %", value=1050.0, key=f"o_al_{i}")
                            oa_arc_hp  = st.number_input("Arc HP %", value=800.0, key=f"o_ah_{i}")
                            
                        o_wave_configs[i] = {
                            "troops": [oa_inf, oa_cav, oa_arc], "capacity": ow_total_capacity if 'ow_total_capacity' in locals() else 1000000,
                            "tier": ow_tier, "tg": ow_tg, "leaders": [oa_l1, oa_l2, oa_l3], "supporters": [oa_s1, oa_s2, oa_s3, oa_s4],
                            "widgets": [oa_w1, oa_w2, oa_w3, 0, 0, 0, 0],
                            "stats": [[oa_inf_atk, oa_inf_def, oa_inf_let, oa_inf_hp], [oa_cav_atk, oa_cav_def, oa_cav_let, oa_cav_hp], [oa_arc_atk, oa_arc_def, oa_arc_let, oa_arc_hp]]
                        }
            
            st.markdown("---")
            o_mc_runs = st.number_input("MC Iterations per Combination", min_value=10, max_value=500, value=40, step=10, key="o_mc_runs")
            o_all_waves_valid = all(st.session_state.get(f"o_wvalid_{w_idx}", True) for w_idx in range(o_num_waves))
            
            if o_all_waves_valid and o_g_valid:
                if st.button("Run Optimization Engine Grid Search", key="o_run_btn"):
                    with st.spinner("Processing Continuous Mathematical Strategy Grids..."):
                        o_g_widgets = [o_g_wid1, o_g_wid2, o_g_wid3, 0, 0, 0, 0]
                        o_g_combat_stats = [[o_gia, o_gid, o_gil, o_gih], [o_gca, o_gcd, o_gcl, o_gch], [o_gaa, o_gad, o_gal, o_gah]]
                        
                        results_grid = []
                        ratio_grid = [(i/10.0, j/10.0, (10-i-j)/10.0) for i in range(11) for j in range(11-i)]
                        
                        def build_waves_opt(wave_1_override_troops=None, wave_1_override_heroes=None):
                            waves = []
                            for idx in range(o_num_waves):
                                w_data = o_wave_configs[idx]
                                t_troops = w_data["troops"]
                                t_sups = w_data["supporters"]
                                if idx == 0:
                                    if wave_1_override_troops is not None: t_troops = wave_1_override_troops
                                    if wave_1_override_heroes is not None: t_sups = wave_1_override_heroes
                                waves.append(TroopSide(t_troops, np.array(w_data["stats"]), w_data["leaders"], t_sups, w_data["tier"], w_data["tg"], w_data["widgets"]))
                            return waves

                        if opt_side == "Garrison (Defenders)" and "Troop Ratios" in opt_mode:
                            for r in ratio_grid:
                                test_troops = [o_g_total_troops * r[0], o_g_total_troops * r[1], o_g_total_troops * r[2]]
                                g_setup = TroopSide(test_troops, np.array(o_g_combat_stats), [o_g_lead1, o_g_lead2, o_g_lead3], o_g_sup_heroes, o_g_tier, o_g_tg, o_g_widgets)
                                w_set = build_waves_opt()
                                tot_surv = sum(np.sum(kingshot_multirally_sim2(copy.deepcopy(w_set), copy.deepcopy(g_setup))[0].troops) for _ in range(o_mc_runs))
                                avg_surv = tot_surv / o_mc_runs
                                results_grid.append({"Configuration": f"Inf: {r[0]*100:.0f}% | Cav: {r[1]*100:.0f}% | Arc: {r[2]*100:.0f}%", "Avg Survivors": avg_surv, "Rate": (avg_surv / o_g_total_troops) * 100})
                        
                        elif opt_side == "Garrison (Defenders)" and "Supporter Heroes" in opt_mode:
                            combos = list(itertools.combinations_with_replacement(opt_hero_pool, 4))
                            for combo in combos:
                                g_setup = TroopSide([o_g_inf, o_g_cav, o_g_arc], np.array(o_g_combat_stats), [o_g_lead1, o_g_lead2, o_g_lead3], list(combo), o_g_tier, o_g_tg, o_g_widgets)
                                w_set = build_waves_opt()
                                tot_surv = sum(np.sum(kingshot_multirally_sim2(copy.deepcopy(w_set), copy.deepcopy(g_setup))[0].troops) for _ in range(o_mc_runs))
                                avg_surv = tot_surv / o_mc_runs
                                results_grid.append({"Configuration": f"{', '.join(combo)}", "Avg Survivors": avg_surv, "Rate": (avg_surv / max(1, o_g_total_troops)) * 100})
                        
                        elif opt_side == "Attacker Waves (Rallies)" and "Troop Ratios" in opt_mode:
                            w1_cap = o_wave_configs[0]["capacity"]
                            g_setup = TroopSide([o_g_inf, o_g_cav, o_g_arc], np.array(o_g_combat_stats), [o_g_lead1, o_g_lead2, o_g_lead3], o_g_sup_heroes, o_g_tier, o_g_tg, o_g_widgets)
                            for r in ratio_grid:
                                test_w1_troops = [w1_cap * r[0], w1_cap * r[1], w1_cap * r[2]]
                                w_set = build_waves_opt(wave_1_override_troops=test_w1_troops)
                                tot_surv = sum(np.sum(kingshot_multirally_sim2(copy.deepcopy(w_set), copy.deepcopy(g_setup))[0].troops) for _ in range(o_mc_runs))
                                avg_surv = tot_surv / o_mc_runs
                                results_grid.append({"Configuration": f"Wave 1 -> Inf: {r[0]*100:.0f}% | Cav: {r[1]*100:.0f}% | Arc: {r[2]*100:.0f}%", "Avg Survivors": avg_surv, "Rate": (avg_surv / max(1, o_g_total_troops)) * 100})
                        
                        elif opt_side == "Attacker Waves (Rallies)" and "Supporter Heroes" in opt_mode:
                            combos = list(itertools.combinations_with_replacement(opt_hero_pool, 4))
                            g_setup = TroopSide([o_g_inf, o_g_cav, o_g_arc], np.array(o_g_combat_stats), [o_g_lead1, o_g_lead2, o_g_lead3], o_g_sup_heroes, o_g_tier, o_g_tg, o_g_widgets)
                            
                            for combo in combos:
                                w_set = build_waves_opt(wave_1_override_heroes=list(combo))
                                g_surv_sum = 0
                                a_surv_sum = 0
                                
                                for _ in range(o_mc_runs):
                                    final_g, logs = kingshot_multirally_sim2(copy.deepcopy(w_set), copy.deepcopy(g_setup))
                                    g_surv_sum += np.sum(final_g.troops)
                                    a_surv_sum += sum(np.sum(log['attacker_surviving']) for log in logs)
                                    
                                avg_g_surv = g_surv_sum / o_mc_runs
                                avg_a_surv = a_surv_sum / o_mc_runs
                                
                                results_grid.append({
                                    "Configuration": f"Wave 1 -> {', '.join(combo)}", 
                                    "Avg Survivors": avg_g_surv, 
                                    "Attacker Retained": avg_a_surv,
                                    "Rate": (avg_g_surv / max(1, o_g_total_troops)) * 100
                                })

                        if opt_side == "Garrison (Defenders)":
                            sorted_results = sorted(results_grid, key=lambda x: (x["Avg Survivors"], -x.get("Attacker Retained", 0)), reverse=True)
                            st.success("🏰 GARRISON OPTIMIZATION COMPLETE")
                        else:
                            sorted_results = sorted(results_grid, key=lambda x: (x["Avg Survivors"], -x.get("Attacker Retained", 0)), reverse=False)
                            st.success("🔥 ATTACKER OPTIMIZATION COMPLETE")

                        st.markdown("### 🏆 Top 5 Matrix Configurations")
                        top_5 = sorted_results[:5]
                        
                        f_top_5 = [{
                            "Rank": i+1, 
                            "Configuration": r["Configuration"], 
                            "Garrison Survivors": f"{r['Avg Survivors']:,.0f}", 
                            "Attacker Survivors": f"{r.get('Attacker Retained', 0):,.0f}",
                            "Survival Rate %": f"{r['Rate']:.1f}%"
                        } for i, r in enumerate(top_5)]
                        
                        st.table(f_top_5)
            else:
                st.button("Run Optimization Engine Grid Search", disabled=True, key="o_run_disabled")

   # =========================================================================
    # --- TAB 3: STAT ROI ENGINE ---
    # =========================================================================
    with tab_roi:
        st.header("Multi-Variable Stat Optimizer")
        
        c1, c2, _ = st.columns([1, 1, 2])
        if c1.button("📋 Copy Profile to Clipboard", key="r_copy"):
            copy_to_clipboard('r')
            st.success("Profile saved to clipboard!")
        if c2.button("📥 Paste Profile from Clipboard", key="r_paste"):
            paste_from_clipboard('r')
            st.rerun()
        st.markdown("---")
        
        roi_main, roi_side_col = st.columns([2, 1])
        
        with roi_side_col:
            st.header("Baseline Profile Setup")
            r_gc1, r_gc2 = st.columns(2)
            r_g_tier = r_gc1.selectbox("Garrison Troop Tier", range(1, 12), index=10, key="r_gtier") 
            r_g_tg = r_gc2.selectbox("Garrison Troop TG Level", range(0, 6), index=5, key="r_gtg")       
            st.markdown("---")
            
            r_g_input_style = st.radio("Garrison Troop Input Type", ("Raw Counts", "Capacity + Ratios"), key="r_g_style")
            if r_g_input_style == "Raw Counts":
                r_g_inf = st.number_input("Garrison Infantry Count", value=1500000, key="r_gi")
                r_g_cav = st.number_input("Garrison Cavalry Count", value=500000, key="r_gc")
                r_g_arc = st.number_input("Garrison Archer Count", value=800000, key="r_ga")
                r_g_total_troops = r_g_inf + r_g_cav + r_g_arc
                r_g_valid = True
            else:
                r_g_total_troops = st.number_input("Total Garrison Capacity Target", value=2800000, step=100000, key="r_gtot")
                r_g_df = [{"Class": "Infantry", "Ratio %": 50}, {"Class": "Cavalry", "Ratio %": 20}, {"Class": "Archer", "Ratio %": 30}]
                r_edited_g_df = st.data_editor(r_g_df, column_config={"Class": st.column_config.TextColumn("Class", disabled=True), "Ratio %": st.column_config.NumberColumn("Ratio %", min_value=0, max_value=100, step=1, format="%d%%")}, disabled=["Class"], hide_index=True, key="r_g_ratio_editor")
                r_g_total_pct = sum(row["Ratio %"] for row in r_edited_g_df)
                r_g_valid = r_g_total_pct == 100
                if not r_g_valid: st.error(f"❌ Garrison ratios must sum to 100%.")
                r_g_inf = int(r_g_total_troops * (r_edited_g_df[0]["Ratio %"] / 100.0))
                r_g_cav = int(r_g_total_troops * (r_edited_g_df[1]["Ratio %"] / 100.0))
                r_g_arc = int(r_g_total_troops * (r_edited_g_df[2]["Ratio %"] / 100.0))

            with st.expander("Garrison Heroes"):
                r_hc1, r_wc1 = st.columns([3, 1])
                r_g_lead1 = r_hc1.selectbox("Infantry Hero", infantry_heroes, index=infantry_heroes.index("Amadeus") if "Amadeus" in infantry_heroes else 0, key="r_gl1")
                r_g_wid1 = r_wc1.number_input("W1", 0, 10, 10, key="r_gw1") 
                r_hc2, r_wc2 = st.columns([3, 1])
                r_g_lead2 = r_hc2.selectbox("Cavalry Hero", cavalry_heroes, index=cavalry_heroes.index("Hilde") if "Hilde" in cavalry_heroes else 0, key="r_gl2")
                r_g_wid2 = r_wc2.number_input("W2", 0, 10, 10, key="r_gw2") 
                r_hc3, r_wc3 = st.columns([3, 1])
                r_g_lead3 = r_hc3.selectbox("Archer Hero", archer_heroes, index=archer_heroes.index("Marlin") if "Marlin" in archer_heroes else 0, key="r_gl3")
                r_g_wid3 = r_wc3.number_input("W3", 0, 10, 10, key="r_gw3") 
                st.markdown("---")
                r_g_sup1 = st.selectbox("Supporter 1", hero_list, index=0, key="r_gs1")
                r_g_sup2 = st.selectbox("Supporter 2", hero_list, index=0, key="r_gs2")
                r_g_sup3 = st.selectbox("Supporter 3", hero_list, index=0, key="r_gs3")
                r_g_sup4 = st.selectbox("Supporter 4", hero_list, index=0, key="r_gs4")
                
            with st.expander("Baseline Profile Combat Stats"):
                r_gia = st.number_input("Inf Atk %", value=850.0, key="r_gia")
                r_gid = st.number_input("Inf Def %", value=900.0, key="r_gid")
                r_gil = st.number_input("Inf Let %", value=1100.0, key="r_gil")
                r_gih = st.number_input("Inf HP %", value=1100.0, key="r_gih")
                st.markdown("---")
                r_gca = st.number_input("Cav Atk %", value=800.0, key="r_gca")
                r_gcd = st.number_input("Cav Def %", value=800.0, key="r_gcd")
                r_gcl = st.number_input("Cav Let %", value=1000.0, key="r_gcl")
                r_gch = st.number_input("Cav HP %", value=1000.0, key="r_gch")
                st.markdown("---")
                r_gaa = st.number_input("Arc Atk %", value=850.0, key="r_gaa")
                r_gad = st.number_input("Arc Def %", value=800.0, key="r_gad")
                r_gal = st.number_input("Arc Let %", value=1100.0, key="r_gal")
                r_gah = st.number_input("Arc HP %", value=1000.0, key="r_gah")

        with roi_main:
            st.subheader("⚙️ Multi-Variable Strategy Allocation Budget")
            
            # Formats the inputs cleanly into three balanced columns
            rc1, rc2, rc3 = st.columns(3)
            total_pool = rc1.number_input("Total Stat Pool (+ %)", min_value=25.0, max_value=2000.0, value=200.0, step=25.0, key="r_total_pool")
            step_size = rc2.number_input("Increment Step Size (+ %)", min_value=5.0, max_value=200.0, value=25.0, step=5.0, key="r_nudge")
            r_mc_runs = rc3.number_input("Monte Carlo Precision", min_value=10, max_value=500, value=50, step=10, key="r_mc_precision")
            
            st.markdown("---")
            r_num_waves = st.number_input("Number of Incoming Mock Rallies to Absorb", min_value=1, max_value=5, value=2, step=1, key="r_waves_cnt")
            r_wave_tabs = st.tabs([f"🌊 Wave {i+1}" for i in range(r_num_waves)])
            r_wave_configs = {}
            
            for i, tab in enumerate(r_wave_tabs):
                with tab:
                    rw_col1, rw_col2 = st.columns(2)
                    with rw_col1:
                        rwc1, rwc2 = st.columns(2)
                        rw_tier = rwc1.selectbox("Troop Tier", range(1, 12), index=9, key=f"r_wtier_{i}")
                        rw_tg = rwc2.selectbox("Troop TG Level", range(0, 6), index=5, key=f"r_wtg_{i}")
                        
                        rw_input_style = st.radio("Troop Input Type", ("Raw Counts", "Rally Size + Ratios"), key=f"r_wstyle_{i}")
                        if rw_input_style == "Raw Counts":
                            ra_inf = st.number_input("Infantry Count", value=600000, key=f"r_winf_{i}")
                            ra_cav = st.number_input("Cavalry Count", value=200000, key=f"r_wcav_{i}")
                            ra_arc = st.number_input("Archer Count", value=200000, key=f"r_warc_{i}")
                            st.session_state[f"r_wvalid_{i}"] = True
                        else:
                            ra_total_capacity = st.number_input("Rally Size Limit", value=1000000, step=50000, key=f"r_wcap_{i}")
                            rw_df = [{"Class": "Infantry", "Ratio %": 60}, {"Class": "Cavalry", "Ratio %": 20}, {"Class": "Archer", "Ratio %": 20}]
                            r_edited_w_df = st.data_editor(rw_df, column_config={"Class": st.column_config.TextColumn("Class", disabled=True), "Ratio %": st.column_config.NumberColumn("Ratio %", min_value=0, max_value=100, step=1, format="%d%%")}, disabled=["Class"], hide_index=True, key=f"r_w_ratio_editor_{i}")
                            rw_total_pct = sum(row["Ratio %"] for row in r_edited_w_df)
                            st.session_state[f"r_wvalid_{i}"] = rw_total_pct == 100
                            if rw_total_pct != 100: st.error(f"❌ Wave {i+1} ratios must equal 100%.")
                            ra_inf = int(ra_total_capacity * (r_edited_w_df[0]["Ratio %"] / 100.0))
                            ra_cav = int(ra_total_capacity * (r_edited_w_df[1]["Ratio %"] / 100.0))
                            ra_arc = int(ra_total_capacity * (r_edited_w_df[2]["Ratio %"] / 100.0))
                            
                    with rw_col2:
                        st.markdown("**Attack Heroes**")
                        ra_l1 = st.selectbox("Infantry Leader", infantry_heroes, index=0, key=f"r_wl1_{i}")
                        ra_w1 = st.number_input("Widget 1", 0, 10, 10, key=f"r_ww1_{i}")
                        ra_l2 = st.selectbox("Cavalry Leader", cavalry_heroes, index=0, key=f"r_wl2_{i}")
                        ra_w2 = st.number_input("Widget 2", 0, 10, 10, key=f"r_ww2_{i}")
                        ra_l3 = st.selectbox("Archer Leader", archer_heroes, index=0, key=f"r_wl3_{i}")
                        ra_w3 = st.number_input("Widget 3", 0, 10, 10, key=f"r_ww3_{i}")
                        st.markdown("---")
                        ra_s1 = st.selectbox("Sup 1", hero_list, index=0, key=f"r_ws1_{i}")
                        ra_s2 = st.selectbox("Sup 2", hero_list, index=0, key=f"r_ws2_{i}")
                        
                    with st.expander(f"Wave {i+1} Attacker Stats"):
                        rsc1, rsc2, rsc3 = st.columns(3)
                        with rsc1:
                            ra_inf_atk = st.number_input("Inf Atk %", value=1000.0, key=f"r_ia_{i}")
                            ra_inf_def = st.number_input("Inf Def %", value=800.0, key=f"r_id_{i}")
                            ra_inf_let = st.number_input("Inf Let %", value=1100.0, key=f"r_il_{i}")
                            ra_inf_hp  = st.number_input("Inf HP %", value=900.0, key=f"r_ih_{i}")
                        with rsc2:
                            ra_cav_atk = st.number_input("Cav Atk %", value=900.0, key=f"r_ca_{i}")
                            ra_cav_def = st.number_input("Cav Def %", value=750.0, key=f"r_cd_{i}")
                            ra_cav_let = st.number_input("Cav Let %", value=850.0, key=f"r_cl_{i}")
                            ra_cav_hp  = st.number_input("Cav HP %", value=700.0, key=f"r_ch_{i}")
                        with rsc3:
                            ra_arc_atk = st.number_input("Arc Atk %", value=900.0, key=f"r_aa_{i}")
                            ra_arc_def = st.number_input("Arc Def %", value=700.0, key=f"r_ad_{i}")
                            ra_arc_let = st.number_input("Arc Let %", value=1050.0, key=f"r_al_{i}")
                            ra_arc_hp  = st.number_input("Arc HP %", value=800.0, key=f"r_ah_{i}")
                            
                        r_wave_configs[i] = {
                            "troops": [ra_inf, ra_cav, ra_arc], "tier": rw_tier, "tg": rw_tg,
                            "leaders": [ra_l1, ra_l2, ra_l3], "supporters": [ra_s1, ra_s2, "None", "None"],
                            "widgets": [ra_w1, ra_w2, ra_w3, 0, 0, 0, 0],
                            "stats": [[ra_inf_atk, ra_inf_def, ra_inf_let, ra_inf_hp], [ra_cav_atk, ra_cav_def, ra_cav_let, ra_cav_hp], [ra_arc_atk, ra_arc_def, ra_arc_let, ra_arc_hp]]
                        }
            
            st.markdown("---")
            r_all_waves_valid = all(st.session_state.get(f"r_wvalid_{w_idx}", True) for w_idx in range(r_num_waves))
            
            if r_all_waves_valid and r_g_valid:
                if st.button("🚀 Run Multi-Variable Allocation Analysis", key="r_run_btn", type="primary"):
                    with st.spinner("Calculating optimal multi-variable allocation path..."):
                        r_g_widgets = [r_g_wid1, r_g_wid2, r_g_wid3, 0, 0, 0, 0]
                        r_g_sups = [r_g_sup1, r_g_sup2, r_g_sup3, r_g_sup4]
                        
                        rally_waves_input = []
                        for wave_idx in range(r_num_waves):
                            rw_data = r_wave_configs[wave_idx]
                            rally_waves_input.append(TroopSide(rw_data["troops"], np.array(rw_data["stats"]), rw_data["leaders"], rw_data["supporters"], rw_data["tier"], rw_data["tg"], rw_data["widgets"]))
                        
                        # Establish our active, shifting baseline profile
                        active_stats = [[r_gia, r_gid, r_gil, r_gih], [r_gca, r_gcd, r_gcl, r_gch], [r_gaa, r_gad, r_gal, r_gah]]
                        
                        stat_map = [
                            ("Infantry Attack", 0, 0), ("Infantry Defense", 0, 1), ("Infantry Lethality", 0, 2), ("Infantry Health", 0, 3),
                            ("Cavalry Attack", 1, 0),  ("Cavalry Defense", 1, 1),  ("Cavalry Lethality", 1, 2),  ("Cavalry Health", 1, 3),
                            ("Archer Attack", 2, 0),   ("Archer Defense", 2, 1),   ("Archer Lethality", 2, 2),   ("Archer Health", 2, 3)
                        ]
                        
                        total_steps = int(total_pool // step_size)
                        allocation_blueprint = {}
                        summary_log = []
                        
                        for current_step in range(1, total_steps + 1):
                            # Calculate control survival for this specific step's baseline
                            control_garrison = TroopSide([r_g_inf, r_g_cav, r_g_arc], np.array(active_stats), [r_g_lead1, r_g_lead2, r_g_lead3], r_g_sups, r_g_tier, r_g_tg, r_g_widgets)
                            control_avg = sum(np.sum(kingshot_multirally_sim2(copy.deepcopy(rally_waves_input), copy.deepcopy(control_garrison))[0].troops) for _ in range(r_mc_runs)) / r_mc_runs
                            
                            step_leaderboard = []
                            
                            # Test adding our increment to every individual node
                            for label, row, col in stat_map:
                                nudged_stats = copy.deepcopy(active_stats)
                                nudged_stats[row][col] += step_size
                                
                                test_garrison = TroopSide([r_g_inf, r_g_cav, r_g_arc], np.array(nudged_stats), [r_g_lead1, r_g_lead2, r_g_lead3], r_g_sups, r_g_tier, r_g_tg, r_g_widgets)
                                test_avg = sum(np.sum(kingshot_multirally_sim2(copy.deepcopy(rally_waves_input), copy.deepcopy(test_garrison))[0].troops) for _ in range(r_mc_runs)) / r_mc_runs
                                
                                saved_troops = max(0.0, test_avg - control_avg)
                                step_leaderboard.append({'label': label, 'row': row, 'col': col, 'saved': saved_troops})
                            
                            # Find the single best node for this specific step
                            step_leaderboard.sort(key=lambda x: x['saved'], reverse=True)
                            winner = step_leaderboard[0]
                            
                            # Lock the stats into our running active pool
                            active_stats[winner['row']][winner['col']] += step_size
                            allocation_blueprint[winner['label']] = allocation_blueprint.get(winner['label'], 0) + step_size
                            
                            summary_log.append({
                                "Allocation Step": f"Step #{current_step} (+{step_size}%)",
                                "Target Stat Selected": winner['label'],
                                "Additional Saved Troops": f"{winner['saved']:,.0f}",
                                "Running Profile State": f"Total Assigned: {allocation_blueprint[winner['label']]}%"
                            })
                            
                        st.success("🎯 Multi-Variable Upgrade Blueprint Calculated!")
                        
                        # Output 1: Clear Summary Matrix Table
                        st.subheader("📋 Step-by-Step Investment Roadmap")
                        st.table(summary_log)
                        
                        # Output 2: Final Tally Summary
                        st.subheader("📊 Final Recommended Stat Distribution")
                        final_tally = [{"Stat Node": k, "Total Investment Recommended": f"+{v}%"} for k, v in allocation_blueprint.items()]
                        st.table(final_tally)
            else:
                st.button("🚀 Run Multi-Variable Allocation Analysis", disabled=True, key="r_run_disabled")
                # =========================================================================
    # --- TAB 4: COMPREHENSIVE ASSET & GEAR OPTIMIZER WITH MONOTONICITY GUARD ---
    # =========================================================================
    with tab_gear:
        st.header("🎯 Greedy Account Progression & Gear Optimizer")
        st.caption("Calculates the highest combat ROI across Charms, Governor Gear, and Hero Gear using true multi-budget simulation passes.")

        # Establish global mapping databases for the execution run
        atlases = load_stat_atlases()
        
        # Ascension milestone requirements table parsed from gear.xlsx: [Required Mastery, Required Mithril, Required Mythic Pieces]
        ascension_table = {
            100: [10, 0, 2],   # Mythic -> Red baseline transition
            120: [11, 10, 3],  # 100 -> 120 bracket step
            140: [12, 20, 5],  # 120 -> 140 bracket step
            160: [13, 30, 5],  # 140 -> 160 bracket step
            180: [14, 40, 10]  # 160 -> 180 bracket step
        }

        g_main, g_side = st.columns([2, 1])

        with g_side:
            st.markdown("### 🎒 Your Asset Inventory")
            
            # Hero Gear XP Parsing (image_d96ccc.png framework)
            with st.expander("✨ Hero Gear XP Quantities", expanded=True):
                green_books = st.number_input("10 Enhancement XP Part (Green)", min_value=0, value=50, step=10, key="g_xp_green")
                purple_books = st.number_input("100 Enhancement XP Part (Purple)", min_value=0, value=15, step=5, key="g_xp_purple")
                com_gear = st.number_input("Common Gear Material (10 XP)", min_value=0, value=20, key="g_xp_com")
                uncom_gear = st.number_input("Uncommon Gear Material (30 XP)", min_value=0, value=10, key="g_xp_uncom")
                rare_gear = st.number_input("Rare Gear Material (60 XP)", min_value=0, value=5, key="g_xp_rare")
                epic_gear = st.number_input("Epic Gear Material (150 XP)", min_value=0, value=2, key="g_xp_epic")
                
                # Calculate aggregated baseline bag pools
                calculated_xp_pool = (green_books * 10) + (purple_books * 100) + (com_gear * 10) + (uncom_gear * 30) + (rare_gear * 60) + (epic_gear * 150)
                st.info(f"**Total Available XP Reservoir:** {calculated_xp_pool:,.0f} XP")
                
            with st.expander("🔨 Mastery & Ascension Forge Assets", expanded=True):
                inv_hammers = st.number_input("Available Forgehammers", min_value=0, value=350, key="g_inv_hammers")
                inv_mithril = st.number_input("Available Mithril", min_value=0, value=15, key="g_inv_mithril")
                inv_mythic_pieces = st.number_input("Available Mythic Gear Duplicates", min_value=0, value=4, key="g_inv_pieces")
                
            with st.expander("📜 Charm & Governor Materials", expanded=True):
                inv_guides = st.number_input("Available Charm Guides", min_value=0, value=500, key="g_inv_guides")
                inv_designs = st.number_input("Available Charm Designs", min_value=0, value=400, key="g_inv_designs")
                inv_satin = st.number_input("Available Satin Sheets", min_value=0, value=25000, key="g_inv_satin")
                inv_threads = st.number_input("Available Thread Spools", min_value=0, value=500, key="g_inv_threads")
                inv_artisans = st.number_input("Available Artisan Tokens", min_value=0, value=120, key="g_inv_artisans")

            with st.expander("🛡️ Target Defense Environment (Rival Wall)"):
                env_inf = st.number_input("Threat Target Infantry Array Count", value=1200000, key="g_env_inf")
                env_stats = st.number_input("Target Defensive Baseline Armor %", value=1400.0, key="g_env_stats")

        with g_main:
            st.markdown("### 🏛️ Active Structural Profiles")
            
            t_c1, t_c2 = st.columns(2)
            mc_precision = t_c1.slider("Greedy Search Pass Precision (Monte Carlo)", 10, 150, 40, step=10, key="g_precision_slider")
            monotonicity_guard = t_c2.toggle("Engage Monotonicity Guard", value=True, key="g_mono_toggle")
            
            st.markdown("#### Current Account Level States")
            st_c1, st_c2, st_c3 = st.columns(3)
            
            # Row 1: Infantry Asset Matrix Input
            with st_c1:
                st.markdown("**Infantry Upgrades**")
                inf_charm_lvl = st.number_input("Charm Level", 0, 10, 6, key="cur_inf_ch")
                inf_gov_lvl = st.number_input("Gov Tier Index", 0, 8, 3, key="cur_inf_gov") 
                inf_hero_tier = st.selectbox("Hero Quality", ["Epic", "Mythic", "Red"], index=1, key="cur_inf_hq")
                inf_hero_lvl = st.number_input("Hero Level", 0, 200, 45, key="cur_inf_hl")
                inf_hero_mastery = st.number_input("Mastery Star Lvl", 0, 20, 4, key="cur_inf_hm")
            
            # Row 2: Cavalry Asset Matrix Input
            with st_c2:
                st.markdown("**Cavalry Upgrades**")
                cav_charm_lvl = st.number_input("Charm Level", 0, 10, 5, key="cur_cav_ch")
                cav_gov_lvl = st.number_input("Gov Tier Index", 0, 8, 2, key="cur_cav_gov")
                cav_hero_tier = st.selectbox("Hero Quality", ["Epic", "Mythic", "Red"], index=1, key="cur_cav_hq")
                cav_hero_lvl = st.number_input("Hero Level", 0, 200, 40, key="cur_cav_hl")
                cav_hero_mastery = st.number_input("Mastery Star Lvl", 0, 20, 3, key="cur_cav_hm")
            
            # Row 3: Archer Asset Matrix Input
            with st_c3:
                st.markdown("**Archer Upgrades**")
                arc_charm_lvl = st.number_input("Charm Level", 0, 10, 5, key="cur_arc_ch")
                arc_gov_lvl = st.number_input("Gov Tier Index", 0, 8, 2, key="cur_arc_gov")
                arc_hero_tier = st.selectbox("Hero Quality", ["Epic", "Mythic", "Red"], index=1, key="cur_arc_hq")
                arc_hero_lvl = st.number_input("Hero Level", 0, 200, 40, key="cur_arc_hl")
                arc_hero_mastery = st.number_input("Mastery Star Lvl", 0, 20, 3, key="cur_arc_hm")

            st.markdown("---")
            
            if st.button("🚀 Execute Comprehensive Greedy Optimization Pass", type="primary", use_container_width=True, key="g_run_pass_btn"):
                with st.spinner("Processing local optimum strategy chains via Multi-Budget Matrix..."):
                    
                    # Format baseline control configurations
                    current_profile = {
                        "charms": [inf_charm_lvl, cav_charm_lvl, arc_charm_lvl],
                        "gov": [inf_gov_lvl, cav_gov_lvl, arc_gov_lvl],
                        "hero_tier": [inf_hero_tier, cav_hero_tier, arc_hero_tier],
                        "hero_lvl": [inf_hero_lvl, cav_hero_lvl, arc_hero_lvl],
                        "hero_mastery": [inf_hero_mastery, cav_hero_mastery, arc_hero_mastery]
                    }
                    
                    wallet = {
                        "XP": calculated_xp_pool, "Forgehammer": inv_hammers, "Mithril": inv_mithril,
                        "Mythic Piece": inv_mythic_pieces, "Charm Guide": inv_guides, "Charm Design": inv_designs,
                        "Satin": inv_satin, "Thread": inv_threads, "Artisan": inv_artisans
                    }
                    
                    def run_isolated_simulation(profile_state):
                        """Translates active tier choices into a simulated match to gather troop retention counts."""
                        sim_stats = np.array([
                            [1400.0, 1100.0, 1300.0, 1200.0],  # Infantry [Atk, Def, Let, HP]
                            [1300.0, 1000.0, 1200.0, 1100.0],  # Cavalry
                            [1450.0, 1050.0, 1350.0, 1150.0]   # Archer
                        ])
                        
                        for r in range(3):
                            # Apply Charms
                            c_lvl = profile_state["charms"][r]
                            charm_boost = sum(atlases["charms"]["deltas"][:c_lvl+1]) * 100.0
                            sim_stats[r, 2] += charm_boost  
                            sim_stats[r, 3] += charm_boost  
                            
                            # Apply Governor Gear
                            g_lvl = profile_state["gov"][r]
                            gov_boost = sum(atlases["gov"]["deltas"][:g_lvl+1]) * 100.0
                            sim_stats[r, 0] += gov_boost  
                            sim_stats[r, 1] += gov_boost  
                            
                            # Apply Base Hero Gear Stats from sheet formulas
                            h_tier = profile_state["hero_tier"][r]
                            h_lvl = profile_state["hero_lvl"][r]
                            hero_boost = get_hero_gear_stat(h_tier, h_lvl) * 100.0
                            
                            # Factor in Mastery Forge Multipliers (+10% base value scaling per star level)
                            m_lvl = profile_state["hero_mastery"][r]
                            mastery_multiplier = 1.0 + (m_lvl * 0.10)
                            final_hero_boost = hero_boost * mastery_multiplier
                            
                            # Inject vectors smoothly into army profile parameters
                            sim_stats[r, 0] += final_hero_boost  
                            sim_stats[r, 2] += final_hero_boost
                            sim_stats[r, 1] += final_hero_boost  
                            sim_stats[r, 3] += final_hero_boost

                        attacker = TroopSide([500000, 200000, 300000], sim_stats, ["Amadeus", "Hilde", "Marlin"], ["Chenko", "Gordon", "None", "None"])
                        defender = TroopSide([env_inf, 400000, 400000], np.array([[env_stats]*4]*3), ["Amadeus", "Hilde", "Marlin"], ["Chenko", "None", "None", "None"])
                        
                        total_surviving_troops = 0
                        for _ in range(mc_precision):
                            res = kingshot_multirally_sim2([copy.deepcopy(attacker)], copy.deepcopy(defender))
                            total_surviving_troops += np.sum(res[0].troops)
                            
                        return total_surviving_troops / mc_precision

                    # --- MULTI-BUDGET LOGIC TETHERING ---
                    budget_multipliers = [1.0, 0.90, 0.80] if monotonicity_guard else [1.0]
                    best_overall_roadmap = []
                    best_final_survival = -1
                    best_wallet_remainder = {}

                    for budget_mod in budget_multipliers:
                        loop_wallet = {k: int(v * budget_mod) for k, v in wallet.items()}
                        loop_state_profile = copy.deepcopy(current_profile)
                        current_roadmap = []
                        
                        for iteration in range(1, 16):  # Computes chronological upgrade chains up to 15 actions out
                            control_surv = run_isolated_simulation(loop_state_profile)
                            candidates = []
                            
                            # --- SCAN OPTION A: CHARMS ---
                            for troop_idx, label in enumerate(["Infantry", "Cavalry", "Archer"]):
                                current_lvl = loop_state_profile["charms"][troop_idx]
                                if current_lvl < 10:
                                    req_guides = atlases["charms"]["guides"][current_lvl + 1]
                                    req_designs = atlases["charms"]["designs"][current_lvl + 1]
                                    if loop_wallet["Charm Guide"] >= req_guides and loop_wallet["Charm Design"] >= req_designs:
                                        test_profile = copy.deepcopy(loop_state_profile)
                                        test_profile["charms"][troop_idx] += 1
                                        test_surv = run_isolated_simulation(test_profile)
                                        saved = max(0.001, test_surv - control_surv)
                                        eff = saved / max(1, req_guides + req_designs)
                                        candidates.append({
                                            "type": "charms", "idx": troop_idx, "label": f"Level up {label} Charms to Lvl {current_lvl + 1}",
                                            "cost": {"Charm Guide": req_guides, "Charm Design": req_designs}, "efficiency": eff, "saved": saved
                                        })

                            # --- SCAN OPTION B: GOVERNOR GEAR ---
                            for troop_idx, label in enumerate(["Infantry", "Cavalry", "Archer"]):
                                current_lvl = loop_state_profile["gov"][troop_idx]
                                if current_lvl < 8:
                                    req_satin = atlases["gov"]["satin"][current_lvl + 1]
                                    req_thread = atlases["gov"]["threads"][current_lvl + 1]
                                    req_artisan = atlases["gov"]["artisans"][current_lvl + 1]
                                    if (loop_wallet["Satin"] >= req_satin and loop_wallet["Thread"] >= req_thread and loop_wallet["Artisan"] >= req_artisan):
                                        test_profile = copy.deepcopy(loop_state_profile)
                                        test_profile["gov"][troop_idx] += 1
                                        test_surv = run_isolated_simulation(test_profile)
                                        saved = max(0.001, test_surv - control_surv)
                                        eff = saved / max(1, req_satin * 0.01 + req_thread + req_artisan * 10)
                                        candidates.append({
                                            "type": "gov", "idx": troop_idx, "label": f"Upgrade {label} Gov Gear to {atlases['gov']['names'][current_lvl + 1]}",
                                            "cost": {"Satin": req_satin, "Thread": req_thread, "Artisan": req_artisan}, "efficiency": eff, "saved": saved
                                        })

                            # --- SCAN OPTION C: HERO GEAR ENHANCEMENTS AND BRACKET GATES ---
                            for troop_idx, label in enumerate(["Infantry", "Cavalry", "Archer"]):
                                current_lvl = loop_state_profile["hero_lvl"][troop_idx]
                                current_tier = loop_state_profile["hero_tier"][troop_idx]
                                current_mastery = loop_state_profile["hero_mastery"][troop_idx]
                                
                                if current_lvl in ascension_table:
                                    # Target piece hits a gated threshold boundary line
                                    req_mastery, req_mithril, req_mythic_pieces = ascension_table[current_lvl]
                                    if current_mastery >= req_mastery:
                                        if loop_wallet["Mithril"] >= req_mithril and loop_wallet["Mythic Piece"] >= req_mythic_pieces:
                                            test_profile = copy.deepcopy(loop_state_profile)
                                            test_profile["hero_lvl"][troop_idx] += 1
                                            if current_lvl == 100 and current_tier == "Mythic":
                                                test_profile["hero_tier"][troop_idx] = "Red"
                                                
                                            test_surv = run_isolated_simulation(test_profile)
                                            saved = max(0.001, test_surv - control_surv)
                                            eff = saved / max(1, (req_mithril * 50) + (req_mythic_pieces * 500))
                                            candidates.append({
                                                "type": "hero_ascend", "idx": troop_idx, "label": f"🔺 Ascend {label} Hero Gear past Lvl {current_lvl} gate",
                                                "cost": {"Mithril": req_mithril, "Mythic Piece": req_mythic_pieces}, "efficiency": eff, "saved": saved
                                            })
                                else:
                                    # Regular incremental level processing loop
                                    req_xp = calculate_hero_gear_xp_cost(current_lvl)
                                    if loop_wallet["XP"] >= req_xp and current_lvl < 200:
                                        test_profile = copy.deepcopy(loop_state_profile)
                                        test_profile["hero_lvl"][troop_idx] += 1
                                        test_surv = run_isolated_simulation(test_profile)
                                        saved = max(0.001, test_surv - control_surv)
                                        eff = saved / max(1, req_xp * 0.1)
                                        candidates.append({
                                            "type": "hero_lvl", "idx": troop_idx, "label": f"Enhance {label} Hero Gear to Lvl {current_lvl + 1} ({current_tier})",
                                            "cost": {"XP": req_xp}, "efficiency": eff, "saved": saved
                                        })

                            # --- SCAN OPTION D: MASTERY FORGE STEPS ---
                            for troop_idx, label in enumerate(["Infantry", "Cavalry", "Archer"]):
                                current_mastery = loop_state_profile["hero_mastery"][troop_idx]
                                if current_mastery < 20:
                                    req_hammers = (current_mastery + 1) * 10
                                    req_pieces = max(0, current_mastery - 9)
                                    
                                    if loop_wallet["Forgehammer"] >= req_hammers and loop_wallet["Mythic Piece"] >= req_pieces:
                                        test_profile = copy.deepcopy(loop_state_profile)
                                        test_profile["hero_mastery"][troop_idx] += 1
                                        test_surv = run_isolated_simulation(test_profile)
                                        saved = max(0.001, test_surv - control_surv)
                                        eff = saved / max(1, req_hammers + (req_pieces * 500))
                                        candidates.append({
                                            "type": "hero_mastery", "idx": troop_idx, "label": f"⭐ Mastery Forge {label} Gear to Star Lvl {current_mastery + 1}",
                                            "cost": {"Forgehammer": req_hammers, "Mythic Piece": req_pieces}, "efficiency": eff, "saved": saved
                                        })

                            if not candidates:
                                break
                                
                            candidates.sort(key=lambda x: x["efficiency"], reverse=True)
                            winner = candidates[0]
                            
                            # Commit deduction transfers
                            for name, value in winner["cost"].items():
                                loop_wallet[name] -= value
                                
                            # Execute targeted state mutations
                            if winner["type"] == "charms":
                                loop_state_profile["charms"][winner["idx"]] += 1
                            elif winner["type"] == "gov":
                                loop_state_profile["gov"][winner["idx"]] += 1
                            elif winner["type"] == "hero_lvl" or winner["type"] == "hero_ascend":
                                loop_state_profile["hero_lvl"][winner["idx"]] += 1
                            elif winner["type"] == "hero_mastery":
                                loop_state_profile["hero_mastery"][winner["idx"]] += 1

                            cost_string = ", ".join([f"{v:,.0f}x {k}" for k, v in winner["cost"].items()])
                            current_roadmap.append({
                                "Execution Order": f"Step #{iteration}",
                                "Target Upgrade Recommended": winner["label"],
                                "Resource Allocation Required": cost_string,
                                "Combat Yield Multiplier Δ": f"+{winner['saved']:.1f} Surviving Troops"
                            })
                        
                        final_timeline_survival = run_isolated_simulation(loop_state_profile)
                        if final_timeline_survival > best_final_survival:
                            best_final_survival = final_timeline_survival
                            best_overall_roadmap = current_roadmap
                            best_wallet_remainder = loop_wallet

                    # Render outputs to the dashboard interface frames
                    if best_overall_roadmap:
                        st.success("🎯 Multi-Budget Execution Roadmap Compiled Successfully!")
                        if monotonicity_guard and budget_multipliers[0] < 1.0:
                            st.info("🛡️ **Monotonicity Guard Active:** Verified sub-budgets to guarantee pathing accuracy.")
                            
                        st.subheader("📋 Chronological Upgrade Action Blueprint")
                        st.dataframe(pd.DataFrame(best_overall_roadmap), hide_index=True, use_container_width=True)
                        
                        st.markdown("#### 👛 Remaining Asset Reserves After Processing")
                        rem_col1, rem_col2, rem_col3, rem_col4 = st.columns(4)
                        rem_col1.metric("Remaining XP Pool", f"{best_wallet_remainder['XP']:,.0f}")
                        rem_col2.metric("Remaining Forgehammers", f"{best_wallet_remainder['Forgehammer']:,.0f}")
                        rem_col3.metric("Remaining Mithril Blocks", f"{best_wallet_remainder['Mithril']:,.0f}")
                        rem_col4.metric("Remaining Mythic Pieces", f"{best_wallet_remainder['Mythic Piece']:,.0f}")
                    else:
                        st.error("❌ The algorithm was unable to process an upgrade link. Verify your input balances.")