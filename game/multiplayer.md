Based on your requirements for a turn-based chess game with matchmaking, here is a complete, logically-verified implementation plan.

### **FACT-BASED ARCHITECTURAL PRINCIPLES**
1.  **Ren'Py's Constraint**: The Ren'Py engine is fundamentally **single-threaded and blocking**. It cannot natively wait for network events without freezing the interface.
2.  **State Authority**: To prevent cheating in a competitive game, the **server must be the single source of truth** for game state (board position, turn, game clock). The client is only a visual representation.
3.  **Matchmaking Requirement**: A random, anonymous "find opponent" feature is impossible with Peer-to-Peer (P2P) networking. It requires a **centralized, persistent server** to pool and pair players.
4.  **Protocol Choice**: HTTP polling is inefficient for real-time features like chat and move updates. **WebSockets** provide a full-duplex, persistent connection suitable for instant updates in a turn-based game.

### **COMPREHENSIVE SYSTEM BLUEPRINT**

**1. PRE-DEVELOPMENT: SYSTEM DEFINITION**
- **Tech Stack Confirmation**:
    - **Server**: Python (FastAPI/WebSockets), `python-chess` library, Redis (for active session state).
    - **Client**: Ren'Py (visuals, input), Pure Python (network module).
    - **Communication**: JSON over WebSockets (WSS for production).
- **Data Flow Model**:
    ```
    [Ren'Py Client Input] --> (WebSocket) --> [Server: Logic & Validation] --> (WebSocket) --> [Opponent's Ren'Py Client]
    ```
- **State Management Rule**: The client sends *intent* (e.g., "move e2e4"). The server calculates the *result* (valid/invalid, new board FEN, game status) and broadcasts it.

**2. PHASE 1: DEDICATED SERVER DEVELOPMENT**
- **Module 1.1: Connection & Session Manager**
    - Function: Maintains WebSocket connections and maps them to player sessions.
    - Logic: Assigns a unique `session_id` upon connection. Removes `session_id` and cleans up resources on disconnect.
- **Module 1.2: Matchmaking Pool**
    - Function: Pairs two waiting players into a game session.
    - Logic:
        1. Player A connects and sends a "find_game" request.
        2. Server adds Player A's `session_id` to a `waiting_players` queue.
        3. Player B connects and sends a "find_game" request.
        4. Server creates a unique `game_id`, removes both players from the queue, and instantiates a **Game Engine** (Module 1.3).
        5. Server sends a `game_start` message to both clients, assigning colors (white/black) and the initial board state.
- **Module 1.3: Game Engine**
    - Core: One instance per active game, powered by `python-chess`.
    - Logic Flow for a Move:
        1. Receives `{"action": "move", "from": "e2", "to": "e4"}` from a client.
        2. **Validates** it's the correct player's turn.
        3. **Attempts the move** using `python-chess`. If illegal, sends an error back to the sender.
        4. If legal:
            a. Updates the internal board state.
            b. Checks for game end (checkmate, stalemate, draw).
            c. Generates a new FEN string (board representation).
            d. Broadcasts a standardized `game_state` message to both players: `{"type": "state_update", "fen": "...", "turn": "w", "status": "active/checkmate/draw"}`.
- **Module 1.4: Chat Relay**
    - Function: Passes messages between players in the same game session.
    - Logic: Receives `{"action": "chat", "text": "..."}`. **Sanitizes the text** (strips dangerous characters, enforces length limit). Broadcasts `{"type": "chat", "player": "sender_id", "text": "..."}` to both players in the `game_id` session.
- **Module 1.5: State Persistence**
    - Volatile State (Redis): `game_id`, `player_sessions`, `board_fen`, `turn`, `move_history`. This is lost on server restart.
    - Persistent State (SQLite/PostgreSQL, optional): `game_id`, `final_result`, `move_history` (PGN). Saved when a game ends for records/replay.

**3. PHASE 2: REN'PY CLIENT INTEGRATION**
- **Core Challenge**: Integrating asynchronous network events into Ren'Py's linear, blocking narrative flow.
- **Solution: The Polling Model**.
    - **Network Module**: A Python class inside the Ren'Py project that manages the WebSocket connection in a **background thread**. It has an **incoming message queue**.
    - **Ren'Py Interaction Loop**:
        1. The visual chess screen is displayed.
        2. A Ren'Py `timer` action fires every **0.1 to 0.5 seconds**.
        3. The timer calls a function that checks the **Network Module's message queue**.
        4. If a message exists (e.g., a state update), it updates the Ren'Py `chessboard` screen variables and the display.
        5. The loop repeats, giving the illusion of real-time updates.
- **User Action Flow**:
    1. Player clicks a piece and a target square.
    2. Ren'Py calls `network.send_move("e2", "e4")`, which pushes the data to the WebSocket in the background thread.
    3. The UI shows a "Waiting..." indicator.
    4. The **polling loop** eventually receives the `state_update` from the server, updates the board, hides the "Waiting..." indicator, and unlocks input for the next turn.

**4. PHASE 3: DEPLOYMENT & INFRASTRUCTURE**
- **Server Hosting**: Requires a **always-on** public server (e.g., a $5-10/month VPS from DigitalOcean/Linode, or PaaS like Railway/Render).
- **Connection Security**: You **must** use `wss://` (WebSocket Secure) in production, which requires SSL/TLS setup (often provided automatically by the hosting platform).
- **Domain & Firewall**: The server needs a public IP/domain. Hosting firewall must allow traffic on your chosen port (e.g., 8000 or 443).

### **CRITICAL LOGICAL DEPENDENCIES & VALIDATIONS**
| Component | Logical Requirement | Rationale & Failure Consequence |
| :--- | :--- | :--- |
| **Server Game Engine** | Must run `python-chess` | The client is not trustworthy. Running logic server-side is the only way to enforce rules and prevent cheating. |
| **Client Polling** | Ren'Py **must not** `pause` or block waiting for the network. | Blocking freezes the entire game interface, creating a poor user experience. The timer/polling model is the canonical workaround. |
| **State Sync** | Client display must **only** update after server confirmation. | If the client updates optimistically, it will show illegal moves during network lag or cheat attempts. |
| **Session Cleanup** | Server must remove disconnected players from the matchmaking pool and active games. | Prevents ghost games and frees resources. Requires a "heartbeat" or disconnect detection. |

### **DEVELOPMENT MILESTONES (TESTING SEQUENCE)**
1.  **Milestone 0**: Local Python script that uses `python-chess` and a console input to play chess against itself. (Validates core game logic).
2.  **Milestone 1**: FastAPI server that runs Milestone 0 logic. Two separate Python scripts (simulating clients) can connect via WebSocket and take turns sending moves, with the server printing the board to its console. (Validates server as referee).
3.  **Milestone 2**: A basic Ren'Py project with a chessboard image and clickable squares that prints "Moved [square] to [square]" to the Ren'Py console. (Validates input layer).
4.  **Milestone 3**: Integrate M2 and M1. Clicking a square in Ren'Py sends the move to the local test server. The server response is printed to the Ren'Py console. (Validates the full client-server pipeline).
5.  **Milestone 4**: Implement the **polling loop** in M3 so that the Ren'Py board graphic updates automatically when a `state_update` is received from the server. (Completes core gameplay).
6.  **Milestone 5**: Implement the matchmaking queue and chat module on the server, then integrate them into the client.

### **NON-ASSUMPTIVE RISKS & MITIGATIONS**
| Risk | Probability | Impact | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **Ren'Py WebSocket Library Incompatibility** | High | Blocking | Test `websockets` or `socket` library import in a blank Ren'Py project **first**. If they fail, you must implement an HTTP long-polling fallback (more complex). |
| **Network Lag/Latency** | Certain | Medium | Design the UI to clearly indicate "Opponent's Turn" or "Waiting for Server." Never let the UI feel unresponsive—use the waiting indicator. |
| **Player Disconnection** | Certain | High | Server must implement an **activity timeout** (e.g., 60 seconds). If a player disconnects, the game is paused. On reconnect (same session ID), the server resends the last game state. |
| **Server Cost & Scaling** | Future Issue | Medium | Start with a cheap VPS. The architecture is per-game lightweight. 100 concurrent games might use ~500MB RAM and minimal CPU. |

This plan is derived from the technical constraints of Ren'Py, the logical requirements for a fair and functional multiplayer game, and established networking patterns. The polling model is the **only** verified method to integrate real-time updates into Ren'Py without modifying its engine.
