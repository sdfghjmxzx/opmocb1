# MULTIPLAYER COMBAT PIPELINE - SOURCE OF TRUTH

## Phase 1: ATTACK PHASE (Attacker P1)

1. **Attacker (P1) plans movement + attack**
   - Calculates BASE damage (no defense calculations)
   - Calculates MISS (is defender in attack pattern?)
   - Sends `combat_attack` to server with:
     - `is_miss` (boolean)
     - `wall_damage` (base damage for walls/objects)
     - `attack_tiles` (pattern tiles)
     - `breakthrough_tiles`
     - Movement bonuses (facing, bounce, pattern)

2. **Server receives `combat_attack`**
   - Stores payload with timestamp
   - Broadcasts to Defender (P2)

3. **Defender (P2) receives `combat_attack`**
   - Sees enemy attack pattern
   - **DOES MISS CALCULATION** - checks if they're in pattern
   - **SENDS VALIDATION BACK TO SERVER** (currently sends hit_chance + damage too, but only MISS is needed for validation at this stage - should remove extra data)
   - If NOT a miss → can continue to defense planning
   - Applies wall_damage to walls/objects to check breakthrough correctly

## Phase 2: DEFENSE PHASE (Defender P2)

4. **Defender (P2) plans defense movement/rotation**
   - Moves to final position
   - Rotates facing
   - **Calculates FULL damage + hit_chance** (with defense bonuses applied)
   - Calculates MISS (am I still in pattern after movement?)
   - Sends `combat_defense` to server with:
     - `path` (movement)
     - `facings` (rotation history)
     - `final_facing`
     - `actions` (list of moves/rotates/defense)
     - **`is_miss`** (IMPORTANT)
     - **`hit_chance`** (full calculation)
     - **`damage`** (full calculation)
     - `counter_is_miss`, `counter_hit_chance`, `counter_damage` (if countering)

5. **Server receives `combat_defense`**
   - Stores payload for later validation
   - Broadcasts defender's movement details to Attacker (P1)

## Phase 3: ATTACKER VALIDATION (Attacker P1)

6. **Attacker (P1) receives `combat_defense`**
   - Sees defender's final position after movement
   - **CANNOT move or manipulate anything**
   - Recalculates FULL damage + hit_chance using defender's final position
   - **Only purpose: provide validation to server**
   - Sends `combat_attacker_validation` to server with:
     - `is_miss`
     - `hit_chance`
     - `damage`
     - `counter_is_miss`, `counter_hit_chance`, `counter_damage`

7. **Server receives `combat_attacker_validation`**
   - Now has all 3 payloads: attack, defense, validation
   - **Cross-checks**: Does attacker validation match defender calculations?
   - If match: Rolls RNG for hit/miss using validated hit_chance
   - Sends `combat_resolution` to BOTH clients with:
     - `hit` (boolean from RNG)
     - `damage` (validated value)
     - `counter_hit`, `counter_damage`

## Phase 4: RESOLUTION (Both Clients)

8. **Both clients receive `combat_resolution`**
   - Apply damage from server (authority)
   - Apply push/knockback
   - Apply status effects
   - Update UI
   - **Advance turn** (increment system turn counter)

---

## CRITICAL RULES

1. **Attacker in attack phase**: Sends attack → waits for defense
2. **Defender in defense phase**: Receives attack → plans defense → sends defense
3. **Attacker receives defense**: DOES NOT change phase, DOES NOT call confirm_turn(), ONLY calculates validation
4. **Server sends resolution**: BOTH clients apply damage and advance turn together
5. **NO client-side damage application** until server resolution arrives
6. **NO turn advancement** until server resolution arrives

---

## CURRENT BUG

- `apply_remote_defense_payload()` calls `confirm_turn()` which ends the turn and advances phase
- This breaks the pipeline because attacker needs to stay in attack-waiting-for-resolution state
- Fix: Remove `confirm_turn()` call, just apply defender's movement/state for validation calculation
