## Main Menu Implementation Plan (Shell + Toggle Mod)

### 1. Current State (From Existing Project)
- The project entry is defined in `script.rpy`:
  - `label main_menu` currently **immediately returns**, effectively **skipping any main menu**.
  - `label start` initializes `CombatGame` and calls `battle_screen`, which is the existing battle UI.
- `screens.rpy` contains the full battle UI (`screen battle_screen`) and other standard Ren'Py screens.
- `options.rpy` defines Ren'Py configuration and is the correct place to add a **one-line toggle** for enabling/disabling a custom main menu.

### 2. Requirements (From `Main Menu.md` + Your Notes)
- Implement a **Main Menu system** as a set of **display-only screens** for now:
  - Root Main Menu with: Single Player, Multiplayer, **Options**, Quit.
  - Single Player flow: Mode Selection → Character Selection → Preset Gallery → Character Creator.
  - Multiplayer flow: Multiplayer Hub → Lobby screen (2-player room).
- **Only functional connections now**:
  - **Quit** button: must exit the game.
  - **Options** button: must open the existing options/preferences UI.
- **No other gameplay connections yet**:
  - No actual battle start, no networking, no save/load, no character persistence.
- Provide a **mod-style toggle** so you can choose between:
  - **Skipping the main menu** and going directly into battle (current behavior).
  - **Using the main menu first**, then (later) proceeding to battle.
- Toggle must be achievable by **editing a single line** in a config-like file.

### 3. High-Level Phase Overview
- **Phase 1**: Introduce a configuration toggle and prepare entrypoint logic (no UI yet).
- **Phase 2**: Implement the **Main Menu Root screen** shell, with working Quit and Options.
- **Phase 3**: Implement **Single Player** flow screens (display-only) and navigation.
- **Phase 4**: Implement **Multiplayer Hub** and **Lobby** screens (display-only) and navigation.
- **Phase 5**: Add state stubs and future integration hooks (without connecting to battle yet).
- **Phase 6**: Final review and toggle behavior verification.

---

### 4. Phase 1 – Config Toggle + Entry Logic

**Goal**: Create a single-line configuration switch that controls whether the game **uses the main menu** or **skips directly to battle**.

- **4.1 Add toggle in `options.rpy`**
  - Add a new Ren'Py config define (name to use in code later):
    - `define config.use_main_menu_shell = True`
  - This line becomes the **mod toggle**:
    - Set to `True` → game will go through the custom main menu.
    - Set to `False` → game will skip the main menu and go directly to battle (current behavior).
  - Location: keep it close to other basic config defines (e.g. below `define config.name`).

- **4.2 Update `label main_menu` in `script.rpy`**
  - Replace the current "empty" implementation with logic that **checks the toggle**:
    - If `config.use_main_menu_shell` is **False**: immediately `return` from `label main_menu` (preserve current behavior – Ren'Py continues to `label start`).
    - If `config.use_main_menu_shell` is **True**: show the new main menu screen (added in Phase 2) and only leave this label when the player chooses to start the game or quit.
  - For now, since we are creating a **display shell**, the main menu will not start any battle yet; it will mainly allow navigation between menu screens and quitting/entering options.

- **4.3 Keep `label start` behavior as-is for now**
  - `label start` remains the entry point for the battle system.
  - No changes to combat initialization or battle UI in this phase.
  - Future phases (after shells are in place) can connect the main menu to `label start` when required.

**Result**: After Phase 1, you will be able to enable/disable the main menu by editing **one line in `options.rpy`**, without touching any battle logic.

---

### 5. Phase 2 – Main Menu Root Screen Shell

**Goal**: Implement a visual main menu shell that appears when `config.use_main_menu_shell` is `True`, with working Quit and Options buttons.

- **5.1 Create a dedicated main menu screen** in `screens.rpy`
  - Add a new Ren'Py screen (name to be used from `label main_menu`, e.g. `main_menu_shell`).
  - Layout based on section **1. MAIN MENU (Root Level)** from `Main Menu.md`:
    - Game title logo at the top.
    - Buttons vertically stacked:
      - Single Player
      - Multiplayer
      - Options (added per your new requirement)
      - Quit
  - Ensure it is a **clean, standalone screen**, not mixed with battle UI.

- **5.2 Hook label to screen**
  - In `label main_menu`, when toggle is **enabled**, call or show the new `main_menu_shell` screen.
  - Design the screen so that **clicking Quit and Options immediately performs real actions**, while Single Player and Multiplayer only navigate to shell screens.

- **5.3 Implement functional Quit and Options**
  - **Quit button**:
    - Call Ren'Py’s quit action (standard exit from game).
  - **Options button**:
    - Open the existing options/preferences screen defined in `screens.rpy` (whatever the project is currently using – likely the standard `preferences` screen).
  - Confirm they work **regardless of the toggle** as long as `config.use_main_menu_shell` is True.

- **5.4 Ensure no other connections**
  - Single Player and Multiplayer buttons must **only** navigate to other menu screens (Phases 3 and 4), not touch battle or network code.

**Result**: A main menu screen that visually matches your plan and respects the toggle, with Quit and Options fully functional.

---

### 6. Phase 3 – Single Player Flow Shell (Display-Only)

**Goal**: Implement all single-player menu screens described in `Main Menu.md` as **UI shells only**, with internal navigation but **no gameplay logic**.

- **6.1 Mode Selection Screen (2.1)**
  - Screen for selecting **VS Computer** vs **2 Players**.
  - Default visual state: VS Computer selected.
  - Buttons:
    - CONTINUE → navigates to Character Selection screen.
    - BACK → returns to Main Menu Root.
  - Store current selection in simple `default` variables for future use (but do not connect to battle yet).

- **6.2 Character Selection Screen (2.2)**
  - Layout based on your plan:
    - Buttons: CHOOSE PRESET, CREATE CUSTOM.
    - Display areas: Selected character slot, Enemy info (Computer/Player 2).
    - Buttons: START GAME, BACK.
  - For now:
    - START GAME is either disabled or only shows a placeholder message (no battle start).
    - BACK returns to Mode Selection.

- **6.3 Preset Character Gallery (2.3)**
  - Full-screen overlay screen for preset character selection.
  - Visual elements:
    - Search bar.
    - Scrollable grid of character slots.
    - Stats preview area.
    - Buttons: CONFIRM, CANCEL.
  - Behavior (shell-only):
    - Selecting a character updates a simple variable and closes back to Character Selection on CONFIRM.
    - CANCEL returns without changes.

- **6.4 Character Creator (2.4)**
  - Screen for custom character creation with:
    - Name field, attribute sliders/buttons, power selection area.
  - Power filter system visually mirrors your plan (categories, filters, scrollable list) but does not need real data yet – dummy entries are acceptable as placeholders.
  - Buttons: CANCEL, SAVE & USE.
    - For now, SAVE & USE can simply set a variable and return to Character Selection without affecting battle logic.

**Result**: You can fully navigate the **single-player menu journey**, but it does not yet start or affect any battle; it only manages menu-local state.

---

### 7. Phase 4 – Multiplayer Hub & Lobby Shells (Display-Only)

**Goal**: Implement the Multiplayer Hub and Lobby UI per `Main Menu.md`, again as **display-only shells** with internal navigation only.

- **7.1 Multiplayer Hub Screen (3.)**
  - Layout per your ASCII mock:
    - Buttons: FIND MATCH, CREATE LOBBY.
    - Global Chat panel (static; messages can be placeholder text).
    - Available Lobbies table with example rows.
  - For now:
    - FIND MATCH and CREATE LOBBY do not perform networking – they can simply navigate to the Lobby screen or show placeholder dialogs.
    - Double-click to join can be visual-only (e.g., single click on a row to enter Lobby screen with that lobby’s name pre-filled).

- **7.2 Lobby Screen (4.)**
  - Layout per your plan:
    - 2-player slots (Host / Guest), ready status indicators.
    - Chat area (static, local-only visuals).
    - Character selection panel that **reuses** the same components used in Single Player (from Phase 3).
    - Buttons: LEAVE LOBBY, READY / UNREADY.
  - For now:
    - READY/UNREADY toggles a local variable and updates the displayed symbol.
    - LEAVE LOBBY returns to Multiplayer Hub.
    - No network, no synchronization; all visual and local.

**Result**: The multiplayer branch of the main menu is navigable and visually complete, without committing to any backend or networking decisions.

---

### 8. Phase 5 – State Stubs & Future Integration Hooks

**Goal**: Prepare **clean integration points** so that later we can connect menu choices to battle logic and (potentially) networking, without changing the UI again.

- **8.1 Define state structures (stubs only)**
  - Based on section **5. STATE MANAGEMENT SUMMARY** in `Main Menu.md`, introduce lightweight variables representing:
    - Single player state: mode, player_character type, enemy_character type, game_ready flag.
    - Multiplayer state: lobby_id, is_host, room_status, players host/guest info, password_protected.
  - Use Ren'Py `default` or small Python classes defined in an `init python` block.

- **8.2 Add internal hooks (no-op for now)**
  - On key actions (e.g., confirming a preset, finishing character creation, toggling ready), update these state variables.
  - Do **not** call battle labels or engine functions yet – all changes stay within menu state.

- **8.3 Plan for future transitions**
  - Document in comments where the future connections will go, e.g.:
    - Single Player → when `game_ready` is true and player presses START GAME, transition to `label start`.
    - Multiplayer → when both players are ready and host starts game, transition to a future multiplayer battle entry label.

**Result**: Menu screens remain display-only but are ready to be wired into actual gameplay with minimal future changes.

---

### 9. Phase 6 – Toggle Behavior & Regression Check

**Goal**: Verify that the new main menu system behaves correctly under both toggle settings, without impacting battle logic.

- **9.1 When `config.use_main_menu_shell = False`**
  - Game should behave **exactly like now**:
    - `label main_menu` returns immediately.
    - Execution continues to `label start` and the battle screen appears directly.
  - Main menu screens exist in code but are never shown.

- **9.2 When `config.use_main_menu_shell = True`**
  - Game should:
    - Enter `label main_menu`.
    - Show the new main menu root screen.
    - Allow navigation into all single-player and multiplayer UI shells.
    - Allow access to Options and Quit as fully functional.
  - Pressing Quit must exit the game; Options must open the current options/preferences UI.

- **9.3 No unintended side effects**
  - No changes to battle mechanics or visuals.
  - No new persistent data that alters combat behavior.

---

### 10. Suggested Task Breakdown (For Implementation)

- **Task 1**: Add `config.use_main_menu_shell` toggle to `options.rpy` and update `label main_menu` logic in `script.rpy`.
- **Task 2**: Implement the Main Menu Root screen shell in `screens.rpy`, with functional Quit and Options.
- **Task 3**: Implement Single Player flow screens (Mode Select, Character Select, Preset Gallery, Character Creator) as display-only with navigation.
- **Task 4**: Implement Multiplayer Hub and Lobby screens as display-only with navigation and local-only ready/chat placeholders.
- **Task 5**: Add state stubs and internal hooks for single player and multiplayer, still without connecting to battle.
- **Task 6**: Verify toggle behavior in both modes and perform a quick regression check on battle startup.
