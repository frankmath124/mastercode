import streamlit as st
import numpy as np
import copy
import itertools
from simulator_engine import kingshot_multirally_sim2, TroopSide, load_hero_db

# Helper to calculate widget expedition bonus based on even-level steps
def get_widget_bonus(level):
    if level == 0:
        return 0.0
    even_level = (level // 2) * 2
    return 2.5 + (even_level / 2) * 2.5

# =========================================================================
# --- SECURITY GATEWAY ---
# =========================================================================
SECRET_PASSCODE = "Frank_BattleSimulator"

st.set_page_config(page_title="FRANK-Optimizer Master Suite", layout="wide")

# ... inside the unlocked application section ...
st.title("FRANK-Optimizer: Kingshot Battle Simulator and Optimizer")
st.caption("Combat Logistics &  Battle Math Matrix.")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔒 Security Access Required")
    user_input = st.text_input("Enter Alliance Passcode:", type="password")
    
    if st.button("Unlock Command Suite"):
        if user_input == SECRET_PASSCODE:
            st.session_state["authenticated"] = True
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
    
    joiner_pool_defaults = [h for h in hero_list if h != "None" and not hero_db[h].get('widget', {}).get('has_widget', True)]
    if not joiner_pool_defaults:
        joiner_pool_defaults = ["Gordon", "Fahd", "Chenko", "Yaenwoo", "Howard", "Quinn", "Amane"]

    # =========================================================================
    # --- MASTER HEADERS & SYSTEM DESCRIPTIONS ---
    # =========================================================================
    st.title("Kingshot Battle Suite")
    st.caption("A comprehensive combat environment simulator driven by predictive derivative matrix loops and stochastic Monte Carlo modeling.")
    
    if st.sidebar.button("Lock Command Suite"):
        st.session_state["authenticated"] = False
        st.rerun()

    # High-level tool breakdowns presented cleanly right at the top
    with st.expander(" Module Descriptions", expanded=True):
        col_desc1, col_desc2, col_desc3 = st.columns(3)
        with col_desc1:
            st.markdown("### Multi-Rally Simulator")
            st.write("Simulate consecutive rally waves hitting a fixed structure. Evaluates sequential attrition, troop depletion curves, and step-by-step win conditions does not work for tile hits.")
        with col_desc2:
            st.markdown("### Tactical Optimizer")
            st.write("Run brute-force grid searches across continuous loops to calculate best performance for troop compositions or optimal joiner heroes.")
        with col_desc3:
            st.markdown("### Stat Optimizer Engine")
            st.write("Isolate variables by injecting small stat changees. Calculates exactly how many fewer troop deaths an upgrade prevents to provide upgrade guidance.")

    # Render master navigation tabs
    tab_sim, tab_opt, tab_roi = st.tabs([
        "Multi-Rally Simulator", 
        "Battle Optimizer", 
        "Stat Improvement Optimizer"
    ])

    # =========================================================================
    # =========================================================================
    # --- TAB 1: MULTI-RALLY SIMULATOR ---
    # =========================================================================
    # =========================================================================
    with tab_sim:


        with st.expander(" Multi-Rally Simulator Quick-Start FAQ", expanded=False):
          st.markdown("""
            * **How do I configure heroes and widgets?** Select the precise Main Leaders and Supporter/Joiner heroes for each wave. Enter the exact widget levels (0–10) to compute independent combat multipliers natively.
            * **How should I input troop sizes?** You can toggle between typing in **Raw Counts** manually or using **Rally Size + Ratios**. When using ratios, use the interactive grid to type or micro-adjust percentages—they must sum to exactly 100% to run.
            * **How do I handle Troop Tier and TG Level?** Check your battle report, calculate or read the average troop tier and TG level of the actual march or structure, and match those dropdowns here to align base health/defense levels.
            * **Can I simulate solo or uncaptained battles?** Yes. Set any main or supporter hero slot to **'None'** to simulate pure solo fights, uncaptained structures, or PvE tile cracks (like Sanctuaries) completely free of hero skill and widget overrides.
            * **This will not simulate tile hits as there is a defensive boost provided by garrisoning that this uses
            """)
        st.header("Sequential Multi-Rally Wave Simulation")
        
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
                s_gia = st.number_input("Inf Atk %", value=850.0, key="s_gia_in")
                s_gid = st.number_input("Inf Def %", value=900.0, key="s_gid_in")
                s_gil = st.number_input("Inf Let %", value=1100.0, key="s_gil_in")
                s_gih = st.number_input("Inf HP %", value=1100.0, key="s_gih_in")
                st.markdown("---")
                s_gca = st.number_input("Cav Atk %", value=800.0, key="s_gca_in")
                s_gcd = st.number_input("Cav Def %", value=800.0, key="s_gcd_in")
                s_gcl = st.number_input("Cav Let %", value=1000.0, key="s_gcl_in")
                s_gch = st.number_input("Cav HP %", value=1000.0, key="s_gch_in")
                st.markdown("---")
                s_gaa = st.number_input("Arc Atk %", value=850.0, key="s_gaa_in")
                s_gad = st.number_input("Arc Def %", value=800.0, key="s_gad_in")
                s_gal = st.number_input("Arc Let %", value=1100.0, key="s_gal_in")
                s_gah = st.number_input("Arc HP %", value=1000.0, key="s_gah_in")

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
                        s_g_widgets = [g_wid1, g_wid2, g_wid3, 0, 0, 0, 0]
                        
                        garrison_setup = TroopSide([s_g_inf, s_g_cav, s_g_arc], s_g_combat_stats, [g_lead1, g_lead2, g_lead3], [s_g_sup1, s_g_sup2, s_g_sup3, s_g_sup4], s_g_tier, s_g_tg, s_g_widgets)
                        
                        rally_waves_input = []
                        for wave_idx in range(s_num_waves):
                            sw_data = s_wave_configs[wave_idx]
                            rally_waves_input.append(TroopSide(sw_data["troops"], copy.deepcopy(sw_data["stats"]), sw_data["leaders"], sw_data["supporters"], sw_data["tier"], sw_data["tg"], sw_data["widgets"]))
                            
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
    # =========================================================================
    # --- TAB 2: TACTICAL OPTIMIZER ---
    # =========================================================================
    # =========================================================================
    with tab_opt:
        with st.expander("Multi-Rally Optimization Engine Quick-Start FAQ", expanded=False):
            st.markdown("""
            * **What does this app optimize?** It isolates a single chosen variable (either Troop Ratios or Supporter Hero team configurations) and runs a brute-force mathematical grid search to solve for optimal efficiency.
            * **How do the results sort?** The engine shifts logic automatically: if you are optimizing **Garrison (Defenders)**, it sorts the leaderboard to **maximize** remaining troops. If optimizing **Attacker Waves**, it sorts to **minimize** garrison survival (inflicting maximum casualty attrition).
            * **How should I set the baseline variables?** Lock in all companion heroes, main heroes, and stat percentages to match your true profile. The engine will hold those frozen while cycling the isolated testing variable across thousands of background calculations.
            * **What should I select for the Joiner Pool?** When optimizing supporters, use the multi-select box to pick your eligible candidate heroes. The engine will compute every mathematical combination of those heroes to find the highest-performing squad synergy.
            * **This can also do single attacks by not selecting multiple waves but cant do tile attacks due to defender garrison boost
        """)
        st.header("Multi-Rally Optimization Engine")
        
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
                o_g_total_troops = st.number_input("Total Garrison Capacity", value=2800000, step=100000, key="o_gtot_r")
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
                    o_g_total_troops = st.number_input("Total Garrison Capacity Target", value=2800000, step=100000, key="o_gtot_c")
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
                            oa_inf_atk = st.number_input("Inf Atk %", value=1000.0, key=f"o_ia_{i}_in")
                            oa_inf_def = st.number_input("Inf Def %", value=800.0, key=f"o_id_{i}_in")
                            oa_inf_let = st.number_input("Inf Let %", value=1100.0, key=f"o_il_{i}_in")
                            oa_inf_hp  = st.number_input("Inf HP %", value=900.0, key=f"o_ih_{i}_in")
                        with osc2:
                            oa_cav_atk = st.number_input("Cav Atk %", value=900.0, key=f"o_ca_{i}_in")
                            oa_cav_def = st.number_input("Cav Def %", value=750.0, key=f"o_cd_{i}_in")
                            oa_cav_let = st.number_input("Cav Let %", value=850.0, key=f"o_cl_{i}_in")
                            oa_cav_hp  = st.number_input("Cav HP %", value=700.0, key=f"o_ch_{i}_in")
                        with osc3:
                            oa_arc_atk = st.number_input("Arc Atk %", value=900.0, key=f"o_aa_{i}_in")
                            oa_arc_def = st.number_input("Arc Def %", value=700.0, key=f"o_ad_{i}_in")
                            oa_arc_let = st.number_input("Arc Let %", value=1050.0, key=f"o_al_{i}_in")
                            oa_arc_hp  = st.number_input("Arc HP %", value=800.0, key=f"o_ah_{i}_in")
                            
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
                        o_g_widgets = [g_wid1, g_wid2, g_wid3, 0, 0, 0, 0]
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
                                waves.append(TroopSide(t_troops, copy.deepcopy(w_data["stats"]), w_data["leaders"], t_sups, w_data["tier"], w_data["tg"], w_data["widgets"]))
                            return waves

                        if opt_side == "Garrison (Defenders)" and "Troop Ratios" in opt_mode:
                            for r in ratio_grid:
                                test_troops = [o_g_total_troops * r[0], o_g_total_troops * r[1], o_g_total_troops * r[2]]
                                g_setup = TroopSide(test_troops, o_g_combat_stats, [o_g_lead1, o_g_lead2, o_g_lead3], o_g_sup_heroes, o_g_tier, o_g_tg, o_g_widgets)
                                w_set = build_waves_opt()
                                tot_surv = sum(np.sum(kingshot_multirally_sim2(copy.deepcopy(w_set), copy.deepcopy(g_setup))[0].troops) for _ in range(o_mc_runs))
                                avg_surv = tot_surv / o_mc_runs
                                results_grid.append({"Configuration": f"Inf: {r[0]*100:.0f}% | Cav: {r[1]*100:.0f}% | Arc: {r[2]*100:.0f}%", "Avg Survivors": avg_surv, "Rate": (avg_surv / o_g_total_troops) * 100})
                        
                        elif opt_side == "Garrison (Defenders)" and "Supporter Heroes" in opt_mode:
                            combos = list(itertools.combinations_with_replacement(opt_hero_pool, 4))
                            for combo in combos:
                                g_setup = TroopSide([o_g_inf, o_g_cav, o_g_arc], o_g_combat_stats, [o_g_lead1, o_g_lead2, o_g_lead3], list(combo), o_g_tier, o_g_tg, o_g_widgets)
                                w_set = build_waves_opt()
                                tot_surv = sum(np.sum(kingshot_multirally_sim2(copy.deepcopy(w_set), copy.deepcopy(g_setup))[0].troops) for _ in range(o_mc_runs))
                                avg_surv = tot_surv / o_mc_runs
                                results_grid.append({"Configuration": f"{', '.join(combo)}", "Avg Survivors": avg_surv, "Rate": (avg_surv / max(1, o_g_total_troops)) * 100})
                        
                        elif opt_side == "Attacker Waves (Rallies)" and "Troop Ratios" in opt_mode:
                            w1_cap = o_wave_configs[0]["capacity"]
                            g_setup = TroopSide([o_g_inf, o_g_cav, o_g_arc], o_g_combat_stats, [o_g_lead1, o_g_lead2, o_g_lead3], o_g_sup_heroes, o_g_tier, o_g_tg, o_g_widgets)
                            for r in ratio_grid:
                                test_w1_troops = [w1_cap * r[0], w1_cap * r[1], w1_cap * r[2]]
                                w_set = build_waves_opt(wave_1_override_troops=test_w1_troops)
                                tot_surv = sum(np.sum(kingshot_multirally_sim2(copy.deepcopy(w_set), copy.deepcopy(g_setup))[0].troops) for _ in range(o_mc_runs))
                                avg_surv = tot_surv / o_mc_runs
                                results_grid.append({"Configuration": f"Wave 1 -> Inf: {r[0]*100:.0f}% | Cav: {r[1]*100:.0f}% | Arc: {r[2]*100:.0f}%", "Avg Survivors": avg_surv, "Rate": (avg_surv / max(1, o_g_total_troops)) * 100})
                        
                        elif opt_side == "Attacker Waves (Rallies)" and "Supporter Heroes" in opt_mode:
                            combos = list(itertools.combinations_with_replacement(opt_hero_pool, 4))
                            g_setup = TroopSide([o_g_inf, o_g_cav, o_g_arc], o_g_combat_stats, [o_g_lead1, o_g_lead2, o_g_lead3], o_g_sup_heroes, o_g_tier, o_g_tg, o_g_widgets)
                            for combo in combos:
                                w_set = build_waves_opt(wave_1_override_heroes=list(combo))
                                tot_surv = sum(np.sum(kingshot_multirally_sim2(copy.deepcopy(w_set), copy.deepcopy(g_setup))[0].troops) for _ in range(o_mc_runs))
                                avg_surv = tot_surv / o_mc_runs
                                results_grid.append({"Configuration": f"Wave 1 -> {', '.join(combo)}", "Avg Survivors": avg_surv, "Rate": (avg_surv / max(1, o_g_total_troops)) * 100})

                        if opt_side == "Garrison (Defenders)":
                            sorted_results = sorted(results_grid, key=lambda x: x["Avg Survivors"], reverse=True)
                            st.success(" GARRISON OPTIMIZATION COMPLETE")
                        else:
                            sorted_results = sorted(results_grid, key=lambda x: x["Avg Survivors"], reverse=False)
                            st.success("ATTACKER OPTIMIZATION COMPLETE")

                        st.markdown("### Top 5 Matrix Configurations")
                        top_5 = sorted_results[:5]
                        f_top_5 = [{"Rank": i+1, "Configuration": r["Configuration"], "Garrison Survivors (Avg)": f"{r['Avg Survivors']:,.0f}", "Garrison Survival Rate %": f"{r['Rate']:.1f}%"} for i, r in enumerate(top_5)]
                        st.table(f_top_5)
            else:
                st.button("Run Optimization Engine Grid Search", disabled=True, key="o_run_disabled")

    # =========================================================================
    # =========================================================================
    # --- TAB 3: STAT ROI ENGINE ---
    # =========================================================================
    # =========================================================================
    with tab_roi:
        with st.expander("Stat Optimizer Engine Quick-Start FAQ", expanded=False):
            st.markdown("""
            * **How does the ROI calculation work?** The engine clones your baseline defensive profile and runs a control batch. It then systematically isolates all 12 core combat stats, injects your specified **Hypothetical Upgrade Increment (+ %)** to one stat at a time, and calculates the precise delta of surviving troops.
            * **Does the recommendation change based on the attacker?** **Yes.** A stat upgrade does not exist in a vacuum. Your optimal path is directly dependent on the specific attacker wave composition and stat profile marching at you. Always input a realistic or rival enemy rally profile to get accurate results.
            * **How do I interpret the leaderboard?** Stats ranked at the top are your current tactical 'bottlenecks'. Upgrading them next will save more of your troops from dying compared to lower-ranked stats, which are currently suffering from severe diminishing returns against that specific threat profile.
            * **What precision setting should I use?** For rapid testing, keep the precision iterations lower (e.g., 40–50 runs). For final coordination decisions, scale it up to minimize Monte Carlo RNG variance.
            """)
        st.header("Multi-Variable Stat Optimizer")
        
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
            st.subheader("Testing Increment Scale (percent level increase stats)")
            rc1, rc2 = st.columns(2)
            nudge_val = rc1.number_input("Hypothetical Upgrade Increment Size (+ %)", min_value=5.0, max_value=200.0, value=25.0, step=5.0, key="r_nudge")
            r_mc_runs = rc2.number_input("Monte Carlo Precision Iterations", min_value=10, max_value=500, value=50, step=10, key="r_mc_precision")
            
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
                            ra_inf_atk = st.number_input("Inf Atk %", value=1000.0, key=f"r_ia_{i}_in")
                            ra_inf_def = st.number_input("Inf Def %", value=800.0, key=f"r_id_{i}_in")
                            ra_inf_let = st.number_input("Inf Let %", value=1100.0, key=f"r_il_{i}_in")
                            ra_inf_hp  = st.number_input("Inf HP %", value=900.0, key=f"r_ih_{i}_in")
                        with rsc2:
                            ra_cav_atk = st.number_input("Cav Atk %", value=900.0, key=f"r_ca_{i}_in")
                            ra_cav_def = st.number_input("Cav Def %", value=750.0, key=f"r_cd_{i}_in")
                            ra_cav_let = st.number_input("Cav Let %", value=850.0, key=f"r_cl_{i}_in")
                            ra_cav_hp  = st.number_input("Cav HP %", value=700.0, key=f"r_ch_{i}_in")
                        with rsc3:
                            ra_arc_atk = st.number_input("Arc Atk %", value=900.0, key=f"r_aa_{i}_in")
                            ra_arc_def = st.number_input("Arc Def %", value=700.0, key=f"r_ad_{i}_in")
                            ra_arc_let = st.number_input("Arc Let %", value=1050.0, key=f"r_al_{i}_in")
                            ra_arc_hp  = st.number_input("Arc HP %", value=800.0, key=f"r_ah_{i}_in")
                            
                        r_wave_configs[i] = {
                            "troops": [ra_inf, ra_cav, ra_arc], "tier": rw_tier, "tg": rw_tg,
                            "leaders": [ra_l1, ra_l2, ra_l3], "supporters": [ra_s1, ra_s2, "None", "None"],
                            "widgets": [ra_w1, ra_w2, ra_w3, 0, 0, 0, 0],
                            "stats": [[ra_inf_atk, ra_inf_def, ra_inf_let, ra_inf_hp], [ra_cav_atk, ra_cav_def, ra_cav_let, ra_cav_hp], [ra_arc_atk, ra_arc_def, ra_arc_let, ra_arc_hp]]
                        }
            
            st.markdown("---")
            r_all_waves_valid = all(st.session_state.get(f"r_wvalid_{w_idx}", True) for w_idx in range(r_num_waves))
            
            if r_all_waves_valid and r_g_valid:
                if st.button(" Run Comprehensive Stat Optimization Analysis", key="r_run_btn"):
                    with st.spinner("Calculating control baseline and spawning stat derivative testing loops..."):
                        r_g_widgets = [g_wid1, g_wid2, g_wid3, 0, 0, 0, 0]
                        r_g_sups = [r_g_sup1, r_g_sup2, r_g_sup3, r_g_sup4]
                        
                        rally_waves_input = []
                        for wave_idx in range(r_num_waves):
                            rw_data = r_wave_configs[wave_idx]
                            rally_waves_input.append(TroopSide(rw_data["troops"], copy.deepcopy(rw_data["stats"]), rw_data["leaders"], rw_data["supporters"], rw_data["tier"], rw_data["tg"], rw_data["widgets"]))
                        
                        baseline_stats = [[r_gia, r_gid, r_gil, r_gih], [r_gca, r_gcd, r_gcl, r_gch], [r_gaa, r_gad, r_gal, r_gah]]
                        control_garrison = TroopSide([r_g_inf, r_g_cav, r_g_arc], copy.deepcopy(baseline_stats), [r_g_lead1, r_g_lead2, r_g_lead3], r_g_sups, r_g_tier, r_g_tg, r_g_widgets)
                        
                        control_surv_total = sum(np.sum(kingshot_multirally_sim2(copy.deepcopy(rally_waves_input), copy.deepcopy(control_garrison))[0].troops) for _ in range(r_mc_runs))
                        control_avg = control_surv_total / r_mc_runs
                        
                        stat_map = [
                            ("Infantry Attack", 0, 0), ("Infantry Defense", 0, 1), ("Infantry Lethality", 0, 2), ("Infantry Health", 0, 3),
                            ("Cavalry Attack", 1, 0),  ("Cavalry Defense", 1, 1),  ("Cavalry Lethality", 1, 2),  ("Cavalry Health", 1, 3),
                            ("Archer Attack", 2, 0),   ("Archer Defense", 2, 1),   ("Archer Lethality", 2, 2),   ("Archer Health", 2, 3)
                        ]
                        
                        roi_leaderboard = []
                        for label, row, col in stat_map:
                            nudged_stats = copy.deepcopy(baseline_stats)
                            nudged_stats[row][col] += nudge_val
                            
                            test_garrison = TroopSide([r_g_inf, r_g_cav, r_g_arc], nudged_stats, [r_g_lead1, r_g_lead2, r_g_lead3], r_g_sups, r_g_tier, r_g_tg, r_g_widgets)
                            test_surv_total = sum(np.sum(kingshot_multirally_sim2(copy.deepcopy(rally_waves_input), copy.deepcopy(test_garrison))[0].troops) for _ in range(r_mc_runs))
                            test_avg = test_surv_total / r_mc_runs
                            
                            saved_troops = test_avg - control_avg
                            roi_leaderboard.append({"Metric Target": label, "Avg Saved Troops": max(0.0, saved_troops), "Casualty Reduction %": (max(0.0, saved_troops) / max(1, r_g_inf+r_g_cav+r_g_arc)) * 100})
                            
                        sorted_roi = sorted(roi_leaderboard, key=lambda x: x["Avg Saved Troops"], reverse=True)
                        st.success("Optimization Analysis Grid Processing Completed!")
                        st.subheader("Upgrade Efficiency Leaderboard")
                        
                        display_board = []
                        for rank, entry in enumerate(sorted_roi):
                            display_board.append({"Rank": rank + 1, "Stat Node Upgrade": f"Add +{nudge_val}% {entry['Metric Target']}", "Fewer Troops Dead (Avg)": f"{entry['Avg Saved Troops']:,.0f}", "Casualty Deflection Delta": f"+{entry['Casualty Reduction %']:.3f}%"})
                        st.table(display_board)
            else:
                st.button("Run Comprehensive Stat ROI Analysis", disabled=True, key="r_run_disabled")