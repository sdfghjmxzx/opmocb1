# MULTIPLAYER COMBAT PIPELINE

## Architecture Overview

**Model**: Hybrid Server-Client Validation
- **Clients calculate** all combat formulas deterministically
- **Server validates** cross-checks and handles RNG (hit chance, spawns, tile effects)
- **Server authority** on random outcomes prevents desync
- **Mismatch = abort** - if calculations don't match, game ends (bug or cheat detected)

---

## Data Flow Per Turn

### Phase 1: ATTACK PHASE (Attacker Planning)

**Attacker Client → Server:**
```json
{
  "phase": "attack",
  "turn": 5,
  "movements": [
    {"from": [5,3], "to": [4,3], "rotation": 0},
    {"from": [4,3], "to": [3,3], "rotation": -45}
  ],
  "bonuses": {
    "facing": {"chain_length": 2, "bonus": 0.20},
    "bounce": {"chain_length": 0, "bonus": 0.0},
    "pattern": {"name": "flanking", "bonus": 0.15}
  },
  "alloys": {
    "haki": {"type": "armament", "effectiveness": 0.25},
    "df": {"damage_alloy": 15, "hit_alloy": 10}
  },
  "action": {
    "type": "heavy",
    "special": null
  },
  "base_damage": 85,
  "attacker_stats": {
    "strength": 100,
    "speed": 80,
    "haki_arm": 90
  }
}
```

**Server → Defender Client:**
- Forwards entire attack package
- Defender client re-calculates locally to verify

---

### Phase 2: DEFENSE PHASE (Defender Planning)

**Defender Client → Server:**
```json
{
  "phase": "defense",
  "turn": 5,
  "movements": [
    {"from": [1,3], "to": [2,3], "rotation": 45}
  ],
  "bonuses": {
    "facing": {"chain_length": 1, "bonus": 0.10},
    "bounce": {"chain_length": 0, "bonus": 0.0},
    "pattern": {"name": null, "bonus": 0.0}
  },
  "alloys": {
    "haki": {"type": "observation", "effectiveness": 0.20},
    "df": {"defense_alloy": 20}
  },
  "action": {
    "type": "counter",
    "special": null
  },
  "defender_stats": {
    "defense": 90,
    "reaction": 85,
    "haki_obs": 80
  },
  "calculated_damage": 62
}
```

---

### Phase 3: SERVER VALIDATION & RESOLUTION

**Server validates:**

1. **Movement sync** - both clients agree on final positions
2. **Bonus match** - facing/bounce/pattern calculations match
3. **Alloy match** - applied alloys and effectiveness values match
4. **Stat sync** - if stats changed (status effects), both clients report same values

**Server calculates (RNG):**
```json
{
  "hit_chance_roll": 73,
  "hit_success": true,
  "tile_spawns": [
    {"type": "sea_tile", "pos": [3,5], "hp": 120}
  ],
  "status_effect_rolls": {
    "burn_duration": 3,
    "poison_damage": 15
  }
}
```

**Server → Both Clients:**
```json
{
  "result": "success",
  "hit_roll": 73,
  "hit_success": true,
  "final_damage": 62,
  "spawns": [...],
  "status_effects": [...]
}
```

---

## Validation Rules

### Movement Validation
- **No server check needed** - if movements differ, bonuses will differ → mismatch detected

### Bonus Validation
- **Facing chain**: `chain_length` + `bonus_value`
- **Bounce chain**: `chain_length` + `bonus_value` + `bounce_type`
- **Pattern**: `pattern_name` + `bonus_value`

### Alloy Validation
- **Haki**: `type` + `effectiveness` (based on stats)
- **DF**: `alloy_type` + `bonus_value` (based on mastery)

### Stat Synchronization
- **Send on change only** - when status effects modify stats
- **Both clients must report** same stat values before resolution
- **Mismatch → abort** - indicates desync or tampering

### Damage Validation
- **Base damage** sent by attacker (used for walls/tiles)
- **Final damage** calculated by both clients after defense
- **Both values must match** before server accepts

---

## Implementation Tasks

### Task 1: Define Action Data Structure
**File**: `controller.py`
**Goal**: Create serializable action data format
- [ ] Define `ActionData` class for attack phase
- [ ] Define `DefenseData` class for defense phase
- [ ] Include all bonuses, alloys, movements, rotations
- [ ] Add serialization methods (to JSON)

### Task 2: Client-Side Action Builder
**File**: `controller.py`
**Goal**: Extract action data from `planned_actions` and combat state
- [ ] Method: `build_attack_action_data()` - extracts from attack planning
- [ ] Method: `build_defense_action_data()` - extracts from defense planning
- [ ] Include movement path with rotations
- [ ] Include bonus calculations (facing/bounce/pattern)
- [ ] Include alloy state (haki + DF)
- [ ] Include base damage calculation

### Task 3: Server-Side Validation Logic
**File**: `multiplayer_server.py`
**Goal**: Cross-check action data from both clients
- [ ] Method: `validate_action_sync(attacker_data, defender_data)`
- [ ] Compare movements (final positions)
- [ ] Compare bonuses (values must match)
- [ ] Compare alloys (types and effectiveness)
- [ ] Compare stats (if changed)
- [ ] Compare final damage
- [ ] Return validation result + mismatches

### Task 4: Server-Side RNG Resolution
**File**: `multiplayer_server.py`
**Goal**: Handle randomized combat elements
- [ ] Method: `calculate_hit_chance(attacker_stats, defender_stats, bonuses)`
- [ ] Method: `roll_hit_chance(hit_chance_value)`
- [ ] Method: `roll_tile_effects(tile_config)`
- [ ] Method: `roll_map_spawns(avg_primary_sum)`
- [ ] Return RNG results to both clients

### Task 5: Network Protocol - Attack Phase
**File**: `multiplayer_server.py` + `script.rpy`
**Goal**: Send/receive attack action data
- [ ] Client: Send attack data after confirm_turn()
- [ ] Server: Store attack data, forward to defender
- [ ] Defender: Receive and validate attack data

### Task 6: Network Protocol - Defense Phase
**File**: `multiplayer_server.py` + `script.rpy`
**Goal**: Send/receive defense action data + validation
- [ ] Client: Send defense data after confirm_turn()
- [ ] Server: Cross-check with stored attack data
- [ ] Server: Calculate RNG (hit chance, spawns)
- [ ] Server: Send resolution to both clients

### Task 7: Client-Side Result Application
**File**: `controller.py`
**Goal**: Apply server-validated results to game state
- [ ] Method: `apply_combat_result(result_data)`
- [ ] Apply damage to players
- [ ] Apply status effects
- [ ] Spawn tiles/walls from server
- [ ] Update game state

### Task 8: Stat Change Synchronization
**File**: `controller.py` + `multiplayer_server.py`
**Goal**: Sync stat changes from status effects
- [ ] Detect stat changes after turn
- [ ] Send stat deltas to server
- [ ] Server waits for both clients to confirm
- [ ] Server validates stats match before next turn

### Task 9: Abort/Desync Handling
**File**: `multiplayer_server.py` + `script.rpy`
**Goal**: Handle validation failures gracefully
- [ ] Server sends abort message on mismatch
- [ ] Clients display desync/cheat warning
- [ ] Return to lobby with error state
- [ ] Log mismatch details for debugging

### Task 10: Testing & Integration
**Goal**: Verify full pipeline works end-to-end
- [ ] Test normal combat flow (hit/miss)
- [ ] Test status effects and stat changes
- [ ] Test tile spawns
- [ ] Test intentional mismatch (force abort)
- [ ] Test network latency handling

---

## Data Size Estimation

**Per Turn** (both phases combined):
- Movements: ~50 bytes (2-3 moves with rotations)
- Bonuses: ~80 bytes (facing + bounce + pattern)
- Alloys: ~60 bytes (haki + DF types)
- Stats: ~40 bytes (3-4 stat values)
- Damage: ~20 bytes (base + final)
- **Total: ~250 bytes per turn**

**Server Processing Per Turn**:
- 2-3 value comparisons (bonuses, damage)
- 1 RNG roll (hit chance)
- 0-2 spawn RNGs (if applicable)
- **Total: <1ms per turn**

**Scalability**: 100 concurrent games × 250 bytes/turn = 25KB/turn across all games = negligible bandwidth

---

## Next Steps

1. Review this pipeline and confirm architecture
2. Discuss implementation approach for each task
3. Start with Task 1 (data structures) once plan is approved
