import asyncio
import json
import uuid
import time
import random

import websockets


connected_clients = set()
claimed_usernames = {}  # session_id -> username
lobbies = {}  # lobby_id -> {"id": str, "name": str, "host_session": str, "host_name": str, "players": {session_id: {"name": str, "ready": bool}}, "chat": list, "locked": bool}
session_lobbies = {}  # session_id -> lobby_id
session_websockets = {}  # session_id -> websocket
last_ping = {}  # session_id -> last heartbeat timestamp
match_queue = []  # FIFO queue of sessions searching for quick match
pending_matches = {}  # match_id -> {"host": session_id, "guest": session_id, "host_accepted": bool, "guest_accepted": bool, "lobby_data": dict, "timestamp": float}
session_pending_match = {}  # session_id -> match_id
# Per-lobby map state for multiplayer combat (server-authoritative)
lobby_maps = {}  # lobby_id -> {"tiles": list, "walls": list, "sea_tiles": list}
# Pending combat pairs per lobby/turn for server-side resolution
pending_combat = {}  # (lobby_id, turn) -> {"attack": dict, "defense": dict, "attacker_validation": dict}
pending_combat_timestamps = {}  # (lobby_id, turn) -> timestamp when first payload arrived
pending_combat_retries = {}  # (lobby_id, turn) -> {"validation_retries": int, "mismatch_retries": int}
# Pending kicks: track host kick requests to verify against leave_lobby
pending_kicks = {}  # lobby_id -> {"kicker_session": str, "kicked_session": str, "timestamp": float}

# ═══════════════════════════════════════════════════════════════════════════════
# BATTLE TIMER SYSTEM - Server State
# ═══════════════════════════════════════════════════════════════════════════════
lobby_turn_timers = {}      # lobby_id -> start_timestamp (ONE shared timer per lobby)
lobby_turn_confirmed = {}   # (lobby_id, turn, phase, session_id) -> bool (per-player tracking for skip logic)
lobby_player_flags = {}     # (lobby_id, session_id) -> flag_count (0-3)
lobby_grace_periods = {}    # (lobby_id, session_id) -> {"active": bool, "start": timestamp, "packets": []}
lobby_current_turn = {}     # lobby_id -> current_turn_number
lobby_current_phase = {}    # lobby_id -> "attack" or "defense"
lobby_sync_tasks = {}       # (lobby_id, turn) -> {"sync_20": task, "sync_40": task}
lobby_sync_tasks = {}       # (lobby_id, turn) -> {"sync_20": task, "sync_40": task}


def _generate_per_turn_spawns(lobby_id: str) -> list:
    """Generate per-turn tile spawns following tiles.py rules.
    
    Per-turn spawn rules (from tiles.py):
    - trap_continuous: 1% chance, cap 1
    - trap_momentary: 1% chance, cap 1, duration 1-3
    - drop_continuous: 1% chance, no cap
    - drop_momentary: 1% chance, cap 1, duration 1-3
    - Walls do NOT spawn per turn
    
    Returns: List of new tile dicts [{"row": int, "col": int, "tile_type": str, "duration": int/None}]
    """
    if lobby_id not in lobby_maps:
        return []
    
    map_state = lobby_maps[lobby_id]
    
    # Get occupied coordinates (updated by validation in Phase 2)
    occupied = set()
    if "occupied" in map_state:
        for coord in map_state["occupied"]:
            try:
                occupied.add(tuple(coord))
            except Exception:
                pass
    else:
        # Fallback: rebuild from map state
        for tile in map_state.get("tiles") or []:
            try:
                occupied.add((int(tile["row"]), int(tile["col"])))
            except Exception:
                pass
        for wall in map_state.get("walls") or []:
            try:
                occupied.add((int(wall["row"]), int(wall["col"])))
            except Exception:
                pass
    
    # Add player positions to occupied
    occupied.add((5, 3))  # Player 1 start
    occupied.add((1, 3))  # Player 2 start
    
    # Count existing tiles by type for cap enforcement
    existing_counts = {}
    for tile in map_state.get("tiles") or []:
        tile_type = tile.get("tile_type")
        if tile_type:
            existing_counts[tile_type] = existing_counts.get(tile_type, 0) + 1
    
    # Per-turn spawnable types with rules
    spawnable_types = [
        ("trap_continuous", 0.01, 1, None),      # 1%, cap 1, continuous
        ("trap_momentary", 0.01, 1, (1, 3)),     # 1%, cap 1, duration 1-3
        ("drop_continuous", 0.01, None, None),   # 1%, no cap, continuous
        ("drop_momentary", 0.01, 1, (1, 3)),     # 1%, cap 1, duration 1-3
    ]
    
    new_tiles = []
    
    for tile_type, chance, cap, duration_range in spawnable_types:
        # Check cap
        if cap is not None:
            current_count = existing_counts.get(tile_type, 0)
            if current_count >= cap:
                continue  # Cap reached, skip this type
        
        # Roll spawn chance
        if random.random() < chance:
            # Find free coordinate
            for attempt in range(20):
                row = random.randint(0, 6)
                col = random.randint(0, 6)
                if (row, col) not in occupied:
                    # Determine duration
                    duration = None
                    if duration_range:
                        duration = random.randint(duration_range[0], duration_range[1])
                    
                    new_tile = {
                        "row": row,
                        "col": col,
                        "tile_type": tile_type,
                        "duration": duration
                    }
                    new_tiles.append(new_tile)
                    occupied.add((row, col))  # Prevent overlap within same spawn
                    
                    # Add to server map state
                    map_state.setdefault("tiles", []).append(new_tile)
                    print(f"[SERVER SPAWN] New tile: {tile_type} at ({row},{col}), duration={duration}")
                    break
    
    return new_tiles


def _generate_initial_map_for_lobby() -> dict:
    """Run RNG and assign coordinates for initial map objects.
    
    Server-authoritative spawn RNG:
    - Rolls spawn chances per walls.py and tiles.py rules
    - Assigns random coordinates avoiding overlaps
    - Returns coordinate lists for clients to render
    - Server tracks occupied positions to prevent future collisions
    """
    occupied = set([(5, 3), (1, 3)])  # Player starting positions
    
    # === WALLS: Per walls.py spawn rules ===
    walls = []
    wall_count = random.randint(2, 3)
    tiers = ['fragile', 'standard', 'reinforced']
    
    for _ in range(wall_count):
        for attempt in range(50):
            row = random.randint(0, 5)
            col = random.randint(0, 5)
            if (row, col) not in occupied:
                orientation = random.choice(['h', 'v'])
                tier = random.choice(tiers)
                walls.append({"row": row, "col": col, "orientation": orientation, "tier": tier})
                occupied.add((row, col))
                break
    
    # === TILES: Per tiles.py spawn rules (2% chance each, force unpassable if nothing spawned) ===
    tiles = []
    tile_types = ['unpassable', 'trap_continuous', 'trap_momentary', 'drop_continuous', 'drop_momentary']
    
    for tile_type in tile_types:
        spawn_chance = 0.02
        # Force unpassable if nothing has spawned yet (per tiles.py line 126)
        if random.random() < spawn_chance or (len(tiles) == 0 and tile_type == 'unpassable'):
            for attempt in range(20):
                r = random.randint(0, 6)
                c = random.randint(0, 6)
                if (r, c) not in occupied:
                    duration = random.randint(1, 3) if 'momentary' in tile_type else None
                    tiles.append({"row": r, "col": c, "tile_type": tile_type, "duration": duration})
                    occupied.add((r, c))
                    break
    
    # === SEA TILES: Per tiles.py spawn rules (20% chance, 1-4 groups per edge, 4-7 tiles per group) ===
    sea_tiles = []
    if random.random() < 0.20:
        edges = ['north', 'south', 'east', 'west']
        for edge in edges:
            group_count = random.randint(1, 4)
            for _ in range(group_count):
                group_size = random.randint(4, 7)
                if edge in ['north', 'south']:
                    # North/South: position is column (0-6)
                    max_start = max(0, 7 - group_size)
                    start_col = random.randint(0, max_start)
                    for i in range(group_size):
                        pos = start_col + i
                        if pos <= 6:  # Valid column range
                            sea_tiles.append({"edge": edge, "position": pos})
                else:  # east, west
                    # East/West: position is row (0-6)
                    max_start = max(0, 7 - group_size)
                    start_row = random.randint(0, max_start)
                    for i in range(group_size):
                        pos = start_row + i
                        if pos <= 6:  # Valid row range
                            sea_tiles.append({"edge": edge, "position": pos})
        
        # Corner tiles: only add if BOTH adjacent edges have sea tiles at that corner
        corners = [
            (0, 0, 'north', 'west'),   # NW corner
            (0, 6, 'north', 'east'),   # NE corner
            (6, 0, 'south', 'west'),   # SW corner
            (6, 6, 'south', 'east')    # SE corner
        ]
        for row, col, edge1, edge2 in corners:
            # Check if edge1 has tile at this corner
            has_edge1 = any(
                st["edge"] == edge1 and 
                ((edge1 in ['north', 'south'] and st["position"] == col) or
                 (edge1 in ['east', 'west'] and st["position"] == row))
                for st in sea_tiles
            )
            # Check if edge2 has tile at this corner
            has_edge2 = any(
                st["edge"] == edge2 and 
                ((edge2 in ['north', 'south'] and st["position"] == col) or
                 (edge2 in ['east', 'west'] and st["position"] == row))
                for st in sea_tiles
            )
            # Only add corner if BOTH edges present
            if has_edge1 and has_edge2:
                sea_tiles.append({"edge": f"corner_{edge1}_{edge2}", "position": row * 10 + col})
    
    # Build occupied coordinates list from final spawns
    occupied_list = list(occupied)
    
    print(f"[SERVER MAP GEN] Generated map for lobby {lobby_id if 'lobby_id' in locals() else 'unknown'}:")
    print(f"[SERVER MAP GEN]   Walls: {len(walls)} - {walls}")
    print(f"[SERVER MAP GEN]   Tiles: {len(tiles)} - {tiles}")
    print(f"[SERVER MAP GEN]   Sea Tiles: {len(sea_tiles)} - {sea_tiles}")
    print(f"[SERVER MAP GEN]   Occupied coordinates: {len(occupied_list)} - {occupied_list}")
    
    return {"tiles": tiles, "walls": walls, "sea_tiles": sea_tiles, "occupied": occupied_list}


def _compute_combat_resolution(lobby_id, pair: dict) -> dict:
    """Compute combat resolution for BOTH main attack and counter attack.

    Validates calculations from both clients match, then rolls RNG.
    Returns resolution OR abort message with detailed mismatch reasons.
    """
    attack = pair.get("attack") or {}
    defense = pair.get("defense") or {}
    attacker_validation = pair.get("attacker_validation") or {}
    turn = defense.get("turn") or attack.get("turn")
    
    print(f"\n[SERVER VALIDATION] ========== Turn {turn} Validation Start ==========")
    
    # VALIDATION PHASE: Compare calculations from attacker vs defender
    validation_errors = []
    
    # === PHASE 2: Validate object creation/destruction ===
    defender_objects_created = defense.get("objects_created") or []
    defender_objects_destroyed = defense.get("objects_destroyed") or []
    
    print(f"[SERVER] Defender objects_created count: {len(defender_objects_created)}")
    print(f"[SERVER] Defender objects_destroyed count: {len(defender_objects_destroyed)}")
    
    # Log created/destroyed objects for debugging
    for obj in defender_objects_created:
        obj_type = obj.get("type")
        row = obj.get("row")
        col = obj.get("col")
        print(f"[SERVER]   Created: {obj_type} at ({row},{col})")
    
    for obj in defender_objects_destroyed:
        obj_type = obj.get("type")
        row = obj.get("row")
        col = obj.get("col")
        print(f"[SERVER]   Destroyed: {obj_type} at ({row},{col})")
    
    # Update server's occupied coordinates list (PHASE 2)
    if lobby_id in lobby_maps:
        occupied = set()
        # Rebuild from current map state
        map_state = lobby_maps[lobby_id]
        for tile in map_state.get("tiles") or []:
            try:
                occupied.add((int(tile["row"]), int(tile["col"])))
            except Exception:
                pass
        for wall in map_state.get("walls") or []:
            try:
                occupied.add((int(wall["row"]), int(wall["col"])))
            except Exception:
                pass
        
        # Remove destroyed object coordinates
        for obj in defender_objects_destroyed:
            try:
                coord = (int(obj["row"]), int(obj["col"]))
                occupied.discard(coord)
            except Exception:
                pass
        
        # Add created object coordinates
        for obj in defender_objects_created:
            try:
                coord = (int(obj["row"]), int(obj["col"]))
                occupied.add(coord)
            except Exception:
                pass
        
        # Store updated occupied list for per-turn spawns
        lobby_maps[lobby_id]["occupied"] = list(occupied)
        print(f"[SERVER] Updated occupied coordinates: {len(occupied)} positions")
    
    # Extract defender's calculations (from defense payload)
    defender_is_miss = defense.get("is_miss", False)
    defender_hit_chance = defense.get("hit_chance")
    defender_damage = defense.get("damage")
    defender_counter_hit_chance = defense.get("counter_hit_chance")
    defender_counter_damage = defense.get("counter_damage")
    
    # Extract attacker's calculations (from attacker_validation payload)
    attacker_is_miss = attacker_validation.get("is_miss", False)
    attacker_hit_chance = attacker_validation.get("hit_chance")
    attacker_damage = attacker_validation.get("damage")
    attacker_counter_hit_chance = attacker_validation.get("counter_hit_chance")
    attacker_counter_damage = attacker_validation.get("counter_damage")
    
    print(f"[SERVER] Defender calculations: is_miss={defender_is_miss}, hit_chance={defender_hit_chance}, damage={defender_damage}")
    print(f"[SERVER] Attacker calculations: is_miss={attacker_is_miss}, hit_chance={attacker_hit_chance}, damage={attacker_damage}")
    
    # Check if attacker validation is present
    if not attacker_validation:
        validation_errors.append("Attacker validation payload missing")
    else:
        # CROSS-VALIDATE: Main attack miss status
        if defender_is_miss != attacker_is_miss:
            validation_errors.append(f"Miss status mismatch: defender={defender_is_miss} vs attacker={attacker_is_miss}")
        
        # If NOT miss, validate hit_chance and damage match
        is_miss = defender_is_miss  # Use defender's value as reference
        if not is_miss:
            # Validate hit_chance (allow small tolerance for float precision)
            if defender_hit_chance is None:
                validation_errors.append("Defender hit_chance is null (not miss scenario)")
            elif attacker_hit_chance is None:
                validation_errors.append("Attacker hit_chance is null (not miss scenario)")
            else:
                try:
                    diff = abs(float(defender_hit_chance) - float(attacker_hit_chance))
                    if diff > 0.001:  # Tolerance for float precision
                        validation_errors.append(f"Hit_chance mismatch: defender={defender_hit_chance:.4f} vs attacker={attacker_hit_chance:.4f} (diff={diff:.4f})")
                except Exception as e:
                    validation_errors.append(f"Hit_chance comparison error: {e}")
            
            # Validate damage (must match exactly)
            if defender_damage is None:
                validation_errors.append("Defender damage is null (not miss scenario)")
            elif attacker_damage is None:
                validation_errors.append("Attacker damage is null (not miss scenario)")
            elif int(defender_damage) != int(attacker_damage):
                validation_errors.append(f"Damage mismatch: defender={defender_damage} vs attacker={attacker_damage}")
        
        # CROSS-VALIDATE: Counter attack (if applicable)
        defender_counter_is_miss = defense.get("counter_is_miss", True)
        attacker_counter_is_miss = attacker_validation.get("counter_is_miss", True)
        
        # Check if counter calculations are needed (defense_type == "counter")
        defense_type = defense.get("defense_type")
        if defense_type == "counter":
            # Validate counter miss status
            # Note: Counter is always from defender position to attacker position
            # No movement after counter, so miss status should always match
            if defender_counter_is_miss != attacker_counter_is_miss:
                validation_errors.append(f"Counter miss status mismatch: defender={defender_counter_is_miss} vs attacker={attacker_counter_is_miss}")
            
            # If counter NOT miss, validate counter hit_chance and damage
            if not defender_counter_is_miss:
                if defender_counter_hit_chance is None:
                    validation_errors.append("Defender counter_hit_chance is null (counter not miss)")
                elif attacker_counter_hit_chance is None:
                    validation_errors.append("Attacker counter_hit_chance is null (counter not miss)")
                else:
                    try:
                        counter_diff = abs(float(defender_counter_hit_chance) - float(attacker_counter_hit_chance))
                        if counter_diff > 0.001:
                            validation_errors.append(f"Counter_hit_chance mismatch: defender={defender_counter_hit_chance:.4f} vs attacker={attacker_counter_hit_chance:.4f} (diff={counter_diff:.4f})")
                    except Exception as e:
                        validation_errors.append(f"Counter_hit_chance comparison error: {e}")
                
                if defender_counter_damage is None:
                    validation_errors.append("Defender counter_damage is null (counter not miss)")
                elif attacker_counter_damage is None:
                    validation_errors.append("Attacker counter_damage is null (counter not miss)")
                elif int(defender_counter_damage) != int(attacker_counter_damage):
                    validation_errors.append(f"Counter_damage mismatch: defender={defender_counter_damage} vs attacker={attacker_counter_damage}")
    
    # Log validation errors and abort if any
    if validation_errors:
        print(f"[SERVER VALIDATION ERROR] Turn {turn}, Lobby {lobby_id}:")
        for err in validation_errors:
            print(f"  - {err}")
        print(f"  Attack payload: {attack}")
        print(f"  Defense payload: {defense}")
        print(f"  Attacker validation: {attacker_validation}")
        
        # Return abort message with detailed reasons
        return {
            "type": "combat_abort",
            "lobby_id": lobby_id,
            "turn": turn,
            "reason": "validation_failed",
            "errors": validation_errors,
            "message": f"Combat desync detected on turn {turn}. Validation errors: {'; '.join(validation_errors)}"
        }
    
    print(f"[SERVER VALIDATION] All checks passed - proceeding to RNG resolution")
    
    # === PHASE 3: Generate per-turn spawns AFTER validation ===
    new_spawns = _generate_per_turn_spawns(lobby_id)
    print(f"[SERVER] Generated {len(new_spawns)} new spawns for turn {turn}")
    
    # RESOLUTION PHASE: Roll RNG for hits (only if validation passed)
    is_miss = defender_is_miss
    
    # MAIN ATTACK RESOLUTION
    if is_miss:
        main_hit = False
        main_damage = 0
        print(f"[SERVER] Turn {turn}: Main attack MISS (positional)")
    else:
        hit_chance = defender_hit_chance
        damage = defender_damage or 0
        try:
            hc = float(hit_chance)
            hc = max(0.0, min(1.0, hc))
            roll = random.random()
            main_hit = roll < hc
            print(f"[SERVER] Turn {turn}: Main attack roll={roll:.3f} vs hit_chance={hc:.3f} -> {'HIT' if main_hit else 'MISS'}")
        except Exception as e:
            print(f"[SERVER ERROR] Turn {turn}: Failed to parse hit_chance={hit_chance}: {e}")
            main_hit = False
        main_damage = int(damage) if main_hit else 0
        print(f"[SERVER] Turn {turn}: Main damage={main_damage}")
    
    # COUNTER ATTACK RESOLUTION
    counter_is_miss = defense.get("counter_is_miss", True)
    if counter_is_miss:
        counter_hit = False
        counter_damage = 0
        print(f"[SERVER] Turn {turn}: Counter attack MISS (positional)")
    else:
        counter_hit_chance = defense.get("counter_hit_chance")
        counter_dmg = defense.get("counter_damage") or 0
        try:
            chc = float(counter_hit_chance)
            chc = max(0.0, min(1.0, chc))
            counter_roll = random.random()
            counter_hit = counter_roll < chc
            print(f"[SERVER] Turn {turn}: Counter roll={counter_roll:.3f} vs hit_chance={chc:.3f} -> {'HIT' if counter_hit else 'MISS'}")
        except Exception as e:
            print(f"[SERVER ERROR] Turn {turn}: Failed to parse counter_hit_chance={counter_hit_chance}: {e}")
            counter_hit = False
        counter_damage = int(counter_dmg) if counter_hit else 0
        print(f"[SERVER] Turn {turn}: Counter damage={counter_damage}")
    
    resolution = {
        "type": "combat_resolution",
        "lobby_id": lobby_id,
        "turn": turn,
        "hit": bool(main_hit),
        "damage": main_damage,
        "counter_hit": bool(counter_hit),
        "counter_damage": counter_damage,
        "new_spawns": new_spawns,  # PHASE 4: Include new spawns
    }
    print(f"[SERVER] Turn {turn}: Resolution={resolution}")
    print(f"[SERVER VALIDATION] ========== Turn {turn} Validation Complete ==========\n")
    return resolution


async def _broadcast_timer_sync(lobby_id: str, turn_number: int, checkpoint: str, remaining: int):
    """Broadcast timer sync checkpoint to both players."""
    if lobby_id not in lobbies:
        return
    
    lobby = lobbies[lobby_id]
    sync_msg = json.dumps({
        "type": "timer_sync",
        "checkpoint": checkpoint,
        "server_time": time.time(),
        "turn": turn_number,
        "remaining": remaining
    })
    
    print(f"[SERVER TIMER] Broadcasting {checkpoint} sync for lobby {lobby_id}, turn {turn_number}")
    
    for player_session in lobby.get("players", {}):
        player_ws = session_websockets.get(player_session)
        if player_ws:
            try:
                await player_ws.send(sync_msg)
            except Exception:
                pass


async def _schedule_timer_syncs(lobby_id: str, turn_number: int):
    """Schedule 20s and 40s sync broadcasts for a turn."""
    # Wait 20 seconds, then broadcast sync_20
    await asyncio.sleep(20.0)
    await _broadcast_timer_sync(lobby_id, turn_number, "20s", 25)
    
    # Wait another 20 seconds (total 40s), then broadcast sync_40
    await asyncio.sleep(20.0)
    await _broadcast_timer_sync(lobby_id, turn_number, "40s", 5)


async def _check_combat_timeouts():
    """Check pending_combat entries for missing validations and abort on timeout.

    Phase 1 behavior: if a turn has been pending too long and is missing any of
    attack/defense/attacker_validation, emit a combat_abort with a clear reason
    and clean up server-side state.
    """
    now = time.time()
    for key, pair in list(pending_combat.items()):
        lobby_id, turn = key
        ts = pending_combat_timestamps.get(key)
        if not ts:
            continue
        age = now - ts
        # Simple hard cutoff for now; can be refined later
        if age < 4.0:
            continue
        attack = pair.get("attack")
        defense = pair.get("defense")
        attacker_validation = pair.get("attacker_validation")
        reason = None
        if attack and defense and not attacker_validation:
            reason = "timeout_missing_attacker_validation"
        elif attack and not defense:
            reason = "timeout_missing_defense"
        elif defense and not attack:
            reason = "timeout_missing_attack"
        if not reason:
            continue
        errors = [
            f"{reason}: attack_present={bool(attack)}, defense_present={bool(defense)}, attacker_validation_present={bool(attacker_validation)}"
        ]
        print(f"[SERVER TIMEOUT] Lobby {lobby_id}, turn {turn}: {reason}, age={age:.2f}s")
        # Log last_ping ages for players in this lobby (for diagnostics only)
        lobby = lobbies.get(lobby_id)
        if lobby:
            for sess_id in lobby.get("players", {}).keys():
                ping_ts = last_ping.get(sess_id)
                if ping_ts:
                    print(f"  [SERVER TIMEOUT] session={sess_id} last_ping_age={now - ping_ts:.2f}s")
                else:
                    print(f"  [SERVER TIMEOUT] session={sess_id} has no last_ping entry")
        abort_msg = {
            "type": "combat_abort",
            "lobby_id": lobby_id,
            "turn": turn,
            "reason": reason,
            "errors": errors,
            "message": f"Server did not receive required combat data for turn {turn} in time ({reason}).",
        }
        payload = json.dumps(abort_msg)
        if lobby:
            for player_session in lobby.get("players", {}).keys():
                ws = session_websockets.get(player_session)
                if ws:
                    try:
                        await ws.send(payload)
                    except Exception:
                        pass
        # Clean up pending state for this turn
        pending_combat.pop(key, None)
        pending_combat_timestamps.pop(key, None)
        pending_combat_retries.pop(key, None)


def _per_turn_map_spawns(lobby_id: str) -> dict:
    """Generate per-turn map spawns for a lobby.
    
    Returns a map_update dict ready to be JSON-serialized and broadcast:
    {"type": "map_update", "lobby_id": str, "tiles": [...], "walls": [], "sea_tiles": []}
    """
    if lobby_id not in lobby_maps:
        return None
    
    # Simple spawn chance (adjust as needed)
    if random.random() > 0.15:
        return None
    
    # Pick a tile type to spawn
    tile_types = [
        "trap_continuous",
        "trap_momentary",
        "drop_continuous",
        "drop_momentary",
    ]
    tile_type = random.choice(tile_types)
    
    # Build occupied set from current map state
    map_state = lobby_maps[lobby_id]
    occupied = set()
    for t in map_state.get("tiles") or []:
        try:
            occupied.add((int(t["row"]), int(t["col"])))
        except Exception:
            pass
    for w in map_state.get("walls") or []:
        try:
            occupied.add((int(w["row"]), int(w["col"])))
        except Exception:
            pass
    
    # Also avoid player starting positions
    occupied.add((5, 3))
    occupied.add((1, 3))
    
    # Find a free coordinate
    new_tile = None
    for _ in range(20):
        r = random.randint(0, 6)
        c = random.randint(0, 6)
        if (r, c) not in occupied:
            new_tile = {"row": r, "col": c, "tile_type": tile_type}
            break
    
    if not new_tile:
        return None
    
    # Add to server state
    map_state.setdefault("tiles", []).append(new_tile)
    
    # Return map_update payload
    return {
        "type": "map_update",
        "lobby_id": lobby_id,
        "tiles": [new_tile],
        "walls": [],
        "sea_tiles": [],
    }


async def _check_grace_period(lobby_id: str, session_id: str, turn_number: int):
    """Check grace period after 5 seconds - determine if disconnect or timeout."""
    await asyncio.sleep(5.0)
    
    grace_key = (lobby_id, session_id)
    if grace_key not in lobby_grace_periods:
        return  # Grace period already handled or cancelled
    
    grace_data = lobby_grace_periods[grace_key]
    if not grace_data.get("active"):
        return  # Already processed
    
    packets_received = grace_data.get("packets", [])
    
    if not lobby_id in lobbies:
        # Lobby no longer exists
        if grace_key in lobby_grace_periods:
            del lobby_grace_periods[grace_key]
        return
    
    lobby = lobbies[lobby_id]
    
    if not packets_received:
        # NO packets during grace period - player disconnected
        print(f"[SERVER TIMER] Grace period expired for {session_id} - NO packets (DISCONNECT)")
        
        # Mark grace period as processed
        lobby_grace_periods[grace_key]["active"] = False
        
        # Broadcast connection_lost to both players
        disconnect_msg = json.dumps({
            "type": "connection_lost",
            "disconnected_player": session_id,
            "turn": turn_number,
            "message": f"{claimed_usernames.get(session_id, session_id)} disconnected"
        })
        
        for player_session in lobby.get("players", {}):
            player_ws = session_websockets.get(player_session)
            if player_ws:
                try:
                    await player_ws.send(disconnect_msg)
                    print(f"[SERVER TIMER] Sent connection_lost to {player_session}")
                except Exception:
                    pass
        
        # TODO: Implement 30-second reconnect logic here
    else:
        # Packets received - player is connected but slow
        print(f"[SERVER TIMER] Grace period expired for {session_id} - {len(packets_received)} packets (CONNECTED)")
        lobby_grace_periods[grace_key]["active"] = False
        
        # Force skip turn for timed-out player
        # Send message instructing client to submit empty turn (0 actions)
        # Include current flag count so client can update UI
        flag_key = (lobby_id, session_id)
        current_flags = lobby_player_flags.get(flag_key, 0)
        
        force_skip_msg = json.dumps({
            "type": "force_skip_turn",
            "turn": turn_number,
            "reason": "timeout_confirmed",
            "message": "Time expired - submitting empty turn",
            "flags": current_flags
        })
        
        ws = session_websockets.get(session_id)
        if ws:
            try:
                await ws.send(force_skip_msg)
                print(f"[SERVER TIMER] Sent force_skip_turn to {session_id} for turn {turn_number}")
            except Exception as e:
                print(f"[SERVER TIMER] Failed to send force_skip_turn: {e}")


async def handle_client(websocket):
    """Minimal WebSocket handler for global chat.

    Protocol (JSON over WebSockets):
    - Incoming from client:
      {"type": "chat", "channel": "global", "text": "...", "sender": "optional_name"}
    - Outgoing to all clients:
      {"type": "chat", "channel": "global", "text": "...", "sender": "name_or_session"}
    """
    session_id = str(uuid.uuid4())
    connected_clients.add(websocket)
    session_websockets[session_id] = websocket
    last_ping[session_id] = time.time()
    print(f"[SERVER] Client connected: {session_id}. Total clients: {len(connected_clients)}")
    try:
        async for raw in websocket:
            # Get username for logging
            username = claimed_usernames.get(session_id, session_id)
            try:
                data = json.loads(raw)
            except Exception:
                # Ignore malformed messages
                continue

            # Update last ping timestamp on any valid message
            last_ping[session_id] = time.time()
            
            # Track packets during grace period (for disconnect detection)
            lobby_id = session_lobbies.get(session_id)
            if lobby_id:
                grace_key = (lobby_id, session_id)
                if grace_key in lobby_grace_periods:
                    grace_data = lobby_grace_periods[grace_key]
                    if grace_data.get("active"):
                        grace_data["packets"].append({
                            "type": data.get("type"),
                            "timestamp": time.time()
                        })
                        print(f"[SERVER TIMER] Packet tracked during grace period: {data.get('type')} from {session_id}")

            msg_type = data.get("type")
            print(f"[SERVER] Received from {username}: {{\"type\": \"{msg_type}\"}}") if msg_type else print(f"[SERVER] Received raw message from {username}: {raw}")
            if msg_type == "chat":
                channel = data.get("channel", "global")
                text = data.get("text", "")
                if not text:
                    continue
                sender = data.get("sender") or session_id

                if channel == "global":
                    # Global chat - broadcast to all
                    payload = json.dumps({
                        "type": "chat",
                        "channel": channel,
                        "text": text,
                        "sender": sender,
                    })
                    print(f"[SERVER] Broadcasting global chat to {len(connected_clients)} clients: {payload}")

                    # Broadcast to all connected clients, skip broken connections
                    if connected_clients:
                        tasks = []
                        for client in list(connected_clients):
                            try:
                                tasks.append(client.send(payload))
                            except Exception:
                                pass
                        if tasks:
                            await asyncio.gather(*tasks, return_exceptions=True)
                
                elif channel == "lobby":
                    # Lobby chat - only broadcast to players in same lobby
                    lobby_id = session_lobbies.get(session_id)
                    if not lobby_id or lobby_id not in lobbies:
                        continue
                    
                    lobby = lobbies[lobby_id]
                    # Append to lobby chat history
                    lobby.setdefault("chat", []).append({"sender": sender, "text": text})
                    payload = json.dumps({
                        "type": "chat",
                        "channel": "lobby",
                        "lobby_id": lobby_id,
                        "text": text,
                        "sender": sender,
                    })
                    print(f"[SERVER] Broadcasting lobby chat to lobby {lobby_id}: {payload}")
                    
                    # Send to each player in this specific lobby
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(payload)
                            except Exception:
                                pass
            
            elif msg_type == "register_username":
                requested_name = data.get("username", "").strip()
                if not requested_name:
                    await websocket.send(json.dumps({"type": "username_response", "success": False, "error": "Empty username"}))
                    continue
                
                # Check if username already taken by another session
                if requested_name in claimed_usernames.values():
                    await websocket.send(json.dumps({"type": "username_response", "success": False, "error": "Username already taken"}))
                else:
                    claimed_usernames[session_id] = requested_name
                    await websocket.send(json.dumps({"type": "username_response", "success": True, "username": requested_name}))
                    print(f"[SERVER] Session {session_id} registered username: {requested_name}")
            
            elif msg_type == "ping":
                # Heartbeat from client - just refresh last_ping (already logged above)
                last_ping[session_id] = time.time()
            
            elif msg_type == "ping_response":
                # Response to ping_request during grace period
                print(f"[SERVER TIMER] Received ping_response from {session_id}")
                # Packet already tracked above in grace period tracking
            
            elif msg_type == "cancel_find_match":
                # Remove from match queue if present
                if session_id in match_queue:
                    try:
                        match_queue.remove(session_id)
                    except ValueError:
                        pass
            
            elif msg_type == "create_lobby":
                lobby_name = claimed_usernames.get(session_id, session_id) + "'s Lobby"
                lobby_id = str(uuid.uuid4())
                lobbies[lobby_id] = {
                    "id": lobby_id,
                    "name": lobby_name,
                    "host_session": session_id,
                    "host_name": claimed_usernames.get(session_id, session_id),
                    "players": {
                        session_id: {
                            "name": claimed_usernames.get(session_id, session_id),
                            "ready": False,
                            "selected_character": "None"
                        }
                    },
                    "chat": [],
                    "locked": False
                }
                session_lobbies[session_id] = lobby_id
                
                # Send lobby_created to creator
                await websocket.send(json.dumps({
                    "type": "lobby_created",
                    "lobby_id": lobby_id,
                    "name": lobby_name,
                    "host_session": session_id,
                    "players": lobbies[lobby_id]["players"],
                    "chat": lobbies[lobby_id]["chat"],
                }))
                print(f"[SERVER] Lobby created: {lobby_id} by {claimed_usernames.get(session_id, session_id)}")
                
                # Broadcast updated lobby list to all clients
                lobby_list = [{"id": l["id"], "name": l["name"], "host": l["host_name"], "players": f"{len(l['players'])}/2", "locked": l["locked"]} for l in lobbies.values()]
                broadcast_payload = json.dumps({"type": "lobby_list_update", "lobbies": lobby_list})
                tasks = []
                for client in list(connected_clients):
                    try:
                        tasks.append(client.send(broadcast_payload))
                    except Exception:
                        pass
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            
            elif msg_type == "request_lobby_list":
                lobby_list = [{"id": l["id"], "name": l["name"], "host": l["host_name"], "players": f"{len(l['players'])}/2", "locked": l["locked"]} for l in lobbies.values()]
                await websocket.send(json.dumps({"type": "lobby_list_update", "lobbies": lobby_list}))
            
            elif msg_type == "find_match":
                # Add this session to the quick-match queue if not already present or in a lobby
                if session_id not in session_lobbies and session_id not in match_queue and session_id not in session_pending_match:
                    match_queue.append(session_id)
                
                # Try to pair up two waiting players
                while len(match_queue) >= 2:
                    # Pop potential host and guest
                    host_session = match_queue.pop(0)
                    guest_session = match_queue.pop(0)
                    
                    # Validate they're still connected and not already in lobbies
                    host_ws = session_websockets.get(host_session)
                    guest_ws = session_websockets.get(guest_session)
                    if (host_ws is None or guest_ws is None or
                        host_session in session_lobbies or guest_session in session_lobbies or
                        host_session in session_pending_match or guest_session in session_pending_match):
                        # One or both invalid; skip and continue
                        continue
                    
                    # Prepare lobby data (don't create yet, wait for both to accept)
                    lobby_name = claimed_usernames.get(host_session, host_session) + "'s Lobby"
                    lobby_id = str(uuid.uuid4())
                    lobby_data = {
                        "id": lobby_id,
                        "name": lobby_name,
                        "host_session": host_session,
                        "host_name": claimed_usernames.get(host_session, host_session),
                        "players": {
                            host_session: {
                                "name": claimed_usernames.get(host_session, host_session),
                                "ready": False,
                                "selected_character": "None"
                            },
                            guest_session: {
                                "name": claimed_usernames.get(guest_session, guest_session),
                                "ready": False,
                                "selected_character": "None"
                            },
                        },
                        "chat": [],
                        "locked": False,
                    }
                    
                    # Create pending match
                    match_id = str(uuid.uuid4())
                    pending_matches[match_id] = {
                        "host": host_session,
                        "guest": guest_session,
                        "host_accepted": False,
                        "guest_accepted": False,
                        "lobby_data": lobby_data,
                        "timestamp": time.time(),
                    }
                    session_pending_match[host_session] = match_id
                    session_pending_match[guest_session] = match_id
                    
                    # Send match_found to both players
                    host_payload = json.dumps({
                        "type": "match_found",
                        "match_id": match_id,
                        "opponent_name": claimed_usernames.get(guest_session, guest_session),
                        "lobby_data": lobby_data,
                    })
                    guest_payload = json.dumps({
                        "type": "match_found",
                        "match_id": match_id,
                        "opponent_name": claimed_usernames.get(host_session, host_session),
                        "lobby_data": lobby_data,
                    })
                    
                    try:
                        await host_ws.send(host_payload)
                    except Exception:
                        pass
                    try:
                        await guest_ws.send(guest_payload)
                    except Exception:
                        pass
                    
                    print(f"[SERVER] Match found: {claimed_usernames.get(host_session, host_session)} vs {claimed_usernames.get(guest_session, guest_session)}")
                    
                    # Only make one match per message to avoid long loops
                    break
            
            elif msg_type == "accept_match":
                match_id = session_pending_match.get(session_id)
                if not match_id or match_id not in pending_matches:
                    continue
                
                match_data = pending_matches[match_id]
                # Mark this player as accepted
                if session_id == match_data["host"]:
                    match_data["host_accepted"] = True
                elif session_id == match_data["guest"]:
                    match_data["guest_accepted"] = True
                
                # Check if both accepted
                if match_data["host_accepted"] and match_data["guest_accepted"]:
                    # Create lobby
                    lobby_data = match_data["lobby_data"]
                    lobby_id = lobby_data["id"]
                    lobbies[lobby_id] = lobby_data
                    
                    host_session = match_data["host"]
                    guest_session = match_data["guest"]
                    session_lobbies[host_session] = lobby_id
                    session_lobbies[guest_session] = lobby_id
                    
                    # Clean up pending match
                    del pending_matches[match_id]
                    del session_pending_match[host_session]
                    del session_pending_match[guest_session]
                    
                    # Send lobby_joined to both players
                    payload = json.dumps({
                        "type": "lobby_joined",
                        "lobby_id": lobby_id,
                        "lobby_name": lobby_data["name"],
                        "host_session": lobby_data["host_session"],
                        "players": lobby_data["players"],
                        "chat": lobby_data.get("chat", []),
                    })
                    for sess in (host_session, guest_session):
                        ws = session_websockets.get(sess)
                        if ws:
                            try:
                                await ws.send(payload)
                            except Exception:
                                pass
                    
                    # Broadcast updated lobby list
                    lobby_list = [{"id": l["id"], "name": l["name"], "host": l["host_name"], "players": f"{len(l['players'])}/2", "locked": l["locked"]} for l in lobbies.values()]
                    broadcast_payload = json.dumps({"type": "lobby_list_update", "lobbies": lobby_list})
                    tasks = []
                    for client in list(connected_clients):
                        try:
                            tasks.append(client.send(broadcast_payload))
                        except Exception:
                            pass
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                    
                    print(f"[SERVER] Match accepted, lobby {lobby_id} created")
            
            elif msg_type == "decline_match":
                match_id = session_pending_match.get(session_id)
                if not match_id or match_id not in pending_matches:
                    continue
                
                match_data = pending_matches[match_id]
                host_session = match_data["host"]
                guest_session = match_data["guest"]
                
                # Notify ONLY the opponent (not the decliner) that match was declined
                opponent_session = guest_session if session_id == host_session else host_session
                decline_msg = json.dumps({"type": "match_declined"})
                opponent_ws = session_websockets.get(opponent_session)
                if opponent_ws:
                    try:
                        await opponent_ws.send(decline_msg)
                    except Exception:
                        pass
                
                # Clean up pending match
                del pending_matches[match_id]
                if host_session in session_pending_match:
                    del session_pending_match[host_session]
                if guest_session in session_pending_match:
                    del session_pending_match[guest_session]
                
                print(f"[SERVER] Match {match_id} declined by {claimed_usernames.get(session_id, session_id)}")
            
            elif msg_type == "join_lobby":
                lobby_id = data.get("lobby_id", "")
                if lobby_id not in lobbies:
                    await websocket.send(json.dumps({"type": "error", "message": "Lobby not found"}))
                    continue
                
                lobby = lobbies[lobby_id]
                if len(lobby["players"]) >= 2:
                    await websocket.send(json.dumps({"type": "error", "message": "Lobby is full"}))
                    continue
                
                # Add player to lobby
                lobby["players"][session_id] = {
                    "name": claimed_usernames.get(session_id, session_id),
                    "ready": False,
                    "selected_character": "None"
                }
                session_lobbies[session_id] = lobby_id
                
                # Send lobby state to joining player
                await websocket.send(json.dumps({
                    "type": "lobby_joined",
                    "lobby_id": lobby_id,
                    "lobby_name": lobby["name"],
                    "host_session": lobby["host_session"],
                    "players": lobby["players"],
                    "chat": lobby.get("chat", []),
                }))
                
                # Broadcast lobby state update to all players in this lobby
                lobby_state = json.dumps({
                    "type": "lobby_state_update",
                    "lobby_id": lobby_id,
                    "name": lobby["name"],
                    "host_session": lobby["host_session"],
                    "players": lobby["players"]
                })
                for player_session in lobby["players"]:
                    player_ws = session_websockets.get(player_session)
                    if player_ws:
                        try:
                            await player_ws.send(lobby_state)
                        except Exception:
                            pass
                
                # Broadcast updated lobby list
                lobby_list = [{"id": l["id"], "name": l["name"], "host": l["host_name"], "players": f"{len(l['players'])}/2", "locked": l["locked"]} for l in lobbies.values()]
                broadcast_payload = json.dumps({"type": "lobby_list_update", "lobbies": lobby_list})
                tasks = []
                for client in list(connected_clients):
                    try:
                        tasks.append(client.send(broadcast_payload))
                    except Exception:
                        pass
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                print(f"[SERVER] {claimed_usernames.get(session_id, session_id)} joined lobby {lobby_id}")
            
            elif msg_type == "ready_with_character":
                # Player clicked ready - receive character + ready state together
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                if session_id in lobby["players"]:
                    character_name = data.get("character", "None")
                    ready_state = data.get("ready", False)
                    
                    # Validate character selected
                    if character_name == "None" or character_name is None:
                        print(f"[SERVER] Ready rejected for {session_id} - no character selected")
                        error_msg = json.dumps({"type": "error", "message": "Select a character first"})
                        ws = session_websockets.get(session_id)
                        if ws:
                            try:
                                await ws.send(error_msg)
                            except Exception:
                                pass
                        continue
                    
                    # Store both character and ready state
                    lobby["players"][session_id]["selected_character"] = character_name
                    lobby["players"][session_id]["ready"] = ready_state
                    print(f"[SERVER] Player {session_id} ready={ready_state}, character={character_name}")
                    
                    # Broadcast lobby state to all players
                    lobby_state = json.dumps({
                        "type": "lobby_state_update",
                        "lobby_id": lobby_id,
                        "name": lobby["name"],
                        "host_session": lobby["host_session"],
                        "players": lobby["players"]
                    })
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(lobby_state)
                            except Exception:
                                pass
                    
                    # Check if both players are ready to start the game
                    if len(lobby["players"]) == 2:
                        all_ready = all(p.get("ready", False) for p in lobby["players"].values())
                        if all_ready:
                            # Both players ready - DO NOT start game yet
                            # Wait for both clients to send start_game_confirmed after countdown
                            print(f"[SERVER] Both players ready in lobby {lobby_id}, waiting for countdown confirmation")
                            pass
            
            elif msg_type == "start_game_confirmed":
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                
                # Track which players have confirmed (use lobby dict to persist between messages)
                if "countdown_confirmations" not in lobby:
                    lobby["countdown_confirmations"] = set()
                
                lobby["countdown_confirmations"].add(session_id)
                print(f"[SERVER] Player {session_id} confirmed countdown in lobby {lobby_id} ({len(lobby['countdown_confirmations'])}/2)")
                
                # Check if BOTH players have confirmed
                if len(lobby["countdown_confirmations"]) >= 2:
                    print(f"[SERVER] Both players confirmed countdown in lobby {lobby_id}, starting game")
                    
                    # Clean up confirmation tracking
                    del lobby["countdown_confirmations"]
                    
                    # Prepare game start data
                    host_session = lobby["host_session"]
                    player_sessions = list(lobby["players"].keys())
                    guest_session = [s for s in player_sessions if s != host_session][0]
                    # Generate and store server-authoritative initial map
                    map_init = _generate_initial_map_for_lobby()
                    lobby_maps[lobby_id] = map_init
                    
                    print(f"[SERVER MAP GEN] Generated map for lobby {lobby_id}:")
                    print(f"[SERVER MAP GEN]   Walls: {len(map_init['walls'])} - {map_init['walls']}")
                    print(f"[SERVER MAP GEN]   Tiles: {len(map_init['tiles'])} - {map_init['tiles']}")
                    print(f"[SERVER MAP GEN]   Sea Tiles: {len(map_init['sea_tiles'])} - {map_init['sea_tiles']}")
                    
                    game_data = {
                        "type": "game_start",
                        "lobby_id": lobby_id,
                        "host_session": host_session,
                        "guest_session": guest_session,
                        "players": lobby["players"],
                        # Server-authoritative initial map for this lobby
                        "map_init": map_init,
                    }
                    
                    # Initialize timer state for this lobby
                    lobby_current_turn[lobby_id] = 1
                    lobby_player_flags[(lobby_id, host_session)] = 0
                    lobby_player_flags[(lobby_id, guest_session)] = 0
                    
                    # Start shared timer for lobby
                    lobby_turn_timers[lobby_id] = time.time()
                    print(f"[SERVER TIMER] Initialized shared timer for lobby {lobby_id}")
                    
                    # Send to both players
                    game_start_msg = json.dumps(game_data)
                    print(f"[SERVER] Sending game_start message with map_init to {len(lobby['players'])} players")
                    print(f"[SERVER] game_start payload size: {len(game_start_msg)} bytes")
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(game_start_msg)
                                print(f"[SERVER] Successfully sent game_start to {player_session}")
                            except Exception as e:
                                print(f"[SERVER] Error sending game_start to {player_session}: {e}")
                        else:
                            print(f"[SERVER] No websocket found for {player_session}")
            
            elif msg_type == "ready_toggle":
                if session_id in lobby["players"]:
                    # Validate player has selected a character before allowing ready
                    player_data = lobby["players"][session_id]
                    selected_char = player_data.get("selected_character", "None")
                    
                    if selected_char == "None" or selected_char is None:
                        # Reject ready toggle - no character selected
                        print(f"[SERVER] Ready toggle rejected for {session_id} - no character selected")
                        error_msg = json.dumps({"type": "error", "message": "Select a character first"})
                        ws = session_websockets.get(session_id)
                        if ws:
                            try:
                                await ws.send(error_msg)
                            except Exception:
                                pass
                        continue
                    
                    # Valid - toggle ready state
                    lobby["players"][session_id]["ready"] = not lobby["players"][session_id]["ready"]
                    print(f"[SERVER] Player {session_id} ready={lobby['players'][session_id]['ready']}, character={selected_char}")
                    
                    # Broadcast lobby state to all players in lobby
                    lobby_state = json.dumps({
                        "type": "lobby_state_update",
                        "lobby_id": lobby_id,
                        "name": lobby["name"],
                        "host_session": lobby["host_session"],
                        "players": lobby["players"]
                    })
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(lobby_state)
                            except Exception:
                                pass
                    
                    # Check if both players are ready to start the game
                    if len(lobby["players"]) == 2:
                        all_ready = all(p.get("ready", False) for p in lobby["players"].values())
                        if all_ready:
                            # Both players ready - DO NOT start game yet
                            # Wait for both clients to send start_game_confirmed after countdown
                            print(f"[SERVER] Both players ready in lobby {lobby_id}, waiting for countdown confirmation")
                            # Clear any previous countdown confirmations when going back to ready state
                            if "countdown_confirmations" in lobby:
                                del lobby["countdown_confirmations"]
                        else:
                            # Someone unreadied - clear countdown confirmations
                            if "countdown_confirmations" in lobby:
                                del lobby["countdown_confirmations"]
            
            elif msg_type == "select_character":
                # Player selected a character in lobby
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                if session_id in lobby["players"]:
                    character_name = data.get("character", "None")
                    # Store selected character in player data
                    lobby["players"][session_id]["selected_character"] = character_name
                    print(f"[SERVER] Player {session_id} selected character: {character_name}")
                    
                    # Broadcast lobby state to all players in lobby
                    lobby_state = json.dumps({
                        "type": "lobby_state_update",
                        "lobby_id": lobby_id,
                        "name": lobby["name"],
                        "host_session": lobby["host_session"],
                        "players": lobby["players"]
                    })
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(lobby_state)
                            except Exception:
                                pass
            
            elif msg_type == "combat_attack":
                # Attack-phase combat payload: relay to both players in lobby
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                lobby = lobbies[lobby_id]
                forward = dict(data)
                forward["from_session"] = session_id
                turn_no = forward.get("turn")
                print(f"[SERVER][COMBAT] attack lobby={lobby_id} turn={turn_no} from={session_id}")
                # Store attack part for server-side resolution
                key = (lobby_id, turn_no)
                pair = pending_combat.get(key) or {"attack": None, "defense": None, "attacker_validation": None}
                pair["attack"] = forward
                pending_combat[key] = pair
                # Track when this combat turn became pending
                if key not in pending_combat_timestamps:
                    pending_combat_timestamps[key] = time.time()
                payload = json.dumps(forward)
                for player_session in lobby["players"]:
                    player_ws = session_websockets.get(player_session)
                    if player_ws:
                        try:
                            await player_ws.send(payload)
                        except Exception:
                            pass
                # DON'T compute resolution after attack - must wait for defense AND attacker_validation
            
            elif msg_type == "combat_defense":
                # Defense-phase combat payload: relay to both players in lobby
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                lobby = lobbies[lobby_id]
                forward = dict(data)
                forward["from_session"] = session_id
                turn_no = forward.get("turn")
                print(f"[SERVER][COMBAT] defense lobby={lobby_id} turn={turn_no} from={session_id}")
                # Store defense part for server-side resolution
                key = (lobby_id, turn_no)
                pair = pending_combat.get(key) or {"attack": None, "defense": None, "attacker_validation": None}
                pair["defense"] = forward
                pending_combat[key] = pair
                # Track when this combat turn became pending
                if key not in pending_combat_timestamps:
                    pending_combat_timestamps[key] = time.time()
                payload = json.dumps(forward)
                for player_session in lobby["players"]:
                    player_ws = session_websockets.get(player_session)
                    if player_ws:
                        try:
                            await player_ws.send(payload)
                        except Exception:
                            pass
                # DON'T compute resolution yet - wait for attacker_validation
                # Resolution will be triggered by combat_attacker_validation message
            
            elif msg_type == "turn_confirm_request":
                # Player clicked confirm - validate timing before allowing turn to proceed
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                turn_number = data.get("turn", lobby_current_turn.get(lobby_id, 1))
                phase = data.get("phase", "attack")
                
                # Check if lobby timer exists, create if first confirmation
                if lobby_id not in lobby_turn_timers:
                    print(f"[SERVER TIMER] Creating shared timer for lobby {lobby_id}")
                    lobby_turn_timers[lobby_id] = time.time()
                
                # Calculate elapsed time from shared timer
                turn_start_time = lobby_turn_timers[lobby_id]
                elapsed = time.time() - turn_start_time
                
                print(f"[SERVER TIMER] Confirm request from {session_id}, turn {turn_number} phase {phase}, elapsed={elapsed:.2f}s")
                
                if elapsed <= 45.0:
                    # Within time limit - approve
                    approval_msg = json.dumps({
                        "type": "turn_confirm_approved",
                        "turn": turn_number,
                        "elapsed": elapsed
                    })
                    ws = session_websockets.get(session_id)
                    if ws:
                        try:
                            await ws.send(approval_msg)
                            print(f"[SERVER TIMER] Turn {turn_number} phase {phase} confirmed for {session_id} at {elapsed:.2f}s")
                        except Exception:
                            pass
                    
                    # Mark as confirmed (per-player tracking for skip logic)
                    timer_key = (lobby_id, turn_number, phase, session_id)
                    lobby_turn_confirmed[timer_key] = True
                    
                    # Reset shared timer for next phase
                    lobby_turn_timers[lobby_id] = time.time()
                    print(f"[SERVER TIMER] Shared timer reset for lobby {lobby_id}")
                else:
                    # Timeout - reject and process skip
                    flag_key = (lobby_id, session_id)
                    current_flags = lobby_player_flags.get(flag_key, 0)
                    lobby_player_flags[flag_key] = current_flags + 1
                    new_flag_count = current_flags + 1
                    
                    print(f"[SERVER TIMER] Turn {turn_number} REJECTED for {session_id} - timeout at {elapsed:.2f}s (flags: {new_flag_count}/3)")
                    
                    # Send rejection to timed-out player
                    rejection_msg = json.dumps({
                        "type": "turn_confirm_rejected",
                        "turn": turn_number,
                        "reason": "timeout",
                        "elapsed": elapsed,
                        "flags": new_flag_count
                    })
                    ws = session_websockets.get(session_id)
                    if ws:
                        try:
                            await ws.send(rejection_msg)
                        except Exception:
                            pass
                    
                    # Broadcast skip to both players
                    skip_msg = json.dumps({
                        "type": "skip_turn",
                        "turn": turn_number,
                        "skipped_player": session_id,
                        "reason": "timeout",
                        "flags": new_flag_count
                    })
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(skip_msg)
                            except Exception:
                                pass
                    
                    # Check for forfeit (3 flags)
                    if new_flag_count >= 3:
                        # Find opponent
                        opponent_session = None
                        for ps in lobby["players"]:
                            if ps != session_id:
                                opponent_session = ps
                                break
                        
                        forfeit_msg = json.dumps({
                            "type": "game_over",
                            "reason": "forfeit_flags",
                            "winner": opponent_session,
                            "loser": session_id,
                            "message": f"{claimed_usernames.get(session_id, session_id)} forfeited (3 timeout flags)"
                        })
                        for player_session in lobby["players"]:
                            player_ws = session_websockets.get(player_session)
                            if player_ws:
                                try:
                                    await player_ws.send(forfeit_msg)
                                    print(f"[SERVER TIMER] Game over - {session_id} forfeited with 3 flags")
                                except Exception:
                                    pass
                    else:
                        # Start grace period to check for disconnect
                        grace_key = (lobby_id, session_id)
                        lobby_grace_periods[grace_key] = {
                            "active": True,
                            "start": time.time(),
                            "packets": [],
                            "turn": turn_number
                        }
                        
                        # Send ping request
                        ping_id = str(uuid.uuid4())
                        ping_msg = json.dumps({
                            "type": "ping_request",
                            "ping_id": ping_id,
                            "turn": turn_number
                        })
                        ws = session_websockets.get(session_id)
                        if ws:
                            try:
                                await ws.send(ping_msg)
                                print(f"[SERVER TIMER] Sent ping_request to {session_id} for grace period check")
                            except Exception:
                                pass
                        
                        # Schedule grace period check (5 seconds)
                        asyncio.create_task(_check_grace_period(lobby_id, session_id, turn_number))
            
            elif msg_type == "clock_out":
                # Client's timer reached 45s - SELF timeout (player reporting own timeout)
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                turn_number = data.get("turn", 1)
                phase = data.get("phase", "attack")
                
                print(f"[SERVER TIMER] Received SELF clock_out from {session_id}, turn {turn_number} phase {phase}")
                
                # Check if player already confirmed this turn+phase
                timer_key = (lobby_id, turn_number, phase, session_id)
                if timer_key in lobby_turn_confirmed and lobby_turn_confirmed[timer_key]:
                    print(f"[SERVER TIMER] Player already confirmed turn {turn_number} phase {phase}, ignoring clock_out")
                    continue
                
                # Check if there's already an active grace period from accusative
                # If accusative arrived first and started grace period, self-report should be ignored
                grace_key = (lobby_id, session_id)
                if grace_key in lobby_grace_periods and lobby_grace_periods[grace_key].get("active"):
                    print(f"[SERVER TIMER] Grace period already active for {session_id} (from accusative), ignoring self-report")
                    continue
                
                # Player timed out without confirming - apply timeout logic
                flag_key = (lobby_id, session_id)
                current_flags = lobby_player_flags.get(flag_key, 0)
                lobby_player_flags[flag_key] = current_flags + 1
                new_flag_count = current_flags + 1
                
                print(f"[SERVER TIMER] Clock_out timeout for {session_id} - flags: {new_flag_count}/3")
                
                # Broadcast skip to both players
                skip_msg = json.dumps({
                    "type": "skip_turn",
                    "turn": turn_number,
                    "skipped_player": session_id,
                    "reason": "clock_out",
                    "flags": new_flag_count
                })
                for player_session in lobby["players"]:
                    player_ws = session_websockets.get(player_session)
                    if player_ws:
                        try:
                            await player_ws.send(skip_msg)
                        except Exception:
                            pass
                
                # Check for forfeit (3 flags)
                if new_flag_count >= 3:
                    opponent_session = None
                    for ps in lobby["players"]:
                        if ps != session_id:
                            opponent_session = ps
                            break
                    
                    forfeit_msg = json.dumps({
                        "type": "game_over",
                        "reason": "forfeit_flags",
                        "winner": opponent_session,
                        "loser": session_id,
                        "message": f"{claimed_usernames.get(session_id, session_id)} forfeited (3 timeout flags)"
                    })
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(forfeit_msg)
                                print(f"[SERVER TIMER] Game over - {session_id} forfeited with 3 flags")
                            except Exception:
                                pass
                else:
                    # Start grace period to check for disconnect
                    grace_key = (lobby_id, session_id)
                    lobby_grace_periods[grace_key] = {
                        "active": True,
                        "start": time.time(),
                        "packets": [],
                        "turn": turn_number
                    }
                    
                    # Send ping request
                    ping_id = str(uuid.uuid4())
                    ping_msg = json.dumps({
                        "type": "ping_request",
                        "ping_id": ping_id,
                        "turn": turn_number
                    })
                    ws = session_websockets.get(session_id)
                    if ws:
                        try:
                            await ws.send(ping_msg)
                            print(f"[SERVER TIMER] Sent ping_request to {session_id} for grace period check")
                        except Exception:
                            pass
                    
                    # Schedule grace period check (5 seconds)
                    asyncio.create_task(_check_grace_period(lobby_id, session_id, turn_number))
            
            elif msg_type == "clock_out_accusative":
                # Client's timer reached 45s - ACCUSATIVE (player reporting OPPONENT's timeout)
                # This handles the case where opponent is ACTIVE but never self-reported (clock_out never received)
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                turn_number = data.get("turn", 1)
                phase = data.get("phase", "attack")
                accuser_session = session_id
                
                print(f"[SERVER TIMER] Received ACCUSATIVE clock_out from {accuser_session}, turn {turn_number} phase {phase}")
                
                # Find the opponent (the accused)
                accused_session = None
                for ps in lobby["players"]:
                    if ps != accuser_session:
                        accused_session = ps
                        break
                
                if not accused_session:
                    print(f"[SERVER TIMER] No opponent found for accusation, ignoring")
                    continue
                
                # Check if ACCUSED already confirmed this turn+phase
                timer_key = (lobby_id, turn_number, phase, accused_session)
                if timer_key in lobby_turn_confirmed and lobby_turn_confirmed[timer_key]:
                    print(f"[SERVER TIMER] Accused player {accused_session} already confirmed turn {turn_number} phase {phase}, ignoring accusation")
                    continue
                
                # CRITICAL: Only process accusative if accused has NO active grace period
                # If grace period exists, it means accused self-reported and we're already handling it
                # Accusative is ONLY for when accused is active but never self-reported
                grace_key = (lobby_id, accused_session)
                if grace_key in lobby_grace_periods and lobby_grace_periods[grace_key].get("active"):
                    print(f"[SERVER TIMER] Grace period already active for accused {accused_session} (self-reported), ignoring accusation")
                    continue
                
                # No grace period = accused never self-reported
                # Start grace period to check if accused is active or disconnected
                print(f"[SERVER TIMER] Accusative received, no self-report from {accused_session} - starting grace period")
                
                # Increment flags for accused (they timed out)
                flag_key = (lobby_id, accused_session)
                current_flags = lobby_player_flags.get(flag_key, 0)
                lobby_player_flags[flag_key] = current_flags + 1
                new_flag_count = current_flags + 1
                
                print(f"[SERVER TIMER] ACCUSED {accused_session} timeout (accusative) - flags: {new_flag_count}/3")
                
                # Broadcast skip to both players
                skip_msg = json.dumps({
                    "type": "skip_turn",
                    "turn": turn_number,
                    "skipped_player": accused_session,
                    "reason": "clock_out_accusative",
                    "flags": new_flag_count
                })
                for player_session in lobby["players"]:
                    player_ws = session_websockets.get(player_session)
                    if player_ws:
                        try:
                            await player_ws.send(skip_msg)
                        except Exception:
                            pass
                
                # Check for forfeit (3 flags)
                if new_flag_count >= 3:
                    forfeit_msg = json.dumps({
                        "type": "game_over",
                        "reason": "forfeit_flags",
                        "winner": accuser_session,
                        "loser": accused_session,
                        "message": f"{claimed_usernames.get(accused_session, accused_session)} forfeited (3 timeout flags)"
                    })
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(forfeit_msg)
                                print(f"[SERVER TIMER] Game over - {accused_session} forfeited with 3 flags")
                            except Exception:
                                pass
                else:
                    # Start grace period to check if ACCUSED is active or disconnected
                    lobby_grace_periods[grace_key] = {
                        "active": True,
                        "start": time.time(),
                        "packets": [],
                        "turn": turn_number
                    }
                    
                    # Send ping request to ACCUSED
                    ping_id = str(uuid.uuid4())
                    ping_msg = json.dumps({
                        "type": "ping_request",
                        "ping_id": ping_id,
                        "turn": turn_number
                    })
                    ws = session_websockets.get(accused_session)
                    if ws:
                        try:
                            await ws.send(ping_msg)
                            print(f"[SERVER TIMER] Sent ping_request to ACCUSED {accused_session} for grace period check")
                        except Exception:
                            pass
                    
                    # Schedule grace period check (5 seconds) for ACCUSED
                    # If ACTIVE: sends force_skip (they're connected but never self-reported)
                    # If INACTIVE: sends connection_lost (disconnect)
                    asyncio.create_task(_check_grace_period(lobby_id, accused_session, turn_number))
            
            elif msg_type == "combat_attacker_validation":
                # Attacker's validation payload after receiving defender movement
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                lobby = lobbies[lobby_id]
                forward = dict(data)
                forward["lobby_id"] = lobby_id
                forward["from_session"] = session_id
                turn_no = forward.get("turn")
                print(f"[SERVER][COMBAT] attacker_validation lobby={lobby_id} turn={turn_no} from={session_id}")
                # Store attacker validation
                key = (lobby_id, turn_no)
                pair = pending_combat.get(key) or {"attack": None, "defense": None, "attacker_validation": None}
                pair["attacker_validation"] = forward
                pending_combat[key] = pair
                # If attack AND defense already present, compute and broadcast resolution
                if pair.get("attack") and pair.get("defense"):
                    try:
                        resolution = _compute_combat_resolution(lobby_id, pair)
                        res_payload = json.dumps(resolution)
                        for player_session in lobby["players"]:
                            player_ws = session_websockets.get(player_session)
                            if player_ws:
                                try:
                                    await player_ws.send(res_payload)
                                except Exception:
                                    pass
                        # After resolution, try per-turn map spawns
                        map_update = _per_turn_map_spawns(lobby_id)
                        if map_update:
                            map_payload = json.dumps(map_update)
                            for player_session in lobby["players"]:
                                player_ws = session_websockets.get(player_session)
                                if player_ws:
                                    try:
                                        await player_ws.send(map_payload)
                                    except Exception:
                                        pass
                        
                        # Start next turn's timer and schedule syncs
                        next_turn = turn_no + 1
                        lobby_current_turn[lobby_id] = next_turn
                        lobby_turn_timers[(lobby_id, next_turn)] = time.time()
                        asyncio.create_task(_schedule_timer_syncs(lobby_id, next_turn))
                        print(f"[SERVER TIMER] Started timer for turn {next_turn}, scheduled syncs")
                        
                        # Broadcast turn_start to clients to reset their timers
                        turn_start_msg = json.dumps({
                            "type": "turn_start",
                            "turn": next_turn,
                            "server_time": time.time()
                        })
                        for player_session in lobby["players"]:
                            player_ws = session_websockets.get(player_session)
                            if player_ws:
                                try:
                                    await player_ws.send(turn_start_msg)
                                    print(f"[SERVER TIMER] Sent turn_start for turn {next_turn} to {player_session}")
                                except Exception:
                                    pass
                    finally:
                        pending_combat.pop(key, None)
            
            elif msg_type == "kick_guest":
                # Host requests to kick guest from lobby
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                # Verify sender is host
                if session_id != lobby["host_session"]:
                    continue
                
                # Find guest session
                guest_session = None
                for player_session in lobby["players"]:
                    if player_session != session_id:
                        guest_session = player_session
                        break
                
                if not guest_session:
                    continue
                
                # Register pending kick
                pending_kicks[lobby_id] = {
                    "kicker_session": session_id,
                    "kicked_session": guest_session,
                    "timestamp": time.time()
                }
                
                # Send "kicked" message to guest
                guest_ws = session_websockets.get(guest_session)
                if guest_ws:
                    kick_payload = json.dumps({"type": "kicked"})
                    try:
                        await guest_ws.send(kick_payload)
                        print(f"[SERVER] Host {session_id} kicked guest {guest_session} from lobby {lobby_id}")
                    except Exception:
                        pass
            
            
            elif msg_type == "forfeit_match":
                # Player forfeits the match
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                username = claimed_usernames.get(session_id, session_id)
                print(f"[SERVER] {username} forfeited match in lobby {lobby_id}")
                
                # Notify opponent that they forfeited
                for player_session in lobby["players"]:
                    if player_session != session_id:
                        opponent_ws = session_websockets.get(player_session)
                        if opponent_ws:
                            forfeit_msg = json.dumps({"type": "opponent_forfeit"})
                            try:
                                await opponent_ws.send(forfeit_msg)
                                print(f"[SERVER] Notified opponent of forfeit")
                            except Exception:
                                pass
                
                # Confirm forfeit to forfeiter
                try:
                    await websocket.send(json.dumps({"type": "forfeit_confirmed"}))
                except Exception:
                    pass
            
            elif msg_type == "rematch_request":
                # Player toggled rematch request
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                requested = data.get("requested", False)
                username = claimed_usernames.get(session_id, session_id)
                
                # Initialize post_match_state if not exists
                if "post_match_state" not in lobby:
                    lobby["post_match_state"] = {
                        "player1_rematch": False,
                        "player2_rematch": False,
                        "player1_change_char": False,
                        "player2_change_char": False
                    }
                
                # Determine if this player is player1 or player2
                is_player1 = (session_id == lobby["host_session"])
                
                # Update this player's rematch state
                if is_player1:
                    lobby["post_match_state"]["player1_rematch"] = requested
                else:
                    lobby["post_match_state"]["player2_rematch"] = requested
                
                print(f"[SERVER] {username} rematch request: {requested} (lobby {lobby_id})")
                print(f"[SERVER DEBUG] Post-match state after update: P1_rematch={lobby['post_match_state']['player1_rematch']}, P2_rematch={lobby['post_match_state']['player2_rematch']}")
                
                # Notify opponent
                for player_session in lobby["players"]:
                    if player_session != session_id:
                        opponent_ws = session_websockets.get(player_session)
                        if opponent_ws:
                            opponent_msg = json.dumps({"type": "opponent_rematch", "requested": requested})
                            try:
                                await opponent_ws.send(opponent_msg)
                            except Exception:
                                pass
                
                # Check if both players want rematch
                if (lobby["post_match_state"]["player1_rematch"] and 
                    lobby["post_match_state"]["player2_rematch"]):
                    print(f"[SERVER] Both players ready for rematch in lobby {lobby_id}")
                    
                    # RESET post_match_state so next game starts clean
                    lobby["post_match_state"] = {
                        "player1_rematch": False,
                        "player2_rematch": False,
                        "player1_change_char": False,
                        "player2_change_char": False
                    }
                    print(f"[SERVER] Reset post_match_state for next game")
                    
                    # Generate new map using EXACT SAME FUNCTION as initial game
                    map_init = _generate_initial_map_for_lobby()
                    
                    # Broadcast countdown start with map_init
                    countdown_msg = json.dumps({
                        "type": "start_rematch_countdown",
                        "map_init": map_init
                    })
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(countdown_msg)
                                print(f"[SERVER] Sent countdown with new map to {player_session}")
                            except Exception:
                                pass
            
            elif msg_type == "change_characters":
                # Player toggled change characters request
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                requested = data.get("requested", False)
                username = claimed_usernames.get(session_id, session_id)
                
                # Initialize post_match_state if not exists
                if "post_match_state" not in lobby:
                    lobby["post_match_state"] = {
                        "player1_rematch": False,
                        "player2_rematch": False,
                        "player1_change_char": False,
                        "player2_change_char": False
                    }
                
                # Determine if this player is player1 or player2
                is_player1 = (session_id == lobby["host_session"])
                
                # Update this player's change_char state
                if is_player1:
                    lobby["post_match_state"]["player1_change_char"] = requested
                else:
                    lobby["post_match_state"]["player2_change_char"] = requested
                
                print(f"[SERVER] {username} change_char request: {requested} (lobby {lobby_id})")
                print(f"[SERVER DEBUG] Post-match state after update: P1_change={lobby['post_match_state']['player1_change_char']}, P2_change={lobby['post_match_state']['player2_change_char']}")
                
                # Notify opponent
                for player_session in lobby["players"]:
                    if player_session != session_id:
                        opponent_ws = session_websockets.get(player_session)
                        if opponent_ws:
                            opponent_msg = json.dumps({"type": "opponent_change_char", "requested": requested})
                            try:
                                await opponent_ws.send(opponent_msg)
                            except Exception:
                                pass
                
                # Check if both players want to change characters
                if (lobby["post_match_state"]["player1_change_char"] and 
                    lobby["post_match_state"]["player2_change_char"]):
                    print(f"[SERVER] Both players ready to change characters in lobby {lobby_id}")
                    
                    # Reset lobby state for fresh character selection
                    for player_session in lobby["players"]:
                        player_data = lobby["players"][player_session]
                        player_data["ready"] = False
                        player_data["character"] = None
                        player_data["selected_character"] = None
                    print(f"[SERVER] Reset all players to unready with no character selected")
                    
                    # Reset post-match state
                    lobby["post_match_state"] = {
                        "player1_rematch": False,
                        "player2_rematch": False,
                        "player1_change_char": False,
                        "player2_change_char": False
                    }
                    
                    # Broadcast lobby state update
                    lobby_state_msg = json.dumps({
                        "type": "lobby_state_update",
                        "lobby_id": lobby_id,
                        "name": lobby["name"],
                        "players": {sid: {"name": p["name"], "ready": p["ready"], "character": p.get("character")} 
                                    for sid, p in lobby["players"].items()},
                        "host_session": lobby["host_session"]
                    })
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(lobby_state_msg)
                            except Exception:
                                pass
                    
                    # Broadcast return to lobby
                    return_msg = json.dumps({"type": "return_to_lobby"})
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(return_msg)
                                print(f"[SERVER] Sent return_to_lobby to {player_session}")
                            except Exception:
                                pass
            
            elif msg_type == "leave_lobby":
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                # Check if this leave is part of a pending kick
                kick_verified = False
                if lobby_id in pending_kicks:
                    kick_data = pending_kicks[lobby_id]
                    # Verify this is the kicked player leaving within reasonable time (30 seconds)
                    if (kick_data["kicked_session"] == session_id and 
                        time.time() - kick_data["timestamp"] < 30.0):
                        kick_verified = True
                        kicker_session = kick_data["kicker_session"]
                        # Clean up pending kick
                        del pending_kicks[lobby_id]
                        print(f"[SERVER] Kick verified: {session_id} left lobby {lobby_id} after kick")
                
                lobby = lobbies[lobby_id]
                if session_id in lobby["players"]:
                    # Notify other players that this player left
                    for player_session in lobby["players"]:
                        if player_session != session_id:
                            player_ws = session_websockets.get(player_session)
                            if player_ws:
                                opponent_left_msg = json.dumps({"type": "opponent_left_lobby"})
                                try:
                                    await player_ws.send(opponent_left_msg)
                                    print(f"[SERVER] Notified {player_session} that opponent left lobby")
                                except Exception:
                                    pass
                    
                    del lobby["players"][session_id]
                    del session_lobbies[session_id]
                
                # If kick was verified, notify host
                if kick_verified:
                    kicker_ws = session_websockets.get(kicker_session)
                    if kicker_ws:
                        kick_success_payload = json.dumps({"type": "kick_confirmed"})
                        try:
                            await kicker_ws.send(kick_success_payload)
                        except Exception:
                            pass
                
                # Check if lobby should be deleted or host transferred
                if len(lobby["players"]) == 0:
                    # Delete empty lobby and cleanup timer
                    if lobby_id in lobby_turn_timers:
                        del lobby_turn_timers[lobby_id]
                        print(f"[SERVER TIMER] Cleaned up timer for lobby {lobby_id}")
                    del lobbies[lobby_id]
                    print(f"[SERVER] Lobby {lobby_id} deleted (empty)")
                elif session_id == lobby["host_session"]:
                    # Transfer host to remaining player
                    new_host_session = list(lobby["players"].keys())[0]
                    lobby["host_session"] = new_host_session
                    lobby["host_name"] = lobby["players"][new_host_session]["name"]
                    lobby["name"] = lobby["host_name"] + "'s Lobby"
                    print(f"[SERVER] Host transferred to {lobby['host_name']} in lobby {lobby_id}")
                    
                    # Notify remaining player of lobby state update
                    lobby_state = json.dumps({
                        "type": "lobby_state_update",
                        "lobby_id": lobby_id,
                        "name": lobby["name"],
                        "host_session": lobby["host_session"],
                        "players": lobby["players"]
                    })
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(lobby_state)
                            except Exception:
                                pass
                else:
                    # Guest left, notify remaining players of updated state
                    lobby_state = json.dumps({
                        "type": "lobby_state_update",
                        "lobby_id": lobby_id,
                        "name": lobby["name"],
                        "host_session": lobby["host_session"],
                        "players": lobby["players"]
                    })
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(lobby_state)
                            except Exception:
                                pass
                
                # Broadcast updated lobby list
                lobby_list = [{"id": l["id"], "name": l["name"], "host": l["host_name"], "players": f"{len(l['players'])}/2", "locked": l["locked"]} for l in lobbies.values()]
                broadcast_payload = json.dumps({"type": "lobby_list_update", "lobbies": lobby_list})
                tasks = []
                for client in list(connected_clients):
                    try:
                        tasks.append(client.send(broadcast_payload))
                    except Exception:
                        pass
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                # After handling this message, check for any combat timeouts
                await _check_combat_timeouts()
    except websockets.exceptions.ConnectionClosedError:
        print(f"[SERVER] Client {session_id} connection closed (normal)")
    except Exception as e:
        print(f"[SERVER] Client {session_id} error: {e}")
    finally:
        connected_clients.discard(websocket)
        
        # Clean up session websocket mapping
        if session_id in session_websockets:
            del session_websockets[session_id]
        # Clean up heartbeat tracking
        if session_id in last_ping:
            del last_ping[session_id]
        # Ensure session is not left in match queue
        if session_id in match_queue:
            try:
                match_queue.remove(session_id)
                print(f"[SERVER] Removed {session_id} from match queue on disconnect")
            except ValueError:
                pass
        
        # Clean up pending match if session has one
        if session_id in session_pending_match:
            match_id = session_pending_match[session_id]
            if match_id in pending_matches:
                match_data = pending_matches[match_id]
                other_session = match_data["guest"] if match_data["host"] == session_id else match_data["host"]
                
                # Notify other player that match was cancelled
                other_ws = session_websockets.get(other_session)
                if other_ws:
                    try:
                        await other_ws.send(json.dumps({"type": "match_cancelled", "reason": "Opponent disconnected"}))
                    except Exception:
                        pass
                
                # Clean up pending match
                del pending_matches[match_id]
                if session_id in session_pending_match:
                    del session_pending_match[session_id]
                if other_session in session_pending_match:
                    del session_pending_match[other_session]
                print(f"[SERVER] Cancelled pending match {match_id} due to disconnect")
        
        # Clean up username on disconnect
        if session_id in claimed_usernames:
            del claimed_usernames[session_id]
        
        # Clean up lobby membership and potentially delete lobby
        if session_id in session_lobbies:
            lobby_id = session_lobbies[session_id]
            del session_lobbies[session_id]
            
            if lobby_id in lobbies:
                lobby = lobbies[lobby_id]
                if session_id in lobby["players"]:
                    del lobby["players"][session_id]
                    print(f"[SERVER] Removed disconnected player {session_id} from lobby {lobby_id}")
                
                # Check if lobby should be deleted or host transferred
                if len(lobby["players"]) == 0:
                    # Delete empty lobby
                    del lobbies[lobby_id]
                    print(f"[SERVER] Lobby {lobby_id} deleted (empty after disconnect)")
                elif session_id == lobby["host_session"]:
                    # Transfer host to remaining player
                    new_host_session = list(lobby["players"].keys())[0]
                    lobby["host_session"] = new_host_session
                    lobby["host_name"] = lobby["players"][new_host_session]["name"]
                    lobby["name"] = lobby["host_name"] + "'s Lobby"
                    print(f"[SERVER] Host transferred to {lobby['host_name']} in lobby {lobby_id} after disconnect")
                    
                    # Notify remaining player
                    new_host_ws = session_websockets.get(new_host_session)
                    if new_host_ws:
                        try:
                            lobby_state = json.dumps({
                                "type": "lobby_state_update",
                                "lobby_id": lobby_id,
                                "name": lobby["name"],
                                "host_session": lobby["host_session"],
                                "players": lobby["players"]
                            })
                            await new_host_ws.send(lobby_state)
                        except Exception:
                            pass
                else:
                    # Notify remaining players of updated state
                    lobby_state = json.dumps({
                        "type": "lobby_state_update",
                        "lobby_id": lobby_id,
                        "name": lobby["name"],
                        "host_session": lobby["host_session"],
                        "players": lobby["players"]
                    })
                    for player_session in lobby["players"]:
                        player_ws = session_websockets.get(player_session)
                        if player_ws:
                            try:
                                await player_ws.send(lobby_state)
                            except Exception:
                                pass
                
                # Broadcast updated lobby list to all clients
                lobby_list = [{"id": l["id"], "name": l["name"], "host": l["host_name"], "players": f"{len(l['players'])}/2", "locked": l["locked"]} for l in lobbies.values()]
                broadcast_payload = json.dumps({"type": "lobby_list_update", "lobbies": lobby_list})
                tasks = []
                for client in list(connected_clients):
                    try:
                        tasks.append(client.send(broadcast_payload))
                    except Exception:
                        pass
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
        
        print(f"[SERVER] Client disconnected: {session_id}. Remaining: {len(connected_clients)}")


async def heartbeat_watcher(timeout: float = 30.0, interval: float = 5.0):
    """Periodically close connections that haven't sent a heartbeat within timeout seconds.

    We rely on handle_client's finally-block to perform all state cleanup when the websocket closes.
    """
    while True:
        await asyncio.sleep(interval)
        now = time.time()
        for session_id, ts in list(last_ping.items()):
            # Skip sessions that no longer have an associated websocket
            ws = session_websockets.get(session_id)
            if ws is None:
                continue
            if now - ts > timeout:
                try:
                    await ws.close()
                except Exception:
                    pass


async def main(host: str = "0.0.0.0", port: int = 8765):
    """Run the WebSocket server for multiplayer global chat.

    This is a minimal first step towards the architecture in game/multiplayer.md.
    """
    async with websockets.serve(handle_client, host, port):
        print(f"Multiplayer WebSocket server running on ws://{host}:{port}")
        # Start heartbeat watcher task
        asyncio.create_task(heartbeat_watcher())
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
