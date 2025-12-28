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
pending_combat = {}  # (lobby_id, turn) -> {"attack": dict, "defense": dict}


def _generate_initial_map_for_lobby() -> dict:
    """Generate initial special tiles for a 7x7 board.

    Keeps logic simple and coordinate-only:
    - Avoids spawning on starting player positions.
    - Avoids duplicate positions across tiles.
    """
    tiles = []
    occupied = set([(5, 3), (1, 3)])  # Starting positions of player1 and player2

    # Candidate tile types, roughly matching engine categories
    tile_types = [
        "unpassable",
        "trap_continuous",
        "trap_momentary",
        "drop_continuous",
        "drop_momentary",
    ]

    # Try at most one tile per type to keep density low
    for t in tile_types:
        # Unpassable slightly rarer
        chance = 0.05 if t == "unpassable" else 0.10
        if random.random() >= chance:
            continue
        # Find a free coordinate
        for _ in range(20):
            r = random.randint(0, 6)
            c = random.randint(0, 6)
            if (r, c) in occupied:
                continue
            occupied.add((r, c))
            tiles.append({"row": r, "col": c, "tile_type": t})
            break

    return {"tiles": tiles, "walls": [], "sea_tiles": []}


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
    }
    print(f"[SERVER] Turn {turn}: Resolution={resolution}")
    print(f"[SERVER VALIDATION] ========== Turn {turn} Validation Complete ==========\n")
    return resolution


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
            print(f"[SERVER] Received raw message: {raw}")
            try:
                data = json.loads(raw)
            except Exception:
                # Ignore malformed messages
                continue

            # Update last ping timestamp on any valid message
            last_ping[session_id] = time.time()

            msg_type = data.get("type")
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
                # Heartbeat from client - just refresh last_ping
                last_ping[session_id] = time.time()
            
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
                
                # Clean up pending match
                del pending_matches[match_id]
                if host_session in session_pending_match:
                    del session_pending_match[host_session]
                if guest_session in session_pending_match:
                    del session_pending_match[guest_session]
                
                # Both players go back to queue if they want
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
                            # Both players ready - start game
                            print(f"[SERVER] Both players ready in lobby {lobby_id}, starting game")
                            
                            # Prepare game start data
                            host_session = lobby["host_session"]
                            player_sessions = list(lobby["players"].keys())
                            guest_session = [s for s in player_sessions if s != host_session][0]
                            # Generate and store server-authoritative initial map
                            map_init = _generate_initial_map_for_lobby()
                            lobby_maps[lobby_id] = map_init
                            
                            game_data = {
                                "type": "game_start",
                                "lobby_id": lobby_id,
                                "host_session": host_session,
                                "guest_session": guest_session,
                                "players": lobby["players"],
                                # Server-authoritative initial map for this lobby
                                "map_init": map_init,
                            }
                            
                            # Send to both players
                            game_start_msg = json.dumps(game_data)
                            for player_session in lobby["players"]:
                                player_ws = session_websockets.get(player_session)
                                if player_ws:
                                    try:
                                        await player_ws.send(game_start_msg)
                                    except Exception as e:
                                        print(f"[SERVER] Error sending game_start to {player_session}: {e}")
            
            elif msg_type == "ready_toggle":
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
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
                forward["lobby_id"] = lobby_id
                forward["from_session"] = session_id
                turn_no = forward.get("turn")
                print(f"[SERVER][COMBAT] attack lobby={lobby_id} turn={turn_no} from={session_id}")
                # Store attack part for server-side resolution
                key = (lobby_id, turn_no)
                pair = pending_combat.get(key) or {"attack": None, "defense": None, "attacker_validation": None}
                pair["attack"] = forward
                pending_combat[key] = pair
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
                forward["lobby_id"] = lobby_id
                forward["from_session"] = session_id
                turn_no = forward.get("turn")
                print(f"[SERVER][COMBAT] defense lobby={lobby_id} turn={turn_no} from={session_id}")
                # Store defense part for server-side resolution
                key = (lobby_id, turn_no)
                pair = pending_combat.get(key) or {"attack": None, "defense": None, "attacker_validation": None}
                pair["defense"] = forward
                pending_combat[key] = pair
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
                    finally:
                        pending_combat.pop(key, None)
            
            elif msg_type == "leave_lobby":
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                if session_id in lobby["players"]:
                    del lobby["players"][session_id]
                    del session_lobbies[session_id]
                
                # Check if lobby should be deleted or host transferred
                if len(lobby["players"]) == 0:
                    # Delete empty lobby
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
