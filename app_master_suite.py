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

def load_governor_gear_atlas():
    """
    Index 0 is 'None'. 
    Index 1 corresponds to 'Green 0★', Index 58 corresponds to 'Red T6 3★'.
    """
    gov_tier_names = ["None", "Green 0★", "Green 1★", "Blue 0★", "Blue 1★", "Blue 2★", "Blue 3★", "Purple 0★", "Purple 1★", "Purple 2★", "Purple 3★", "Purple T1 0★", "Purple T1 1★", "Purple T1 2★", "Purple T1 3★", "Gold 0★", "Gold 1★", "Gold 2★", "Gold 3★", "Gold T1 0★", "Gold T1 1★", "Gold T1 2★", "Gold T1 3★", "Gold T2 0★", "Gold T2 1★", "Gold T2 2★", "Gold T2 3★", "Gold T3 0★", "Gold T3 1★", "Gold T3 2★", "Gold T3 3★", "Red 0★", "Red 1★", "Red 2★", "Red 3★", "Red T1 0★", "Red T1 1★", "Red T1 2★", "Red T1 3★", "Red T2 0★", "Red T2 1★", "Red T2 2★", "Red T2 3★", "Red T3 0★", "Red T3 1★", "Red T3 2★", "Red T3 3★", "Red T4 0★", "Red T4 1★", "Red T4 2★", "Red T4 3★", "Red T5 0★", "Red T5 1★", "Red T5 2★", "Red T5 3★", "Red T6 0★", "Red T6 1★", "Red T6 2★", "Red T6 3★"]

    gov_costs_satin = [0, 1500, 3800, 7000, 9700, 1000, 1000, 1500, 1500, 6500, 8000, 10000, 11000, 13000, 15000, 22000, 23000, 25000, 26000, 28000, 30000, 32000, 35000, 38000, 43000, 45000, 48000, 60000, 70000, 80000, 90000, 108000, 114000, 121000, 128000, 154000, 163000, 173000, 183000, 220000, 233000, 247000, 264000, 288000, 302000, 317000, 333000, 358000, 384000, 403000, 423000, 451000, 479000, 507000, 535000, 548000, 565000, 582000, 599000]

    gov_costs_threads = [0, 15, 40, 70, 95, 10, 10, 15, 15, 65, 80, 95, 110, 130, 160, 220, 230, 250, 260, 280, 300, 320, 340, 360, 430, 460, 500, 600, 700, 800, 900, 1080, 1140, 1210, 1280, 1540, 1630, 1730, 1830, 2200, 2330, 2470, 2640, 2880, 3020, 3170, 3330, 3580, 3840, 4030, 4230, 4510, 4790, 5070, 5350, 5480, 5650, 5820, 5990]

    gov_costs_vision = [0, 0, 0, 0, 0, 45, 50, 60, 70, 40, 50, 60, 70, 85, 100, 40, 40, 45, 45, 45, 55, 55, 55, 55, 75, 80, 85, 120, 140, 160, 180, 220, 230, 240, 250, 300, 320, 340, 360, 430, 460, 490, 520, 570, 600, 630, 660, 720, 770, 810, 850, 910, 970, 1030, 1090, 1110, 1140, 1170, 1210]

    gov_stat_deltas = [0.0, 9.35, 3.40, 4.25, 4.25, 4.25, 4.25, 4.25, 2.89, 2.89, 2.89, 2.89, 2.89, 2.89, 2.89, 2.55, 2.55, 2.55, 2.55, 2.55, 2.55, 2.55, 2.55, 2.55, 2.55, 2.55, 2.55, 2.55, 2.55, 2.55, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.75, 2.75, 2.75, 2.75, 2.75, 2.75, 2.75, 2.75, 3.00, 3.00, 3.00, 3.00, 3.00, 3.00, 3.00, 3.00]

    gov_set_bonuses = [0.0, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.0, 5.0, 5.0, 6.0, 6.0, 6.0, 6.0, 7.0, 7.0, 7.0, 7.0, 8.0, 8.0, 8.0, 8.0, 9.0, 9.0, 9.0, 9.0, 10.0, 10.0, 10.0, 10.0, 12.0, 12.0, 12.0, 12.0, 14.0, 14.0, 14.0, 14.0, 16.5, 16.5, 16.5, 16.5, 19.5, 19.5, 19.5, 19.5, 23.0, 23.0, 23.0, 23.0, 26.5, 26.5, 26.5, 26.5, 30.0, 30.0, 30.0, 30.0]
    
    return {
        "names": gov_tier_names, "satin": gov_costs_satin, "threads": gov_costs_threads, 
        "vision": gov_costs_vision, "deltas": gov_stat_deltas, "set_bonuses": gov_set_bonuses
    }

def load_charm_cost_atlas():
    """
    Returns lists mapped exactly to Charm target levels 1 through 22.
    Index 0 is a placeholder so that index 1 = Level 1 costs, index 22 = Level 22 costs.
    """
    charm_guides =  [0, 5, 40, 60, 80, 100, 120, 140, 200, 300, 420, 560, 580, 610, 645, 685, 730, 780, 835, 895, 960, 1030, 1105]
    charm_designs = [0, 5, 15, 40, 100, 200, 300, 400, 400, 400, 420, 420, 600, 780, 960, 1140, 1320, 1500, 1680, 1860, 2040, 2220, 2400]
    stat_deltas =   [0.0, 9.0, 3.0, 4.0, 3.0, 6.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]
    
    return {"guides": charm_guides, "designs": charm_designs, "deltas": stat_deltas}

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
    st.session_state["authenticated"] = True
    st.session_state["joiner_filter_enabled"] = True

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
        col_desc1, col_desc2, col_desc3, col_desc4,col_desc5, col_desc6 = st.columns(6)
        with col_desc1:
            st.markdown("### Multi-Rally Simulator")
            st.write("Simulate consecutive rally waves hitting a fixed structure. Evaluates sequential attrition, troop depletion curves, and step-by-step win conditions.")
        with col_desc2:
            st.markdown("### Tactical Optimizer")
            st.write("Run brute-force grid searches across continuous loops to calculate best performance for troop compositions or optimal joiner heroes.")
        with col_desc3:
            st.markdown("### Stat Optimizer Engine")
            st.write("Isolate variables by injecting small stat changes. Calculates exactly how many fewer troop deaths an upgrade prevents to provide upgrade guidance.")
        with col_desc4:
            st.markdown("### Hero Gear Optimizer Engine")
            st.write("Input Hero Gear as well as upgrade material decide if you want to optimize your defense or attack. Input current stats and for your desired opponent. The optimizer then uses..." \
            "a greedy algorithm to determine which upgrade paths provide the best performance against the opponent ")
        with col_desc5:
            st.markdown("### Charm Optimizer Engine")
            st.write("Input Charms as well as upgrade material decide if you want to optimize your defense or attack. Input current stats and for your desired opponent. The optimizer then uses..." \
            "a greedy algorithm to determine which upgrade paths provide the best performance against the opponent ****uses the hero gear battle stats so update that ")
        with col_desc6:
            st.markdown("### Governor Gear Optimizer Engine")
            st.write("Input Governor gear as well as upgrade material decide if you want to optimize your defense or attack. Input current stats and for your desired opponent. The optimizer then uses..." \
            "a greedy algorithm to determine which upgrade paths provide the best performance against the opponent ****uses the hero gear battle stats so update that ")

# Replace your old tab layout row with this four-tab tuple:
    tab_sim, tab_opt, tab_roi, tab_gear, tab_charms, tab_gov, tab_manual = st.tabs([
        "Multi-Rally Simulator", 
        "Battle Optimizer", 
        "Stat Improvement Optimizer", 
        "Hero Gear Optimizer",
        "Charm Optimizer",
        "Governor Gear Optimizer",
        "User Manual"
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
    #     # =========================================================================
    # 

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
                                t_garrison = garrison_setup.clone()
                                t_waves = [wave.clone() for wave in rally_waves_input]
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
                                    tot_surv = sum(np.sum(kingshot_multirally_sim2([w.clone() for w in w_set], g_setup.clone())[0].troops) for _ in range(o_mc_runs))
                                    avg_surv = tot_surv / o_mc_runs
                                    results_grid.append({"Configuration": f"Inf: {r[0]*100:.0f}% | Cav: {r[1]*100:.0f}% | Arc: {r[2]*100:.0f}%", "Avg Survivors": avg_surv, "Rate": (avg_surv / o_g_total_troops) * 100})
                            
                            elif opt_side == "Garrison (Defenders)" and "Supporter Heroes" in opt_mode:
                                combos = list(itertools.combinations_with_replacement(opt_hero_pool, 4))
                                for combo in combos:
                                    g_setup = TroopSide([o_g_inf, o_g_cav, o_g_arc], np.array(o_g_combat_stats), [o_g_lead1, o_g_lead2, o_g_lead3], list(combo), o_g_tier, o_g_tg, o_g_widgets)
                                    w_set = build_waves_opt()
                                    tot_surv = sum(np.sum(kingshot_multirally_sim2([w.clone() for w in w_set], g_setup.clone())[0].troops) for _ in range(o_mc_runs))
                                    avg_surv = tot_surv / o_mc_runs
                                    results_grid.append({"Configuration": f"{', '.join(combo)}", "Avg Survivors": avg_surv, "Rate": (avg_surv / max(1, o_g_total_troops)) * 100})
                            
                            elif opt_side == "Attacker Waves (Rallies)" and "Troop Ratios" in opt_mode:
                                w1_cap = o_wave_configs[0]["capacity"]
                                g_setup = TroopSide([o_g_inf, o_g_cav, o_g_arc], np.array(o_g_combat_stats), [o_g_lead1, o_g_lead2, o_g_lead3], o_g_sup_heroes, o_g_tier, o_g_tg, o_g_widgets)
                                for r in ratio_grid:
                                    test_w1_troops = [w1_cap * r[0], w1_cap * r[1], w1_cap * r[2]]
                                    w_set = build_waves_opt(wave_1_override_troops=test_w1_troops)
                                    tot_surv = sum(np.sum(kingshot_multirally_sim2([w.clone() for w in w_set], g_setup.clone())[0].troops) for _ in range(o_mc_runs))
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
                                        final_g, logs = kingshot_multirally_sim2([w.clone() for w in w_set], g_setup.clone())
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
                                control_avg = sum(np.sum(kingshot_multirally_sim2([w.clone() for w in rally_waves_input], control_garrison.clone())[0].troops) for _ in range(r_mc_runs)) / r_mc_runs

                                
                                # Test adding our increment to every individual node
                                for label, row, col in stat_map:
                                    nudged_stats = copy.deepcopy(active_stats)
                                    nudged_stats[row][col] += step_size
                                    
                                    test_garrison = TroopSide([r_g_inf, r_g_cav, r_g_arc], np.array(nudged_stats), [r_g_lead1, r_g_lead2, r_g_lead3], r_g_sups, r_g_tier, r_g_tg, r_g_widgets)
                                    test_avg = sum(np.sum(kingshot_multirally_sim2([w.clone() for w in rally_waves_input], test_garrison.clone())[0].troops) for _ in range(r_mc_runs)) / r_mc_runs
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
        # =========================================================================
        # --- TAB 4: SURGICAL HERO GEAR OPTIMIZER ---
        # =========================================================================
    with tab_gear:
            st.header("🎯 Surgical Hero Gear Optimizer")
            st.caption("A granular, slot-specific optimizer that calculates exact combat ROI for Helm, Glove, Chest, and Boot upgrades.")

            # Establish global mapping databases for the execution run
            atlases = load_stat_atlases()
            
            # Ascension milestone requirements table: [Required Mastery, Required Mithril, Required Mythic Pieces]
            ascension_table = {
                100: [10, 0, 2],   # Mythic -> Red baseline transition
                120: [11, 10, 3],  # 100 -> 120 bracket step
                140: [12, 20, 5],  # 120 -> 140 bracket step
                160: [13, 30, 5],  # 140 -> 160 bracket step
                180: [14, 40, 10]  # 160 -> 180 bracket step
            }

            # -------------------------------------------------------------------------
            # --- COMBAT INTEGRATION CONFIG PANEL (FULL WIDTH) ---
            # -------------------------------------------------------------------------
            st.markdown("### ⚔️ Battle Context & Deployment Settings")
            st.caption("Configure the deployment profile and operational role to test your gear upgrades in a real match scenario.")

            role_col, prec_col = st.columns(2)
            with role_col:
                opt_role = st.radio(
                    "Target Optimization Strategy Role",
                    ["Rally Attacker", "Garrison Defender"],
                    help="Selects whether your hero gear upgrades are simulated as the attacking force or the defending wall garrison.",
                    horizontal=True,
                    key="g_opt_role"
                )
            with prec_col:
                mc_precision = st.slider("Greedy Search Pass Precision (Monte Carlo)", 10, 150, 40, step=10, key="g_precision_slider")

            # Layout containers for active army scaling parameters
            ctx_exp1, ctx_exp2 = st.columns(2)
            
            with ctx_exp1:
                st.markdown("#### 🏹 Your Deployment Profile")
                my_inf = st.number_input("Your Infantry Count", min_value=0, value=500000, step=50000, key="g_my_inf")
                my_cav = st.number_input("Your Cavalry Count", min_value=0, value=200000, step=50000, key="g_my_cav")
                my_arc = st.number_input("Your Archer Count", min_value=0, value=300000, step=50000, key="g_my_arc")
                
                st.markdown("**Your Active Hero Selection**")
                h_col1, h_col2, h_col3 = st.columns(3)
                my_h1 = h_col1.selectbox("Leader 1", ["Amadeus", "Hilde", "Marlin", "Petra", "Helga", "Saul", "None"], index=0, key="g_my_h1")
                my_h2 = h_col2.selectbox("Leader 2", ["Amadeus", "Hilde", "Marlin", "Petra", "Helga", "Saul", "None"], index=1, key="g_my_h2")
                my_h3 = h_col3.selectbox("Leader 3", ["Amadeus", "Hilde", "Marlin", "Petra", "Helga", "Saul", "None"], index=2, key="g_my_h3")
                
                with st.expander("Your Exact Battle Report Stats", expanded=True):
                    y_c1, y_c2, y_c3 = st.columns(3)
                    with y_c1:
                        my_ia = st.number_input("Inf Atk %", value=1400.0, key="g_my_ia")
                        my_id = st.number_input("Inf Def %", value=1100.0, key="g_my_id")
                        my_il = st.number_input("Inf Let %", value=1300.0, key="g_my_il")
                        my_ih = st.number_input("Inf HP %", value=1200.0, key="g_my_ih")
                    with y_c2:
                        my_ca = st.number_input("Cav Atk %", value=1300.0, key="g_my_ca")
                        my_cd = st.number_input("Cav Def %", value=1000.0, key="g_my_cd")
                        my_cl = st.number_input("Cav Let %", value=1200.0, key="g_my_cl")
                        my_ch = st.number_input("Cav HP %", value=1100.0, key="g_my_ch")
                    with y_c3:
                        my_aa = st.number_input("Arc Atk %", value=1450.0, key="g_my_aa")
                        my_ad = st.number_input("Arc Def %", value=1050.0, key="g_my_ad")
                        my_al = st.number_input("Arc Let %", value=1350.0, key="g_my_al")
                        my_ah = st.number_input("Arc HP %", value=1150.0, key="g_my_ah")

            with ctx_exp2:
                st.markdown("#### 🛡️ Rival Target Environment")
                opp_inf = st.number_input("Rival Infantry Count", min_value=0, value=600000, step=50000, key="g_opp_inf")
                opp_cav = st.number_input("Rival Cavalry Count", min_value=0, value=400000, step=50000, key="g_opp_cav")
                opp_arc = st.number_input("Rival Archer Count", min_value=0, value=400000, step=50000, key="g_opp_arc")
                
                st.markdown("**Rival Active Hero Selection**")
                oh_col1, oh_col2, oh_col3 = st.columns(3)
                opp_h1 = oh_col1.selectbox("Rival Leader 1", ["Amadeus", "Hilde", "Marlin", "Petra", "Helga", "Saul", "None"], index=0, key="g_opp_h1")
                opp_h2 = oh_col2.selectbox("Rival Leader 2", ["Amadeus", "Hilde", "Marlin", "Petra", "Helga", "Saul", "None"], index=1, key="g_opp_h2")
                opp_h3 = oh_col3.selectbox("Rival Leader 3", ["Amadeus", "Hilde", "Marlin", "Petra", "Helga", "Saul", "None"], index=2, key="g_opp_h3")
                
                with st.expander("Rival Exact Battle Report Stats", expanded=True):
                    o_c1, o_c2, o_c3 = st.columns(3)
                    with o_c1:
                        opp_ia = st.number_input("Inf Atk %", value=1300.0, key="g_opp_ia")
                        opp_id = st.number_input("Inf Def %", value=1100.0, key="g_opp_id")
                        opp_il = st.number_input("Inf Let %", value=1200.0, key="g_opp_il")
                        opp_ih = st.number_input("Inf HP %", value=1200.0, key="g_opp_ih")
                    with o_c2:
                        opp_ca = st.number_input("Cav Atk %", value=1250.0, key="g_opp_ca")
                        opp_cd = st.number_input("Cav Def %", value=1050.0, key="g_opp_cd")
                        opp_cl = st.number_input("Cav Let %", value=1150.0, key="g_opp_cl")
                        opp_ch = st.number_input("Cav HP %", value=1050.0, key="g_opp_ch")
                    with o_c3:
                        opp_aa = st.number_input("Arc Atk %", value=1350.0, key="g_opp_aa")
                        opp_ad = st.number_input("Arc Def %", value=1000.0, key="g_opp_ad")
                        opp_al = st.number_input("Arc Let %", value=1250.0, key="g_opp_al")
                        opp_ah = st.number_input("Arc HP %", value=1050.0, key="g_opp_ah")

            st.markdown("---")

            # -------------------------------------------------------------------------
            # --- INVENTORY & GEAR STATE COLUMNS ---
            # -------------------------------------------------------------------------
            g_main, g_side = st.columns([2, 1])

            with g_side:
                st.markdown("### 🎒 Your Asset Inventory")
                
                with st.expander("✨ Hero Gear XP Quantities", expanded=True):
                    green_books = st.number_input("10 XP Part (Green)", min_value=0, value=50, step=10, key="g_xp_green")
                    purple_books = st.number_input("100 XP Part (Purple)", min_value=0, value=15, step=5, key="g_xp_purple")
                    com_gear = st.number_input("Common Gear (10 XP)", min_value=0, value=20, key="g_xp_com")
                    uncom_gear = st.number_input("Uncommon Gear (30 XP)", min_value=0, value=10, key="g_xp_uncom")
                    rare_gear = st.number_input("Rare Gear (60 XP)", min_value=0, value=5, key="g_xp_rare")
                    epic_gear = st.number_input("Epic Gear (150 XP)", min_value=0, value=2, key="g_xp_epic")
                    
                    calculated_xp_pool = (green_books * 10) + (purple_books * 100) + (com_gear * 10) + (uncom_gear * 30) + (rare_gear * 60) + (epic_gear * 150)
                    st.info(f"**Total Available XP Reservoir:** {calculated_xp_pool:,.0f} XP")
                    
                with st.expander("🔨 Mastery & Ascension Forge Assets", expanded=True):
                    inv_hammers = st.number_input("Available Forgehammers", min_value=0, value=350, key="g_inv_hammers")
                    inv_mithril = st.number_input("Available Mithril", min_value=0, value=15, key="g_inv_mithril")
                    inv_mythic_pieces = st.number_input("Available Mythic Gear Duplicates", min_value=0, value=4, key="g_inv_pieces")

            with g_main:
                st.markdown("### 🏛️ Active Structural Profiles")
                monotonicity_guard = st.toggle("Engage Monotonicity Guard", value=True, key="g_mono_toggle")
                
                st.markdown("#### Granular Hero Gear States")
                
                def create_gear_slot_ui(slot_name, default_tier, default_lvl, default_mast, key_prefix):
                    """Helper function to cleanly generate UI for specific gear slots."""
                    st.markdown(f"**{slot_name}**")
                    tier = st.selectbox("Tier", ["Epic", "Mythic", "Red"], index=["Epic", "Mythic", "Red"].index(default_tier), key=f"{key_prefix}_t")
                    lvl = st.number_input("Enhance Lvl", 0, 200, default_lvl, key=f"{key_prefix}_l")
                    mast = st.number_input("Mastery", 0, 20, default_mast, key=f"{key_prefix}_m")
                    return {"tier": tier, "lvl": lvl, "mastery": mast}

                # 🛡️ INFANTRY BLOCK
                with st.expander("🛡️ Infantry Hero Gear", expanded=True):
                    i_c1, i_c2, i_c3, i_c4 = st.columns(4)
                    with i_c1: inf_helm = create_gear_slot_ui("Helm (Lethality)", "Mythic", 83, 4, "g_inf_helm")
                    with i_c2: inf_gloves = create_gear_slot_ui("Gloves (Health)", "Red", 120, 11, "g_inf_gloves")
                    with i_c3: inf_chest = create_gear_slot_ui("Chest (Health)", "Mythic", 100, 7, "g_inf_chest")
                    with i_c4: inf_boots = create_gear_slot_ui("Boots (Lethality)", "Mythic", 85, 5, "g_inf_boots")
                
                # 🏇 CAVALRY BLOCK
                with st.expander("🏇 Cavalry Hero Gear", expanded=True):
                    c_c1, c_c2, c_c3, c_c4 = st.columns(4)
                    with c_c1: cav_helm = create_gear_slot_ui("Helm (Lethality)", "Mythic", 87, 5, "g_cav_helm")
                    with c_c2: cav_gloves = create_gear_slot_ui("Gloves (Health)", "Mythic", 48, 1, "g_cav_gloves")
                    with c_c3: cav_chest = create_gear_slot_ui("Chest (Health)", "Mythic", 48, 1, "g_cav_chest")
                    with c_c4: cav_boots = create_gear_slot_ui("Boots (Lethality)", "Mythic", 87, 5, "g_cav_boots")
                
                # 🏹 ARCHER BLOCK
                with st.expander("🏹 Archer Hero Gear", expanded=True):
                    a_c1, a_c2, a_c3, a_c4 = st.columns(4)
                    with a_c1: arc_helm = create_gear_slot_ui("Helm (Lethality)", "Mythic", 84, 5, "g_arc_helm")
                    with a_c2: arc_gloves = create_gear_slot_ui("Gloves (Health)", "Mythic", 61, 2, "g_arc_gloves")
                    with a_c3: arc_chest = create_gear_slot_ui("Chest (Health)", "Mythic", 61, 2, "g_arc_chest")
                    with a_c4: arc_boots = create_gear_slot_ui("Boots (Lethality)", "Mythic", 87, 5, "g_arc_boots")

                st.markdown("---")
                
            if st.button("🚀 Execute Granular Hero Gear Optimization Pass", type="primary", use_container_width=True, key="g_run_pass_btn"):
                
                # --- UI PROGRESS INDICATORS ---
                st.info("⚙️ Initializing Heavy Monte Carlo Grid Search. This may take a minute...")
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Format baseline control configurations
                current_profile = {
                    "infantry": {"Helm": inf_helm, "Gloves": inf_gloves, "Chest": inf_chest, "Boots": inf_boots},
                    "cavalry": {"Helm": cav_helm, "Gloves": cav_gloves, "Chest": cav_chest, "Boots": cav_boots},
                    "archer": {"Helm": arc_helm, "Gloves": arc_gloves, "Chest": arc_chest, "Boots": arc_boots}
                }
                
                wallet = {
                    "XP": calculated_xp_pool, "Forgehammer": inv_hammers, "Mithril": inv_mithril,
                    "Mythic Piece": inv_mythic_pieces
                }
                
                def run_isolated_simulation(profile_state):
                    """Dynamically applies gear upgrades by isolating the stat delta and injecting it into raw battle report data."""
                    
                    # 1. Load exact battle report stats (These implicitly include your CURRENT gear)
                    my_stats_matrix = np.array([
                        [my_ia, my_id, my_il, my_ih], 
                        [my_ca, my_cd, my_cl, my_ch], 
                        [my_aa, my_ad, my_al, my_ah]
                    ])
                    
                    opp_stats_matrix = np.array([
                        [opp_ia, opp_id, opp_il, opp_ih],
                        [opp_ca, opp_cd, opp_cl, opp_ch],
                        [opp_aa, opp_ad, opp_al, opp_ah]
                    ])
                    
                    # 2. Select target matrix based on your operational role
                    target_matrix = my_stats_matrix if opt_role == "Rally Attacker" else opp_stats_matrix
                    active_profile = profile_state if opt_role == "Rally Attacker" else current_profile
                    
                    # 3. Strip Old Gear and Apply New Gear (Delta Method)
                    troop_keys = ["infantry", "cavalry", "archer"]
                    for r, troop in enumerate(troop_keys):
                        
                        # --- LETHALITY (Helms & Boots) ---
                        # Calculate the stats of the gear you are ALREADY wearing
                        curr_h_stat = get_hero_gear_stat(current_profile[troop]["Helm"]["tier"], current_profile[troop]["Helm"]["lvl"]) * 100.0
                        curr_h = curr_h_stat * (1.0 + (current_profile[troop]["Helm"]["mastery"] * 0.10))
                        curr_b_stat = get_hero_gear_stat(current_profile[troop]["Boots"]["tier"], current_profile[troop]["Boots"]["lvl"]) * 100.0
                        curr_b = curr_b_stat * (1.0 + (current_profile[troop]["Boots"]["mastery"] * 0.10))
                        
                        # Calculate the stats of the gear the optimizer is TESTING
                        test_h_stat = get_hero_gear_stat(active_profile[troop]["Helm"]["tier"], active_profile[troop]["Helm"]["lvl"]) * 100.0
                        test_h = test_h_stat * (1.0 + (active_profile[troop]["Helm"]["mastery"] * 0.10))
                        test_b_stat = get_hero_gear_stat(active_profile[troop]["Boots"]["tier"], active_profile[troop]["Boots"]["lvl"]) * 100.0
                        test_b = test_b_stat * (1.0 + (active_profile[troop]["Boots"]["mastery"] * 0.10))
                        
                        # Apply the exact delta (- Old, + New) to the Battle Report Lethality
                        target_matrix[r, 2] = target_matrix[r, 2] - (curr_h + curr_b) + (test_h + test_b)
                        
                        # --- HEALTH (Gloves & Chests) ---
                        curr_g_stat = get_hero_gear_stat(current_profile[troop]["Gloves"]["tier"], current_profile[troop]["Gloves"]["lvl"]) * 100.0
                        curr_g = curr_g_stat * (1.0 + (current_profile[troop]["Gloves"]["mastery"] * 0.10))
                        curr_c_stat = get_hero_gear_stat(current_profile[troop]["Chest"]["tier"], current_profile[troop]["Chest"]["lvl"]) * 100.0
                        curr_c = curr_c_stat * (1.0 + (current_profile[troop]["Chest"]["mastery"] * 0.10))
                        
                        test_g_stat = get_hero_gear_stat(active_profile[troop]["Gloves"]["tier"], active_profile[troop]["Gloves"]["lvl"]) * 100.0
                        test_g = test_g_stat * (1.0 + (active_profile[troop]["Gloves"]["mastery"] * 0.10))
                        test_c_stat = get_hero_gear_stat(active_profile[troop]["Chest"]["tier"], active_profile[troop]["Chest"]["lvl"]) * 100.0
                        test_c = test_c_stat * (1.0 + (active_profile[troop]["Chest"]["mastery"] * 0.10))
                        
                        # Apply the exact delta (- Old, + New) to the Battle Report Health
                        target_matrix[r, 3] = target_matrix[r, 3] - (curr_g + curr_c) + (test_g + test_c)

                    # 4. Assemble dynamic TroopSide elements
                    my_march = TroopSide([my_inf, my_cav, my_arc], my_stats_matrix, [my_h1, my_h2, my_h3], ["None"]*4)
                    opp_march = TroopSide([opp_inf, opp_cav, opp_arc], opp_stats_matrix, [opp_h1, opp_h2, opp_h3], ["None"]*4)
                    
                    attacker_side = my_march if opt_role == "Rally Attacker" else opp_march
                    defender_side = opp_march if opt_role == "Rally Attacker" else my_march
                    
                    total_surviving_target = 0
                    for _ in range(mc_precision):
                        res = kingshot_multirally_sim2([attacker_side.clone()], defender_side.clone())
                        if opt_role == "Rally Attacker":
                            total_surviving_target += np.sum(res[1][0]['attacker_surviving'])
                        else:
                            total_surviving_target += np.sum(res[0].troops)
                            
                    return total_surviving_target / mc_precision

# --- MULTI-BUDGET LOGIC TETHERING ---
                budget_multipliers = [1.0, 0.90, 0.80] if monotonicity_guard else [1.0]
                best_overall_roadmap = []
                best_final_survival = -1
                best_wallet_remainder = {}
                best_final_profile = {}
                best_piece_costs = {}

                # Capture absolute maximums for Percentage Normalization
                max_budget = {
                    "XP": max(1, calculated_xp_pool), 
                    "Forgehammer": max(1, inv_hammers), 
                    "Mithril": max(1, inv_mithril), 
                    "Mythic Piece": max(1, inv_mythic_pieces)
                }
                
                def calculate_normalized_efficiency(saved_troops, cost_dict, is_red_gear=False):
                    """Calculates value based on the % of total budget used, applying a 10x penalty to irreversible resources."""
                    budget_used_pct = 0.0
                    for item, amount in cost_dict.items():
                        pct = amount / max_budget[item]
                        # Apply 10x penalty to irreversible resources (Hammers, Mithril, Pieces, or Red XP)
                        if item in ["Forgehammer", "Mithril", "Mythic Piece"] or (item == "XP" and is_red_gear):
                            pct *= 10.0
                        budget_used_pct += pct
                    
                    pct_used = max(0.0001, budget_used_pct * 100.0)
                    return saved_troops / pct_used

                # Calculate total steps for the progress bar
                total_ops = len(budget_multipliers) * 15
                ops_completed = 0

                for b_idx, budget_mod in enumerate(budget_multipliers):
                    loop_wallet = {k: int(v * budget_mod) for k, v in wallet.items()}
                    loop_state_profile = copy.deepcopy(current_profile)
                    current_roadmap = []
                    piece_costs = {t: {s: {} for s in ["Helm", "Gloves", "Chest", "Boots"]} for t in ["infantry", "cavalry", "archer"]}
                    
                    for iteration in range(1, 16):  # Computes chronological upgrade chains up to 15 actions out
                        
                        # --- UPDATE UI DYNAMICALLY ---
                        status_text.markdown(f"**🔍 Analyzing Grid Path {b_idx + 1}/{len(budget_multipliers)} | Simulating Optimal Upgrade Move #{iteration}...**")
                        
                        control_surv = run_isolated_simulation(loop_state_profile)
                        candidates = []
                        
                        # --- SCAN HERO GEAR ENHANCEMENTS AND BRACKET GATES ---
                        for troop in ["infantry", "cavalry", "archer"]:
                            for slot in ["Helm", "Gloves", "Chest", "Boots"]:
                                current_lvl = loop_state_profile[troop][slot]["lvl"]
                                current_tier = loop_state_profile[troop][slot]["tier"]
                                current_mastery = loop_state_profile[troop][slot]["mastery"]
                                
                                if current_lvl in ascension_table:
                                    # Target piece hits a gated threshold boundary line
                                    req_mastery, req_mithril, req_mythic_pieces = ascension_table[current_lvl]
                                    if current_mastery >= req_mastery:
                                        if loop_wallet["Mithril"] >= req_mithril and loop_wallet["Mythic Piece"] >= req_mythic_pieces:
                                            test_profile = copy.deepcopy(loop_state_profile)
                                            test_profile[troop][slot]["lvl"] += 1
                                            if current_lvl == 100 and current_tier == "Mythic":
                                                test_profile[troop][slot]["tier"] = "Red"
                                                
                                                test_surv = run_isolated_simulation(test_profile)
                                                saved = max(0.001, test_surv - control_surv)
                                                costs = {"Mithril": req_mithril, "Mythic Piece": req_mythic_pieces}
                                                eff = calculate_normalized_efficiency(saved, costs, is_red_gear=True)
                                                candidates.append({
                                                    "type": "hero_ascend", "troop": troop, "slot": slot, "label": f"🔺 Ascend {troop.capitalize()} {slot} past Lvl {current_lvl} gate",
                                                    "cost": costs, "efficiency": eff, "saved": saved
                                                })
                                else:
                                    # Regular incremental level processing loop
                                    req_xp = calculate_hero_gear_xp_cost(current_lvl)
                                    if loop_wallet["XP"] >= req_xp and current_lvl < 200:
                                            test_profile = copy.deepcopy(loop_state_profile)
                                            test_profile[troop][slot]["lvl"] += 1
                                            test_surv = run_isolated_simulation(test_profile)
                                            saved = max(0.001, test_surv - control_surv)
                                            costs = {"XP": req_xp}
                                            eff = calculate_normalized_efficiency(saved, costs, is_red_gear=(current_lvl >= 100))
                                            candidates.append({
                                                "type": "hero_lvl", "troop": troop, "slot": slot, "label": f"Enhance {troop.capitalize()} {slot} to Lvl {current_lvl + 1} ({current_tier})",
                                                "cost": costs, "efficiency": eff, "saved": saved
                                            })

                        # --- SCAN MASTERY FORGE STEPS ---
                        for troop in ["infantry", "cavalry", "archer"]:
                            for slot in ["Helm", "Gloves", "Chest", "Boots"]:
                                current_mastery = loop_state_profile[troop][slot]["mastery"]
                                if current_mastery < 20:
                                    req_hammers = (current_mastery + 1) * 10
                                    req_pieces = max(0, current_mastery - 9)
                                    
                                    if loop_wallet["Forgehammer"] >= req_hammers and loop_wallet["Mythic Piece"] >= req_pieces:
                                            test_profile = copy.deepcopy(loop_state_profile)
                                            test_profile[troop][slot]["mastery"] += 1
                                            test_surv = run_isolated_simulation(test_profile)
                                            saved = max(0.001, test_surv - control_surv)
                                            costs = {"Forgehammer": req_hammers, "Mythic Piece": req_pieces}
                                            eff = calculate_normalized_efficiency(saved, costs)
                                            candidates.append({
                                                "type": "hero_mastery", "troop": troop, "slot": slot, "label": f"⭐ Mastery Forge {troop.capitalize()} {slot} to Star Lvl {current_mastery + 1}",
                                                "cost": costs, "efficiency": eff, "saved": saved
                                            })

                        # Increment Progress Bar
                        ops_completed += 1
                        progress_bar.progress(min(1.0, ops_completed / total_ops))

                        if not candidates:
                            # If no more upgrades are possible, fast-forward the progress bar for the skipped steps
                            remaining_steps = 16 - iteration
                            ops_completed += remaining_steps
                            progress_bar.progress(min(1.0, ops_completed / total_ops))
                            break
                            
                        candidates.sort(key=lambda x: x["efficiency"], reverse=True)
                        winner = candidates[0]
                        
                        # Commit deduction transfers AND track costs per item
                        for name, value in winner["cost"].items():
                            loop_wallet[name] -= value
                            piece_costs[winner["troop"]][winner["slot"]][name] = piece_costs[winner["troop"]][winner["slot"]].get(name, 0) + value
                            
                        # Execute targeted state mutations
                        if winner["type"] == "hero_lvl" or winner["type"] == "hero_ascend":
                            loop_state_profile[winner["troop"]][winner["slot"]]["lvl"] += 1
                        elif winner["type"] == "hero_mastery":
                            loop_state_profile[winner["troop"]][winner["slot"]]["mastery"] += 1

                        current_roadmap.append(winner)
                    
                    final_timeline_survival = run_isolated_simulation(loop_state_profile)
                    if final_timeline_survival > best_final_survival:
                        best_final_survival = final_timeline_survival
                        best_overall_roadmap = current_roadmap
                        best_wallet_remainder = loop_wallet
                        best_final_profile = copy.deepcopy(loop_state_profile)
                        best_piece_costs = copy.deepcopy(piece_costs)

                # Clean up the UI indicators once finished
                progress_bar.empty()
                status_text.empty()

                

                    # Render outputs to the dashboard interface frames
                if best_overall_roadmap:
                        st.success("🎯 Multi-Budget Execution Roadmap Compiled Successfully!")
                        if monotonicity_guard and budget_multipliers[0] < 1.0:
                            st.info("🛡️ **Monotonicity Guard Active:** Verified sub-budgets to guarantee pathing accuracy.")
                            
                        # --- CONSTRUCT GROUPED OUTPUT TABLE ---
                        grouped_data = []
                        stat_type_map = {"Helm": "Lethality", "Gloves": "Health", "Chest": "Health", "Boots": "Lethality"}
                        
                        for troop in ["infantry", "cavalry", "archer"]:
                            for slot in ["Helm", "Gloves", "Chest", "Boots"]:
                                old_state = current_profile[troop][slot]
                                new_state = best_final_profile[troop][slot]
                                
                                if old_state != new_state: # Something changed on this specific piece
                                    lvl_change = f"{old_state['lvl']} ➔ {new_state['lvl']}" if old_state['lvl'] != new_state['lvl'] else "—"
                                    mast_change = f"{old_state['mastery']} ➔ {new_state['mastery']}" if old_state['mastery'] != new_state['mastery'] else "—"
                                    tier_change = f"{old_state['tier']} ➔ {new_state['tier']}" if old_state['tier'] != new_state['tier'] else "—"
                                    
                                    # Calculate Exact Stat Gain Delta
                                    old_base = get_hero_gear_stat(old_state['tier'], old_state['lvl']) * 100.0
                                    old_final = old_base * (1.0 + (old_state['mastery'] * 0.10))
                                    
                                    new_base = get_hero_gear_stat(new_state['tier'], new_state['lvl']) * 100.0
                                    new_final = new_base * (1.0 + (new_state['mastery'] * 0.10))
                                    
                                    stat_gain = f"+{(new_final - old_final):.2f}%"
                                    
                                    # Format Cost String
                                    costs = best_piece_costs[troop][slot]
                                    cost_str = ", ".join([f"+{v:,.0f} {k}" for k, v in costs.items()])
                                    
                                    grouped_data.append({
                                        "Gear Piece": f"{troop.capitalize()} {slot} ({stat_type_map[slot]})",
                                        "Tier Change": tier_change,
                                        "Level Change": lvl_change,
                                        "Mastery Change": mast_change,
                                        "Total Cost": cost_str,
                                        "Stat Gain": stat_gain
                                    })

                        st.subheader("📋 Consolidated Gear Upgrade Plan")
                        st.dataframe(pd.DataFrame(grouped_data), hide_index=True, use_container_width=True)
                        
                        st.markdown("#### 👛 Remaining Asset Reserves After Processing")
                        rem_col1, rem_col2, rem_col3, rem_col4 = st.columns(4)
                        rem_col1.metric("Remaining XP Pool", f"{best_wallet_remainder['XP']:,.0f}")
                        rem_col2.metric("Remaining Forgehammers", f"{best_wallet_remainder['Forgehammer']:,.0f}")
                        rem_col3.metric("Remaining Mithril Blocks", f"{best_wallet_remainder['Mithril']:,.0f}")
                        rem_col4.metric("Remaining Mythic Pieces", f"{best_wallet_remainder['Mythic Piece']:,.0f}")
                else:
                        st.error("❌ The algorithm was unable to process an upgrade link. Verify your input balances.")

# =========================================================================
    # --- TAB 5: SURGICAL CHARMS OPTIMIZER ---
    # =========================================================================
    with tab_charms:
        st.header("⚡ Surgical Charms Optimizer")
        st.caption("Optimizes all 18 charm slots dynamically using direct Monte Carlo simulation output squared against item scarcity.")

        charm_atlas = load_charm_cost_atlas()

        # -------------------------------------------------------------------------
        # --- INVENTORY & SIDE CONFIG PANEL ---
        # -------------------------------------------------------------------------
        c_main, c_side = st.columns([2, 1])

        with c_side:
            st.markdown("### 🎒 Charm Asset Inventory")
            inv_guides = st.number_input("Available Charm Guides", min_value=0, value=2500, step=100, key="ch_inv_guides")
            inv_designs = st.number_input("Available Charm Designs", min_value=0, value=300, step=25, key="ch_inv_designs")
            
            st.markdown("---")
            st.markdown("### ⚙️ Search Precision")
            ch_precision = st.slider("Monte Carlo Pass Precision", 10, 150, 40, step=10, key="ch_precision_slider")
            max_actions = st.number_input("Max Upgrades to Map", min_value=1, max_value=30, value=10, step=1)

        with c_main:
            st.markdown("### 🔮 Current Charm Levels (0 - 22)")
            
            # Group Charms logically into 3 Troop columns
            ch_col1, ch_col2, ch_col3 = st.columns(3)
            
            current_charms = {"infantry": [], "cavalry": [], "archer": []}
            
            with ch_col1:
                st.markdown("#### 🛡️ Infantry Charms")
                for i in range(6):
                    # Changed min_value to 0 to support un-forged empty slots
                    lvl = st.number_input(f"Infantry Slot #{i+1}", min_value=0, max_value=22, value=5, step=1, key=f"ch_inf_{i}")
                    current_charms["infantry"].append(lvl)
                    
            with ch_col2:
                st.markdown("#### 🏇 Cavalry Charms")
                for i in range(6):
                    lvl = st.number_input(f"Cavalry Slot #{i+1}", min_value=0, max_value=22, value=4, step=1, key=f"ch_cav_{i}")
                    current_charms["cavalry"].append(lvl)
                    
            with ch_col3:
                st.markdown("#### 🏹 Archer Charms")
                for i in range(6):
                    lvl = st.number_input(f"Archer Slot #{i+1}", min_value=0, max_value=22, value=4, step=1, key=f"ch_arc_{i}")
                    current_charms["archer"].append(lvl)

            st.markdown("---")
            
            if st.button("🚀 Execute Combat-Driven Charms Optimization", type="primary", use_container_width=True, key="ch_run_btn"):
                ch_progress = st.progress(0)
                ch_status = st.empty()
                
                # Snapshot wallets
                ch_wallet = {"Guides": inv_guides, "Designs": inv_designs}
                running_charms = copy.deepcopy(current_charms)
                charms_roadmap = []
                
                # Tracking accumulation matrix per charm slot to consolidate output
                accumulated_gains = {t: [0.0 for _ in range(6)] for t in ["infantry", "cavalry", "archer"]}
                accumulated_costs = {t: [{"Guides": 0, "Designs": 0} for _ in range(6)] for t in ["infantry", "cavalry", "archer"]}
                starting_levels = copy.deepcopy(current_charms)

                def run_charm_isolated_simulation(charm_state):
                    """Injects the baseline battle report stats modified by the running charm configurations."""
                    my_stats_matrix = np.array([
                        [my_ia, my_id, my_il, my_ih], 
                        [my_ca, my_cd, my_cl, my_ch], 
                        [my_aa, my_ad, my_al, my_ah]
                    ])
                    opp_stats_matrix = np.array([
                        [opp_ia, opp_id, opp_il, opp_ih],
                        [opp_ca, opp_cd, opp_cl, opp_ch],
                        [opp_aa, opp_ad, opp_al, opp_ah]
                    ])
                    
                    target_matrix = my_stats_matrix if opt_role == "Rally Attacker" else opp_stats_matrix
                    
                    # Add Charm stat values onto the battle matrix baseline
                    for r, troop in enumerate(["infantry", "cavalry", "archer"]):
                        total_stat_pct = 0.0
                        for lvl in charm_state[troop]:
                            # Slice sums up all cumulative stats up to the current level
                            total_stat_pct += sum(charm_atlas["deltas"][:lvl+1])
                        
                        # Charms uniformly increase both Lethality (Col 2) and Health (Col 3)
                        target_matrix[r, 2] += total_stat_pct
                        target_matrix[r, 3] += total_stat_pct

                    my_march = TroopSide([my_inf, my_cav, my_arc], my_stats_matrix, [my_h1, my_h2, my_h3], ["None"]*4)
                    opp_march = TroopSide([opp_inf, opp_cav, opp_arc], opp_stats_matrix, [opp_h1, opp_h2, opp_h3], ["None"]*4)
                    
                    attacker_side = my_march if opt_role == "Rally Attacker" else opp_march
                    defender_side = opp_march if opt_role == "Rally Attacker" else my_march
                    
                    total_surviving_target = 0
                    for _ in range(ch_precision):
                        res = kingshot_multirally_sim2([attacker_side.clone()], defender_side.clone())
                        total_surviving_target += np.sum(res[1][0]['attacker_surviving']) if opt_role == "Rally Attacker" else np.sum(res[0].troops)
                            
                    return total_surviving_target / ch_precision

                # -------------------------------------------------------------------------
                # --- GREEDY SEARCH LOOP WITH SQUARED SCARCITY SCORING ---
                # -------------------------------------------------------------------------
                for action_step in range(1, max_actions + 1):
                    ch_status.markdown(f"**🔍 Calculating Optimal Charm Progression Step #{action_step}...**")
                    
                    control_surv = run_charm_isolated_simulation(running_charms)
                    candidates = []
                    
                    # Squared Scarcity Weight calculations based on current wallets
                    g_pool = max(1, ch_wallet["Guides"])
                    d_pool = max(1, ch_wallet["Designs"])
                    
                    w_guides = 1.0 / (g_pool ** 2)
                    w_designs = 1.0 / (d_pool ** 2)

                    for troop in ["infantry", "cavalry", "archer"]:
                        for slot_idx, current_lvl in enumerate(running_charms[troop]):
                            if current_lvl >= 22:
                                continue # Max level cap boundary reached
                                
                            target_lvl = current_lvl + 1
                            req_g = charm_atlas["guides"][target_lvl]
                            req_d = charm_atlas["designs"][target_lvl]
                            
                            if ch_wallet["Guides"] >= req_g and ch_wallet["Designs"] >= req_d:
                                # Clone profile and nudge slot
                                test_charms = copy.deepcopy(running_charms)
                                test_charms[troop][slot_idx] += 1
                                
                                test_surv = run_charm_isolated_simulation(test_charms)
                                troops_saved = max(0.001, test_surv - control_surv)
                                
                                # Apply Squared Scarcity cost weighting denominator
                                resource_score = (req_g * w_guides) + (req_d * w_designs)
                                efficiency = troops_saved / max(1e-9, resource_score)
                                
                                candidates.append({
                                    "troop": troop, "slot": slot_idx, "next_lvl": target_lvl,
                                    "cost_g": req_g, "cost_d": req_d, "efficiency": efficiency, "saved": troops_saved
                                })

                    if not candidates:
                        ch_progress.progress(1.0)
                        break
                        
                    # Choose step winner
                    candidates.sort(key=lambda x: x["efficiency"], reverse=True)
                    winner = candidates[0]
                    
                    # Deduct assets from loop wallet
                    ch_wallet["Guides"] -= winner["cost_g"]
                    ch_wallet["Designs"] -= winner["cost_d"]
                    
                    # Mutate loop states
                    running_charms[winner["troop"]][winner["slot"]] += 1
                    
                    # Accumulate tracking arrays for consolidated output mapping
                    lvl_idx = winner["next_lvl"]
                    stat_gain_amt = charm_atlas["deltas"][lvl_idx]
                    
                    accumulated_gains[winner["troop"]][winner["slot"]] += stat_gain_amt
                    accumulated_costs[winner["troop"]][winner["slot"]]["Guides"] += winner["cost_g"]
                    accumulated_costs[winner["troop"]][winner["slot"]]["Designs"] += winner["cost_d"]
                    
                    charms_roadmap.append(winner)
                    ch_progress.progress(action_step / max_actions)

                ch_progress.empty()
                ch_status.empty()

                # -------------------------------------------------------------------------
                # --- CONSOLIDATE AND DISPLAY FINAL BLUEPRINT ---
                # -------------------------------------------------------------------------
                if charms_roadmap:
                    st.success("🎯 Optimal Charm Allocation Roadmap Compiled Successfully!")
                    
                    consolidated_rows = []
                    for troop in ["infantry", "cavalry", "archer"]:
                        for slot_idx in range(6):
                            start_l = starting_levels[troop][slot_idx]
                            end_l = running_charms[troop][slot_idx]
                            
                            if start_l != end_l:
                                costs = accumulated_costs[troop][slot_idx]
                                cost_display = f"+{costs['Guides']:,} Guides, +{costs['Designs']:,} Designs"
                                stat_gain = accumulated_gains[troop][slot_idx]
                                
                                consolidated_rows.append({
                                    "Charm Piece Target": f"{troop.capitalize()} Charm Slot #{slot_idx + 1}",
                                    "Level Transition": f"Level {start_l} ➔ {end_l}",
                                    "Total Resource Allocation Required": cost_display,
                                    "Stat Gain Yield (Lethality & HP)": f"+{stat_gain:.2f}%"
                                })
                                
                    st.subheader("📋 Consolidated Charm Upgrade Action Plan")
                    if consolidated_rows:
                        st.dataframe(pd.DataFrame(consolidated_rows), hide_index=True, use_container_width=True)
                    else:
                        st.info("No level transitions occurred. Upgrades analyzed were outvalued by core budget limits.")
                        
                    st.markdown("#### 👛 Remaining Asset Reserves After Processing")
                    r_ch1, r_ch2 = st.columns(2)
                    r_ch1.metric("Remaining Charm Guides", f"{ch_wallet['Guides']:,}")
                    r_ch2.metric("Remaining Charm Designs", f"{ch_wallet['Designs']:,}")
                else:
                    st.error("❌ The algorithm was unable to calculate an upgrade link. Verify your input balances or max upgrade constraints.")

                    # =========================================================================
    # --- TAB 6: GOVERNOR GEAR OPTIMIZER ---
    # =========================================================================
    with tab_gov:
        st.header("👑 Governor Gear Optimizer")
        st.caption("Calculates exact ROI across all 58 tiers, automatically factoring in Cumulative Set Bonuses and multi-resource bottlenecks.")

        gov_atlas = load_governor_gear_atlas()
        gov_names = gov_atlas["names"]

        # -------------------------------------------------------------------------
        # --- INVENTORY & SIDE CONFIG PANEL ---
        # -------------------------------------------------------------------------
        gv_main, gv_side = st.columns([2, 1])
        with gv_side:
            st.markdown("### 🎒 Governor Assets")
            inv_satin = st.number_input("Available Satin", min_value=0, value=25000, step=1000, key="gv_inv_satin")
            inv_threads = st.number_input("Available Gilded Threads", min_value=0, value=1200, step=50, key="gv_inv_threads")
            inv_vision = st.number_input("Available Artisan's Vision", min_value=0, value=250, step=10, key="gv_inv_vision")
            
            st.markdown("---")
            st.markdown("### ⚙️ Search Engine")
            gv_precision = st.slider("MC Pass Precision", 10, 150, 40, step=10, key="gv_precision_slider")
            gv_max_actions = st.number_input("Max Tiers to Map", min_value=1, max_value=20, value=6, step=1)

        with gv_main:
            st.markdown("### 📸 Auto-Scanner & Gear Assignment")
            st.caption("Upload a screenshot to auto-populate Governor Gear tiers and Charm levels simultaneously.")
            
            def apply_gov_inputs():
                """
                Callback function executed BEFORE the UI renders.
                Implements a custom PIL + EasyOCR computer vision pipeline.
                """
                from PIL import Image
                import numpy as np
                
                # Check if a screenshot was uploaded
                if st.session_state.get("gov_screenshot_uploader") is not None:
                    try:
                        # 1. Fetch our globally cached EasyOCR reader and process the image
                        reader = load_ocr_reader()
                        img = Image.open(st.session_state["gov_screenshot_uploader"]).convert('RGB')
                        img_np = np.array(img)
                        h, w = img_np.shape[:2]
                        
                        # 2. Define relative coordinate bounding boxes based on the mobile layout
                        # Dictionary maps: [Y_start, Y_end, X_start, X_end] as percentages
                        bboxes = {
                            "cav": {"0": (0.20, 0.32, 0.15, 0.38), "1": (0.20, 0.32, 0.62, 0.85)},
                            "inf": {"0": (0.45, 0.57, 0.15, 0.38), "1": (0.45, 0.57, 0.62, 0.85)},
                            "arc": {"0": (0.68, 0.80, 0.15, 0.38), "1": (0.68, 0.80, 0.62, 0.85)}
                        }
                        
                        for troop in ['cav', 'inf', 'arc']:
                            for piece in ["0", "1"]:
                                y1, y2, x1, x2 = bboxes[troop][piece]
                                
                                # Crop the specific gear piece and the charms strip directly below it
                                gear_crop = img_np[int(y1*h):int(y2*h), int(x1*w):int(x2*w)]
                                charm_crop = img_np[int(y2*h):int((y2+0.05)*h), int(x1*w):int(x2*w)]
                                
                                # --- STEP A: DETECT GEAR TIER VIA RGB SAMPLING ---
                                # Sample the top-left corner to get the pure background color
                                corner = gear_crop[0:15, 0:15] 
                                r, g, b = corner.mean(axis=(0,1))
                                
                                tier = "Gold" # Safe default
                                if r > 160 and g < 100 and b < 100: tier = "Red"
                                elif r > 150 and g > 120 and b < 100: tier = "Gold"
                                elif r > 100 and g < 100 and b > 130: tier = "Purple"
                                elif b > 130 and r < 100: tier = "Blue"
                                elif g > 130 and r < 130 and b < 130: tier = "Green"
                                
                                # --- STEP B: DETECT MASTERY VIA YELLOW PIXEL DENSITY ---
                                # Crop the bottom-left quadrant where the stars are located
                                gh, gw = gear_crop.shape[:2]
                                bl_corner = gear_crop[int(gh*0.6):, 0:int(gw*0.5)]
                                # Identify yellow pixels (High Red & Green, Low Blue)
                                yellow_mask = (bl_corner[:,:,0] > 180) & (bl_corner[:,:,1] > 150) & (bl_corner[:,:,2] < 100)
                                yellow_pixels = np.sum(yellow_mask)
                                
                                stars = 0
                                if yellow_pixels > 200: stars = 3
                                elif yellow_pixels > 100: stars = 2
                                elif yellow_pixels > 30: stars = 1
                                
                                # Construct the string and map it to the exact index in your atlas
                                target_name = f"{tier} {stars}★"
                                if target_name in gov_names:
                                    st.session_state[f"gv_{troop}_{piece}"] = gov_names.index(target_name)
                                    
                                # --- STEP C: OCR CHARM EXTRACTION ---
                                # Feed the cropped strip to EasyOCR looking strictly for numbers
                                results = reader.readtext(charm_crop, allowlist='0123456789')
                                results.sort(key=lambda x: x[0][0][0]) # Sort Left to Right physically
                                
                                charm_lvls = []
                                for bbox_res, text, prob in results:
                                    if text.isdigit() and 0 <= int(text) <= 22:
                                        charm_lvls.append(int(text))
                                
                                # If the image is blurry and OCR misses a charm, pad it with a safe default
                                while len(charm_lvls) < 3:
                                    charm_lvls.append(4) 
                                    
                                # Route the 3 charm levels into the 6 available slots per troop type
                                offset = 0 if piece == "0" else 3
                                st.session_state[f"ch_{troop}_{offset}"] = charm_lvls[0]
                                st.session_state[f"ch_{troop}_{offset+1}"] = charm_lvls[1]
                                st.session_state[f"ch_{troop}_{offset+2}"] = charm_lvls[2]

                        st.session_state["gov_toast"] = "📸 Computer Vision extraction complete! Successfully mapped Tier colors, Mastery stars, and Charm layouts."
                    except Exception as e:
                        st.session_state["gov_toast"] = f"⚠️ Image processing error: {e}"
                else:
                    # GLOBAL DROPDOWN APPLY
                    global_tier = st.session_state.get("gv_global_set")
                    if global_tier in gov_names:
                        target_idx = gov_names.index(global_tier)
                        for troop in ['inf', 'cav', 'arc']:
                            for piece in [0, 1]:
                                st.session_state[f"gv_{troop}_{piece}"] = target_idx
                        st.session_state["gov_toast"] = f"✅ Globally applied {global_tier} to all slots."

            # --- UI: Top Action Row (Matches Kingshot Optimizer Layout) ---
            act_c1, act_c2, act_c3 = st.columns([1.5, 2, 1.5])
            with act_c1:
                st.selectbox("Set all to:", gov_names, index=15, key="gv_global_set")
            with act_c2:
                # Key is required here to access the file in the callback
                st.file_uploader("Upload screenshot", type=["png", "jpg", "jpeg"], label_visibility="collapsed", key="gov_screenshot_uploader")
            with act_c3:
                # on_click safely alters session state before the inputs are redrawn
                st.button("Apply to Inputs", type="primary", use_container_width=True, on_click=apply_gov_inputs)
                
            # Fire the toast notification if the callback set one
            if "gov_toast" in st.session_state:
                st.toast(st.session_state["gov_toast"])
                del st.session_state["gov_toast"]

            st.markdown("---")
            
            # --- UI: 2-Column Card Grid (Matches Kingshot Optimizer Layout) ---
            current_gov = {"infantry": [], "cavalry": [], "archer": []}
            
            # Row 1: Cavalry (Top in game UI)
            row1_c1, row1_c2 = st.columns(2)
            with row1_c1:
                with st.container(border=True):
                    st.markdown("🏇 **Cavalry 1**")
                    lvl_0 = st.selectbox("Tier", range(len(gov_names)), format_func=lambda x: gov_names[x], key="gv_cav_0", label_visibility="collapsed")
                    stat_val = sum(gov_atlas["deltas"][:lvl_0+1])
                    st.caption(f"Current Stat: {stat_val:.2f}%")
            with row1_c2:
                with st.container(border=True):
                    st.markdown("🏇 **Cavalry 2**")
                    lvl_1 = st.selectbox("Tier", range(len(gov_names)), format_func=lambda x: gov_names[x], key="gv_cav_1", label_visibility="collapsed")
                    stat_val = sum(gov_atlas["deltas"][:lvl_1+1])
                    st.caption(f"Current Stat: {stat_val:.2f}%")
            current_gov["cavalry"] = [lvl_0, lvl_1]
                    
            # Row 2: Infantry (Middle in game UI)
            row2_c1, row2_c2 = st.columns(2)
            with row2_c1:
                with st.container(border=True):
                    st.markdown("🛡️ **Infantry 1**")
                    lvl_0 = st.selectbox("Tier", range(len(gov_names)), format_func=lambda x: gov_names[x], key="gv_inf_0", label_visibility="collapsed")
                    stat_val = sum(gov_atlas["deltas"][:lvl_0+1])
                    st.caption(f"Current Stat: {stat_val:.2f}%")
            with row2_c2:
                with st.container(border=True):
                    st.markdown("🛡️ **Infantry 2**")
                    lvl_1 = st.selectbox("Tier", range(len(gov_names)), format_func=lambda x: gov_names[x], key="gv_inf_1", label_visibility="collapsed")
                    stat_val = sum(gov_atlas["deltas"][:lvl_1+1])
                    st.caption(f"Current Stat: {stat_val:.2f}%")
            current_gov["infantry"] = [lvl_0, lvl_1]

            # Row 3: Archer (Bottom in game UI)
            row3_c1, row3_c2 = st.columns(2)
            with row3_c1:
                with st.container(border=True):
                    st.markdown("🏹 **Archery 1**")
                    lvl_0 = st.selectbox("Tier", range(len(gov_names)), format_func=lambda x: gov_names[x], key="gv_arc_0", label_visibility="collapsed")
                    stat_val = sum(gov_atlas["deltas"][:lvl_0+1])
                    st.caption(f"Current Stat: {stat_val:.2f}%")
            with row3_c2:
                with st.container(border=True):
                    st.markdown("🏹 **Archery 2**")
                    lvl_1 = st.selectbox("Tier", range(len(gov_names)), format_func=lambda x: gov_names[x], key="gv_arc_1", label_visibility="collapsed")
                    stat_val = sum(gov_atlas["deltas"][:lvl_1+1])
                    st.caption(f"Current Stat: {stat_val:.2f}%")
            current_gov["archer"] = [lvl_0, lvl_1]

            st.markdown("---")
            

# ... existing code ...
            
            if st.button("🚀 Execute Governor Matrix Optimization", type="primary", use_container_width=True, key="gv_run_btn"):
                gv_progress = st.progress(0)
                gv_status = st.empty()
                
                # Snapshot wallets
                gv_wallet = {"Satin": inv_satin, "Threads": inv_threads, "Vision": inv_vision}
                running_gov = copy.deepcopy(current_gov)
                gov_roadmap = []
                
                # Tracking accumulation matrix
                accumulated_gains = {t: [0.0 for _ in range(2)] for t in ["infantry", "cavalry", "archer"]}
                accumulated_costs = {t: [{"Satin": 0, "Threads": 0, "Vision": 0} for _ in range(2)] for t in ["infantry", "cavalry", "archer"]}
                starting_gov = copy.deepcopy(current_gov)

                def run_gov_isolated_simulation(gov_state):
                    """Injects the baseline battle report stats modified by Governor Gear scaling + Set Bonuses."""
                    my_stats_matrix = np.array([
                        [my_ia, my_id, my_il, my_ih], 
                        [my_ca, my_cd, my_cl, my_ch], 
                        [my_aa, my_ad, my_al, my_ah]
                    ])
                    opp_stats_matrix = np.array([
                        [opp_ia, opp_id, opp_il, opp_ih],
                        [opp_ca, opp_cd, opp_cl, opp_ch],
                        [opp_aa, opp_ad, opp_al, opp_ah]
                    ])
                    
                    target_matrix = my_stats_matrix if opt_role == "Rally Attacker" else opp_stats_matrix
                    
                    # Process Gov Gear Stats + Set Bonuses
                    for r, troop in enumerate(["infantry", "cavalry", "archer"]):
                        piece_1_lvl = gov_state[troop][0]
                        piece_2_lvl = gov_state[troop][1]
                        
                        # 1. Base Stats
                        stat1_pct = sum(gov_atlas["deltas"][:piece_1_lvl+1])
                        stat2_pct = sum(gov_atlas["deltas"][:piece_2_lvl+1])
                        
                        # 2. Cumulative Set Bonus Calculation (Key Mechanic!)
                        # Set bonus is based on the lowest tier between the two pieces
                        min_tier = min(piece_1_lvl, piece_2_lvl)
                        set_bonus_pct = gov_atlas["set_bonuses"][min_tier]
                        
                        total_boost = stat1_pct + stat2_pct + set_bonus_pct
                        
                        # Apply equally to all 4 fundamental stats
                        target_matrix[r, 0] += total_boost # Atk
                        target_matrix[r, 1] += total_boost # Def
                        target_matrix[r, 2] += total_boost # Leth
                        target_matrix[r, 3] += total_boost # HP

                    my_march = TroopSide([my_inf, my_cav, my_arc], my_stats_matrix, [my_h1, my_h2, my_h3], ["None"]*4)
                    opp_march = TroopSide([opp_inf, opp_cav, opp_arc], opp_stats_matrix, [opp_h1, opp_h2, opp_h3], ["None"]*4)
                    
                    attacker_side = my_march if opt_role == "Rally Attacker" else opp_march
                    defender_side = opp_march if opt_role == "Rally Attacker" else my_march
                    
                    total_surviving_target = 0
                    for _ in range(gv_precision):
                        res = kingshot_multirally_sim2([attacker_side.clone()], defender_side.clone())
                        total_surviving_target += np.sum(res[1][0]['attacker_surviving']) if opt_role == "Rally Attacker" else np.sum(res[0].troops)
                            
                    return total_surviving_target / gv_precision

                # -------------------------------------------------------------------------
                # --- GREEDY SEARCH LOOP WITH TRIPLE SQUARED SCARCITY ---
                # -------------------------------------------------------------------------
                for action_step in range(1, gv_max_actions + 1):
                    gv_status.markdown(f"**🔍 Calculating Optimal Governor Tier Step #{action_step}...**")
                    
                    control_surv = run_gov_isolated_simulation(running_gov)
                    candidates = []
                    
                    # Triple Scarcity Weighting
                    s_pool = max(1, gv_wallet["Satin"])
                    t_pool = max(1, gv_wallet["Threads"])
                    v_pool = max(1, gv_wallet["Vision"])
                    
                    w_satin = 1.0 / (s_pool ** 2)
                    w_threads = 1.0 / (t_pool ** 2)
                    w_vision = 1.0 / (v_pool ** 2)

                    for troop in ["infantry", "cavalry", "archer"]:
                        for slot_idx, current_lvl in enumerate(running_gov[troop]):
                            if current_lvl >= 58: # Max level cap (Red T6 3★)
                                continue 
                                
                            target_lvl = current_lvl + 1
                            req_s = gov_atlas["satin"][target_lvl]
                            req_t = gov_atlas["threads"][target_lvl]
                            req_v = gov_atlas["vision"][target_lvl]
                            
                            if gv_wallet["Satin"] >= req_s and gv_wallet["Threads"] >= req_t and gv_wallet["Vision"] >= req_v:
                                test_gov = copy.deepcopy(running_gov)
                                test_gov[troop][slot_idx] += 1
                                
                                test_surv = run_gov_isolated_simulation(test_gov)
                                troops_saved = max(0.001, test_surv - control_surv)
                                
                                # Budget Normalization Denominator
                                resource_score = (req_s * w_satin) + (req_t * w_threads) + (req_v * w_vision)
                                efficiency = troops_saved / max(1e-9, resource_score)
                                
                                candidates.append({
                                    "troop": troop, "slot": slot_idx, "next_lvl": target_lvl,
                                    "cost_s": req_s, "cost_t": req_t, "cost_v": req_v,
                                    "efficiency": efficiency, "saved": troops_saved
                                })

                    if not candidates:
                        gv_progress.progress(1.0)
                        break
                        
                    # Commit the best step
                    candidates.sort(key=lambda x: x["efficiency"], reverse=True)
                    winner = candidates[0]
                    
                    gv_wallet["Satin"] -= winner["cost_s"]
                    gv_wallet["Threads"] -= winner["cost_t"]
                    gv_wallet["Vision"] -= winner["cost_v"]
                    
                    running_gov[winner["troop"]][winner["slot"]] += 1
                    
                    # Consolidate outputs
                    lvl_idx = winner["next_lvl"]
                    stat_gain_amt = gov_atlas["deltas"][lvl_idx]
                    
                    # Log base stat gains. Set bonus will be calculated globally at the end for display.
                    accumulated_gains[winner["troop"]][winner["slot"]] += stat_gain_amt
                    accumulated_costs[winner["troop"]][winner["slot"]]["Satin"] += winner["cost_s"]
                    accumulated_costs[winner["troop"]][winner["slot"]]["Threads"] += winner["cost_t"]
                    accumulated_costs[winner["troop"]][winner["slot"]]["Vision"] += winner["cost_v"]
                    
                    gov_roadmap.append(winner)
                    gv_progress.progress(action_step / gv_max_actions)

                gv_progress.empty()
                gv_status.empty()

                # -------------------------------------------------------------------------
                # --- CONSOLIDATE AND DISPLAY FINAL BLUEPRINT ---
                # -------------------------------------------------------------------------
                if gov_roadmap:
                    st.success("🎯 Optimal Governor Gear Roadmap Compiled Successfully!")
                    
                    consolidated_rows = []
                    for troop in ["infantry", "cavalry", "archer"]:
                        for slot_idx in range(2):
                            start_l = starting_gov[troop][slot_idx]
                            end_l = running_gov[troop][slot_idx]
                            
                            if start_l != end_l:
                                costs = accumulated_costs[troop][slot_idx]
                                cost_display = f"+{costs['Satin']:,} Satin"
                                if costs['Threads'] > 0: cost_display += f", +{costs['Threads']:,} Threads"
                                if costs['Vision'] > 0: cost_display += f", +{costs['Vision']:,} Vision"
                                
                                stat_gain = accumulated_gains[troop][slot_idx]
                                
                                # Format visual names
                                str_start = gov_names[start_l]
                                str_end = gov_names[end_l]
                                
                                consolidated_rows.append({
                                    "Target Piece": f"{troop.capitalize()} Piece #{slot_idx + 1}",
                                    "Tier Jump": f"{str_start} ➔ {str_end}",
                                    "Required Resources": cost_display,
                                    "Base Stat Yield": f"+{stat_gain:.2f}%"
                                })
                                
                    st.subheader("📋 Consolidated Governor Upgrade Action Plan")
                    if consolidated_rows:
                        st.dataframe(pd.DataFrame(consolidated_rows), hide_index=True, use_container_width=True)
                        
                        # Highlight Set Bonus changes if any occurred
                        st.markdown("#### ⚡ Set Bonus Impacts")
                        set_bonus_text = []
                        for troop in ["infantry", "cavalry", "archer"]:
                            old_min = min(starting_gov[troop][0], starting_gov[troop][1])
                            new_min = min(running_gov[troop][0], running_gov[troop][1])
                            if old_min != new_min:
                                old_bonus = gov_atlas["set_bonuses"][old_min]
                                new_bonus = gov_atlas["set_bonuses"][new_min]
                                set_bonus_text.append(f"- **{troop.capitalize()} Set:** Upgraded from +{old_bonus}% to **+{new_bonus}%**")
                        
                        if set_bonus_text:
                            for text in set_bonus_text:
                                st.success(text)
                        else:
                            st.info("No Set Bonus thresholds were crossed during this specific roadmap calculation.")
                            
                    else:
                        st.info("No transitions occurred. Upgrades analyzed were outvalued by core budget limits.")
                        
                    st.markdown("#### 👛 Remaining Asset Reserves After Processing")
                    r_g1, r_g2, r_g3 = st.columns(3)
                    r_g1.metric("Remaining Satin", f"{gv_wallet['Satin']:,}")
                    r_g2.metric("Remaining Gilded Threads", f"{gv_wallet['Threads']:,}")
                    r_g3.metric("Remaining Artisan's Vision", f"{gv_wallet['Vision']:,}")
                else:
                    st.error("❌ The algorithm was unable to calculate an upgrade link. Verify your input balances.")


                        # --- TAB 7- Manual ---
    # =========================================================================
with tab_manual:
        st.header("📖 User Manual")
        st.caption("Centralized operating guide for combat simulation, OCR parsing, and mathematical gear optimization.")
        
        st.markdown("""
        ### 👑 FRANK-Optimizer: Master Suite
        Welcome to the **FRANK-Optimizer**, a high-performance combat logistics engine. 
        Unlike standard algebraic calculators, this suite utilizes **direct Monte Carlo simulation physics**. 
        Your results are derived from thousands of virtual battle iterations, capturing non-linear battlefield synergies instead of static, arbitrary stat weights.
        
        ---
        
        ### 📸 The Dual-Column OCR Scanner
        *Automatically populate battlefield baselines directly from your combat logs.*
        
        *   **How to Use**: Upload a clean screenshot of your battle report. The thread-locked OCR engine will map the **Left** (Attacker) and **Right** (Garrison) statistics directly into their corresponding input coordinates.
        *   **⚠️ Important Limitation**: The OCR engine is explicitly designed for the **Multi-Rally Simulator** and **Tactical Optimizer** modules. It **does not** auto-populate resource inventories for the Gear, Charm, or Governor Gear optimizers.
        
        ---
        
        ### ⚙️ Engine Mechanics: Monte Carlo Iterations
        *Kingshot* combat is governed by critical stochastic variables (hero skill procs, troop target dispersion, and dodge checks). A single battle is simply one random roll of the dice. We use **Monte Carlo sweeps** to run battles repeatedly and extract a reliable average.
        
        #### 📊 Iteration Scaling Guide: Precision vs. Performance
        
        | Iterations | Precision | Latency | Recommended Use Case |
        | :---: | :---: | :---: | :--- |
        | **10 - 30** | Rough | Instant | **Napkin Math:** Quick sanity checks to see if an setup trend is viable. |
        | **40 - 60** | Balanced | Fast | **Gear & Charm Optimizers:** Sweeping dozens of combinations quickly. |
        | **100 - 200** | High | Moderate | **Simulator Wave Testing:** Precision baseline verification before a major event. |
        | **500+** | Scientific | Slow | **Ultimate Optimization:** Isolating tight variable margins (use sparingly). |
        
        💡 ***Law of Convergence:** Beyond 200 iterations, variance drops below 0.1%. Doubling the iterations to 1,000 doubles your wait time without yielding any mathematically significant improvement.*
        
        ---
        
        ### 🧠 Optimization Modules
        
        #### 1. Multi-Rally Simulator (The Attrition Engine)
        Models sequential, wave-on-wave combat. Losses are persistent (troops killed or injured in garrison in Wave 1 cannot fight in Wave 2). Always configure your **Garrison** baselines first, then append your sequential **Attacking Waves**.
        
        #### 2. Tactical Optimizer (The Grid Search)
        Brute-forces the mathematically perfect setup. It sweeps all permutations of **Troop Ratios** or **Supporter Hero Sets** to maximize absolute end-of-combat survivors.
        
        #### 3. Stat Improvement Optimizer (ROI Engine)
        Isolates individual stat impact. It injects minor stat shifts, evaluates survivor deltas, and creates a prioritized ranking of where to invest your next stat point pool.
        
        #### 4, 5, & 6. Gear, Charm, & Governor Gear Optimizers
        These modules govern your resource deployment using specialized surgical logic:
        *   **Squared Scarcity Logic**: If you are bottlenecked on an item (e.g., 5,000 Guides but only 500 Designs), the scarce item's cost weight is mathematically squared ($1/\text{remaining}^2$). The algorithm automatically maneuvers around your bottleneck asset to maximize your returns.
        *   **Resource Irreversibility Penalty**: Reversible assets (like Mythic Level XP) are treated normally. Irreversible actions (Mithril, Forgehammers, Red Gear upgrades) incur a **10x cost penalty** to prevent the engine from locking you into low-ROI upgrades.
        """)
        
        st.info("💡 **Power-User Tips (The FRANK Rules)**")
        
        st.markdown("""
        1.  **The Terror Set Widget Rule**  
            If you are actively wearing a **Terror Set**, you **must set your widget levels to 0** in the optimizer interface.  
            *Why?* The engine automatically factors in widget stat matrices. If left at 10+, it will calculate ghost stats that do not actually exist in a Terror configuration.
            
        2.  **Sequential vs. Global Strategy**  
            *   **Sequential**: Evaluates the single best next immediate upgrade step.
            *   **Global (Optimizer Mode)**: Looks 10–15 steps down the pipeline. It may recommend an apparently lower-value upgrade first because it knows it unlocks a high-value milestone breakthrough (like an imbuement benchmark) at step 3. *Always trust Global Mode.*
            
        3.  **Understanding Combat ROI**  
            The suite optimizes for **Combat Survivability per Resource Unit**. If a piece of gear saves 4,500 troops, and another saves 4,800, it selects the latter. It ignores traditional arbitrary "weights" because it simulates the physics of frontline collapse—it knows that if your infantry shield folds, your archers die, no matter how much raw attack they have.
            
        4.  **Manual Overrides**  
            If OCR fails to read a blurry log file, manually type the value in. The user interface inputs always take global priority over raw OCR cache values.
        """)