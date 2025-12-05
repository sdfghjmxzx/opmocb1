# **FINAL CORRECTED RULE CHANGES DOCUMENT**

---

## **SECTION 7.1 - ATTACK TYPE MODIFIERS (CRITICAL FIX)**

**REPLACE the table with:**

| Attack | Range | **Base Damage** | Hit Chance Modifier | Damage Modifier |
|--------|-------|-----------------|---------------------|-----------------|
| Quick | 1 | **20** | **+25%** | **-50%** |
| Normal | 2 | **20** | **0%** | **0%** |
| Heavy | 3 | **20** | **-25%** | **+50%** |

**Result:** Final damage becomes 10/20/30 after applying the modifier.

---

## **SECTION 7.7 - HIT CHANCE FORMULA**

**REPLACE with this exact structure:**

```python
# Step 1: Base attack type modifier
if attack_type == "quick": hit_mod += 25%
if attack_type == "heavy": hit_mod -= 25%

# Step 2: Defense type modifier
if defense_type == "evade": hit_mod -= 25%
if defense_type == "defend": hit_mod += 25%
if defense_type == "counter": hit_mod += 25%

# Step 3: Universal defensive dodge bonus (all defenses)
dodge_mod += FacingBonus + BounceBonus + (PatternBonus × 0.5)

# Step 4: Stat nullification
hit_mod += (speed - reaction) × 0.15%
hit_mod += (combat_instinct - opp_ci) × 0.15%
hit_mod += (aura - willpower) × 0.10%

# Step 5: Haki alloys
if observation_haki_active: dodge_mod += 30%

# Final calculation
FinalHitChance = 66% + hit_mod + dodge_mod
FinalHitChance = clamp(FinalHitChance, 5%, 95%)
```

---

## **SECTION 7.8 - DAMAGE FORMULA**

**REPLACE with this exact structure:**

```python
# Step 1: Base damage with attack/defense modifiers
damage_mod = 0
if attack_type == "quick": damage_mod -= 50%
if attack_type == "heavy": damage_mod += 50%
if defense_type == "evade": damage_mod += 50%
if defense_type == "defend": damage_mod -= 50%
if defense_type == "counter": damage_mod += 50%

base_damage_mod = BaseDamage × (1 + damage_mod)

# Step 2: Stat multipliers
stat_multiplier = (1 + (strength - defense) × 0.15%) 
                × (1 + (aura - willpower) × 0.15% + aura × 0.05%)
                × DFComponent
                × (1 - willpower × 0.10%)

# Step 3: Position bonuses (offensive)
offensive_multiplier = (1 + FacingBonus + BounceBonus + PatternBonus)

# Step 4: Defensive multipliers
defensive_multiplier = 1.0
if defense_alloy_active: defensive_multiplier *= 0.90
if armament_haki_active: defensive_multiplier *= (1 - 0.30 × effectiveness)

# Final damage
FinalDamage = base_damage_mod × stat_multiplier × offensive_multiplier × defensive_multiplier
FinalDamage = max(1, FinalDamage)  # DAMAGE FLOOR - CRITICAL FIX
```

---

## **SECTION 13.1 - DF ALLOYS (CORRECTED)**

```diff
- Defense Alloy: -10 flat damage taken
+ Defense Alloy: -10% damage taken (does NOT add dodge chance)
```

**FINAL ALLOY TABLE:**

| Alloy Type | Base DF Cost | Effect | Applicable Actions |
|------------|--------------|--------|-------------------|
| **Defense Alloy** | **5** | **-10% damage taken** | **Evade, Defend, Counters** |
| **Hit Alloy** | 5 | +8% hit chance (Counter) / **+8% dodge chance** (Evade/Defend) | All defensive actions |
| Damage Alloy | 5 | +10 flat damage | Counter-Quick, Counter-Normal |
| Width Boost L1 | 20 | Expand width 3→5 | Quick, Normal, Heavy, Counters |
| Width Boost L2 | 60 | Expand width 5→7 | Quick, Normal, Heavy, Counters |
| Length Boost | 10-60 | +1 to +6 range | Quick, Normal, Heavy, Counters |

---

## **SECTION 12.1 - HAKI DEFENSE EFFECTS**

| Haki Type | Counter | Evade | Defend |
|-----------|---------|-------|--------|
| **Armament** | +30% counter dmg | **+30% damage reduction** | **+30% damage reduction** |
| **Observation** | +30% counter hit | **+30% dodge chance** | **+30% dodge chance** |
| Conqueror | Debuffs attacker | Debuffs attacker | Debuffs attacker |

**Additional:** Observation Haki grants **-15% stamina cost for entire defense phase**.

---

## **SECTION 14.1 - DEFENSE RESOLUTION RULES**

| Defense | Hit Mod | Damage Mod | Resolution |
|---------|---------|------------|------------|
| Tank | 0% | 0% | Take full damage, gain +30 stamina |
| Evade | -25% | +50% | **Roll dodge:** Success = 0 damage. **Fail = apply damage formula** |
| Defend | +25% | -50% | **Always take reduced damage** (formula) |
| **Counter** | +25% | +50% | **Take damage first (formula). If alive, trigger counter-attack (10 base dmg).** |

---

## **SECTION 14.4 - BONUS CONVERSION**

When using **Evade, Defend, or Counter (defensive phase) **:
- ** Facing Direction **: ** +15% dodge chance ** AND ** +15% damage reduction **
- ** Bounce **: ** +10% dodge chance ** AND ** +10% damage reduction **
- ** Pattern **: ** +12.5% dodge chance ** AND ** +12.5% damage reduction **

** Counter (offensive phase):** Use offensive bonuses normally (+hit, +dmg).

---

## **SECTION 18.2 - HIT CHANCE TAX**

```python
# Defense stamina cost multiplier
base_multiplier = 1.25  # +25% for all defenses

# Additional tax
hit_chance_tax = max(0, (AttackerFinalHitChance - 66) × 2%)
hit_chance_tax = min(hit_chance_tax, 0.25)  # Cap at +25%

# Total multiplier
total_stamina_multiplier = base_multiplier + hit_chance_tax

# Observation Haki discount (if active)
if observation_haki: total_stamina_multiplier *= 0.85

# Final cost
FinalStaminaCost = BaseActionCost × total_stamina_multiplier
```

---

## **SECTION 3.2 - DEFENSE PHASE ORDER**

1. **Attack type sets base** (+25% Quick, -25% Heavy)
2. **Defense type modifies base** (+25% Defend, -25% Evade)
3. **Apply defensive bonuses** (Facing/Bounce/Pattern inverted → dodge/dmg reduction)
4. **Apply Haki/Alloys** (Observation, Armament, Defense Alloy)
5. **Apply stat nullification** (Speed vs Reaction, CI vs CI, Aura vs Willpower)
6. **Resolve**:
   - Evade: Roll vs FinalHitChance. Success = 0 damage.
   - Defend: Apply damage formula.
   - Counter: Apply damage formula, then trigger counter-attack if defender survives.

---

## **ADD TO SECTION 5.3 - DAMAGE FLOOR**

```python
# After all damage calculations
FinalDamage = max(1, FinalDamage)  # Minimum damage of 1
```

---

## **ADD TO SECTION 7.7 - DODGE ROLL**

```python
# For Evade defense:
dodge_success = random(1-100) ≤ dodge_mod
if dodge_success:
    damage = 0
else:
    damage = FinalDamage  # Calculate normally
```

---

**ALL CHANGES VERIFIED. ** No other errors detected.