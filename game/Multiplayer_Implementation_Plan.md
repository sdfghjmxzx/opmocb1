## Multiplayer System Implementation Plan (Hub + Lobby + Networking)

### 1. Source Documents and Constraints (Fact Basis Only)
- This plan is derived strictly from:
  - `game/multiplayer.md` (architecture: single-threaded Ren'Py, authoritative server, WebSockets, matchmaking, chat, state persistence).
  - `game/Main Menu.md` (section 3: Multiplayer Hub, section 4: Lobby Screen, plus Multiplayer state summary).
  - `game/Main Menu Implementation Plan.md` (Phase 4: Multiplayer Hub and Lobby shells as display-only UI, to be wired later).
- Hard constraints taken as facts:
  - Ren'Py is single-threaded and blocking; it cannot wait on network operations in-line.
  - Server must be the single source of truth for multiplayer game state; client is only a visual representation.
  - Matchmaking and lobby listing require a centralized server; peer-to-peer is not acceptable.
  - WebSockets are the chosen protocol for real-time features (matchmaking, lobby updates, chat).

### 2. Overall Scope and Milestones
- Immediate goal (current work):
  - **Complete and refine the existing Multiplayer Hub screen** (`mp_hub_screen` in `screens.rpy`), which already matches the layout from `Main Menu.md`, by:
    - Wiring the existing Find Match button to local behavior (and later networking).
    - Wiring the existing Create Lobby button to update local lobby state and navigate to the lobby.
    - Completing the Global Chat panel behavior (local chat list + send action + auto-scroll).
    - Replacing hard-coded lobby text with a local lobbies data structure and selection behavior.   
  - This first pass remains **local-only** (no real networking), but all widgets must map cleanly to future network calls.
- Near-term goals (next steps after hub shell refinement):
  - **Complete and refine the existing Lobby Screen** (`mp_lobby_screen` in `screens.rpy`) per `Main Menu.md` with player slots, ready toggles, lobby chat, and character selection hooks, still using only local state.
  - Ensure clean navigation between main menu → multiplayer hub → lobby and back.
- Medium-term goals (after local UI behavior is solid):
  - Implement a standalone Python WebSocket server with the modules defined in `multiplayer.md` for connection management, matchmaking, chat relay, and basic game session tracking.
  - Implement a Ren'Py-compatible **Network Module** that runs in a background thread, exposes a message queue, and is polled by timers from the Multiplayer Hub and Lobby screens.
  - Wire the hub and lobby UI actions to real server messages for: Find Match, Create Lobby, Join Lobby, Lobby List refresh, and Global Chat.
- Long-term goals (explicitly out of scope for the first implementation step):
  - Integrate server-side game engine with this project's combat system and battle flow.
  - Implement persistence (e.g., storing finished games) if needed.

### 3. Current Project Integration Points
- Entry and menu system (from `Main Menu Implementation Plan.md`):
  - The project uses a toggle in `options.rpy` (`config.use_main_menu_shell`) to decide whether to show the custom main menu.
  - The root main menu screen includes a **Multiplayer** button that shows the multiplayer hub.
- Multiplayer-specific screens (already implemented shells):
  - The Multiplayer Hub screen (`mp_hub_screen` in `screens.rpy`) is reachable from the root main menu via the Multiplayer button.
  - The Lobby screen (`mp_lobby_screen` in `screens.rpy`) is reachable from the Multiplayer Hub (from Find Match, Create Lobby, and joining via lobby list).
- Battle integration:
  - No direct connection to `CombatGame` or battle labels is required in this phase; the multiplayer flow will stop at an in-lobby "ready" state.

### 4. Phase 1 – Complete Existing Multiplayer Hub Screen (Local-Only)
**Goal:** Use the existing **Multiplayer Hub** UI (`mp_hub_screen` in `screens.rpy`) and finish its behavior, keeping everything local-only but structured for later networking.

4.1 Screen responsibilities
- Present the main multiplayer actions:
  - Find Match (quick matchmaking intent).
  - Create Lobby (manual lobby creation with optional password, currently via the existing Create Lobby button).
  - Global Chat (read/write text messages in a shared channel, using `main_menu_mp_global_chat_lines`).
  - Available Lobbies list (view and select existing lobbies).
- For this phase, all data (chat lines, lobbies) remains **local dummy data**, but must be structured so that in later phases each interaction maps directly to a server request.

4.2 UI layout mapping (from `Main Menu.md`)
- Upper section:
  - Left: "Find Match" box with a prominent button and descriptive label (Quick Play).
  - Right: "Create Lobby" box with text fields for Lobby Name and Password and a Create button.
- Middle section:
  - Global Chat panel with:
    - Simple tab row for Global vs (future) Team chat.
    - Scrollable area for messages.
    - Input field and Send button.
- Lower section:
  - Available Lobbies panel with:
    - Search field.
    - Scrollable table listing lobbies (Name, Host, Status, Lock indicator).
    - A clear note or interaction pattern that selecting a lobby opens the Lobby screen.

4.3 Local state and behavior (no networking yet)
- Use Ren'Py `default` variables or a small Python data structure to hold:
  - A list of dummy lobby entries (name, host, current players, capacity, locked flag).
  - A list of chat messages (author, text, timestamp or order index).
  - Current search filter text for the lobby list.
  - Current text in the chat input field.
- Actions in this phase:
  - Find Match button: navigates to the Lobby screen with a placeholder "Matchmaking" context (e.g., a local lobby name) but does not contact a server.
  - Create Lobby: appends a new local lobby entry and navigates to the Lobby screen as host.
  - Global Chat send: appends a new local message into the chat list and auto-scrolls to the bottom.
  - Lobby selection: selecting a lobby in the table navigates to the Lobby screen as guest.

4.4 Auto-scroll behavior
- The Global Chat message area should:
  - Have a fixed viewport size with scrollbars.
  - Auto-scroll to the bottom when new messages are added, matching the behavior described for other scrollable UIs in this project (planned actions / battle log rules).

### 5. Phase 2 – Complete Existing Lobby Screen (Local-Only)
**Goal:** Use the existing **Lobby Screen** UI (`mp_lobby_screen` in `screens.rpy`) and finish its behavior, matching `Main Menu.md` section 4, using local state only.

5.1 Screen responsibilities
- Show a 2-player room with:
  - Lobby name and host name.
  - Host and Guest slots, each with name and Ready indicator.
  - Lobby-specific chat.
  - Character selection area for each player (reusing existing character selection UI components where possible).
- Provide basic actions:
  - Ready/Unready toggle for the local player.
  - Leave Lobby to return to the Multiplayer Hub.
  - Local chat send.

5.2 UI layout mapping (from `Main Menu.md`)
- Top: Lobby header (title, lobby name, host).
- Left/Right or top row: two framed player boxes (Host and Guest) with ready indicators.
- Middle: chat panel similar to the Global Chat UI but scoped to this lobby.
- Bottom/mid-right: Character selection area that visually mirrors the single player selection (Choose Preset, Create Custom, Your Character, Enemy Character), with no connection to battle yet.
- Bottom row: Leave Lobby button and Ready/Unready toggle button.

5.3 Local state and behavior (no networking yet)
- Store, via Ren'Py variables or small Python structures:
  - Lobby metadata: lobby id or name, host name, whether this client is host.
  - Player slots: host and guest records (name, is_ready, selected_character summary).
  - Local lobby chat messages.
- Actions in this phase:
  - Ready/Unready toggles only affect the local player's ready flag and its visual indicator.
  - Leave Lobby returns to the Multiplayer Hub without any further side effects.
  - Lobby chat send appends to a local list and auto-scrolls to bottom.
  - Character selection buttons open or reuse existing character gallery/creator screens; selections are stored locally for display.

### 6. Phase 3 – Network Client Module for Ren'Py (Background Thread + Queue)
**Goal:** Implement a Ren'Py-compatible network client module exactly following the pattern in `multiplayer.md`.

6.1 Architecture requirements (from `multiplayer.md`)
- Network module is a pure Python class inside the Ren'Py project that:
  - Manages a WebSocket connection in a background thread.
  - Maintains an **incoming message queue** (thread-safe) for data from server to client.
  - Exposes simple methods the UI can call (for example: connect, disconnect, send matchmaking intent, send chat message).
- Ren'Py screens (Multiplayer Hub and Lobby) do not block waiting for network responses.
  - Instead, they rely on a Ren'Py timer that periodically polls the message queue (e.g., every 0.1–0.5 seconds) and updates screen variables.

6.2 Planned client-side responsibilities
- Connection lifecycle:
  - Establish a WebSocket connection to the server when entering the Multiplayer Hub.
  - Keep the connection alive while in Hub or Lobby screens.
  - Close the connection cleanly when leaving multipayer screens back to main menu.
- Message sending (high-level operations only):
  - Find Match intent.
  - Create Lobby (name, password).
  - Join Lobby (by id or name from lobby list).
  - Request Lobby List (for periodic refresh).
  - Send Global Chat message.
  - Send Lobby Chat message.
- Message receiving:
  - Global Chat updates.
  - Lobby List updates.
  - Lobby state updates (players joined/left, ready status, lobby closed).
  - Matchmaking results (e.g., server assigns a game or lobby id when Find Match succeeds).

6.3 Integration method with screens
- Add a small polling function that:
  - Reads all available messages from the Network Module's queue.
  - Decodes them into structured events (string type plus data payload).
  - Dispatches them to handlers that update Ren'Py variables (chat lists, lobby list, current lobby state).
- Call this polling function from a Ren'Py timer on both Multiplayer Hub and Lobby screens.

### 7. Phase 4 – Minimal WebSocket Server (Matchmaking, Lobbies, Global Chat)
**Goal:** Implement the server-side functionality described in `multiplayer.md` that is required to support the hub and lobby features.

7.1 Modules to implement (directly from `multiplayer.md`)
- Connection and Session Manager:
  - Accept WebSocket connections and assign a unique session id to each.
  - Track active sessions and clean them up on disconnect.
- Matchmaking Pool:
  - Maintain a queue of players who requested Find Match.
  - When two players are available, pair them into a new game or lobby id and notify both clients.
- Game Engine (minimal for now):
  - For this phase, it is sufficient that a game or lobby id is created and tracked; detailed combat rules can be deferred.
- Chat Relay:
  - Receive global chat messages and broadcast them to all connected clients.
  - Receive lobby chat messages and broadcast them only to clients in that lobby.
- State Persistence (optional later):
  - For initial implementation, keep lobby and matchmaking state in memory.
  - Database persistence for results can be added when battle integration is ready.

7.2 Message design principles
- All messages between client and server should:
  - Use a simple envelope with an explicit action or type field.
  - Carry only the minimum required data for the action (for example, lobby name, password, message text).
  - Be designed so that they can be parsed easily by the Ren'Py client and extended later when combat integration is added.

### 8. Phase 5 – Wiring UI to Server (Non-Battle Features Only)
**Goal:** Connect the Multiplayer Hub and Lobby UI to the WebSocket server for matchmaking, lobby management, lobby list refresh, and chat, without starting any battle.

8.1 Multiplayer Hub actions mapped to server
- Find Match:
  - When clicked, send a matchmaking request through the network module.
  - Disable Find Match button or show a "Searching..." state until the server responds.
  - On server match assignment, transition to Lobby screen with the appropriate lobby id and role.
- Create Lobby:
  - Send a lobby creation request with name and password (if any).
  - On success, transition to Lobby screen as host with the new lobby id.
- Lobby List:
  - Periodically request lobby list updates.
  - Replace the local dummy list with the server-provided list.
  - Selecting a lobby sends a join request; on success, transition to Lobby screen as guest.
- Global Chat:
  - Sending a message forwards it to the server.
  - Incoming global chat messages from other players are appended to the local chat list via the polling handler.

8.2 Lobby actions mapped to server
- Ready/Unready:
  - Send a state change to server; the server broadcasts updated lobby state to both clients.
- Leave Lobby:
  - Notify server that the player left; server updates lobby membership and possibly closes the lobby if host leaves.
  - Client returns to Multiplayer Hub screen.
- Lobby Chat:
  - Send messages through server and display any messages received for this lobby.
- Character selection:
  - Initially, character selection can remain local in the lobby.
  - Later, when integrating with battle, selected characters will be synchronized to server as part of game setup state.

### 9. Phase 6 – Future: Battle Integration (Deferred)
**Goal:** Prepare for, but do not yet implement, integration between multiplayer lobbies and this game's combat/battle system.

- When both players are ready and the server marks a lobby as ready to start:
  - Server will finalize game setup (selected characters, initial positions, any configuration).
  - Clients will receive a start-game message that includes necessary identifiers and initial state.
- On the client side (Ren'Py):
  - A dedicated label or entry point for multiplayer battle will be created at a later time.
  - The lobby screen will transition to that entry point, passing any needed parameters.
- Until battle integration work begins, the lobby "ready" state remains purely visual and does not trigger combat.

### 10. Implementation Order Summary (What We Do First)
- Step 1: Verify or implement the main menu root and Multiplayer button according to `Main Menu Implementation Plan.md`.
- Step 2: Complete and refine the existing Multiplayer Hub screen (`mp_hub_screen`) with local-only data and correct behavior (chat, lobbies, navigation).
- Step 3: Complete and refine the existing Lobby screen (`mp_lobby_screen`) with local-only data and navigation from and back to the hub.
- Step 4: Implement the Network Module in Python (background thread + message queue), without yet wiring UI actions.
- Step 5: Implement the minimal WebSocket server supporting matchmaking, lobbies, and chat as per `multiplayer.md`.
- Step 6: Wire Multiplayer Hub and Lobby actions to server messages via the Network Module, keeping battle integration out of scope for now.
- Step 7: Only after all of the above are stable, design and implement the battle integration flow as a separate, later phase.
