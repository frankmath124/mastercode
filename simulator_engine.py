import numpy as np
import pandas as pd
import copy

# Load the base stats database globally
try:
    TROOP_DB = pd.read_csv('troop_stats.csv')
except FileNotFoundError:
    print("WARNING: troop_stats.csv not found. Engine requires base stats to run.")
    TROOP_DB = None

def get_base_stats(troop_type, tier, tg_level):
    """Fetches the 4 base stats [Atk, Def, Let, HP] for a specific troop type."""
    if TROOP_DB is not None:
        try:
            row = TROOP_DB[(TROOP_DB['Type'] == troop_type) & 
                           (TROOP_DB['Tier'] == tier) & 
                           (TROOP_DB['TG'] == tg_level)]
            if not row.empty:
                return row[['Attack', 'Defense', 'Lethality', 'Health']].values[0]
        except Exception:
            pass
    
    # Failsafe default matching T10 TG5 from your CSV format
    if troop_type == 'infantry': return np.array([597.0, 10.0, 10.0, 1790.0])
    if troop_type == 'cavalry':  return np.array([1790.0, 10.0, 10.0, 597.0])
    return np.array([2387.0, 10.0, 10.0, 448.0])

class TroopSide:
    def __init__(self, troops, stats, leader_heroes, supporter_heroes, tier=10, tg_level=5, widget_levels=None):
        self.troops = np.array(troops, dtype=float)
        self.bonus_stats_percentage = np.array(stats, dtype=float) 
        self.leader_heroes = leader_heroes
        self.supporter_heroes = supporter_heroes
        self.tier = tier 
        self.tg_level = tg_level 
        
        self.widget_levels = widget_levels if widget_levels else [0] * 7 
        self.widget_bonus = self.calculate_widget_bonus()
        
        # Additive Widget integration: Add widget bonus directly to UI Attack (Col 0) and Defense (Col 1)
        # This keeps them ready for easy zeroing via the Streamlit interface.
        if self.widget_bonus > 0:
            self.bonus_stats_percentage[:, 0] += self.widget_bonus
            self.bonus_stats_percentage[:, 1] += self.widget_bonus
            
        types = ['infantry', 'cavalry', 'archers']
        self.true_base_stats = np.zeros((3, 4))
        for i, t_type in enumerate(types):
            self.true_base_stats[i] = get_base_stats(t_type, self.tier, self.tg_level)

    def calculate_widget_bonus(self):
        total_bonus = 0.0
        for level in self.widget_levels:
            if level > 0:
                even_level = (level // 2) * 2
                total_bonus += 2.5 + (even_level / 2) * 2.5
        return total_bonus

    def clone(self):
        return copy.deepcopy(self)

class CombatMods:
    def __init__(self):
        self.atk = 1.0
        self.def_val = 1.0
        self.leth = 1.0
        self.hp = 1.0
        self.dmg = 1.0
        self.reduct = 1.0
        self.dodge = 0.0
        self.enemy_leth_down = 0.0
        self.enemy_atk_down = 0.0
        self.enemy_dmg_down = 0.0
        self.enemy_taken_up = 0.0
        
        self.class_dmg = np.ones(3)
        self.class_atk_mod = np.ones(3)
        
        self.procs = []
        self.active_debuffs = []

    def __getattr__(self, name):
        return 0.0 

def apply_skill(skill, mods):
    if isinstance(skill, list):
        for sub_skill in skill:
            mods = apply_skill(sub_skill, mods)
        return mods
        
    sk_type = skill.get('type')
    val = skill.get('val', 0.0)
    
    if sk_type == 'atk':               mods.atk += val
    elif sk_type == 'defense':         mods.def_val += val
    elif sk_type == 'lethality':       mods.leth += val
    elif sk_type == 'health':          mods.hp += val
    elif sk_type == 'dmg':             mods.dmg += val
    elif sk_type == 'enemy_leth_down': mods.enemy_leth_down += val
    elif sk_type == 'enemy_atk_down':  mods.enemy_atk_down += val
    elif sk_type == 'enemy_taken_up':  mods.enemy_taken_up += val
    
    elif sk_type == 'dmg_reduction':   mods.reduct *= (1.0 - val)
    elif sk_type == 'enemy_dmg_down':  mods.enemy_dmg_down = 1.0 - ((1.0 - mods.enemy_dmg_down) * (1.0 - val))
    elif sk_type in ['dodge', 'dodge_chance']: 
        mods.dodge = 1.0 - ((1.0 - mods.dodge) * (1.0 - val))
        
    elif sk_type in ['proc', 'timed_shield']:
        mods.procs.append(skill)
        
    elif sk_type == 'class_dmg_buff':
        mods.class_dmg += np.array(skill.get('buffs', [0, 0, 0]))
        
    elif sk_type == 'class_atk_buff':
        mods.class_atk_mod[skill.get('target_class', 0)] += val
        
    return mods

def load_hero_db():
    db = {}
    # Gen 1
    db['Amadeus'] = {'skill1': {'type': 'lethality', 'val': 0.25}, 'skill2': {'type': 'atk', 'val': 0.25}, 'skill3': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg', 'val': 1.50}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'atk', 'val': 0.15}}
    db['Helga'] = {'skill1': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg_reduction', 'val': 0.50}, 'skill2': {'type': 'atk', 'val': 0.25}, 'skill3': {'type': 'lethality', 'val': 0.25}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    db['Saul'] = {'skill1': [{'type': 'health', 'val': 0.15}, {'type': 'defense', 'val': 0.10}], 'skill2': {'type': 'dmg_reduction', 'val': 0.0}, 'skill3': {'type': 'lethality', 'val': 0.25}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'atk', 'val': 0.15}}
    db['Jabel'] = {'skill1': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg_reduction', 'val': 0.40}, 'skill2': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg', 'val': 1.50}, 'skill3': {'type': 'dmg', 'val': 0.25}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    
    # Gen 2
    db['Zoe'] = {'skill1': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg', 'val': 1.40}, 'skill2': {'type': 'atk', 'val': 0.25}, 'skill3': {'type': 'proc', 'chance': 0.50, 'effect': 'enemy_taken_up', 'val': 1.50}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'atk', 'val': 0.10}}
    db['Marlin'] = {'skill1': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg', 'val': 1.50}, 'skill2': {'type': 'proc', 'chance': 0.20, 'effect': 'enemy_leth_down', 'val': 0.50, 'duration': 2}, 'skill3': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg', 'val': 1.50}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    db['Hilde'] = {'skill1': [{'type': 'atk', 'val': 0.15}, {'type': 'defense', 'val': 0.10}], 'skill2': {'type': 'proc', 'chance': 0.25, 'effect': 'dmg', 'val': 2.00}, 'skill3': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg_reduction', 'val': 0.50}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'dodge', 'val': 0.05}}
    
    # Gen 3
    db['Petra'] = {'skill1': {'type': 'proc', 'chance': 0.50, 'effect': 'enemy_taken_up', 'val': 1.50}, 'skill2': {'type': 'proc', 'chance': 0.50, 'effect': 'atk', 'val': 1.50}, 'skill3': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg_reduction', 'val': 0.50}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'atk', 'val': 0.15}}
    db['Eric'] = {'skill1': {'type': 'atk', 'val': -0.20}, 'skill2': {'type': 'dmg_reduction', 'val': 0.20}, 'skill3': {'type': 'health', 'val': 0.25}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'defense', 'val': 0.15}}
    db['Jaegar'] = {'skill1': {'type': 'proc', 'chance': 0.20, 'effect': 'dmg', 'val': 1.40}, 'skill2': {'type': 'proc', 'chance': 0.20, 'effect': 'enemy_leth_down', 'val': 0.50, 'duration': 2}, 'skill3': {'type': 'health', 'val': 0.25}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'health', 'val': 0.15}}
    
    # Gen 4
    db['Alcar'] = {'skill1': {'type': 'timed_shield', 'interval': 5, 'duration': 2, 'val': 0.70, 'targets': [0, 2]}, 'skill2': {'type': 'class_dmg_buff', 'buffs': [1.00, 0.10, 0.10]}, 'skill3': [{'type': 'class_dmg_buff', 'buffs': [0.60, 0.0, 0.0]}, {'type': 'enemy_taken_up', 'val': 0.25}], 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'health', 'val': 0.15}}
    db['Rosa'] = {'skill1': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg', 'val': 1.50}, 'skill2': {'type': 'enemy_dmg_down', 'val': 0.20}, 'skill3': {'type': 'class_atk_buff', 'target_class': 2, 'val': 0.30}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    db['Margot'] = {'skill1': {'type': 'atk', 'val': 0.25}, 'skill2': {'type': 'dodge_chance', 'val': 0.20}, 'skill3': {'type': 'proc', 'chance': 0.25, 'effect': 'double_strike', 'val': 2.00}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'lethality', 'val': 0.15}}

    # Joiners
    db['Gordon'] = {'skill1': {'type': 'health', 'val': 0.25}, 'skill2': {'type': 'proc', 'chance': 1.00, 'effect': 'dmg', 'val': 1.00}, 'skill3': {'type': 'atk', 'val': 0.25}, 'widget': {'has_widget': False}}
    db['Fahd'] = {'skill1': {'type': 'dmg_reduction', 'val': 0.20}, 'skill2': {'type': 'proc', 'chance': 1.00, 'effect': 'dmg', 'val': 1.00}, 'skill3': {'type': 'atk', 'val': 0.00}, 'widget': {'has_widget': False}}
    db['Chenko'] = {'skill1': {'type': 'lethality', 'val': 0.25}, 'skill2': {'type': 'dmg', 'val': 0.00}, 'skill3': {'type': 'health', 'val': 0.15}, 'widget': {'has_widget': False}}
    db['Yaenwoo'] = {'skill1': {'type': 'lethality', 'val': 0.25}, 'skill2': {'type': 'dmg', 'val': 0.00}, 'skill3': {'type': 'health', 'val': 0.15}, 'widget': {'has_widget': False}}
    db['Howard'] = {'skill1': {'type': 'dmg_reduction', 'val': 0.20}, 'skill2': {'type': 'enemy_atk_down', 'val': 0.20}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    db['Amane'] = {'skill1': {'type': 'atk', 'val': 0.25}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    db['Quinn'] = {'skill1': {'type': 'dmg_reduction', 'val': 0.20}, 'skill2': {'type': 'dmg', 'val': 0.50}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    return db

# =========================================================================
# --- CORE COMBAT ENGINE FUNCTION ---
# =========================================================================
def kingshot_multirally_sim2(rally_waves, garrison, max_rounds=200):
    combat_scale = 8.0
    cav_backline_split = 0.20
    
    hero_db = load_hero_db()
    current_garrison = garrison.clone()
    
    counter_matrix = np.array([
        [1.0, 1.1, 0.9],  # Inf vs [Inf, Cav, Arch]
        [0.9, 1.0, 1.1],  # Cav vs [Inf, Cav, Arch]
        [1.1, 0.9, 1.0]   # Arch vs [Inf, Cav, Arch]
    ])
    
    wave_logs = []
    
    for wave_idx, wave_data in enumerate(rally_waves):
        attacker = wave_data.clone()
        
        a_mods = CombatMods()
        d_mods = CombatMods()
        
        for hero_name in attacker.leader_heroes:
            if hero_name and hero_name != "None" and hero_name in hero_db:
                hero = hero_db[hero_name]
                a_mods = apply_skill(hero['skill1'], a_mods)
                a_mods = apply_skill(hero['skill2'], a_mods)
                a_mods = apply_skill(hero['skill3'], a_mods)
                if hero.get('widget', {}).get('has_widget') and hero['widget']['scenario'] == 'rally':
                    a_mods = apply_skill(hero['widget'], a_mods)
                    
        for hero_name in current_garrison.leader_heroes:
            if hero_name and hero_name != "None" and hero_name in hero_db:
                hero = hero_db[hero_name]
                d_mods = apply_skill(hero['skill1'], d_mods)
                d_mods = apply_skill(hero['skill2'], d_mods)
                d_mods = apply_skill(hero['skill3'], d_mods)
                if hero.get('widget', {}).get('has_widget') and hero['widget']['scenario'] == 'garrison':
                    d_mods = apply_skill(hero['widget'], d_mods)
                    
        for hero_name in attacker.supporter_heroes:
            if hero_name and hero_name != "None" and hero_name in hero_db:
                a_mods = apply_skill(hero_db[hero_name]['skill1'], a_mods)
        for hero_name in current_garrison.supporter_heroes:
            if hero_name and hero_name != "None" and hero_name in hero_db:
                d_mods = apply_skill(hero_db[hero_name]['skill1'], d_mods)
                
        # --- STATE OF SURVIVAL ADDITIVE STAT ALIGNMENT ---
        a_ui = attacker.bonus_stats_percentage / 100.0
        d_ui = current_garrison.bonus_stats_percentage / 100.0
        
        a_base = attacker.true_base_stats
        d_base = current_garrison.true_base_stats
        
        eff_a_stats = np.zeros((3, 4))
        eff_d_stats = np.zeros((3, 4))
        
        # Col 0: Attack
        eff_a_stats[:, 0] = a_base[:, 0] * np.maximum(0.1, 1.0 + a_ui[:, 0] + (a_mods.atk - 1.0) + (a_mods.class_atk_mod - 1.0) - d_mods.enemy_atk_down)
        eff_d_stats[:, 0] = d_base[:, 0] * np.maximum(0.1, 1.0 + d_ui[:, 0] + (d_mods.atk - 1.0) + (d_mods.class_atk_mod - 1.0) - a_mods.enemy_atk_down)
        
        # Col 1: Defense
        eff_a_stats[:, 1] = a_base[:, 1] * np.maximum(0.1, 1.0 + a_ui[:, 1] + (a_mods.def_val - 1.0))
        eff_d_stats[:, 1] = d_base[:, 1] * np.maximum(0.1, 1.0 + d_ui[:, 1] + (d_mods.def_val - 1.0))
        
        # Col 2: Lethality
        eff_a_stats[:, 2] = a_base[:, 2] * np.maximum(0.1, 1.0 + a_ui[:, 2] + (a_mods.leth - 1.0) - d_mods.enemy_leth_down)
        eff_d_stats[:, 2] = d_base[:, 2] * np.maximum(0.1, 1.0 + d_ui[:, 2] + (d_mods.leth - 1.0) - a_mods.enemy_leth_down)
        
        # Col 3: Health
        eff_a_stats[:, 3] = a_base[:, 3] * np.maximum(0.1, 1.0 + a_ui[:, 3] + (a_mods.hp - 1.0))
        eff_d_stats[:, 3] = d_base[:, 3] * np.maximum(0.1, 1.0 + d_ui[:, 3] + (d_mods.hp - 1.0))
        
        a_troops = np.copy(attacker.troops)
        d_troops = np.copy(current_garrison.troops)
        
        # --- TURN BASED BATTLE LOOP ---
        for r in range(1, max_rounds + 1):
            if np.sum(a_troops) <= 0 or np.sum(d_troops) <= 0:
                break
            
            try: a_frontline = np.where(d_troops > 0)[0][0]
            except IndexError: a_frontline = None
            try: d_frontline = np.where(a_troops > 0)[0][0]
            except IndexError: d_frontline = None
            
            round_a_dmg_mult = a_mods.dmg * (1.0 - d_mods.enemy_dmg_down)
            round_d_dmg_mult = d_mods.dmg * (1.0 - a_mods.enemy_dmg_down)
            
            a_shield_mult = np.ones(3)
            d_shield_mult = np.ones(3)
            
            for proc in a_mods.procs:
                if proc.get('type') == 'timed_shield':
                    if ((r - 1) % proc['interval']) < proc['duration']:
                        for target in proc['targets']: 
                            a_shield_mult[target] *= (1.0 - proc['val'])
            for proc in d_mods.procs:
                if proc.get('type') == 'timed_shield':
                    if ((r - 1) % proc['interval']) < proc['duration']:
                        for target in proc['targets']: 
                            d_shield_mult[target] *= (1.0 - proc['val'])

            round_a_atk_mult = 1.0
            round_d_atk_mult = 1.0
            a_taken_mult = 1.0 + d_mods.enemy_taken_up
            d_taken_mult = 1.0 + a_mods.enemy_taken_up
            a_reduct_proc = 0.0; d_reduct_proc = 0.0
            
            # Decay debuffs
            for debuff_list in [a_mods.active_debuffs, d_mods.active_debuffs]:
                for debuff in debuff_list[:]:
                    debuff['remaining_duration'] -= 1
                    if debuff['remaining_duration'] <= 0:
                        debuff_list.remove(debuff)

            for proc in a_mods.procs:
                if proc.get('type') != 'proc': continue
                if np.random.rand() < proc.get('chance', 0.0):
                    eff = proc['effect']
                    val = proc['val']
                    if eff == 'dmg': round_a_dmg_mult += (val - 1.0)
                    elif eff == 'atk': round_a_atk_mult += (val - 1.0)
                    elif eff == 'enemy_taken_up': d_taken_mult += (val - 1.0)
                    elif eff == 'dmg_reduction': a_reduct_proc += val
                    elif eff == 'double_strike': round_a_dmg_mult += (val - 1.0)
                    elif eff == 'enemy_leth_down':
                        d_mods.active_debuffs.append({'effect': 'enemy_leth_down', 'val': val, 'remaining_duration': proc.get('duration', 2), 'target_side': 'defender'})
                        
            for proc in d_mods.procs:
                if proc.get('type') != 'proc': continue
                if np.random.rand() < proc.get('chance', 0.0):
                    eff = proc['effect']
                    val = proc['val']
                    if eff == 'dmg': round_d_dmg_mult += (val - 1.0)
                    elif eff == 'atk': round_d_atk_mult += (val - 1.0)
                    elif eff == 'enemy_taken_up': a_taken_mult += (val - 1.0)
                    elif eff == 'dmg_reduction': d_reduct_proc += val
                    elif eff == 'double_strike': round_d_dmg_mult += (val - 1.0)
                    elif eff == 'enemy_leth_down':
                        a_mods.active_debuffs.append({'effect': 'enemy_leth_down', 'val': val, 'remaining_duration': proc.get('duration', 2), 'target_side': 'attacker'})
            
            final_a_reduct = max(0.1, a_mods.reduct - a_reduct_proc)
            final_d_reduct = max(0.1, d_mods.reduct - d_reduct_proc)
            
            # Temporary Lethality adjustments for active duration procs
            current_a_leth_debuff = sum(d['val'] for d in a_mods.active_debuffs if d['effect'] == 'enemy_leth_down')
            current_d_leth_debuff = sum(d['val'] for d in d_mods.active_debuffs if d['effect'] == 'enemy_leth_down')
            
            # --- ATTACKER SNAPSHOT ---
            d_loss_pool = np.zeros(3)
            for idx in range(3):
                if a_troops[idx] <= 0: continue
                # Attack * Lethality
                active_leth_mult = max(0.1, eff_a_stats[idx, 2] - current_a_leth_debuff)
                base_offensive_power = np.sqrt(a_troops[idx]) * (eff_a_stats[idx, 0] * round_a_atk_mult) * active_leth_mult * round_a_dmg_mult * a_mods.class_dmg[idx]
                
                if idx in [0, 2]: t_pos = a_frontline
                else: t_pos = 2 if (d_troops[2] > 0 and np.random.rand() < cav_backline_split) else a_frontline
                if t_pos is None or d_troops[t_pos] <= 0: continue
                
                squad_power = base_offensive_power * counter_matrix[idx, t_pos]
                if np.random.rand() < d_mods.dodge: squad_power *= 0.5
                
                # Defense * Health
                squad_defense_pool = eff_d_stats[t_pos, 1] * eff_d_stats[t_pos, 3]
                squad_losses = (squad_power / squad_defense_pool) * final_d_reduct * combat_scale * d_taken_mult * d_shield_mult[t_pos]
                d_loss_pool[t_pos] += squad_losses
                
            # --- DEFENDER SNAPSHOT ---
            a_loss_pool = np.zeros(3)
            for idx in range(3):
                if d_troops[idx] <= 0: continue
                active_leth_mult = max(0.1, eff_d_stats[idx, 2] - current_d_leth_debuff)
                base_offensive_power = np.sqrt(d_troops[idx]) * (eff_d_stats[idx, 0] * round_d_atk_mult) * active_leth_mult * round_d_dmg_mult * d_mods.class_dmg[idx]
                
                if idx in [0, 2]: t_pos = d_frontline
                else: t_pos = 2 if (a_troops[2] > 0 and np.random.rand() < cav_backline_split) else d_frontline
                if t_pos is None or a_troops[t_pos] <= 0: continue
                
                squad_power = base_offensive_power * counter_matrix[idx, t_pos]
                if np.random.rand() < a_mods.dodge: squad_power *= 0.5
                
                squad_defense_pool = eff_a_stats[t_pos, 1] * eff_a_stats[t_pos, 3]
                squad_losses = (squad_power / squad_defense_pool) * final_a_reduct * combat_scale * a_taken_mult * a_shield_mult[t_pos]
                a_loss_pool[t_pos] += squad_losses
                
            d_troops = np.maximum(0.0, d_troops - d_loss_pool)
            a_troops = np.maximum(0.0, a_troops - a_loss_pool)
            
        wave_logs.append({'attacker_surviving': a_troops, 'defender_surviving': d_troops})
        current_garrison.troops = d_troops
        
    return current_garrison, wave_logs