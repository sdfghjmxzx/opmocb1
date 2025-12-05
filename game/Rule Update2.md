# **COMPLETELY CORRECTED FINAL RULE CHANGES FOR LAST 2 STEPS**

---

## **STEP 1: STATUS-EFFECT EXECUTION SEMANTICS**

### **SECTION 17.1 - EFFECT TYPE REGISTRY**

**Change**: Renamed from `effect_subtypes` to `effect_types`. These are the master keys (burn, poison, freeze) that define which categories they can trigger and base magnitude/duration ranges.

**Rule**: Each effect type declares `allowed_categories` as an array, and provides `base_magnitude_range` and `base_duration_range` as [min, max] integer pairs.

**File: `effect_types.json`**
```json
{
    "effect_types": {
        "burn": {
            "allowed_categories": ["damage_over_time", "instant_damage"],
            "base_magnitude_range": [1, 20],
            "base_duration_range": [1, 8]
        },
        "poison": {
            "allowed_categories": ["damage_over_time", "stamina_drain"],
            "base_magnitude_range": [1, 15],
            "base_duration_range": [1, 6]
        },
        "freeze": {
            "allowed_categories": ["stat_debuff", "instant_damage"],
            "base_magnitude_range": [5, 25],
            "base_duration_range": [1, 5]
        },
        "slow": {
            "allowed_categories": ["stat_debuff"],
            "base_magnitude_range": [10, 30],
            "base_duration_range": [2, 6]
        }
    }
}
```

---

### **SECTION 17.2 - EFFECT CATEGORY MECHANICS**

**Rule**: Categories define the mechanical behavior. They are universal and do not change per fruit.

**File: `effect_categories.json`**
```json
{
    "effect_categories": {
        "damage_over_time": {
            "mechanic": "Apply magnitude damage at start of affected player's turn",
            "stackable": false,
            "stack_rule": "Refresh duration to longest when same type re-applied",
            "removal_condition": "duration_zero"
        },
        "instant_damage": {
            "mechanic": "Apply magnitude damage immediately upon application",
            "stackable": true,
            "removal_condition": "instant"
        },
        "stat_debuff": {
            "mechanic": "Reduce target stat by magnitude (flat additive)",
            "stackable": true,
            "max_stacks": 5,
            "removal_condition": "duration_zero"
        },
        "stamina_drain": {
            "mechanic": "Reduce max stamina pool by magnitude% per turn",
            "stackable": false,
            "removal_condition": "duration_zero"
        }
    }
}
```

---

### **SECTION 17.3 - APPLICATION & RESOLUTION RULES**

**Magnitude Formula**:
```
magnitude = floor(base_min + (random(0, base_max - base_min) × (df_mastery / 100)))

Where:
- base_min, base_max come from effect_type's base_magnitude_range
- df_mastery is attacker's devil_fruit_mastery stat (0-100)
```

**Duration Formula**:
```
duration = ceil(1 + (random(0, base_max - 1) × (df_mastery / 100)))

Where:
- base_max comes from effect_type's base_duration_range[1]
- Result is minimum 1 turn
```

**Application Timing**:
- **Attack hit**: Apply effect **after** damage is calculated and deducted
- **Trap entry**: Apply effect **immediately** upon stepping on tile
- **Type advantage**: Apply effect **simultaneously** with damage

**Resolution Order (Per Turn Start)**:
1. Remove effects where `duration == 0`
2. Roll for chance-based effects (if any)
3. Apply DoT effects to health/stamina
4. Recalculate stats with active debuffs applied (additive)
5. Decrement all effect durations by 1
6. Process player actions

---

### **SECTION 17.4 - RESISTANCE APPLICATION**

**Rule**: Resistance is a **property of the defender's fruit**, not the effect. Each fruit declares `effect_resistance` object mapping effect type to multiplier.

**Resistance Formula**:
```
FinalMagnitude = CalculatedMagnitude × defender.effect_resistance[type] × (defender.df_mastery / 100)

Example:
- Fire user (burn: 0.0) at 80 mastery hit by burn DoT (calc 5)
  = 5 × 0.0 × 0.80 = 0 (immune)

- Ice user (freeze: 0.5) at 60 mastery hit by freeze instant (calc 10)
  = 10 × 0.5 × 0.60 = 3 damage
```

**Cap**: Final magnitude cannot be negative. Minimum is 0.

---

## **STEP 2: RUNTIME JSON CONTENT**

### **File: `devil_fruits.json`** (FULL CORRECTED EXAMPLE)

**Structure**: Each fruit declares its resistance, type advantages, special actions, and alloy availability.

```json
{
    "fruits": [
        {
            "id": "mera_mera",
            "name": "Mera Mera no Mi",
            "main_group": "Logia",
            "subgroup": "Elemental",
            "type": "Fire",
            "manipulation_range": 5,
            
            "effect_resistance": {
                "burn": 0.0,
                "freeze": 1.5,
                "poison": 1.0,
                "slow": 0.8
            },
            
            "type_advantages": {
                "vs": {
                    "Ice": {
                        "damage_multiplier": 1.5,
                        "speed_multiplier": 1.2,
                        "effect_bonus": {
                            "type": "burn",
                            "category": "instant_damage",
                            "magnitude_multiplier": 2.0
                        }
                    },
                    "Wood": {
                        "damage_multiplier": 1.8,
                        "speed_multiplier": 1.1,
                        "effect_bonus": {
                            "type": "burn",
                            "category": "damage_over_time",
                            "duration_bonus": 2
                        }
                    }
                },
                "weak_vs": {
                    "Water": {
                        "damage_multiplier": 0.6,
                        "speed_multiplier": 0.7
                    }
                }
            },
            
            "special_attacks": {
                "fire_fist": {
                    "pattern": [[0,1], [0,2], [0,3], [1,1], [-1,1]],
                    "damage_modifier": -25,
                    "df_stamina_cost": 25,
                    "hit_chance_modifier": 0,
                    "effect": {
                        "type": "burn",
                        "category": "damage_over_time",
                        "magnitude_formula": "floor(1 + (random(0,19) * (df_mastery / 100)))",
                        "duration_formula": "ceil(1 + (random(0,7) * (df_mastery / 100)))"
                    }
                },
                "inferno_burst": {
                    "pattern": [[0,1], [0,2], [1,0], [-1,0], [1,1], [-1,1]],
                    "damage_modifier": 50,
                    "df_stamina_cost": 40,
                    "hit_chance_modifier": -10,
                    "effect": {
                        "type": "burn",
                        "category": "instant_damage",
                        "magnitude_formula": "floor(10 + (random(0,20) * (df_mastery / 100)))"
                    }
                }
            },
            
            "special_defenses": {
                "flame_shield": {
                    "pattern": [[1,0], [-1,0], [0,0]],
                    "df_stamina_cost": 35,
                    "damage_reduction": 40,
                    "hit_chance_modifier": 15,
                    "effect": {
                        "type": "burn",
                        "category": "damage_over_time",
                        "magnitude_formula": "floor(random(0,9) * (df_mastery / 100))",
                        "duration_formula": "ceil(1 + (random(0,3) * (df_mastery / 100)))"
                    }
                }
            },
            
            "alloys_available": {
                "damage_alloy": {"enabled": true, "df_cost": 5},
                "hit_alloy": {"enabled": true, "df_cost": 5},
                "defense_alloy": {"enabled": true, "df_cost": 5},
                "width_boost_l1": {"enabled": true, "df_cost": 20},
                "width_boost_l2": {"enabled": true, "df_cost": 60},
                "length_boost": {"enabled": true, "df_cost_formula": "10 + (boost_level * 10)"}
            },
            
            "map_abilities": {
                "fire_wall": {
                    "type": "wall",
                    "df_cost_tier": {
                        "fragile": 20,
                        "standard": 30,
                        "reinforced": 40
                    },
                    "placement": {"range": 5, "facing": "manual", "tiles": 3}
                },
                "burning_ground": {
                    "type": "trap",
                    "df_cost": 15,
                    "placement": {"range": 5, "targeting": "single_tile"},
                    "effect": {
                        "type": "burn",
                        "category": "damage_over_time",
                        "magnitude_formula": "floor(1 + (random(0,7) * (df_mastery / 100)))",
                        "duration_formula": "ceil(1 + (random(0,3) * (df_mastery / 100)))"
                    }
                }
            }
        }
    ]
}
```

---

### **File: `tile_config.json`** (CORRECTED)

**Rule**: Tiles generate effects on entry using the same type system as DF abilities. No special triggers or visual metadata belong in rule files.

```json
{
    "spawn_rates": {
        "initial": {
            "unpassable": 0.02,
            "trap": 0.04,
            "drop": 0.04,
            "sea_tile": 0.20
        },
        "per_turn": {
            "trap": 0.02,
            "drop": 0.02
        }
    },
    
    "caps": {
        "unpassable": 1,
        "trap": 1,
        "drop": "unlimited"
    },
    
    "trap_generation": {
        "type_pool": ["burn", "poison", "freeze", "slow"],
        "magnitude_range": [2, 8],
        "duration_range": [1, 4]
    },
    
    "drop_generation": {
        "health_restore": {"magnitude_range": [15, 25]},
        "stamina_restore": {"magnitude_range": [20, 40]}
    }
}
```

---

### **File: `effect_types.json`**

```json
{
    "effect_types": {
        "burn": {
            "allowed_categories": ["damage_over_time", "instant_damage"],
            "base_magnitude_range": [1, 20],
            "base_duration_range": [1, 8]
        },
        "poison": {
            "allowed_categories": ["damage_over_time", "stamina_drain"],
            "base_magnitude_range": [1, 15],
            "base_duration_range": [1, 6]
        },
        "freeze": {
            "allowed_categories": ["stat_debuff", "instant_damage"],
            "base_magnitude_range": [5, 25],
            "base_duration_range": [1, 5]
        },
        "slow": {
            "allowed_categories": ["stat_debuff"],
            "base_magnitude_range": [10, 30],
            "base_duration_range": [2, 6]
        }
    }
}
```

---

### **File: `effect_categories.json`**

```json
{
    "effect_categories": {
        "damage_over_time": {
            "mechanic": "Apply magnitude damage at start of affected player's turn",
            "stackable": false,
            "removal_condition": "duration_zero"
        },
        "instant_damage": {
            "mechanic": "Apply magnitude damage immediately upon application",
            "stackable": true
        },
        "stat_debuff": {
            "mechanic": "Reduce target stat by magnitude (flat additive)",
            "stackable": true,
            "max_stacks": 5
        },
        "stamina_drain": {
            "mechanic": "Reduce max stamina pool by magnitude% per turn",
            "stackable": false
        }
    }
}
```

---

### **File: `alloys.json`** (NEW - Global Definitions)

```json
{
    "alloys": {
        "damage_alloy": {
            "df_stamina_cost": 5,
            "damage_modifier": 15,
            "applicable_actions": ["counter_quick", "counter_normal"]
        },
        "hit_alloy": {
            "df_stamina_cost": 5,
            "hit_chance_modifier": 10,
            "applicable_actions": ["all_attacks", "all_defenses"]
        },
        "defense_alloy": {
            "df_stamina_cost": 5,
            "damage_reduction": 15,
            "applicable_actions": ["evade", "defend", "counter"]
        },
        "width_boost_l1": {
            "df_stamina_cost": 20,
            "width_increase": 2,
            "applicable_actions": ["quick", "normal", "heavy", "counter"]
        },
        "width_boost_l2": {
            "df_stamina_cost": 60,
            "width_increase": 4,
            "applicable_actions": ["quick", "normal", "heavy", "counter"]
        },
        "length_boost": {
            "df_stamina_cost_formula": "10 + (boost_amount * 10)",
            "applicable_actions": ["quick", "normal", "heavy", "counter"]
        }
    }
}
```

---

## **SUMMARY: WHAT WAS MISSING & NOW FIXED**

1. **Alloys**: Now fully specified in `alloys.json` with DF stamina costs and percentage modifiers
2. **Special actions**: Use `damage_modifier` and `hit_chance_modifier` as percentages relative to Normal base
3. **DF stamina**: Explicitly separated from regular stamina for all DF abilities
4. **Resistance**: Moved to fruit file as flat multipliers (0.0 to 2.0)
5. **Formulas**: All magnitude/duration use string formulas with `df_mastery` variable
6. **Tile generation**: Simplified to single trap/drop type with random generation ranges

**No assumptions made. Every number derives from the percentage-based, stat-driven system established in attack rules.**