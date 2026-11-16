import numpy as np
import pandas as pd
import copy
import math

# Load the base stats database globally
try:
    TROOP_DB = pd.read_csv('troop_stats.csv')
except FileNotFoundError:
    print("WARNING: troop_stats.csv not found. Using built-in scaling fallback.")
    TROOP_DB = None

def get_base_stats(troop_type, tier, tg_level):
    """Fetches [Attack, Defense, Lethality, Health] from troop_stats.csv."""
    if TROOP_DB is not None:
        try:
            row = TROOP_DB[(TROOP_DB['Type'] == troop_type) & 
                           (TROOP_DB['Tier'] == tier) & 
                           (TROOP_DB['TG'] == tg_level)]
            if not row.empty:
                return row[['Attack', 'Defense', 'Lethality', 'Health']].values[0].astype(float)
        except Exception:
            pass

    # Fallback matching the exact CSV table layout
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

        # Store UI percentages cleanly for direct scaling
        self.ui_multipliers = 1.0 + (ui_pct / 100.0)
        self.final_combat_stats = self.true_base_stats * self.ui_multipliers

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
# --- SKILLMOD & OP-CODE ENGINE (BATTLE REPORT COMPATIBLE) ---
# =========================================================================
def map_skill_to_ops(skill):
    """
    Translates a hero skill dictionary into standardized tuples.
    Ignores static stats (atk, lethality, defense, health) since they are 
    already baked into the battle report UI percentage numbers.
    """
    if isinstance(skill, list):
        out = []
        for s in skill:
            out.extend(map_skill_to_ops(s))
        return out

    sk_type = skill.get('type', 'none')
    if sk_type in ['none', 'atk', 'lethality', 'defense', 'health']:
        return []

    if sk_type == 'dmg':             return [('DamageUp', 102, skill.get('val', 0.0), None)]
    if sk_type == 'dmg_reduction':   return [('DefenseUp', 111, skill.get('val', 0.0), None)]
    if sk_type == 'enemy_dmg_down':  return [('OppDamageDown', 201, skill.get('val', 0.0), None)]
    if sk_type == 'enemy_atk_down':  return [('OppDamageDown', 202, skill.get('val', 0.0), None)]
    if sk_type == 'enemy_leth_down': return [('OppDamageDown', 203, skill.get('val', 0.0), None)]
    if sk_type == 'enemy_taken_up':  return [('OppDefenseDown', 211, skill.get('val', 0.0), None)]

    if sk_type in ['dodge', 'dodge_chance', 'class_dmg_buff', 'class_atk_buff', 'timed_shield', 'proc']:
        return [('Special', 0, 0.0, skill)]

    return []

class SideSkillState:
    def __init__(self):
        self.base_ops = {
            'DamageUp': {},
            'DefenseUp': {},
            'OppDamageDown': {},
            'OppDefenseDown': {}
        }
        self.class_dmg_up = np.zeros(3)
        self.dodge = 0.0
        self.procs = []
        self.timed_shields = []
        self.active_durations = []

    def add_op(self, family, op_code, val):
        if val == 0.0:
            return
        self.base_ops[family][op_code] = self.base_ops[family].get(op_code, 0.0) + val

    def register_skill(self, skill):
        for family, op_code, val, meta in map_skill_to_ops(skill):
            if family != 'Special':
                self.add_op(family, op_code, val)
            else:
                st_type = meta.get('type')
                if st_type in ['dodge', 'dodge_chance']:
                    v = meta.get('val', 0.0)
                    self.dodge = 1.0 - ((1.0 - self.dodge) * (1.0 - v))
                elif st_type == 'class_atk_buff':
                    self.class_dmg_up[meta.get('target_class', 0)] += meta.get('val', 0.0)
                elif st_type == 'class_dmg_buff':
                    self.class_dmg_up += np.array(meta.get('buffs', [0.0, 0.0, 0.0]))
                elif st_type == 'timed_shield':
                    self.timed_shields.append(meta)
                elif st_type == 'proc':
                    self.procs.append(meta)

    def roll_round_ops(self, round_idx):
        round_ops = {fam: dict(ops) for fam, ops in self.base_ops.items()}

        for item in self.active_durations[:]:
            fam, op, val = item['family'], item['op'], item['val']
            round_ops[fam][op] = round_ops[fam].get(op, 0.0) + val
            item['remaining'] -= 1
            if item['remaining'] <= 0:
                self.active_durations.remove(item)

        for proc in self.procs:
            if np.random.rand() < proc.get('chance', 0.0):
                eff = proc.get('effect')
                raw_val = proc.get('val', 0.0)
                bonus_val = (raw_val - 1.0) if raw_val >= 1.0 else raw_val
                duration = proc.get('duration', 1)

                fam, op = None, None
                if eff in ['dmg', 'double_strike']: fam, op = 'DamageUp', 103
                elif eff == 'atk':                  fam, op = 'DamageUp', 102
                elif eff == 'enemy_taken_up':       fam, op = 'OppDefenseDown', 211
                elif eff == 'dmg_reduction':        fam, op = 'DefenseUp', 111
                elif eff == 'enemy_leth_down':      fam, op = 'OppDamageDown', 203

                if fam is not None and bonus_val > 0.0:
                    round_ops[fam][op] = round_ops[fam].get(op, 0.0) + bonus_val
                    if duration > 1:
                        self.active_durations.append({
                            'family': fam, 'op': op, 'val': bonus_val, 'remaining': duration - 1
                        })

        fam_mults = {}
        for fam, ops in round_ops.items():
            prod = 1.0
            for op_sum in ops.values():
                prod *= max(0.1, 1.0 + op_sum)
            fam_mults[fam] = prod

        shield_mult = np.ones(3)
        for sh in self.timed_shields:
            if ((round_idx - 1) % sh['interval']) < sh['duration']:
                for t in sh['targets']:
                    shield_mult[t] *= (1.0 - sh['val'])

        return fam_mults, shield_mult

# =========================================================================
# --- HERO DATABASE ---
# =========================================================================
def load_hero_db():
    db = {}
    db['Amadeus'] = {'skill1': {'type': 'lethality', 'val': 0.25}, 'skill2': {'type': 'atk', 'val': 0.25}, 'skill3': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg', 'val': 1.50}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'atk', 'val': 0.15}}
    db['Helga'] = {'skill1': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg_reduction', 'val': 0.50}, 'skill2': {'type': 'atk', 'val': 0.25}, 'skill3': {'type': 'lethality', 'val': 0.25}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    db['Saul'] = {'skill1': [{'type': 'health', 'val': 0.15}, {'type': 'defense', 'val': 0.10}], 'skill2': {'type': 'dmg_reduction', 'val': 0.0}, 'skill3': {'type': 'lethality', 'val': 0.25}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'atk', 'val': 0.15}}
    db['Jabel'] = {'skill1': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg_reduction', 'val': 0.40}, 'skill2': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg', 'val': 1.50}, 'skill3': {'type': 'dmg', 'val': 0.25}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    
    db['Zoe'] = {'skill1': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg', 'val': 1.40}, 'skill2': {'type': 'atk', 'val': 0.25}, 'skill3': {'type': 'proc', 'chance': 0.50, 'effect': 'enemy_taken_up', 'val': 1.50}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'atk', 'val': 0.10}}
    db['Marlin'] = {'skill1': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg', 'val': 1.50}, 'skill2': {'type': 'proc', 'chance': 0.20, 'effect': 'enemy_leth_down', 'val': 0.50, 'duration': 2}, 'skill3': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg', 'val': 1.50}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    db['Hilde'] = {'skill1': [{'type': 'atk', 'val': 0.15}, {'type': 'defense', 'val': 0.10}], 'skill2': {'type': 'proc', 'chance': 0.25, 'effect': 'dmg', 'val': 2.00}, 'skill3': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg_reduction', 'val': 0.50}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'dodge', 'val': 0.05}}
    
    db['Petra'] = {'skill1': {'type': 'proc', 'chance': 0.50, 'effect': 'enemy_taken_up', 'val': 1.50}, 'skill2': {'type': 'proc', 'chance': 0.50, 'effect': 'atk', 'val': 1.50}, 'skill3': {'type': 'proc', 'chance': 0.50, 'effect': 'dmg_reduction', 'val': 0.50}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'atk', 'val': 0.15}}
    db['Eric'] = {'skill1': {'type': 'enemy_atk_down', 'val': 0.20}, 'skill2': {'type': 'dmg_reduction', 'val': 0.20}, 'skill3': {'type': 'health', 'val': 0.25}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'defense', 'val': 0.15}}
    db['Jaegar'] = {'skill1': {'type': 'proc', 'chance': 0.20, 'effect': 'dmg', 'val': 1.40}, 'skill2': {'type': 'proc', 'chance': 0.20, 'effect': 'enemy_leth_down', 'val': 0.50, 'duration': 2}, 'skill3': {'type': 'health', 'val': 0.25}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'health', 'val': 0.15}}
    
    db['Alcar'] = {'skill1': {'type': 'timed_shield', 'interval': 5, 'duration': 2, 'val': 0.70, 'targets': [0, 2]}, 'skill2': {'type': 'class_dmg_buff', 'buffs': [1.00, 0.10, 0.10]}, 'skill3': [{'type': 'class_dmg_buff', 'buffs': [0.60, 0.0, 0.0]}, {'type': 'enemy_taken_up', 'val': 0.25}], 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'health', 'val': 0.15}}
    db['Rosa'] = {'skill1': {'type': 'proc', 'chance': 0.40, 'effect': 'dmg', 'val': 1.50}, 'skill2': {'type': 'enemy_dmg_down', 'val': 0.20}, 'skill3': {'type': 'class_atk_buff', 'target_class': 2, 'val': 0.30}, 'widget': {'has_widget': True, 'scenario': 'rally', 'type': 'lethality', 'val': 0.15}}
    db['Margot'] = {'skill1': {'type': 'atk', 'val': 0.25}, 'skill2': {'type': 'dodge_chance', 'val': 0.20}, 'skill3': {'type': 'proc', 'chance': 0.25, 'effect': 'double_strike', 'val': 2.00}, 'widget': {'has_widget': True, 'scenario': 'garrison', 'type': 'lethality', 'val': 0.15}}

    db['Gordon'] = {'skill1': {'type': 'health', 'val': 0.25}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'atk', 'val': 0.25}, 'widget': {'has_widget': False}}
    db['Fahd'] = {'skill1': {'type': 'enemy_dmg_down', 'val': 0.20}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    db['Chenko'] = {'skill1': {'type': 'lethality', 'val': 0.25}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'health', 'val': 0.15}, 'widget': {'has_widget': False}}
    db['Yaenwoo'] = {'skill1': {'type': 'lethality', 'val': 0.25}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'health', 'val': 0.15}, 'widget': {'has_widget': False}}
    db['Howard'] = {'skill1': {'type': 'dmg_reduction', 'val': 0.20}, 'skill2': {'type': 'enemy_atk_down', 'val': 0.20}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    db['Amane'] = {'skill1': {'type': 'atk', 'val': 0.25}, 'skill2': {'type': 'none'}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    db['Quinn'] = {'skill1': {'type': 'dmg_reduction', 'val': 0.20}, 'skill2': {'type': 'dmg', 'val': 0.50}, 'skill3': {'type': 'none'}, 'widget': {'has_widget': False}}
    return db

# =========================================================================
# --- CORE COMBAT ENGINE FUNCTION ---
# =========================================================================
def kingshot_multirally_sim2(rally_waves, garrison, max_rounds=200):
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

        a_skills = SideSkillState()
        d_skills = SideSkillState()

        for hero_name in attacker.leader_heroes:
            if hero_name and hero_name != "None" and hero_name in hero_db:
                h = hero_db[hero_name]
                a_skills.register_skill(h['skill1'])
                a_skills.register_skill(h['skill2'])
                a_skills.register_skill(h['skill3'])
                if h.get('widget', {}).get('has_widget') and h['widget']['scenario'] == 'rally':
                    a_skills.register_skill(h['widget'])

        for hero_name in current_garrison.leader_heroes:
            if hero_name and hero_name != "None" and hero_name in hero_db:
                h = hero_db[hero_name]
                d_skills.register_skill(h['skill1'])
                d_skills.register_skill(h['skill2'])
                d_skills.register_skill(h['skill3'])
                if h.get('widget', {}).get('has_widget') and h['widget']['scenario'] == 'garrison':
                    d_skills.register_skill(h['widget'])

        for hero_name in attacker.supporter_heroes[:4]:
            if hero_name and hero_name != "None" and hero_name in hero_db:
                a_skills.register_skill(hero_db[hero_name]['skill1'])

        for hero_name in current_garrison.supporter_heroes[:4]:
            if hero_name and hero_name != "None" and hero_name in hero_db:
                d_skills.register_skill(hero_db[hero_name]['skill1'])

# Use true Base Attack (Col 0) and Base Health (Col 3), scaled directly by UI Atk% and HP%, 
        # and scale Offense/Defense pools using direct UI Atk/Leth and Def/HP products:
        a_att_per_troop = (attacker.true_base_stats[:, 0] * attacker.ui_multipliers[:, 0] * 
                           attacker.true_base_stats[:, 2] * attacker.ui_multipliers[:, 2]) / 100.0
        a_def_per_troop = (attacker.true_base_stats[:, 1] * attacker.ui_multipliers[:, 1] * 
                           attacker.true_base_stats[:, 3] * attacker.ui_multipliers[:, 3]) / 100.0

        d_att_per_troop = (current_garrison.true_base_stats[:, 0] * current_garrison.ui_multipliers[:, 0] * 
                           current_garrison.true_base_stats[:, 2] * current_garrison.ui_multipliers[:, 2]) / 100.0
        d_def_per_troop = (current_garrison.true_base_stats[:, 1] * current_garrison.ui_multipliers[:, 1] * 
                           current_garrison.true_base_stats[:, 3] * current_garrison.ui_multipliers[:, 3]) / 100.0

        a_troops = np.copy(attacker.troops)
        d_troops = np.copy(current_garrison.troops)

        army_min = min(np.sum(a_troops), np.sum(d_troops))

        for r in range(1, max_rounds + 1):
            if np.sum(a_troops) <= 0 or np.sum(d_troops) <= 0 or army_min <= 0:
                break

            a_fams, a_shield = a_skills.roll_round_ops(r)
            d_fams, d_shield = d_skills.roll_round_ops(r)

            skill_mod_a_to_d = (a_fams['DamageUp'] * a_fams['OppDefenseDown']) / (d_fams['OppDamageDown'] * d_fams['DefenseUp'])
            skill_mod_d_to_a = (d_fams['DamageUp'] * d_fams['OppDefenseDown']) / (a_fams['OppDamageDown'] * a_fams['DefenseUp'])

            for idx in range(3):
                if np.sum(a_troops) <= 0 or np.sum(d_troops) <= 0:
                    break

                d_alive = np.where(d_troops > 0)[0]
                a_alive = np.where(a_troops > 0)[0]
                if len(d_alive) == 0 or len(a_alive) == 0:
                    break
                
                a_idx = idx if a_troops[idx] > 0 else a_alive[0]
                d_idx = idx if d_troops[idx] > 0 else d_alive[0]

                a_target_front = d_alive[0]
                d_target_front = a_alive[0]

                # --- Attacker Attack ---
                d_kills = 0.0
                d_target = a_target_front
                if a_troops[a_idx] > 0:
                    if a_idx == 1 and d_troops[2] > 0 and np.random.rand() < cav_backline_split:
                        d_target = 2
                    army_factor_a = math.sqrt(a_troops[a_idx] * army_min)
                    class_skill_a = skill_mod_a_to_d * (1.0 + a_skills.class_dmg_up[a_idx])
                    type_bonus_a = counter_matrix[a_idx, d_target]

                    dmg_a = (army_factor_a * (a_att_per_troop[a_idx] / d_def_per_troop[d_target])
                             * type_bonus_a * class_skill_a) / 100.0
                    if np.random.rand() < d_skills.dodge:
                        dmg_a *= 0.5
                    d_kills = math.ceil(dmg_a * d_shield[d_target])

                # --- Defender Counterattack ---
                a_kills = 0.0
                a_target = d_target_front
                if d_troops[d_idx] > 0:
                    if d_idx == 1 and a_troops[2] > 0 and np.random.rand() < cav_backline_split:
                        a_target = 2
                    army_factor_d = math.sqrt(d_troops[d_idx] * army_min)
                    class_skill_d = skill_mod_d_to_a * (1.0 + d_skills.class_dmg_up[d_idx])
                    type_bonus_d = counter_matrix[d_idx, a_target]

                    dmg_d = (army_factor_d * (d_att_per_troop[d_idx] / a_def_per_troop[a_target])
                             * type_bonus_d * class_skill_d) / 100.0
                    if np.random.rand() < a_skills.dodge:
                        dmg_d *= 0.5
                    a_kills = math.ceil(dmg_d * a_shield[a_target])

                if d_kills > 0:
                    d_troops[d_target] = max(0.0, d_troops[d_target] - d_kills)
                if a_kills > 0:
                    a_troops[a_target] = max(0.0, a_troops[a_target] - a_kills)

        wave_logs.append({
            'attacker_surviving': a_troops,
            'defender_surviving': d_troops
        })
        current_garrison.troops = d_troops

    return current_garrison, wave_logs