Here is the complete, final timer implementation logic:

---

## **BATTLE TIMER SYSTEM - COMPLETE LOGICAL SPECIFICATION**

### **1. CORE TIMER MECHANICS**

**45-Second Turn Limit:**
- Each turn begins with a 45-second countdown
- Timer displays in battle UI: progress bar + seconds remaining
- After 45 seconds, the confirm button locks automatically
- Player receives 1 flag per timeout (3 flags = automatic forfeit)
- Flags persist across turns (non-consecutive counts)

---

### **2. TIME INTERVALS & ACTIONS**

**T+0s (Turn Start):**
- Server broadcasts `turn_start` message (server timestamp, player ID, turn number)
- Client resets timer to 45s, enables confirm button, starts visual countdown

**T+20s:**
- Server broadcasts `sync_20` checkpoint (server timestamp, remaining: 25s)
- Client adjusts local timer if drift >1s from server

**T+40s:**
- Server broadcasts `sync_40` checkpoint (server timestamp, remaining: 5s)
- Client displays visual warning (red text, pulsing animation)

**T+45s (Timeout Event):**
- Client locks confirm button, stops countdown
- Client sends `clock_out` message to server
- Client UI shows: **"Timeout - Verifying Connection..."**

**T+45s to T+50s (5-Second Grace Period):**
- Server receives `clock_out` from client
- Server sends `ping_request` with unique ID to that player
- Server waits 5 seconds for ANY packet from that player

---

### **3. MESSAGE FLOW DECISION TREE**

**Path A: Normal Turn Submission**
```
Client → Server: turn_submitted (before T+45s)
Server → Both: turn_validated + next_turn
Result: Timer resets, next turn begins normally
```

**Path B: Grace Period Save (Turn Within 5s Window)**
```
Client → Server: clock_out (at T+45s)
Server sends ping_request
Client → Server: turn_submitted (at T+47s)
Server → Both: timeout_cancelled + turn_validated
Result: No flag, turn processed normally
```

**Path C: Valid Timeout (Connected But Late)**
```
Client → Server: clock_out (at T+45s)
Server sends ping_request
Server receives ANY packet within 5s (turn, ping response, chat)
Server → Both: skip_turn (player flagged, +1 flag)
Result: Turn skipped, flag assigned, opponent continues
```

**Path D: Disconnect (No Packets 5s)**
```
Client → Server: clock_out (at T+45s)
Server sends ping_request
Server receives NO packets for 5 seconds
Server → Both: connection_lost (player: disconnected)
Result: Game PAUSED, reconnect logic triggered
```

**Path E: Late Turn (After Grace Period)**
```
Client → Server: clock_out (at T+45s)
Server sends ping_request
Grace period expires at T+50s (skip processed)
Client → Server: turn_submitted (at T+52s)
Server → Client A: turn_rejected (late, flag assigned)
Server → Client B: opponent_late_turn (opponent flagged)
Result: Skip stands, late move rejected, flag assigned
```

---

### **4. DISCONNECT DETECTION LOGIC**

**At T+50s (Grace Period Expiry):**
- Server checks: "Did I receive ANY packet from this player in the last 5 seconds?"
- **If YES (any packet):** Player is connected but slow → apply timeout flag, process skip
- **If NO (absolute silence):** Player is disconnected → **PAUSE GAME**, trigger reconnect sequence

**Reconnect Sequence:**
- Paused player has 30 seconds to reconnect
- If reconnect succeeds: Game resumes (player still gets timeout flag for missed turn)
- If reconnect fails: Automatic forfeit (3 flags if already at 2)
- Opponent sees: "Opponent reconnecting..." countdown

**No Dependency:** Does not use scheduled ping. Uses active ping_request at the exact moment it's needed.

---

### **5. SERVER STATE MANAGEMENT**

**Per-Turn State:**
```json
{
  "current_turn": 5,
  "active_player": "player_A_id",
  "turn_start_time": 1704091234567,
  "ping_request_id": "ping_12345",
  "grace_period_active": false,
  "packets_received_in_grace": [],
  "player_flags": {
    "player_A_id": 1,
    "player_B_id": 0
  }
}
```

**Server Actions:**
- **On `clock_out`:** Send `ping_request`, start 5s grace timer, set `grace_period_active: true`
- **On ANY packet during grace:** Add to `packets_received_in_grace` (timestamp, type)
- **On grace expiry:** Check if array is empty → disconnect, else → timeout flag
- **On 3 flags:** Trigger `force_forfeit`

---

### **6. CLIENT STATE MANAGEMENT**

**Client Actions:**
- **On `turn_start`:** Reset timer, unlock button, start countdown
- **On local T+45s:** Lock button, send `clock_out`, show "Verifying..."
- **On `ping_request`:** Immediately respond with `ping_response` (auto-respond, no player action)
- **On `skip_turn`:** Show "Turn Skipped - Flag Added", update flag counter
- **On `connection_lost`:** Show "Connection Lost - Game Paused", wait for reconnect
- **On `turn_rejected`:** Show "Move Too Late - Flag Added ⚑"

---

### **7. FLAG SYSTEM RULES**

- **Flag triggers:** Timeout, late turn (>5s), invalid move
- **Flag limit:** 3 flags = instant forfeit
- **Flag display:** Visible to both players (⚑⚑⚐ 1/3)
- **Flag persistence:** Flags remain for entire match (don't reset between turns)
- **Flag consequence:** 3rd flag forces immediate forfeit to opponent

---

### **8. VISUAL FEEDBACK SPECIFICATION**

**Client A (Active Player) Display:**
```
T+0s to T+40s:  "Time: 45s" (blue bar)
T+40s to T+45s:  "Time: 5s" (yellow, flashing)
T+45s:           "Timeout - Verifying Connection..."
T+50s (timeout): "Turn Skipped - Flag ⚑ (1/3)"
T+50s (late):    "Move Rejected - Late ⚑ (2/3)"
```

**Client B (Opponent) Display:**
```
T+0s to T+50s:   "Opponent's Turn: 45s" (blue)
T+50s (timeout): "Opponent Timeout - Your Turn" (green)
T+52s (late):    "Opponent Late - Flagged ⚑"
```

**Connection Paused Display:**
```
Both Clients: "Game Paused - Connection Issue"
Countdown: "Resuming in 30s... (29, 28, 27...)"
```

---

### **9. FINAL RULES SUMMARY**

1. **45s hard limit:** Confirm button locks at 0s, no late submissions possible
2. **5s grace period:** Only for connection verification, not extra move time
3. **Active ping request:** Server asks specifically at T+45s, not waiting for scheduled ping
4. **Any packet counts:** Turn submission, ping response, chat—any proves connection
5. **Silence = disconnect:** 5 seconds with zero packets = game paused
6. **Late = rejected:** Moves after T+50s are rejected, flag assigned, skip stands
8. **3 flags = forfeit:** Persistent across turns, immediate game end on 3rd flag
9. **Event-driven:** Server only processes messages, never actively polls
10. **Hybrid sync:** Server syncs at 20s/40s, client handles 45s countdown locally

---

