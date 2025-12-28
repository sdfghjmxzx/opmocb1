# Multiplayer Data Requirements - Traced from Combat Formulas

## Core Combat Formulas

The entire multiplayer validation is built around 2 formulas:
1. **calculate_hit_chance()** - determines if attack hits
2. **calculate_damage()** - calculates damage dealt

Both formulas are in `engine/combat.py` and require identical inputs.

## What the Formulas Actually Need

### Formula Inputs (from combat.py lines 15-30, 47-63)

```python
calculate_hit_chance(
    attacker,                           # Player object with stats
    defender,                           # Player object with stats  
    attack_type,                        # "quick"/"normal"/"heavy"/"special:name"
    defense_type,                       # "evade"/"defend"/"counter" or None
    facing_bonus,                       # float: 0.0 to 0.50
    bounce_bonus,                       # float: 0.0 to 0.20
    pattern_bonus,                      # float: varies by pattern
    attacker_df_multipliers,            # Dict or None
    attacker_haki_obs_effectiveness,    # float: 0.0 to 1.0
    defender_haki_obs_effectiveness,    # float: 0.0 to 1.0
    is_defense_phase,                   # bool
    attacker_df_alloys,                 # set: {"hit_alloy", "damage_alloy", etc}
    defender_df_alloys,                 # set
    fov_hit_bonus                       # float: 0.0/0.10/0.30
)
```

## Data Source Tracing

### 1. MOVEMENT BONUSES (controller.py lines 3192-3202, 3422-3432)

**Facing Bonus:**
- Calculated from: `self.facing_chain_length` 
- Formula: `min(0.10 * chain_length, 0.50)`
- Network: **not sent** – both clients (and optionally server) reconstruct `facing_chain_length` from the received movement path + facing history.

**Bounce Bonus:**
- Calculated from: `self.bounce_chain_length` and `self.bounce_active` (bool)
- Formula: `hits[min(max(1, chain_length), 5) - 1]` where `hits = [0.10, 0.125, 0.15, 0.175, 0.20]`
- Network: **not sent** – reconstructed by running the same bounce detection (`detect_bounce`) over the received path and the synchronized wall/tile state.

**Pattern Bonus:**
- Calculated from: `self.pattern_memory` / `PatternEvaluator.evaluate()` using path + facing + opponent position
- Network: **not sent** – reconstructed by running `PatternEvaluator.evaluate()` on both clients using the same path, facing and opponent position.

**Result:** movement bonuses are **purely derived** from the shared movement data, **never transmitted** as explicit values.

### 2. ACTION TYPES (controller.py lines 3204-3206, 3409-3413)

- **Attack Type**: string from planned_actions ("quick"/"normal"/"heavy"/"special:name"/"skip")
- **Defense Type**: string from planned_actions ("evade"/"defend"/"counter" or None)
- **Base Damage**: Always 20, modified by special attacks (controller.py line 3406, 3449-3452)

For specials: Send special name, both players look up damage_modifier from JSON
- Send: `attack_type` (1 byte enum) + `defense_type` (1 byte enum) + `special_name` (optional, ~10 bytes avg) = **~12 bytes max**

### 3. HAKI STATE (controller.py lines 3184-3188, 3522-3530)

**Haki Activation:**
- Tracked in: `self.applied_haki_alloys` (set of strings: "armament", "observation", "conqueror")
- Used to set flags: `attacker_arm_active`, `attacker_obs_active`, etc
- Send: 2 bits (armament active Y/N, observation active Y/N) = **1 byte**

**Haki Effectiveness:**
- Calculated from: `attacker.haki_armament`, `defender.haki_armament`, `both_activated` flag
- Formula (haki.py lines 26-41):
  - If only one uses haki: `haki_stat / 100.0`
  - If both use haki: `max(0.0, (attacker_haki - defender_haki) / 100.0)`
- **CRITICAL**: Stats are synchronized, so both players calculate identical effectiveness
- Send: **NOTHING** (calculated from synchronized stats)

### 4. DEVIL FRUIT ALLOYS (controller.py lines 3213-3214, 3402, 3533-3534)

**DF Alloys:**
- Tracked in: `self.applied_df_alloys` (set of strings like "damage_alloy", "hit_alloy", "defense_alloy")
- Effects (from combat.py):
  - "hit_alloy": +8% hit chance
  - "damage_alloy": +10% damage
  - "defense_alloy": +10% dodge bonus
- Send: Bitmask (3 bits for common alloys) = **1 byte**

### 5. DEVIL FRUIT TYPE ADVANTAGE (controller.py lines 3511-3520)

**DF Multipliers:**
- Calculated from: `attacker.devil_fruit_type`, `defender.devil_fruit_type`, both mastery stats
- Uses `calculate_type_advantage()` from `engine/devil_fruit.py`
- **CRITICAL**: Both players have identical DF type/mastery data, calculate same multipliers
- Send: **NOTHING** (calculated from synchronized character data)

### 6. FOV POSITIONING (controller.py lines 3540-3546)

**FOV Hit Bonus:**
- Calculated from: defender's facing direction + attacker position + defender position
- Formula: `get_fov_hit_bonus(defender.facing, (def_row, def_col), (att_row, att_col))`
- Returns: 0.0 (front), 0.10 (periphery), or 0.30 (behind)
- **CRITICAL**: Positions and facing are part of movement data
- Send: **NOTHING** (calculated from movement path final position)

### 7. STATUS EFFECTS (controller.py lines 3536-3538, 7169-7206)

**Stat Modifications:**
- Tracked in: `self.active_effects` (dict by player name)
- Effects: "slow" reduces speed/reaction, "freeze" reduces defense
- Applied via: `_get_effective_player()` creates modified copy
- **CRITICAL**: Status effects are applied by server (RNG-based), synced to both clients
- Send: **NOTHING** (already synchronized)

### 8. MOVEMENT PATH & POSITION (controller.py lines 3206-3210, 3479-3484)

**Position Data:**
- Final attacker position: `(attacker.row, attacker.col, attacker.facing)`
- Final defender position: `(defender.row, defender.col, defender.facing)` 
- **Used for**: FOV bonus calculation, attack pattern generation
- Send: 6 bytes (3 positions * 2 players) = **6 bytes**

**Movement Actions:**
- List of movements: `[{"from": [r,c], "to": [r,c], "rotation": degrees}, ...]`
- **Used for**: Reproducing exact movement bonuses on both clients
- Send: ~8 bytes per movement * max 3 movements = **~24 bytes**

## TOTAL DATA PER TURN

### Attack Phase (attacker to server to defender):
```
Movement data:        ~17 bytes (path + facing history)
Position data:         6 bytes (final positions)
Action types:         ~12 bytes (attack/defense/special)
Haki state:            1 byte (2 bits: arm/obs active)
DF alloys:             1 byte (bitmask)
Derived bonuses:       0 bytes (computed locally on both clients)
```
**Total: ~37 bytes**

### Defense Phase (defender to server, server validates):
```
Movement data:        ~17 bytes (defender movement path + facings)
Position data:         6 bytes (defender final position)
Local formulas:        0 bytes on wire (defender computes hit_chance + damage locally)
Hit chance value:      2 bytes (encoded float or int scaled *1000)
Damage calculated:     2 bytes (int16)
Hit result flag:       1 byte (server's RNG outcome if needed)
```
**Total: ~28 bytes**

### Server Response (after validation):
```
Hit chance result:     1 byte (hit Y/N or packed flags)
Final damage:          2 bytes (if hit)
Status effects:       ~5 bytes (if any new effects applied)
Tile spawns:          ~8 bytes (if any)
```
**Total: ~16 bytes**

## GRAND TOTAL: ~80–90 bytes per turn (worst case)

## THE CRITICAL INSIGHT: Bonus Verification

**Problem**: Player 2 receives Player 1's movement list, but how does Player 2 verify bonuses WITHOUT entering planning mode?

**Solution**: The bonus calculation functions are **PURE FUNCTIONS** that don't require planning mode!

### Bonus Calculation Functions (All Pure):

1. **Facing Bonus** - `_update_facing_chain()` (controller.py:1617-1650)
   - Input: `path` (list of positions), `move_facing_history` (facing at each move)
   - Output: `facing_chain_length` (0-5)
   - Logic: Walk backward from end, count consecutive moves matching facing

2. **Bounce Bonus** - `detect_bounce()` (engine/push_bounce.py:8-252)
   - Input: `path_segment` (last 3 tiles), `wall_system`, `tile_system`
   - Output: `{'type': 'cardinal'/'diagonal', 'hit_bonus': 0.2}` or None
   - Logic: Check entry→wall→exit pattern, validate bounce rules

3. **Pattern Bonus** - `PatternEvaluator.evaluate()` (engine/pattern.py:191-274)
   - Input: `path`, `facing`, `opponent_position`
   - Output: `{'name': 'circle', 'hit_bonus': 0.20, 'damage_bonus': 0.0}` or None
   - Logic: Detect circle/zigzag/spearhead/knight patterns

### Verification Pipeline:

```python
def verify_opponent_bonuses(movement_data, wall_system, tile_system, opponent_pos):
    """
    Player 2 receives Player 1's movement data and independently verifies bonuses.
    NO PLANNING MODE REQUIRED - pure calculation from data.
    """
    # Extract from movement_data
    path = movement_data['path']  # [(r,c), (r,c), ...]
    move_facings = movement_data['facings']  # [270.0, 270.0, 315.0, ...]
    final_facing = movement_data['final_facing']  # 315.0
    
    # 1. Calculate facing bonus
    facing_chain_length = 0
    for i in range(len(path) - 1, 0, -1):
        r1, c1 = path[i-1]
        r2, c2 = path[i]
        move_dir = (c2 - c1, r2 - r1)
        facing_at_move = move_facings[i-1]
        facing_vec = _facing_to_vector(facing_at_move)
        if move_dir == facing_vec:
            facing_chain_length += 1
        else:
            break
    facing_bonus = min(0.10 * facing_chain_length, 0.50)
    
    # 2. Calculate bounce bonus
    bounce_chain_length = 0
    bounce_active = False
    for i in range(2, len(path)):
        segment = path[i-2:i+1]  # 3 tiles
        bounce_result = detect_bounce(segment, wall_system, tile_system)
        if bounce_result:
            # Complex chain logic from controller.py:1293-1370
            bounce_chain_length += 1
            bounce_active = True
    
    if bounce_active:
        hits = [0.10, 0.125, 0.15, 0.175, 0.20]
        idx = min(max(1, bounce_chain_length), 5) - 1
        bounce_bonus = hits[idx]
    else:
        bounce_bonus = 0.0
    
    # 3. Calculate pattern bonus
    pattern_evaluator = PatternEvaluator()  # Uses same JSON config
    pattern_result = pattern_evaluator.evaluate(path, final_facing, opponent_pos)
    if pattern_result:
        pattern_hit = pattern_result.get('hit_bonus', 0.0)
        pattern_dmg = pattern_result.get('damage_bonus', 0.0)
    else:
        pattern_hit = 0.0
        pattern_dmg = 0.0
    
    return {
        'facing_bonus': facing_bonus,
        'bounce_bonus': bounce_bonus,
        'pattern_hit': pattern_hit,
        'pattern_dmg': pattern_dmg
    }
```

### What Gets Sent:

**Movement Data (Attack Phase):**
```python
{
    'path': [(5,3), (5,4), (4,4), (3,4)],  # 4 moves * 2 bytes = 8 bytes
    'facings': [270, 270, 315, 315],       # 4 facings * 1 byte (div 45) = 4 bytes
    'final_facing': 315,                    # 1 byte
    'rotations': [0, 0, +45, 0]            # 4 rotations * 1 byte (div 45) = 4 bytes
}
# Total: ~17 bytes for movement
```

**Both players then run the SAME calculation functions:**
- Player 1 calculates during planning → gets bonuses
- Player 1 sends movement data → server
- Server forwards to Player 2
- Player 2 receives data → runs SAME functions → gets SAME bonuses
- Player 2 sends calculated bonuses back to server
- Server compares: if `player1_bonuses == player2_bonuses` → valid, else abort

### Key Advantages:

1. **No planning mode needed** - Pure functions operate on data structures
2. **Deterministic** - Same inputs = same outputs, always
3. **Small data** - Only send path + facings, not bonus values
4. **Trustless** - Both players calculate independently, server verifies match
5. **Cheat-proof** - Opponent can't lie about bonuses when both calculate from same movement

## What We DON'T Send

1. **Player Stats** - Synchronized only on status effect changes
2. **Devil Fruit Types** - Part of character selection, never changes
3. **Haki Effectiveness Values** - Calculated from synchronized stats
4. **DF Type Multipliers** - Calculated from synchronized character data
5. **FOV Bonuses** - Calculated from movement data
6. **Attack Pattern Tiles** - Calculated from position + action type
7. **Wall Data** - Synchronized separately when walls change

## Validation Strategy

### Both Players Calculate:
1. Movement bonuses (from received movement list)
2. Haki effectiveness (from synchronized stats + activation flags)
3. DF multipliers (from synchronized character data)
4. FOV bonuses (from received positions)
5. Hit chance formula (deterministic with all above inputs)
6. Damage formula (deterministic with all above inputs)

### Server Calculates:
1. **Hit chance RNG roll** - compares random(0,1) vs hit_chance
2. **Status effect RNG** - applies/extends effects based on probability
3. **Tile spawn RNG** - spawns special tiles based on probability

### Server Validates:
1. Both players' calculated hit_chance values match
2. Both players' calculated damage values match
3. If mismatch: abort game (bug or cheat detected)

## Implementation Notes

### Data Encoding
- Use byte arrays, not JSON
- Movement: 3 bytes per move (row, col, rotation/8)
- Positions: 1 byte row, 1 byte col, 1 byte facing/45
- Bonuses: float32 (4 bytes) or int16 scaled (*100)
- Flags: bitmasks

### Optimization
- Movement lists can be delta-encoded (relative to previous position)
- Bonuses can be sent as int16 (multiply by 100, divide on receive)
- Common patterns: pre-define pattern IDs (1 byte) instead of sending bonuses

### Critical Insight
The formulas are **100% deterministic** given the inputs. The ONLY randomness is:
1. Hit chance roll (server does this)
2. Status effect application (server does this)
3. Tile spawns (server does this)

Everything else is math that both players perform identically.
