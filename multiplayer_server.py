import asyncio
import json
import uuid
import time

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
                            "ready": False
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
                            },
                            guest_session: {
                                "name": claimed_usernames.get(guest_session, guest_session),
                                "ready": False,
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
                    "ready": False
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
            
            elif msg_type == "ready_toggle":
                lobby_id = session_lobbies.get(session_id)
                if not lobby_id or lobby_id not in lobbies:
                    continue
                
                lobby = lobbies[lobby_id]
                if session_id in lobby["players"]:
                    lobby["players"][session_id]["ready"] = not lobby["players"][session_id]["ready"]
                    
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
            except ValueError:
                pass
        
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
