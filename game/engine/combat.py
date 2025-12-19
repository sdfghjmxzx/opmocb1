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
    is_defense_phase: bool = False,
    attacker_df_alloys: Optional[set] = None,
    defender_df_alloys: Optional[set] = None,
    fov_hit_bonus: float = 0.0
) -> float:
    """
    Calculate final hit chance per Rule Update.md Section 7.7.
    Returns value in range [0.05, 0.95].
    """
    print(f"\n{'='*60}")
    print(f"[HIT CHANCE CALCULATION]")
    print(f"Attacker: {attacker.name} | Defender: {defender.name}")
    print(f"Attack Type: {attack_type} | Defense Type: {defense_type}")
    print(f"Phase: {'DEFENSE' if is_defense_phase else 'ATTACK'}")
    print(f"{'-'*60}")
    
    # BASE HIT CHANCE: 66%
    base = 0.66
    print(f"Base hit chance: {base:.2%}")
    
    # Step 1: Attack type modifier
    hit_mod = 0.0
    if attack_type == "quick":
        hit_mod += 0.25
        print(f"Attack modifier (quick): +25% = {hit_mod:+.2%}")
    elif attack_type == "heavy":
        hit_mod -= 0.25
        print(f"Attack modifier (heavy): -25% = {hit_mod:+.2%}")
    else:
        print(f"Attack modifier (normal/other): {hit_mod:+.2%}")
    
    # Step 2: Defense type modifier (defense phase only)
    if is_defense_phase and defense_type:
        if defense_type == "evade":
            hit_mod -= 0.25
            print(f"Defense modifier (evade): -25%, total hit_mod = {hit_mod:+.2%}")
        elif defense_type in ("defend", "counter"):
            hit_mod += 0.25
            print(f"Defense modifier ({defense_type}): +25%, total hit_mod = {hit_mod:+.2%}")
    else:
        print(f"Defense modifier: N/A (attack phase or no defense type)")
    
    # Step 3: Movement bonuses (attack phase) / Dodge bonuses (defense phase)
    dodge_mod = 0.0
    if is_defense_phase and defense_type:
        # Defense phase: convert offensive bonuses to dodge
        print(f"\n[DEFENSE PHASE - Movement Bonuses as Dodge]")
        dodge_mod += min(facing_bonus, 0.15)
        print(f"  Facing dodge: +{min(facing_bonus, 0.15):.2%} (from {facing_bonus:.2%})")
        dodge_mod += min(bounce_bonus * 0.4, 0.10)
        print(f"  Bounce dodge: +{min(bounce_bonus * 0.4, 0.10):.2%} (from {bounce_bonus:.2%} * 0.4)")
        dodge_mod += min(pattern_bonus * 0.5, 0.125)  # Half pattern bonus for dodge
        print(f"  Pattern dodge: +{min(pattern_bonus * 0.5, 0.125):.2%} (from {pattern_bonus:.2%} * 0.5)")
        print(f"  Total dodge bonus: {dodge_mod:.2%}")
    else:
        # Attack phase: apply offensive bonuses to hit chance
        print(f"\n[ATTACK PHASE - Movement Bonuses to Hit]")
        facing_hit = facing_bonus  # full facing chain bonus (already capped at 50% in controller)
        bounce_hit = bounce_bonus  # full bounce bonus (already capped at 20% in controller)
        pattern_hit = pattern_bonus  # full pattern bonus (already capped at 25% in controller)
        print(f"  Facing hit: +{facing_hit:.2%} (from {facing_bonus:.2%})")
        print(f"  Bounce hit: +{bounce_hit:.2%} (from {bounce_bonus:.2%})")
        print(f"  Pattern hit: +{pattern_hit:.2%} (from {pattern_bonus:.2%})")
        hit_mod += facing_hit + bounce_hit + pattern_hit
        print(f"  Total movement bonus to hit: +{facing_hit + bounce_hit + pattern_hit:.2%}")
        print(f"  Running hit_mod: {hit_mod:+.2%}")
    
    # Step 4: Stat nullification (purely difference-based)
    speed_null = (attacker.speed - defender.reaction) * 0.0015
    ci_att = getattr(attacker, 'combat_instinct', 0)
    ci_def = getattr(defender, 'combat_instinct', 0)
    ci_null = (ci_att - ci_def) * 0.0015
    aura_att = getattr(attacker, 'aura', 0)
    will_def = getattr(defender, 'willpower', 0)
    aura_null = (aura_att - will_def) * 0.0010
    
    print(f"\n[Stat Nullification]")
    print(f"  Speed vs Reaction: ({attacker.speed} - {defender.reaction}) * 0.0015 = {speed_null:+.2%}")
    print(f"  Combat Instinct: ({ci_att} - {ci_def}) * 0.0015 = {ci_null:+.2%}")
    print(f"  Aura vs Willpower: ({aura_att} - {will_def}) * 0.0010 = {aura_null:+.2%}")

    # Step 5: DF Alloy bonuses
    df_alloy_hit_bonus = 0.0
    df_alloy_defense_bonus = 0.0
    
    print(f"\n[DF Alloy Bonuses]")
    if attacker_df_alloys:
        print(f"  Attacker DF alloys: {attacker_df_alloys}")
        if "hit_alloy" in attacker_df_alloys:
            df_alloy_hit_bonus += 0.08  # +8% hit chance
            print(f"    → hit_alloy: +8% hit chance")
    else:
        print(f"  Attacker DF alloys: None")
    
    if defender_df_alloys and is_defense_phase:
        print(f"  Defender DF alloys: {defender_df_alloys}")
        if "defense_alloy" in defender_df_alloys:
            df_alloy_defense_bonus += 0.10  # +10% dodge (defender's defense alloy)
            print(f"    → defense_alloy: +10% dodge (defense phase only)")
    else:
        if is_defense_phase:
            print(f"  Defender DF alloys: None")
        else:
            print(f"  Defender DF alloys: N/A (attack phase)")
    
    print(f"  Total DF alloy hit bonus: {df_alloy_hit_bonus:+.2%}")
    print(f"  Total DF alloy defense bonus: {df_alloy_defense_bonus:+.2%}")

    # Step 6: Observation Haki (difference-based, nullified when equal)
    # attacker_haki_obs_effectiveness and defender_haki_obs_effectiveness are already
    # normalized effectiveness values in [0, 1], incorporating nullification when both
    # sides activate Observation on the same action.
    print(f"\n[Observation Haki]")
    if attacker_haki_obs_effectiveness > 0.0:
        haki_hit = 0.30 * attacker_haki_obs_effectiveness
        hit_mod += haki_hit
        print(f"  Attacker Haki Obs: +{haki_hit:.2%} (effectiveness: {attacker_haki_obs_effectiveness:.2f})")
    else:
        print(f"  Attacker Haki Obs: inactive")
    
    if defender_haki_obs_effectiveness > 0.0:
        haki_dodge = 0.30 * defender_haki_obs_effectiveness
        dodge_mod += haki_dodge
        print(f"  Defender Haki Obs: +{haki_dodge:.2%} dodge (effectiveness: {defender_haki_obs_effectiveness:.2f})")
    else:
        print(f"  Defender Haki Obs: inactive")
    
    # Step 7: FOV Positional Bonus (Attack Phase Only)
    fov_bonus_applied = 0.0
    print(f"\n[FOV Positional Bonus]")
    if not is_defense_phase:
        # Attack phase: apply FOV bonus
        fov_bonus_applied = fov_hit_bonus
        if fov_bonus_applied > 0.0:
            # Label by layer for clarity
            layer_label = "Periphery" if abs(fov_bonus_applied - 0.10) < 1e-6 else "Behind" if abs(fov_bonus_applied - 0.30) < 1e-6 else "Unknown"
            # Check if defender Observation Haki negates FOV bonus
            if defender_haki_obs_effectiveness > 0.0:
                print(f"  FOV bonus: {fov_hit_bonus:.2%} ({layer_label}, NEGATED by defender Observation Haki)")
                fov_bonus_applied = 0.0
            else:
                print(f"  FOV bonus: +{fov_bonus_applied:.2%} ({layer_label})")
                hit_mod += fov_bonus_applied
        else:
            print(f"  FOV bonus: 0.00% (FOV/front)")
    else:
        print(f"  FOV bonus: N/A (defense phase)")
    
    # Final calculation (no uncancelable or DF components)
    total = base + hit_mod + speed_null + ci_null + aura_null + df_alloy_hit_bonus - dodge_mod - df_alloy_defense_bonus
    
    print(f"\n[FINAL CALCULATION]")
    print(f"  Base: {base:.2%}")
    print(f"  + Hit modifiers: {hit_mod:+.2%}")
    print(f"  + Stat nullification: {speed_null + ci_null + aura_null:+.2%}")
    print(f"  + DF alloy hit: {df_alloy_hit_bonus:+.2%}")
    print(f"  - Dodge modifiers: {dodge_mod:+.2%}")
    print(f"  - DF alloy defense: {df_alloy_defense_bonus:+.2%}")
    print(f"  = Unclamped total: {total:.2%}")
    
    # Clamp to [5%, 95%]
    final = max(0.05, min(0.95, total))
    print(f"  Clamped [5%, 95%]: {final:.2%}")
    print(f"{'='*60}\n")
    return final

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
    is_defense_phase: bool = False,
    attacker_df_alloys: Optional[set] = None,
    defender_df_alloys: Optional[set] = None
) -> int:
    """
    Calculate final damage per Rule Update.md Section 7.8.
    Returns integer damage with minimum floor of 1.
    """
    print(f"\n{'='*60}")
    print(f"[DAMAGE CALCULATION]")
    print(f"Attacker: {attacker.name} | Defender: {defender.name}")
    print(f"Attack Type: {attack_type} | Defense Type: {defense_type}")
    print(f"Base Damage: {base_damage}")
    print(f"Phase: {'DEFENSE' if is_defense_phase else 'ATTACK'}")
    print(f"{'-'*60}")
    # Step 1: Base damage with attack/defense modifiers
    damage_mod = 0.0
    if attack_type == "quick":
        damage_mod -= 0.50
        print(f"Attack type modifier (quick): -50%")
    elif attack_type == "heavy":
        damage_mod += 0.50
        print(f"Attack type modifier (heavy): +50%")
    else:
        print(f"Attack type modifier (normal): 0%")
    
    if defense_type:
        if defense_type == "evade":
            damage_mod += 0.50
            print(f"Defense type modifier (evade): +50%")
        elif defense_type == "defend":
            damage_mod -= 0.50
            print(f"Defense type modifier (defend): -50%")
        elif defense_type == "counter":
            damage_mod += 0.50
            print(f"Defense type modifier (counter): +50%")
    
    print(f"Total type modifier: {damage_mod:+.0%}")
    
    # DF Alloy: damage_alloy adds +10% damage (attack phase only, applied as a multiplier)
    df_alloy_damage_bonus = 0.0
    print(f"\n[DF Alloy Damage Bonus]")
    if attacker_df_alloys and not is_defense_phase:
        print(f"  Attacker DF alloys: {attacker_df_alloys}")
        if "damage_alloy" in attacker_df_alloys:
            df_alloy_damage_bonus = 0.10
            print(f"    → damage_alloy: +10% damage (attack phase)")
    else:
        if is_defense_phase:
            print(f"  DF damage alloy: N/A (defense phase)")
        else:
            print(f"  Attacker DF alloys: None")
    
    # Base damage before stat and positional multipliers
    base_damage_mod = base_damage * (1.0 + damage_mod)
    print(f"\nBase damage calculation:")
    print(f"  {base_damage} * (1.0 + {damage_mod:.2f}) = {base_damage_mod:.2f}")
    
    # Step 2: Stat multipliers
    strength_mod = 1.0 + (attacker.strength - defender.defense) * 0.0015
    
    aura = getattr(attacker, 'aura', 0)
    will = getattr(defender, 'willpower', 0)
    aura_will_mod = 1.0 + (aura - will) * 0.0015
    
    print(f"\n[Stat Multipliers]")
    print(f"  Strength vs Defense: 1.0 + ({attacker.strength} - {defender.defense}) * 0.0015 = {strength_mod:.4f}")
    print(f"  Aura vs Willpower: 1.0 + ({aura} - {will}) * 0.0015 = {aura_will_mod:.4f}")
    
    # DF component
    if attacker_df_multipliers:
        effective_strength = attacker.strength * attacker_df_multipliers.get('damage_multiplier', 1.0)
        df_comp = 1.0 + (effective_strength - defender.defense) * 0.0015 - (attacker.strength - defender.defense) * 0.0015
        print(f"  DF Type Advantage: {attacker_df_multipliers}")
        print(f"    Effective STR: {attacker.strength} * {attacker_df_multipliers.get('damage_multiplier', 1.0):.2f} = {effective_strength:.2f}")
        print(f"    DF component: {df_comp:.4f}")
    else:
        df_comp = 1.0
        print(f"  DF Type Advantage: None")
    
    # Combined stat multiplier (strength, aura/will, DF)
    stat_multiplier = strength_mod * aura_will_mod * df_comp
    print(f"  Combined stat multiplier: {strength_mod:.4f} * {aura_will_mod:.4f} * {df_comp:.4f} = {stat_multiplier:.4f}")
    
    # Step 3: Position bonuses (offensive)
    offensive_multiplier = 1.0
    print(f"\n[Position/Movement Bonuses]")
    if is_defense_phase and defense_type:
        # Defense phase: bonuses converted to damage reduction
        dmg_reduction = 0.0
        facing_red = min(facing_bonus, 0.15)
        bounce_red = min(bounce_bonus * 0.4, 0.10)
        pattern_red = min(pattern_bonus * 0.5, 0.125)
        dmg_reduction = facing_red + bounce_red + pattern_red
        print(f"  DEFENSE PHASE - Damage Reduction:")
        print(f"    Facing: {facing_red:.2%} (from {facing_bonus:.2%})")
        print(f"    Bounce: {bounce_red:.2%} (from {bounce_bonus:.2%} * 0.4)")
        print(f"    Pattern: {pattern_red:.2%} (from {pattern_bonus:.2%} * 0.5)")
        print(f"    Total reduction: {dmg_reduction:.2%}")
        offensive_multiplier = 1.0 - dmg_reduction
        print(f"  Offensive multiplier: 1.0 - {dmg_reduction:.2%} = {offensive_multiplier:.4f}")
    else:
        # Attack phase: offensive bonuses
        facing_bonus_capped = facing_bonus  # full facing chain bonus (already capped at 50% upstream)
        bounce_bonus_capped = min(bounce_bonus * 0.4, 0.10)
        pattern_bonus_capped = min(pattern_bonus, 0.25)
        bonus_sum = facing_bonus_capped + bounce_bonus_capped + pattern_bonus_capped
        print(f"  ATTACK PHASE - Damage Bonus:")
        print(f"    Facing: {facing_bonus_capped:.2%} (from {facing_bonus:.2%})")
        print(f"    Bounce: {bounce_bonus_capped:.2%} (from {bounce_bonus:.2%} * 0.4)")
        print(f"    Pattern: {pattern_bonus_capped:.2%} (from {pattern_bonus:.2%}, capped at 25%)")
        print(f"    Total bonus: {bonus_sum:.2%}")
        offensive_multiplier = 1.0 + bonus_sum
        print(f"  Offensive multiplier: 1.0 + {bonus_sum:.2%} = {offensive_multiplier:.4f}")
    
    # Step 4: Defensive multipliers (Haki armament + DF Alloy defense)
    haki_dmg_boost = 1.0
    haki_defense_reduction = 1.0
    haki_damage_bonus_percent = 0.0
    haki_reduction_percent = 0.0
    df_defense_reduction_percent = 0.0
    
    print(f"\n[Haki & DF Defense Multipliers]")
    if is_defense_phase and defense_type == "counter":
        # Counter: attacker's armament boosts counter damage
        haki_damage_bonus_percent = attacker_haki_armament_effectiveness * 0.30
        haki_dmg_boost = 1.0 + haki_damage_bonus_percent
        print(f"  Counter: Attacker Armament boosts damage")
        print(f"    Armament effectiveness: {attacker_haki_armament_effectiveness:.2f}")
        print(f"    Damage boost: 1.0 + ({attacker_haki_armament_effectiveness:.2f} * 0.30) = {haki_dmg_boost:.4f}")
    elif not is_defense_phase:
        # Attack phase: attacker's armament boosts damage
        haki_damage_bonus_percent = attacker_haki_armament_effectiveness * 0.30
        haki_dmg_boost = 1.0 + haki_damage_bonus_percent
        print(f"  Attack: Attacker Armament boosts damage")
        print(f"    Armament effectiveness: {attacker_haki_armament_effectiveness:.2f}")
        print(f"    Damage boost: 1.0 + ({attacker_haki_armament_effectiveness:.2f} * 0.30) = {haki_dmg_boost:.4f}")
    else:
        print(f"  Attacker Haki Armament: inactive")
    
    if is_defense_phase and defense_type in ("evade", "defend"):
        # Defender's armament reduces damage
        haki_reduction_percent = defender_haki_armament_effectiveness * 0.30
        haki_defense_reduction = 1.0 - haki_reduction_percent
        print(f"  Defender Armament reduces damage")
        print(f"    Armament effectiveness: {defender_haki_armament_effectiveness:.2f}")
        print(f"    Damage reduction: 1.0 - ({defender_haki_armament_effectiveness:.2f} * 0.30) = {haki_defense_reduction:.4f}")
        
        # DF Alloy: defense_alloy adds additional -10% damage reduction (defense phase only)
        if defender_df_alloys and "defense_alloy" in defender_df_alloys:
            df_defense_reduction_percent = 0.10
            total_def_red = haki_reduction_percent + df_defense_reduction_percent
            haki_defense_reduction = 1.0 - total_def_red
            print(f"  DF Defense Alloy: Additional 10% reduction")
            print(f"    Total defense reduction factor: {haki_defense_reduction:.4f}")
    else:
        print(f"  Defender Haki/DF Defense: inactive")
    
    # Final damage with additive bonus stacking per spec
    # Aggregate all percentage-based bonuses into a single net modifier on top of base*stats
    movement_damage_bonus_percent = bonus_sum
    movement_reduction_percent = dmg_reduction if is_defense_phase and defense_type else 0.0
    total_bonus_percent = 0.0
    total_reduction_percent = 0.0
    
    if not is_defense_phase:
        # Attack phase: movement + Haki + DF damage alloy all stack additively
        total_bonus_percent = movement_damage_bonus_percent + haki_damage_bonus_percent + df_alloy_damage_bonus
    else:
        # Defense phase: attacker Haki can boost (counter), defender tools reduce incoming damage
        total_bonus_percent = haki_damage_bonus_percent + df_alloy_damage_bonus
        total_reduction_percent = movement_reduction_percent + haki_reduction_percent + df_defense_reduction_percent
    
    net_percent = total_bonus_percent - total_reduction_percent
    damage_factor = 1.0 + net_percent
    damage = (base_damage_mod * stat_multiplier * damage_factor)
    
    print(f"\n[FINAL CALCULATION]")
    print(f"  Base damage (modified): {base_damage_mod:.2f}")
    print(f"  * Stat multiplier: {stat_multiplier:.4f}")
    print(f"  * Total bonus percent: {total_bonus_percent:.4f}")
    print(f"  * Total reduction percent: {total_reduction_percent:.4f}")
    print(f"  * Net percent: {net_percent:.4f} -> damage factor {damage_factor:.4f}")
    print(f"  = Raw damage: {damage:.2f}")
    
    final_damage = max(1, int(damage))
    print(f"  Floored (min 1): {final_damage}")
    print(f"{'='*60}\n")
    return final_damage

def get_attack_quality(damage: int, base_damage: int) -> str:
    """
    Determine attack quality tier per spec v5.1 section 8.1.
    Returns: 'bad', 'good', or 'excellent'.
    """
    ratio = damage / base_damage if base_damage > 0 else 1.0
    
    if ratio >= 1.33:
        quality = 'excellent'
    elif ratio >= 1.01:
        quality = 'good'
    else:
        quality = 'bad'
    
    print(f"[COMBAT] get_attack_quality: damage={damage}, base={base_damage}, ratio={ratio:.3f} -> '{quality}'")
    return quality

def calculate_defense_stamina_cost(base_cost: int, attacker_hit_chance: float, defender_obs_active: bool, defender_stunned: bool = False, defender_fov_layer: str = "FOV", is_movement: bool = False) -> int:
    """
    Calculate defense stamina cost per Rule Update.md Section 18.2.
    Per spec 9.2: Stunned status adds +50% stamina cost to next defensive action.
    Per Rule Update9.md: FOV layer modifies stamina costs based on defender's awareness.
    
    Args:
        base_cost: Base stamina cost
        attacker_hit_chance: Final hit chance of attacker
        defender_obs_active: Whether defender has Observation Haki active
        defender_stunned: Whether defender is stunned
        defender_fov_layer: FOV layer where attacker is located ("FOV", "Periphery", "Behind")
        is_movement: True for movement costs, False for defense action costs
    """
    # Base multiplier: +25% for all defenses
    base_multiplier = 1.25
    
    # FOV Stamina Modifier (Rule Update9.md Part II)
    fov_multiplier = 1.0
    if defender_fov_layer == "FOV":
        # Defender sees attacker coming
        if is_movement:
            fov_multiplier = 0.85  # -15% movement cost
        else:
            fov_multiplier = 0.70  # -30% defense action cost
    elif defender_fov_layer == "Behind":
        # Defender is blind-sided
        if is_movement:
            fov_multiplier = 1.15  # +15% movement cost
        # Defense actions: no special modifier (stays at 1.0)
    # Periphery: neutral (fov_multiplier = 1.0)
    
    # Hit chance tax: 2% per point above 66%, capped at 25%
    hit_chance_tax = max(0.0, (attacker_hit_chance - 0.66) * 2.0)
    hit_chance_tax = min(hit_chance_tax, 0.25)
    
    # Total multiplier (FOV applied to base before tax)
    total_stamina_multiplier = (base_multiplier * fov_multiplier) + hit_chance_tax
    
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
    Per spec 8.1: bad=0, good=1, excellent=2 tiles push.
    """
    if quality == 'excellent':
        push = 2
    elif quality == 'good':
        push = 1
    else:
        push = 0
    
    print(f"[COMBAT] get_push_distance: quality='{quality}' -> {push} tiles")
    return push
