import numpy as np
import pandas as pd
import copy
import math

# Load the base stats database globally
try:
    TROOP_DB = pd.read_csv('troop_stats.csv')
except FileNotFoundError:
    TROOP_DB = None

def get_base_stats(troop_type, tier, tg_level):
    """Fetches [Attack, Defense, Lethality, Health] from troop_stats.csv or falls back cleanly."""
    if TROOP_DB is not None:
        try:
            row = TROOP_DB[(TROOP_DB['Type'] == troop_type) & 
                           (TROOP_DB['Tier'] == tier) & 
                           (TROOP_DB['TG'] == tg_level)]
            if not row.empty:
                return row[['Attack', 'Defense', 'Lethality', 'Health']].values[0].astype(float)
        except Exception:
            pass

    base_t10_tg5 = {
        'infantry': np.array([597.0, 10.0, 10.0, 1790.0]),
        'cavalry':  np.array([1790.0, 10.0, 10.0, 597.0]),
        'archers':  np.array([2387.0, 10.0, 10.0, 448.0])
    }
    scale = (1.20 ** (tier - 10)) * (1.045 ** (tg_level - 5))
    vec = base_t10_tg5.get(troop_type, base_t10_tg5['infantry']).copy()
    vec[0] *= scale
    vec[3] *= scale
    return vec

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

        types = ['infantry', 'cavalry', 'archers']
        self.true_base_stats = np.zeros((3, 4))
        for i, t_type in enumerate(types):
            self.true_base_stats[i] = get_base_stats(t_type, self.tier, self.tg_level)

        ui_pct = np.copy(self.bonus_stats_percentage)
        if self.widget_bonus > 0:
            ui_pct[:, 0] += self.widget_bonus
            ui_pct[:, 1] += self.widget_bonus

        self.ui_multipliers = 1.0 + (ui_pct / 100.0)

    def calculate_widget_bonus(self):
        total_bonus = 0.0
        for level in self.widget_levels:
            if level > 0:
                even_level = (level // 2) * 2
                total_bonus += 2.5 + (even_level / 2) * 2.5
        return total_bonus

    @property
    def stats(self):
        return self.bonus_stats_percentage

    def clone(self):
        return copy.deepcopy(self)

# =========================================================================
# --- HERO DATABASE ---
# =========================================================================
def load_hero_db():
    db = {}
    db['Amadeus'] = {'skill1': {'type': 'none'}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg', 'val': 0.50}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'atk', 'val': 0.15}}
    db['Helga'] = {'skill1': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg_reduction', 'val': 0.50}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    db['Saul'] = {'skill1': {'type': 'none'}, 'skill2': {'type': 'dmg_reduction', 'val': 0.0}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'atk', 'val': 0.15}}
    db['Jabel'] = {'skill1': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg_reduction', 'val': 0.40}, 'skill2': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg', 'val': 0.50}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    
    db['Zoe'] = {'skill1': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg', 'val': 0.40}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'proc', 'chance': 0.50, 'effect': 'enemy_taken_up', 'val': 0.50}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'atk', 'val': 0.10}}
    db['Marlin'] = {'skill1': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg', 'val': 0.50}, 'skill2': {'type': 'proc', 'chance': 0.20, 'effect': 'enemy_leth_down', 'val': 0.50, 'duration': 2}, 'skill3': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg', 'val': 0.50}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    db['Hilde'] = {'skill1': {'type': 'none'}, 'skill2': {'type': 'proc', 'chance': 0.25, 'effect': 'dmg', 'val': 1.00}, 'skill3': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg_reduction', 'val': 0.50}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'dodge', 'val': 0.05}}
    
    db['Petra'] = {'skill1': {'type': 'proc', 'chance': 0.50, 'effect': 'enemy_taken_up', 'val': 0.50}, 'skill2': {'type': 'proc', 'chance': 0.50, 'effect': 'none'}, 'skill3': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg_reduction', 'val': 0.50}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'atk', 'val': 0.15}}
    db['Eric'] = {'skill1': {'type': 'none'}, 'skill2': {'type': 'dmg_reduction', 'val': 0.20}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'defense', 'val': 0.15}}
    db['Jaegar'] = {'skill1': {'type': 'proc', 'chance': 0.20, 'effect': 'dmg', 'val': 0.40}, 'skill2': {'type': 'proc', 'chance': 0.20, 'effect': 'enemy_leth_down', 'val': 0.50, 'duration': 2}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'health', 'val': 0.15}}
    
    db['Alcar'] = {'skill1': {'type': 'timed_shield', 'interval': 5, 'duration': 2, 'val': 0.70, 'targets': [0, 2]}, 'skill2': {'type': 'class_dmg_buff', 'buffs': [1.00, 0.10, 0.10]}, 'skill3': [{'type': 'class_dmg_buff', 'buffs': [0.60, 0.0, 0.0]}, {'type': 'enemy_taken_up', 'val': 0.25}], 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'health', 'val': 0.15}}
    db['Rosa'] = {'skill1': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg', 'val': 0.50}, 'skill2': {'type': 'enemy_dmg_down', 'val': 0.20}, 'skill3': {'type': 'class_atk_buff', 'target_class': 2, 'val': 0.30}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    db['Margot'] = {'skill1': {'type': 'none'}, 'skill2': {'type': 'dodge_chance', 'val': 0.20}, 'skill3': {'type': 'proc', 'chance': 0.25, 'effect': 'double_strike', 'val': 1.00}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'lethality', 'val': 0.15}}

    # Gen 5: Long Fei, Vivian, Thrud[cite: 13]
    db['Long Fei'] = {
        'skill1': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg_reduction', 'val': 0.50},
        'skill2': {'type': 'none'},
        'skill3': {'type': 'proc', 'chance': 0.25, 'effect': 'dmg', 'val': 1.00},
        'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'atk', 'val': 0.15}
    }
    db['Vivian'] = {
        'skill1': {'type': 'enemy_taken_up', 'val': 0.25},                               # +25% Damage Taken[cite: 13]
        'skill2': [
            {'type': 'periodic_proc', 'interval': 2, 'effect': 'dmg', 'val': 1.00},      # Trigger more frequently for burst scaling[cite: 13]
            {'type': 'periodic_proc', 'interval': 2, 'effect': 'enemy_taken_up', 'val': 0.15}
        ],
        'skill3': {'type': 'periodic_proc', 'interval': 2, 'target_class': 2, 'effect': 'dmg', 'val': 0.60}, # Archer bonus[cite: 13]
        'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'defense', 'val': 0.15}
    }
    db['Thrud'] = {
        'skill1': [
            {'type': 'dmg_reduction', 'val': 0.15},
            {'type': 'class_dmg_buff', 'buffs': [0.15, 0.0, 0.15]}
        ],
        'skill2': {'type': 'proc', 'chance': 0.20, 'effect': 'dmg', 'val': 1.00},
        'skill3': [
            {'type': 'periodic_proc', 'interval': 2, 'effect': 'dmg', 'val': 0.25},
            {'type': 'periodic_proc', 'interval': 2, 'effect': 'dmg_reduction', 'val': 0.25, 'duration': 2}
        ],
        'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}
    }

    # Joiners
    db['Gordon'] = {'skill1': {'type': 'none'}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    db['Fahd'] = {'skill1': {'type': 'enemy_dmg_down', 'val': 0.20}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    db['Chenko'] = {'skill1': {'type': 'none'}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    db['Yaenwoo'] = {'skill1': {'type': 'none'}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    db['Howard'] = {'skill1': {'type': 'dmg_reduction', 'val': 0.20}, 'skill2': {'type': 'enemy_atk_down', 'val': 0.20}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    db['Amane'] = {'skill1': {'type': 'none'}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    db['Quinn'] = {'skill1': {'type': 'dmg_reduction', 'val': 0.20}, 'skill2': {'type': 'dmg', 'val': 0.50}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    return db

class SideCombatState:
    def __init__(self):
        self.procs = []
        self.dodge = 0.0
        self.base_enemy_taken_up = 0.0
        self.base_dmg_reduction = 1.0
        self.class_atk_mod = np.ones(3)
        self.class_dmg_up = np.zeros(3)

    def register_skills_from_hero(self, hero_dict):
        if not hero_dict: return
        for s_key in ['skill1', 'skill2', 'skill3']:
            sk = hero_dict.get(s_key)
            if not sk: continue
            if isinstance(sk, list):
                for sub in sk: self._parse_single_skill(sub)
            else: self._parse_single_skill(sk)

    def register_joiner_skill(self, hero_dict):
        if not hero_dict or 'skill1' not in hero_dict: return
        sk = hero_dict['skill1']
        if isinstance(sk, list):
            for sub in sk: self._parse_single_skill(sub)
        else: self._parse_single_skill(sk)

    def _parse_single_skill(self, skill):
        stype = skill.get('type')
        val = skill.get('val', 0.0)
        
        if stype in ['dodge', 'dodge_chance']:
            self.dodge = 1.0 - ((1.0 - self.dodge) * (1.0 - val))
        elif stype == 'class_atk_buff':
            self.class_atk_mod[skill.get('target_class', 2)] += val
        elif stype == 'class_dmg_buff':
            self.class_dmg_up += np.array(skill.get('buffs', [0.0, 0.0, 0.0]))
        elif stype == 'enemy_taken_up':
            self.base_enemy_taken_up += val
        elif stype == 'dmg_reduction':
            self.base_dmg_reduction *= max(0.0, 1.0 - val)
        elif stype in ['proc', 'periodic_proc', 'timed_shield']:
            self.procs.append(skill)

    def roll_round_procs(self, round_idx):
        # BASE DAMAGE MULTIPLIER MUST START AT 1.0 (Standard 100% output)
        round_dmg_bonus = 1.0
        class_dmg_bonus = np.zeros(3)
        enemy_taken_bonus = self.base_enemy_taken_up
        round_reduct = self.base_dmg_reduction
        
        for proc in self.procs:
            ptype = proc.get('type')
            triggered = False
            
            if ptype == 'proc' and np.random.rand() < proc.get('chance', 0.0):
                triggered = True
            elif ptype == 'periodic_proc' and (round_idx % proc.get('interval', 2) == 0):
                triggered = True
                
            if triggered:
                eff = proc.get('effect')
                val = proc.get('val', 0.0)
                t_class = proc.get('target_class', None)
                
                if eff in ['dmg', 'double_strike']:
                    if t_class is not None:
                        class_dmg_bonus[t_class] += val
                    else:
                        round_dmg_bonus += val
                elif eff == 'enemy_taken_up':
                    enemy_taken_bonus += val
                elif eff == 'dmg_reduction':
                    round_reduct *= max(0.0, 1.0 - val)
                    
        return round_dmg_bonus, class_dmg_bonus, enemy_taken_bonus, round_reduct

# =========================================================================
# --- COMPLETE SIMULATOR ENGINE ---
# =========================================================================
def kingshot_multirally_sim2(rally_waves, garrison, max_rounds=200):
    cav_backline_split = 0.20
    hero_db = load_hero_db()
    current_garrison = garrison.clone()

    counter_matrix = np.array([
        [1.0, 1.1, 0.9],
        [0.9, 1.0, 1.1],
        [1.1, 0.9, 1.0]
    ])

    wave_logs = []

    for wave_data in rally_waves:
        attacker = wave_data.clone()

        a_state = SideCombatState()
        d_state = SideCombatState()

        for h_name in attacker.leader_heroes:
            if h_name in hero_db:
                a_state.register_skills_from_hero(hero_db[h_name])
                h_def = hero_db[h_name]
                if h_def.get('widget', {}).get('has_widget') and h_def['widget']['scenario'] == 'rally':
                    w_type = h_def['widget']['type']
                    w_val = h_def['widget']['val']
                    if w_type == 'lethality': attacker.ui_multipliers[:, 2] += w_val
                    elif w_type == 'defense': attacker.ui_multipliers[:, 1] += w_val
                    elif w_type == 'atk': attacker.ui_multipliers[:, 0] += w_val

        for h_name in attacker.supporter_heroes[:4]:
            if h_name in hero_db: a_state.register_joiner_skill(hero_db[h_name])

        for h_name in current_garrison.leader_heroes:
            if h_name in hero_db:
                d_state.register_skills_from_hero(hero_db[h_name])
                h_def = hero_db[h_name]
                if h_def.get('widget', {}).get('has_widget') and h_def['widget']['scenario'] == 'garrison':
                    w_type = h_def['widget']['type']
                    w_val = h_def['widget']['val']
                    if w_type == 'lethality': current_garrison.ui_multipliers[:, 2] += w_val
                    elif w_type == 'defense': current_garrison.ui_multipliers[:, 1] += w_val
                    elif w_type == 'atk': current_garrison.ui_multipliers[:, 0] += w_val

        for h_name in current_garrison.supporter_heroes[:4]:
            if h_name in hero_db: d_state.register_joiner_skill(hero_db[h_name])

        a_att_power = (attacker.true_base_stats[:, 0] * attacker.ui_multipliers[:, 0] * (1.0 + a_state.class_atk_mod) *
                       attacker.true_base_stats[:, 2] * attacker.ui_multipliers[:, 2]) / 100.0
        d_att_power = (current_garrison.true_base_stats[:, 0] * current_garrison.ui_multipliers[:, 0] * (1.0 + d_state.class_atk_mod) *
                       current_garrison.true_base_stats[:, 2] * current_garrison.ui_multipliers[:, 2]) / 100.0

        a_def_pool = (attacker.true_base_stats[:, 1] * attacker.ui_multipliers[:, 1] * 
                      attacker.true_base_stats[:, 3] * attacker.ui_multipliers[:, 3]) / 100.0
        d_def_pool = (current_garrison.true_base_stats[:, 1] * current_garrison.ui_multipliers[:, 1] * 
                      current_garrison.true_base_stats[:, 3] * current_garrison.ui_multipliers[:, 3]) / 100.0

        a_troops = np.copy(attacker.troops)
        d_troops = np.copy(current_garrison.troops)

        army_min = min(np.sum(a_troops), np.sum(d_troops))

        for r in range(1, max_rounds + 1):
            if np.sum(a_troops) <= 0 or np.sum(d_troops) <= 0 or army_min <= 0:
                break

            d_alive = np.where(d_troops > 0)[0]
            a_alive = np.where(a_troops > 0)[0]
            if len(d_alive) == 0 or len(a_alive) == 0:
                break

            d_front = d_alive[0]
            a_front = a_alive[0]

            a_dmg_bonus, a_class_dmg, a_taken_bonus, a_reduct = a_state.roll_round_procs(r)
            d_dmg_bonus, d_class_dmg, d_taken_bonus, d_reduct = d_state.roll_round_procs(r)

            for idx in range(3):
                if np.sum(a_troops) <= 0 or np.sum(d_troops) <= 0:
                    break

                if a_troops[idx] > 0:
                    d_target = d_front
                    if idx == 1 and len(d_alive) > 1 and np.random.rand() < cav_backline_split:
                        d_target = d_alive[1]

                    army_factor_a = math.sqrt(a_troops[idx] * army_min)
                    type_bonus_a = counter_matrix[idx, d_target]
                    class_mult_a = 1.0 + a_state.class_dmg_up[idx] + a_class_dmg[idx]
                    total_dmg_mult_a = a_dmg_bonus * class_mult_a * (1.0 + d_taken_bonus)

                    dmg_a = (army_factor_a * (a_att_power[idx] / d_def_pool[d_target]) * type_bonus_a * total_dmg_mult_a) / 100.0
                    dmg_a *= d_reduct
                    if np.random.rand() < d_state.dodge: dmg_a *= 0.5
                    d_troops[d_target] = max(0.0, d_troops[d_target] - math.ceil(dmg_a))

                d_alive = np.where(d_troops > 0)[0]
                if len(d_alive) == 0: break
                d_front = d_alive[0]

                if d_troops[idx] > 0:
                    a_target = a_front
                    if idx == 1 and len(a_alive) > 1 and np.random.rand() < cav_backline_split:
                        a_target = a_alive[1]

                    army_factor_d = math.sqrt(d_troops[idx] * army_min)
                    type_bonus_d = counter_matrix[idx, a_target]
                    class_mult_d = 1.0 + d_state.class_dmg_up[idx] + d_class_dmg[idx]
                    total_dmg_mult_d = d_dmg_bonus * class_mult_d * (1.0 + a_taken_bonus)

                    dmg_d = (army_factor_d * (d_att_power[idx] / a_def_pool[a_target]) * type_bonus_d * total_dmg_mult_d) / 100.0
                    dmg_d *= a_reduct
                    if np.random.rand() < a_state.dodge: dmg_d *= 0.5
                    a_troops[a_target] = max(0.0, a_troops[a_target] - math.ceil(dmg_d))

                a_alive = np.where(a_troops > 0)[0]
                if len(a_alive) == 0: break
                a_front = a_alive[0]

        wave_logs.append({
            'attacker_surviving': a_troops,
            'defender_surviving': d_troops
        })
        current_garrison.troops = d_troops

    return current_garrison, wave_logs