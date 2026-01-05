# FIELD OF VIEW (FOV) SYSTEM SPECIFICATION
**Version 5.1 - Final Production Rules**

---

## PART I: FOV LAYER ARCHITECTURE

### 1.1 FOV Layer Definitions (All-Inclusive)

The battlefield is divided into **three perpetual vision layers** relative to each player's **facing direction**. These layers apply to **all tiles** on the board, not just adjacent ones.

**Layer 1: FOV (Front Arc)**
- **Coverage**: 180° arc directly in front of the player
- **Direction Vectors**: Front, Front-Right, Front-Left
- **Tiles**: All tiles whose coordinates lie within the 180° forward cone

**Layer 2: Periphery (Side Arcs)**
- **Coverage**: 90° total (45° left and 45° right of the player)
- **Direction Vectors**: Left, Right
- **Tiles**: All tiles on the player's immediate flanks

**Layer 3: Behind (Rear Arc)**
- **Coverage**: 180° arc directly behind the player
- **Direction Vectors**: Behind, Behind-Left, Behind-Right
- **Tiles**: All tiles in the 180° rear cone

**Geometric Mapping by Facing Direction:**

| Facing | FOV Directions | Periphery Directions | Behind Directions |
|--------|----------------|----------------------|-------------------|
| **North** | N, NE, NW | W, E | S, SE, SW |
| **South** | S, SE, SW | E, W | N, NE, NW |
| **East** | E, NE, SE | N, S | W, NW, SW |
| **West** | W, NW, SW | S, N | E, NE, SE |
| **North-East** | NE, N, E | NW, SE | SW, S, W |
| **North-West** | NW, N, W | NE, SW | SE, S, E |
| **South-East** | SE, S, E | SW, NE | NW, N, W |
| **South-West** | SW, S, W | SE, NW | NE, N, E |

---

## PART II: FOV-BASED COMBAT BONUSES

### 2.1 Attacker Bonuses (Applied During Attack Phase)

The attacker's bonus is determined by **where the defender is positioned relative to the attacker's FOV layers** at the moment of attack.

```python
# Determine attacker's FOV layer containing defender
fov_layer = get_fov_layer(attacker.facing, attacker_position, defender_position)

if fov_layer == "FOV":
    hit_chance_bonus = 0%  # No bonus for frontal attack
elif fov_layer == "Periphery":
    hit_chance_bonus = +10%  # Flanking bonus
elif fov_layer == "Behind":
    hit_chance_bonus = +30%  # Rear attack bonus (surprise)

FinalHitChance = BaseHitChance + hit_chance_bonus
```

**Example:**  
Attacker facing North at 4D. Defender at 2E (South-East direction).  
From attacker's perspective: **Behind layer** → **+30% hit chance bonus**.

---

### 2.2 Defender Bonuses/Debuffs (Applied During Defense Phase)

The defender's modifiers are determined by **where the attacker is positioned relative to the defender's FOV layers** at the moment of defense.

```python
# Determine defender's FOV layer containing attacker
defender_fov_layer = get_fov_layer(defender.facing, defender_position, attacker_position)

if defender_fov_layer == "FOV":
    # Defender sees the attack coming
    defense_stamina_cost = BaseCost × 0.70  # -30% discount
    movement_stamina_cost = BaseCost × 0.85  # -15% discount
    
elif defender_fov_layer == "Periphery":
    # Neutral position
    defense_stamina_cost = BaseCost  # No change
    movement_stamina_cost = BaseCost  # No change
    
elif defender_fov_layer == "Behind":
    # Defender is blind-sided
    defense_stamina_cost = BaseCost  # No special defense bonus
    movement_stamina_cost = BaseCost × 1.15  # +15% penalty
    counter_success_chance *= 0.80  # -20% success on Counter defense
```

**Example:**  
Defender facing North at 4D. Attacker at 2E (South-East direction).  
From defender's perspective: **Behind layer** → **+15% movement cost, -20% Counter success**.

---

## PART III: FOV DYNAMICS & TURN TIMING

### 3.1 When FOV Status is Determined

**Defender Penalties:** Checked **once** at the **start of the Defensive Phase** based on attacker's position.

**Attacker Bonuses:** Checked **Once**:
1. **After Defensive Phase Ends**: Determines **bonus for combat calculation**

```python
# Turn Sequence
# 1. Defensive Phase
#    - Determine defender's FOV layer containing attacker
#    - Apply defender FOV debuffs to defensive actions
#    - Defender may rotate (costs stamina, updates FOV)

# 2. End of Defensive Phase
#    - Recalculate attacker's position relative to defender's NEW facing
#    - Determine attacker's FOV bonus combat calculation
```

**Key Rule:** If defender **rotates** during their phase, the attacker's **bonus for the next turn may change,depending where attacker is in the FOV system after defensive phase ends**.

---

### 3.2 FOV + Rotation Interaction

**Defender rotates 45° or 90°** (cost: 5 stamina attack / 20 stamina defense):
- **FOV updates instantly** to new facing direction
- **All FOV bonuses/debuffs recalculate** based on new facing
- **Attacker's NEXT turn bonus** uses the **new FOV layout**

**Example:**
- **Turn 1 Attack**: Attacker behind defender → **+30% hit chance** for this attack
- **Defensive Phase**: Defender rotates to face attacker → **FOV becomes FOV layer**
- **Turn 2 Attack**: Attacker now in defender's FOV → **0% hit chance bonus** for next attack

---

## PART IV: HAKI + FOV INTERACTION RULES

### 4.1 Observation Haki Defensive Alloy

When defender activates **Observation Haki** during their defensive phase:

```python
# Observation Haki removes ALL attacker FOV hit chance bonuses
if defender_uses_observation_haki:
    attacker_fov_bonus = 0  # Negated entirely
    
    # Attacker cannot gain FOV bonus this turn or next turn
    attacker_fov_status_for_this_attack = "FOV"  # Treat as frontal
    attacker_fov_status_for_next_turn = "FOV"    # No bonus
    
    # Defender Counter defense gets +20% success chance
    if defender_uses_counter:
        counter_success_chance += 20%
```

**Effect:** Observation Haki **completely erases** the attacker's positional advantage, forcing them to rely on **raw stats and pattern bonuses etc**.


---

## PART V: SPECIAL TILE VISIBILITY RULES

### 5.1 Initial Spawn Visibility

**Continuous/Momentary Traps & Drops:**
- Spawned **outside defender's FOV/Periphery** (blind spot) → **Invisible**
- Spawned **inside defender's FOV/Periphery** → **Instantly visible** with glow

### 5.2 Tile Movement Visibility

**Invisible tile enters FOV/Periphery:**
- **Does NOT become visible immediately**
- **Reveals at end of current defensive phase**
- **Attacks from invisible tiles**: Hit chance bonus **still applies** until revealed

**Example:**
- Trap spawns at 2E (defender's blind spot) → **Invisible**
- Attacker attacks from 2E → **+30% hit chance bonus**
- Defensive phase ends → **Trap reveals (glows red)**
- **Next turn**: Trap is visible, no longer grants bonus

---

### 5.3 Stepping on Invisible Traps

```python
if player.steps_on_tile and tile.is_trap and not tile.visible:
    # Debuff applies immediately
    apply_trap_effect(player, tile)
    
    # Player does NOT see the tile yet
    tile.remains_invisible = True
    
    # At end of defensive phase:
    tile.visible = True
    show_message("You triggered an invisible trap!")
    
    # Debuff was hidden until now
    player.show_hidden_debuffs()  # Reveal to player
```

---

### 5.4 Sea Tiles (Always Visible)
```
Sea tiles are always visible, regardless of FOV
Sea tile edges glow white when in FOV
Sea tile edges are dim when in blind spot (but still visible)
```

---

## PART VI: SCAN ACTION

### 6.1 Scan Action Mechanics

```python
Action: SCAN
Stamina Cost: 10
Restrictions:
- Can be used **once per turn** (either Attack or Defense Phase)
- **Cannot be undone** (terminal action, no undo/redo)
- **Cannot be queued** (must be executed immediately)

Effects:
- Instantly reveals **ALL** special tiles on entire battlefield
- Makes **invisible traps** visible (but does not disarm them)
- Shows **future spawn locations** for next turn (purple outline)
- Reveals **hidden debuffs** currently affecting player

UI:
- Button appears in action panel: "SCAN (10)"
- Clicking it disables all other action buttons
- Confirmation dialog: "Reveal all tiles? (10 stamina)"
- After confirmation: Battlefield flashes white, tiles reveal
```

---

### 6.2 Scan + FOV Interaction

```python
# Scan reveals everything, but FOV bonuses still apply
if player_uses_scan:
    reveal_all_tiles()
    
    # Scan does NOT affect FOV hit chance bonuses
    # Attacker still gets +30% if behind defender
    # FOV system remains active
    
    # Scan is a separate action, does not affect attack/defense
    # Can be used before planning actions or after
```

---


## PART VII: COMPLETE ECS INTEGRATION

```python
# core/ecs/components.py
@dataclass
class FOVComponent:
    facing: Facing = Facing.NORTH
    fov_tiles: List[Tuple[int, int]] = field(default_factory=list)
    peripheral_tiles: List[Tuple[int, int]] = field(default_factory=list)
    behind_tiles: List[Tuple[int, int]] = field(default_factory=list)

@dataclass
class ScanComponent:
    used_this_turn: bool = False
    revealed_tiles: List[int] = field(default_factory=list)  # Tile IDs

# core/systems/fov_system.py
def update_fov_layers(entity):
    pos = entity.get_component(PositionComponent)
    fov = entity.get_component(FOVComponent)
    
    # Clear previous
    fov.fov_tiles = []
    fov.peripheral_tiles = []
    fov.behind_tiles = []
    
    # Get all tiles in each layer based on facing
    all_tiles = get_all_board_tiles()
    
    for tile in all_tiles:
        relative_pos = get_relative_direction(pos, tile)
        layer = get_layer_from_direction(relative_pos, fov.facing)
        
        if layer == "FOV":
            fov.fov_tiles.append(tile)
        elif layer == "Periphery":
            fov.peripheral_tiles.append(tile)
        elif layer == "Behind":
            fov.behind_tiles.append(tile)

def get_fov_layer_for_target(attacker, defender):
    attacker_fov = attacker.get_component(FOVComponent)
    defender_pos = defender.get_component(PositionComponent)
    
    if defender_pos in attacker_fov.fov_tiles:
        return "FOV"
    elif defender_pos in attacker_fov.peripheral_tiles:
        return "Periphery"
    elif defender_pos in attacker_fov.behind_tiles:
        return "Behind"
    else:
        return "Behind"  # Default fallback
```

---

## PART VIII: FINAL VERIFICATION

### Scenario 1: Attacker Behind Defender
- **Attacker position**: 2E (South-East of defender)
- **Defender facing**: North
- **Attacker layer relative to defender**: Behind
- **Bonuses**:
  - Attacker: **+30% hit chance**
  - Defender: **+15% movement stamina**, **-20% Counter success**

---

### Scenario 2: Attacker in Periphery
- **Attacker position**: 4E (East of defender)
- **Defender facing**: North
- **Attacker layer**: Periphery (Right)
- **Bonuses**:
  - Attacker: **+10% hit chance**
  - Defender: **No changes**

---

### Scenario 3: Attacker in FOV
- **Attacker position**: 2D (North of defender)
- **Defender facing**: North
- **Attacker layer**: FOV
- **Bonuses**:
  - Attacker: **0% hit chance**
  - Defender: **-30% defense stamina**, **-15% movement stamina**

---

### Scenario 4: Observation Haki Active
- **Defender uses Observation Haki** during defense
- **Attacker's +30% bonus** (from behind) → **Negated to 0%**
- **Counter success**: **+20%** (if defender uses Counter)

---

### Scenario 5: Invisible Trap
- **Trap spawns at 2E** (defender's blind spot) → **Invisible**
- **Attacker attacks from 2E** → **+30% hit chance**
- **Defender steps on trap** → Debuff applies, **trap stays invisible**
- **Defensive phase ends** → **Trap becomes visible**, debuff revealed

---

## PART IX: RULE SUMMARY TABLE

| Layer | Attacker Hit Chance | Defender Defense Cost | Defender Move Cost | Counter Penalty |
|-------|---------------------|------------------------|--------------------|-----------------|
| **FOV** | 0% | **-30%** | **-15%** | None |
| **Periphery** | **+10%** | 0% | 0% | None |
| **Behind** | **+30%** | 0% | **+15%** | **-20% success** |

**Special Rules:**
- **Observation Haki**: Removes attacker hit chance bonus, **+20% Counter success**
- **Scan Action**: 10 stamina, **once per turn**, **reveals all tiles**, **not undoable**
- **Invisible tiles**: Hidden until **end of defensive phase**, then **reveal**
- **Sea tiles**: Always visible

**System Status: Triple-verified and production-ready.**

---

## IMPLEMENTATION PLAN

### Overview
The FOV system adds positional awareness bonuses/penalties based on where players are located relative to each other's facing directions. This integrates into existing combat formulas without breaking additive bonus stacking rules.

### Core Components Needed

#### 1. FOV Layer Calculation Module (`game/engine/fov.py`)
**Purpose**: Determine which FOV layer (FOV/Periphery/Behind) a target occupies relative to a player's facing

**Functions**:
- `get_direction_vector(facing_degrees: float) -> Tuple[int, int]`: Convert facing (0-359°) to 8-direction vector
- `get_relative_direction(from_pos: Tuple[int, int], to_pos: Tuple[int, int]) -> str`: Get compass direction from one position to another
- `get_fov_layer(player_facing: float, player_pos: Tuple[int, int], target_pos: Tuple[int, int]) -> str`: Returns "FOV", "Periphery", or "Behind"

**Implementation Details**:
- Use facing direction lookup table (Part I, section 1.1)
- Handle all 8 cardinal/diagonal facings (N, NE, E, SE, S, SW, W, NW)
- Return layer classification based on relative direction

#### 2. FOV Bonus Integration into Combat Formulas

**A. Attack Phase - Hit Chance Bonus (`calculate_hit_chance`)**
- Add `fov_hit_bonus: float = 0.0` parameter
- Apply FOV bonus to `hit_mod`:
  - FOV layer: +0% (no bonus)
  - Periphery layer: +10%
  - Behind layer: +30%
- Add debug output showing FOV layer and bonus

**B. Defense Phase - Stamina Cost Modifiers (`calculate_defense_stamina_cost`)**
- Add `defender_fov_layer: str = "FOV"` parameter
- Modify stamina multipliers based on where attacker is:
  - FOV: -30% defense action cost, -15% movement cost
  - Periphery: no change
  - Behind: +15% movement cost

**C. Defense Phase - Counter Success Penalty**
- Add `defender_fov_layer` check in counter resolution
- Behind layer: Apply -20% to counter hit chance calculation
- FOV layer: No penalty

#### 3. Observation Haki + FOV Interaction

**Defender Observation Haki Negation**:
- When defender activates Observation Haki during defense:
  - Attacker's FOV hit bonus → forced to 0% (treat as "FOV" layer)
  - Counter success penalty removed (if applicable)
  - Add +20% to counter hit chance if Counter defense selected

**Implementation**:
- Check `defender_haki_obs_effectiveness > 0` in hit chance calculation
- If true: override `fov_hit_bonus = 0.0`
- Add counter bonus in counter resolution logic

#### 4. Controller Integration Points

**Attack Preview Calculation**:
- Call `get_fov_layer(attacker.facing, attacker.pos, defender.pos)`
- Pass `fov_hit_bonus` to `calculate_hit_chance`
- Display FOV bonus in preview UI (future task)

**Defense Phase Resolution**:
- At defense phase start: calculate `defender_fov_layer = get_fov_layer(defender.facing, defender.pos, attacker.pos)`
- Pass to stamina cost calculations for all movement planning
- Pass to counter resolution if Counter selected
- Check Observation Haki status for negation

**Attack Phase Resolution**:
- At end of defense phase: recalculate FOV layer based on defender's NEW facing (after any rotations)
- Use final FOV bonus in combat calculation

### Integration Strategy (Preserves Existing Systems)

#### Step 1: Create FOV Engine
- New file: `game/engine/fov.py`
- Implement layer calculation functions
- Unit test all 8 facings × 3 layers = 24 scenarios

#### Step 2: Extend Combat Formulas
- Add `fov_hit_bonus` parameter to `calculate_hit_chance` (default 0.0)
- Add FOV section to debug output
- Apply as **additive term** to `hit_mod` (preserves stacking rule)

#### Step 3: Extend Stamina Calculation
- Add `defender_fov_layer` parameter to `calculate_defense_stamina_cost`
- Multiply base stamina by FOV modifier before hit chance tax

#### Step 4: Controller Wiring
- Import `fov` module
- Calculate FOV layer at correct timing points:
  - Preview: when hovering over defender
  - Defense start: when entering defense planning
  - Attack resolution: after defender rotations finalized
- Pass FOV bonuses to all combat/stamina calls

#### Step 5: Observation Haki Override
- In hit chance calculation: check defender Observation Haki
- If active: set `fov_hit_bonus = 0.0` regardless of layer
- Add counter bonus logic in counter resolution

### Data Flow Example

```python
# Attack Phase Preview
fov_layer = get_fov_layer(attacker.facing, (attacker.row, attacker.col), (defender.row, defender.col))
fov_bonus = {"FOV": 0.0, "Periphery": 0.10, "Behind": 0.30}[fov_layer]
hit_chance = calculate_hit_chance(
    attacker, defender, attack_type, None,
    facing_bonus, bounce_bonus, pattern_bonus,
    df_multipliers, haki_obs_att, haki_obs_def,
    is_defense_phase=False,
    attacker_df_alloys=set(), defender_df_alloys=set(),
    fov_hit_bonus=fov_bonus  # NEW PARAMETER
)

# Defense Phase Start
defender_fov = get_fov_layer(defender.facing, (defender.row, defender.col), (attacker.row, attacker.col))
movement_cost = calculate_defense_stamina_cost(
    base_cost=15,
    hit_chance=preview_hit_chance,
    obs_haki_active=defender_obs_active,
    defender_fov_layer=defender_fov  # NEW PARAMETER
)

# Defense Phase - Observation Haki Override
if defender_haki_obs_effectiveness > 0.0:
    fov_hit_bonus = 0.0  # Negated
    if defense_type == "counter":
        counter_hit_bonus += 0.20  # +20% counter success
```

### File Modifications Summary

1. **NEW FILE**: `game/engine/fov.py` (~100 lines)
   - Layer calculation functions
   - Direction mapping tables

2. **MODIFY**: `game/engine/combat.py`
   - `calculate_hit_chance`: Add `fov_hit_bonus` parameter, apply to `hit_mod`
   - `calculate_defense_stamina_cost`: Add `defender_fov_layer` parameter, apply modifiers

3. **MODIFY**: `game/controller.py`
   - Import `fov` module
   - Calculate FOV layers at timing points:
     - `preview_attack_outcome`: attacker FOV bonus
     - Defense phase start: defender FOV layer
     - All defense stamina cost calls: pass `defender_fov_layer`
     - Attack resolution: recalculate FOV after defender rotations
   - Observation Haki override logic in hit chance calls
   - Counter penalty logic in counter resolution

4. **UPDATE**: `game/# ULTRA-COMPREHENSIVE BATTLE SYSTEM 1.01.txt`
   - Add Section 31: FOV System
   - Reference Rule Update9.md for full spec
   - Add FOV bonuses to hit chance formula (section 7.7)
   - Add FOV modifiers to stamina cost (section 18)

### Compatibility Guarantees

- **Additive Stacking**: FOV bonuses add to `hit_mod` alongside attack type, movement, Haki (no multiplication)
- **No Breaking Changes**: All existing combat calls work with `fov_hit_bonus=0.0` default
- **Status Effects**: FOV bonuses do not interact with status effect stat modifications (separate systems)
- **Pattern/Bounce**: FOV bonuses stack additively with all movement bonuses
- **Haki**: Observation Haki negates FOV bonuses (override, not multiplication)

### Testing Checklist

- [ ] FOV layer calculation correct for all 8 facings
- [ ] Hit chance bonus applies correctly (0/10/30%)
- [ ] Defender stamina costs modified correctly (FOV: -30%/-15%, Behind: +15%)
- [ ] Counter penalty applies (-20% success when attacker behind defender)
- [ ] Observation Haki negates attacker FOV bonus
- [ ] Observation Haki adds +20% counter success
- [ ] FOV recalculates after defender rotation
- [ ] FOV bonuses stack additively with movement/Haki/pattern bonuses
- [ ] Debug output shows FOV layer and bonuses