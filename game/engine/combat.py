"""Combat module - Phase 3/Defense: Hit chance & damage formulas with defense resolution."""

from typing import Optional, Dict, Any

def calculate_hit_chance(
    attacker: Any,
    defender: Any,
    attack_type: str,
    defense_type: Optional[str] = None,
    facing_bonus: float = 0.0,
    bounce_bonus: float = 0.0,
    pattern_bonus: float = 0.0,
    attacker_df_multipliers: Optional[Dict[str, float]] = None,
    attacker_haki_obs_effectiveness: float = 0.0,
    defender_haki_obs_effectiveness: float = 0.0,
    is_defense_phase: bool = False
) -> float:
    """
    Calculate final hit chance per Rule Update.md Section 7.7.
    Returns value in range [0.05, 0.95].
    """
    # Base hit chance
    base = 0.66
    
    # Step 1: Attack type modifier
    hit_mod = 0.0
    if attack_type == "quick":
        hit_mod += 0.25
    elif attack_type == "heavy":
        hit_mod -= 0.25
    
    # Step 2: Defense type modifier (if defense phase)
    if defense_type:
        if defense_type == "evade":
            hit_mod -= 0.25
        elif defense_type in ("defend", "counter"):
            hit_mod += 0.25
    
    # Step 3: Universal defensive dodge bonus (defense phase only)
    dodge_mod = 0.0
    if is_defense_phase and defense_type:
        # Convert offensive bonuses to dodge
        dodge_mod += min(facing_bonus, 0.15)
        dodge_mod += min(bounce_bonus * 0.4, 0.10)
        dodge_mod += min(pattern_bonus * 0.5, 0.125)  # Half pattern bonus for dodge
    
    # Step 4: Stat nullification
    stat_null = (attacker.speed - defender.reaction) * 0.0015
    ci = getattr(attacker, 'combat_instinct', 0)
    opp_ci = getattr(defender, 'combat_instinct', 0)
    ci_null = (ci - opp_ci) * 0.0015
    aura = getattr(attacker, 'aura', 0)
    will = getattr(defender, 'willpower', 0)
    aura_null = (aura - will) * 0.0010
    
    # Offensive bonuses (attack phase only)
    offensive_hit = 0.0
    if not is_defense_phase:
        offensive_hit += min(facing_bonus, 0.15)
        offensive_hit += min(bounce_bonus * 0.4, 0.10)
        offensive_hit += min(pattern_bonus, 0.25)
    
    # Uncancelable bonuses
    ci_uncancelable = ci * 0.0005
    aura_uncancelable = aura * 0.0003
    
    # DF component
    if attacker_df_multipliers:
        effective_speed = attacker.speed * attacker_df_multipliers.get('speed_multiplier', 1.0)
        df_component = (effective_speed - defender.reaction - attacker.speed + defender.reaction) * 0.0015
    else:
        df_component = 0.0
    
    # Step 5: Haki observation (dodge for defender on defense)
    haki_obs_hit = 0.0
    if is_defense_phase:
        # Defender's observation adds to dodge
        dodge_mod += defender_haki_obs_effectiveness * 0.30
    else:
        # Attacker's observation adds to hit
        haki_obs_hit = attacker_haki_obs_effectiveness * 0.30
    
    # Final calculation
    total = (base + hit_mod + dodge_mod + stat_null + ci_null + aura_null + offensive_hit +
             ci_uncancelable + aura_uncancelable + df_component + haki_obs_hit)
    
    # Clamp to [5%, 95%]
    return max(0.05, min(0.95, total))

def calculate_damage(
    attacker: Any,
    defender: Any,
    base_damage: int,
    attack_type: str,
    defense_type: Optional[str] = None,
    facing_bonus: float = 0.0,
    bounce_bonus: float = 0.0,
    pattern_bonus: float = 0.0,
    attacker_df_multipliers: Optional[Dict[str, float]] = None,
    attacker_haki_armament_effectiveness: float = 0.0,
    defender_haki_armament_effectiveness: float = 0.0,
    is_defense_phase: bool = False
) -> int:
    """
    Calculate final damage per Rule Update.md Section 7.8.
    Returns integer damage with minimum floor of 1.
    """
    # Step 1: Base damage with attack/defense modifiers
    damage_mod = 0.0
    if attack_type == "quick":
        damage_mod -= 0.50
    elif attack_type == "heavy":
        damage_mod += 0.50
    
    if defense_type:
        if defense_type == "evade":
            damage_mod += 0.50
        elif defense_type == "defend":
            damage_mod -= 0.50
        elif defense_type == "counter":
            damage_mod += 0.50
    
    base_damage_mod = base_damage * (1.0 + damage_mod)
    
    # Step 2: Stat multipliers
    stat_multiplier = 1.0 + (attacker.strength - defender.defense) * 0.0015
    
    aura = getattr(attacker, 'aura', 0)
    will = getattr(defender, 'willpower', 0)
    aura_mod = 1.0 + (aura - will) * 0.0015 + aura * 0.0005
    
    will_reduction = 1.0 - will * 0.0010
    
    # DF component
    if attacker_df_multipliers:
        effective_strength = attacker.strength * attacker_df_multipliers.get('damage_multiplier', 1.0)
        df_comp = 1.0 + (effective_strength - defender.defense) * 0.0015 - (attacker.strength - defender.defense) * 0.0015
    else:
        df_comp = 1.0
    
    # Step 3: Position bonuses (offensive)
    offensive_multiplier = 1.0
    if is_defense_phase and defense_type:
        # Defense phase: bonuses converted to damage reduction
        dmg_reduction = 0.0
        dmg_reduction += min(facing_bonus, 0.15)
        dmg_reduction += min(bounce_bonus * 0.4, 0.10)
        dmg_reduction += min(pattern_bonus * 0.5, 0.125)  # Half pattern bonus
        offensive_multiplier = 1.0 - dmg_reduction
    else:
        # Attack phase: offensive bonuses
        bonus_sum = min(facing_bonus, 0.15) + min(bounce_bonus * 0.4, 0.10) + min(pattern_bonus, 0.25)
        offensive_multiplier = 1.0 + bonus_sum
    
    # Step 4: Defensive multipliers (Haki armament)
    haki_dmg_boost = 1.0
    haki_defense_reduction = 1.0
    
    if is_defense_phase and defense_type == "counter":
        # Counter: attacker's armament boosts counter damage
        haki_dmg_boost = 1.0 + attacker_haki_armament_effectiveness * 0.30
    elif not is_defense_phase:
        # Attack phase: attacker's armament boosts damage
        haki_dmg_boost = 1.0 + attacker_haki_armament_effectiveness * 0.30
    
    if is_defense_phase and defense_type in ("evade", "defend"):
        # Defender's armament reduces damage
        haki_defense_reduction = 1.0 - defender_haki_armament_effectiveness * 0.30
    
    # Final damage
    damage = (base_damage_mod * stat_multiplier * aura_mod * will_reduction * df_comp *
              offensive_multiplier * haki_dmg_boost * haki_defense_reduction)
    
    return max(1, int(damage))

def get_attack_quality(damage: int, base_damage: int) -> str:
    """
    Determine attack quality tier per spec v5.1 section 8.1.
    Returns: 'bad', 'good', or 'excellent'.
    """
    ratio = damage / base_damage if base_damage > 0 else 1.0
    if ratio >= 1.33:
        return 'excellent'
    elif ratio >= 1.01:
        return 'good'
    else:
        return 'bad'

def calculate_defense_stamina_cost(base_cost: int, attacker_hit_chance: float, defender_obs_active: bool, defender_stunned: bool = False) -> int:
    """
    Calculate defense stamina cost per Rule Update.md Section 18.2.
    Per spec 9.2: Stunned status adds +50% stamina cost to next defensive action.
    """
    # Base multiplier: +25% for all defenses
    base_multiplier = 1.25
    
    # Hit chance tax: 2% per point above 66%, capped at 25%
    hit_chance_tax = max(0.0, (attacker_hit_chance - 0.66) * 2.0)
    hit_chance_tax = min(hit_chance_tax, 0.25)
    
    # Total multiplier
    total_stamina_multiplier = base_multiplier + hit_chance_tax
    
    # Observation Haki discount (if active)
    if defender_obs_active:
        total_stamina_multiplier *= 0.85
    
    # Stunned status: +50% cost per spec 9.2
    if defender_stunned:
        total_stamina_multiplier *= 1.50
    
    # Final cost
    return int(base_cost * total_stamina_multiplier)

def get_push_distance(quality: str) -> int:
    """
    Get push distance from attack quality.
    """
    if quality == 'excellent':
        return 2
    elif quality == 'good':
        return 1
    else:
        return 0
