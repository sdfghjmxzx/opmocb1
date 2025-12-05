"""Devil Fruit system - Phase 3: Type advantages and effective stats."""

from typing import Optional, Dict, Any

def calculate_type_advantage(
    attacker_df_type: Optional[str],
    defender_df_type: Optional[str],
    attacker_mastery: int,
    defender_mastery: int,
    type_advantages: Optional[Dict[str, Any]] = None
) -> Dict[str, float]:
    """
    Calculate DF multipliers per spec v5.1 section 16.
    Returns dict with 'damage_multiplier' and 'speed_multiplier'.
    """
    # No DF on either side
    if not attacker_df_type and not defender_df_type:
        return {'damage_multiplier': 1.0, 'speed_multiplier': 1.0}
    
    # Attacker has DF, defender doesn't: base advantage 1.10 damage, 1.05 speed
    if attacker_df_type and not defender_df_type:
        attacker_mastery_frac = attacker_mastery / 100.0
        dmg_mult = 1.0 + (1.10 - 1.0) * attacker_mastery_frac
        spd_mult = 1.0 + (1.05 - 1.0) * attacker_mastery_frac
        return {'damage_multiplier': dmg_mult, 'speed_multiplier': spd_mult}
    
    # Defender has DF, attacker doesn't: no advantage
    if not attacker_df_type and defender_df_type:
        return {'damage_multiplier': 1.0, 'speed_multiplier': 1.0}
    
    # Both have DF: check type_advantages
    if not type_advantages:
        return {'damage_multiplier': 1.0, 'speed_multiplier': 1.0}
    
    attacker_mastery_frac = attacker_mastery / 100.0
    defender_mastery_frac = defender_mastery / 100.0
    
    # Check advantage
    if 'vs' in type_advantages and defender_df_type in type_advantages['vs']:
        adv = type_advantages['vs'][defender_df_type]
        max_dmg = adv.get('damage_multiplier', 1.0)
        max_spd = adv.get('speed_multiplier', 1.0)
        # Scale from 1.0 to max based on attacker mastery
        attacker_dmg = 1.0 + (max_dmg - 1.0) * attacker_mastery_frac
        attacker_spd = 1.0 + (max_spd - 1.0) * attacker_mastery_frac
        # Defender mitigation: up to 50% reduction
        counter_strength = 1.0 - (0.5 * defender_mastery_frac)
        final_dmg = 1.0 + (attacker_dmg - 1.0) * counter_strength
        final_spd = 1.0 + (attacker_spd - 1.0) * counter_strength
        return {'damage_multiplier': final_dmg, 'speed_multiplier': final_spd}
    
    # Check disadvantage
    if 'weak_vs' in type_advantages and defender_df_type in type_advantages['weak_vs']:
        dis = type_advantages['weak_vs'][defender_df_type]
        min_dmg = dis.get('damage_multiplier', 1.0)
        min_spd = dis.get('speed_multiplier', 1.0)
        # Scale from min to 1.0 based on attacker mastery
        attacker_dmg = min_dmg + (1.0 - min_dmg) * attacker_mastery_frac
        attacker_spd = min_spd + (1.0 - min_spd) * attacker_mastery_frac
        # Defender mitigation
        counter_strength = 1.0 - (0.5 * defender_mastery_frac)
        final_dmg = 1.0 + (attacker_dmg - 1.0) * counter_strength
        final_spd = 1.0 + (attacker_spd - 1.0) * counter_strength
        return {'damage_multiplier': final_dmg, 'speed_multiplier': final_spd}
    
    # No type interaction
    return {'damage_multiplier': 1.0, 'speed_multiplier': 1.0}

class DevilFruitSystem:
    def __init__(self):
        self.registry = {}
