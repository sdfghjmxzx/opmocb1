import asyncio
import json
import uuid

import websockets


connected_clients = set()


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
    print(f"[SERVER] Client connected: {session_id}. Total clients: {len(connected_clients)}")
    try:
        async for raw in websocket:
            print(f"[SERVER] Received raw message: {raw}")
            try:
                data = json.loads(raw)
            except Exception:
                # Ignore malformed messages
                continue

            msg_type = data.get("type")
            if msg_type == "chat":
                channel = data.get("channel", "global")
                text = data.get("text", "")
                if not text:
                    continue
                sender = data.get("sender") or session_id

                payload = json.dumps({
                    "type": "chat",
                    "channel": channel,
                    "text": text,
                    "sender": sender,
                })
                print(f"[SERVER] Broadcasting to {len(connected_clients)} clients: {payload}")

                # Broadcast to all connected clients, skip broken connections
                if connected_clients:
                    tasks = []
                    for client in list(connected_clients):
                        try:
                            tasks.append(client.send(payload))
                        except Exception:
                            # Client connection broken, will be removed in finally block
                            pass
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
    except websockets.exceptions.ConnectionClosedError:
        print(f"[SERVER] Client {session_id} connection closed (normal)")
    except Exception as e:
        print(f"[SERVER] Client {session_id} error: {e}")
    finally:
        connected_clients.discard(websocket)
        print(f"[SERVER] Client disconnected: {session_id}. Remaining: {len(connected_clients)}")


async def main(host: str = "0.0.0.0", port: int = 8765):
    """Run the WebSocket server for multiplayer global chat.

    This is a minimal first step towards the architecture in game/multiplayer.md.
    """
    async with websockets.serve(handle_client, host, port):
        print(f"Multiplayer WebSocket server running on ws://{host}:{port}")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
