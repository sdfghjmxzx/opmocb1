Here's the complete battle menu system architecture:

---

## **BATTLE MENU SYSTEM ARCHITECTURE**

### **1. IN-GAME BATTLE MENU (Pause/Options Overlay)**

**Triggered by:** ESC key or [Options] button during active battle

```
┌─────────────────────────────────────────────────────────┐
│  BATTLE PAUSED                                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [RESUME]                                               │
│  [FORFEIT MATCH]                                        │
│  [OPTIONS]                                              │
│  [EXIT TO MAIN MENU]                                    │
│                                                         │
│  [CANCEL]                                               │
└─────────────────────────────────────────────────────────┘
```

**Button Actions:**

**1.1 FORFEIT MATCH**
- **Forfeiting Player:**
  - Immediate loss recorded
  - Returns to **Multiplayer Hub**
  - Sees message: "You forfeited the match"

- **Winner (Opponent):**
  - Sees overlay: **"OPPONENT FORFEIT - YOU WIN!"**
  ```
  ┌─────────────────────────────────────────┐
  │  OPPONENT FORFEIT                       │
  │       YOU WIN! 🏆                       │
  ├─────────────────────────────────────────┤
  │  [BACK TO LOBBY]  [EXIT TO MP HUB]      │
  └─────────────────────────────────────────┘
  ```

**1.2 OPTIONS**
- Opens standard **Options Menu** (Graphics, Audio, Controls)
- **Resume** button returns to battle
- No impact on match state

**1.3 EXIT TO MAIN MENU**
- **Exiting Player:**
  - Counted as loss
  - Returns to **Main Menu**
  - Sees confirmation: "Leaving will count as loss. Continue?"

- **Winner (Opponent):**
  - Sees overlay: **"OPPONENT LEFT - YOU WIN!"**
  ```
  ┌─────────────────────────────────────────┐
  │  OPPONENT LEFT                          │
  │       YOU WIN! 🏆                       │
  ├─────────────────────────────────────────┤
  │  [BACK TO LOBBY]  [EXIT TO MP HUB]      │
  └─────────────────────────────────────────┘
  ```

---

### **2. POST-MATCH VICTORY/DEFEAT SCREEN**

**Shows when:** Match ends naturally (checkmate/HP zero)

```
┌─────────────────────────────────────────────────────────┐
│              YOU WON! 🏆                                │
│              YOU LOST! 💀                               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Player Actions:                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ [ ☐ REMATCH ]        [ ☐ CHANGE CHARACTERS ]    │  │
│  │          ↑                    ↑                  │  │
│  │    Your checkmark        Your checkmark         │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  [EXIT TO MAIN MENU]                                    │
│                                                         │
│  Opponent Status: [Waiting...]                        │
└─────────────────────────────────────────────────────────┘
```

**Button Mechanics:**

**2.1 REMATCH**
- **Click once:** Adds **✓ checkmark** to your button
- **Click again:** Removes checkmark (toggle)
- **Both players checked:** Auto-starts new match after 3-second countdown
- **Visual Feedback:**
  ```
  Player 1 clicked:  [ ✓ REMATCH ]  [ ☐ CHANGE CHARACTERS ]
  Player 2 sees:     [ ☐ REMATCH (Opponent Ready)]  [ ☐ CHANGE CHARACTERS ]
  ```

**2.2 CHANGE CHARACTERS**
- **Click once:** Adds **✓ checkmark** to your button
- **Click again:** Removes checkmark (toggle)
- **Both players checked:** Returns to **Character Selection Lobby**
- **Visual Feedback:**
  ```
  Player 1 clicked:  [ ☐ REMATCH ]  [ ✓ CHANGE CHARACTERS ]
  Player 2 sees:     [ ☐ REMATCH ]  [ ☐ CHANGE CHAR (Opponent Ready)]
  ```

**2.3 EXIT TO MAIN MENU**
- **Clicking Player:**
  - Leaves immediately to **Main Menu**
  - Lobby destroyed if they were host

- **Remaining Player Sees:**
  ```
  ┌─────────────────────────────────────────────────┐
  │  OPPONENT LEFT                                  │
  ├─────────────────────────────────────────────────┤
  │  [BACK TO LOBBY]    [EXIT TO MP HUB]           │
  └─────────────────────────────────────────────────┘
  ```

---

### **3. CHECKMARK VISUAL SYSTEM**

**Checkmark States:**
```css
/* Button not clicked */
[ ☐ REMATCH ] - Gray outline, transparent checkbox

/* Button clicked by YOU */
[ ✓ REMATCH ] - Green background, green checkmark

/* Button clicked by OPPONENT (what you see) */
[ ☐ REMATCH (Ready)] - Yellow outline, text shows "Ready"

/* Both clicked - auto transition */
[Both Ready! Starting in 3...] - Green pulsing animation
```

**Color Coding:**
- **Green ✓:** Your selection
- **Yellow outline:** Opponent's selection visible to you
- **Blue ✓:** Both players ready (temporary state)

---

### **4. STATE MANAGEMENT FOR POST-MATCH**

```json
{
  "post_match_state": {
    "winner": "player_1_id",
    "loser": "player_2_id",
    "rematch_status": {
      "player_1": false,
      "player_2": true
    },
    "change_char_status": {
      "player_1": true,
      "player_2": false
    },
    "exit_initiated": null,
    "transition_triggered": false
  }
}
```

**Auto-Transition Logic:**
```javascript
// When both rematch === true
if (rematch_status.player_1 && rematch_status.player_2) {
  transition_to("new_match_same_characters");
}

// When both change_characters === true
if (change_char_status.player_1 && change_char_status.player_2) {
  transition_to("character_selection_lobby");
}
```

---

### **5. NETWORK MESSAGE FLOW**

**Forfeit/Exit During Battle:**
```
Player A → Server: {action: "forfeit_match"}
Server → Player B: {message: "opponent_forfeit", you_win: true}
Server → Player A: {message: "you_forfeited", redirect: "mp_hub"}
```

**Post-Match Options:**
```
Player A → Server: {action: "request_rematch"}
Server → Player B: {message: "opponent_wants_rematch", show_checkmark: true}

Player B → Server: {action: "accept_rematch"}
Server → Both: {message: "rematch_confirmed", countdown: 3}
```

---

### **6. IMPLEMENTATION PRIORITY**

**Essential (MVP):**
- [ ] Forfeit button + loss penalty
- [ ] Exit to Main Menu with confirmation
- [ ] Basic "You Won/Lost" screen
- [ ] Rematch button with checkmarks
- [ ] Exit button functionality

**Enhanced:**
- [ ] Change Characters option
- [ ] Real-time checkmark syncing
- [ ] 3-second countdown for rematches
- [ ] Visual polish (animations, colors)
- [ ] Host/guest differentiation in UI

This system creates a clear, synchronized post-match experience where both players must agree on the next action while providing clear visual feedback through the checkmark system.