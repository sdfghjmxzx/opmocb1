# MP BATTLE OPTIONS - IMPLEMENTATION PLAN

## ANALYSIS OF EXISTING CODE

### Current State
1. **Battle Screen**: `battle_screen_mp()` at line 7478 in screens.rpy
2. **Game End Detection**: Lines 9442-9456 check `combat_game.game_active` and `combat_game.winner`
3. **Victory Screen**: Currently shows "RESTART BATTLE" and "QUIT GAME" buttons
4. **Network Client**: Has methods for lobby management (send_leave_lobby, etc.)
5. **Lobby State**: Tracked via `main_menu_mp_lobby_id`, `main_menu_mp_lobby_name`, `mp_i_am_player1`
6. **Server Leave Logic**: `leave_lobby` message handled at line 1320 in multiplayer_server.py

### What Needs to be Built

## PHASE 1: IN-GAME PAUSE MENU (ESC KEY)

### Components Needed:
1. **Pause State Variable**
   - `default mp_battle_paused = False`
   - Controls overlay visibility

2. **ESC Key Binding**
   - Add to battle_screen_mp: `key "K_ESCAPE" action ToggleScreenVariable("mp_battle_paused")`
   - Toggle pause state

3. **Pause Menu Overlay**
   - Frame with buttons: RESUME, FORFEIT MATCH, OPTIONS, EXIT TO MAIN MENU, CANCEL
   - Positioned center screen (xalign 0.5, yalign 0.5)
   - Semi-transparent background (#000000CC)

4. **Button Actions**:
   - **RESUME**: `SetScreenVariable("mp_battle_paused", False)`
   - **FORFEIT MATCH**: Call `mp_forfeit_match()` function
   - **OPTIONS**: Open options screen (existing screen if available)
   - **EXIT TO MAIN MENU**: Call `mp_exit_to_main_menu()` with confirmation
   - **CANCEL**: Same as RESUME

### Network Messages for Phase 1:
- **Forfeit**: `{"type": "forfeit_match", "lobby_id": str}`
- **Exit**: Use existing `leave_lobby` message

### Functions to Create:
```python
def mp_forfeit_match():
    # Send forfeit message to server
    # Set combat_game.game_active = False
    # Set combat_game.winner = opponent name
    # Trigger post-match screen OR redirect to MP Hub
```

```python
def mp_exit_to_main_menu():
    # Show confirmation dialog
    # If confirmed: send leave_lobby, navigate to main menu
```

## PHASE 2: POST-MATCH SCREEN OVERHAUL

### Components Needed:
1. **Post-Match State Variables**
   - `default mp_post_match_my_rematch = False`
   - `default mp_post_match_opponent_rematch = False`
   - `default mp_post_match_my_change_char = False`
   - `default mp_post_match_opponent_change_char = False`
   - `default mp_post_match_countdown = 0`

2. **Victory/Defeat Screen Replacement**
   - Replace lines 9442-9456 with new layout
   - Show: "YOU WON!" or "YOU LOST!" based on combat_game.winner vs mp_i_am_player1
   - Two checkbox buttons: REMATCH, CHANGE CHARACTERS
   - EXIT TO MAIN MENU button
   - Opponent status display

3. **Checkbox Toggle Buttons**
   - Click once: sets your flag to True, sends message to server
   - Click again: sets flag to False, sends cancel message
   - Visual states:
     - Unchecked: `[ ☐ REMATCH ]` gray
     - Your check: `[ ✓ REMATCH ]` green background
     - Opponent ready: Show text "(Opponent Ready)" in yellow

4. **Auto-Transition Logic**
   - Timer checks every 0.1 seconds:
     - If both rematch == True: Start 3-second countdown, then rematch
     - If both change_char == True: Return to lobby screen

5. **Countdown Display**
   - Frame appears when countdown starts
   - Shows "Starting in 3... 2... 1..."
   - Then calls rematch function

### Network Messages for Phase 2:
- **Rematch Request**: `{"type": "rematch_request", "lobby_id": str, "requested": bool}`
- **Change Char Request**: `{"type": "change_characters", "lobby_id": str, "requested": bool}`
- **Exit**: Use existing `leave_lobby`

### Server-Side Messages to Handle:
- **Opponent Rematch**: `{"type": "opponent_rematch", "requested": bool}`
- **Opponent Change Char**: `{"type": "opponent_change_char", "requested": bool}`
- **Both Ready Rematch**: `{"type": "start_rematch_countdown"}`
- **Both Ready Change**: `{"type": "return_to_lobby"}`
- **Opponent Left**: `{"type": "opponent_left_match"}`

### Functions to Create:
```python
def mp_toggle_rematch():
    # Toggle mp_post_match_my_rematch
    # Send rematch_request message
    # Check if both ready -> trigger countdown
```

```python
def mp_toggle_change_characters():
    # Toggle mp_post_match_my_change_char
    # Send change_characters message
    # Check if both ready -> return to lobby
```

```python
def mp_start_rematch():
    # Reset combat_game state
    # Reset post-match flags
    # Restart battle (call confirm_turn or reset system_turn_counter)
```

```python
def mp_return_to_lobby():
    # Clear post-match flags
    # Navigate to mp_lobby_screen
    # Reset character selections
```

## PHASE 3: SERVER-SIDE IMPLEMENTATION

### New Message Handlers Needed in multiplayer_server.py:

1. **forfeit_match**
   - Validate lobby_id and session
   - Broadcast to opponent: `{"type": "opponent_forfeit"}`
   - Send to forfeiter: `{"type": "forfeit_confirmed", "redirect": "mp_hub"}`

2. **rematch_request**
   - Store rematch state for this player in lobby
   - Broadcast to opponent: `{"type": "opponent_rematch", "requested": bool}`
   - If both true: Broadcast `{"type": "start_rematch_countdown"}`

3. **change_characters**
   - Store change_char state for this player in lobby
   - Broadcast to opponent: `{"type": "opponent_change_char", "requested": bool}`
   - If both true: Broadcast `{"type": "return_to_lobby"}`

4. **leave during match**
   - Detect leave_lobby during active match
   - Broadcast to remaining player: `{"type": "opponent_left_match"}`

### Lobby State Extensions:
```python
lobbies[lobby_id] = {
    # ... existing fields ...
    "match_active": bool,
    "post_match_state": {
        "player1_rematch": False,
        "player2_rematch": False,
        "player1_change_char": False,
        "player2_change_char": False
    }
}
```

## IMPLEMENTATION ORDER

### MILESTONE 1: Pause Menu (Forfeit + Exit)
1. Add pause state variable
2. Add ESC key binding
3. Create pause menu overlay UI
4. Implement mp_forfeit_match() function
5. Implement mp_exit_to_main_menu() function
6. Add NetworkClient methods: send_forfeit(), send_exit()
7. Add server handlers for forfeit
8. Test forfeit flow both sides

### MILESTONE 2: Post-Match Checkboxes
1. Add post-match state variables
2. Replace victory screen UI with new layout
3. Create checkbox toggle buttons with visual states
4. Implement mp_toggle_rematch() function
5. Implement mp_toggle_change_characters() function
6. Add NetworkClient methods for post-match messages
7. Add poll_network_messages handlers for opponent states
8. Test checkbox syncing

### MILESTONE 3: Auto-Transitions
1. Add countdown timer display
2. Implement mp_start_rematch() function
3. Implement mp_return_to_lobby() function
4. Add server-side "both ready" detection
5. Add server broadcast for transitions
6. Test full rematch flow
7. Test full change-characters flow

### MILESTONE 4: Edge Cases
1. Handle opponent leaving during pause
2. Handle opponent leaving during post-match
3. Show "Opponent Left" overlay with options
4. Handle host vs guest lobby destruction
5. Add confirmation dialogs where needed
6. Test all disconnect scenarios

## FILES TO MODIFY

1. **game/screens.rpy**
   - Add pause menu UI
   - Replace post-match UI
   - Add state variables
   - Add toggle functions
   - Add NetworkClient methods
   - Add poll_network_messages handlers

2. **multiplayer_server.py**
   - Add forfeit_match handler
   - Add rematch_request handler
   - Add change_characters handler
   - Extend lobby state structure
   - Add "both ready" detection logic

3. **game/controller.py** (MAYBE)
   - May need reset methods for rematch
   - Check if existing restart logic can be reused

## POTENTIAL ISSUES

1. **Rematch State Reset**: Need to ensure combat_game fully resets between rematches
2. **Animation Cleanup**: Need to clear animation queue on forfeit/exit
3. **Network Sync**: Post-match states must stay synced between clients
4. **Lobby Persistence**: Lobby should remain intact during match and post-match
5. **Turn Counter**: system_turn_counter needs to reset on rematch

## QUESTIONS FOR VERIFICATION

1. Does combat_game have a reset() method or do we manually reset fields?
2. Should OPTIONS button open existing options screen or create new one?
3. On forfeit, go to MP Hub or stay in post-match for opponent decision?
4. Should countdown be cancellable or automatic once both ready?
5. Does lobby auto-destroy when both players leave post-match?
