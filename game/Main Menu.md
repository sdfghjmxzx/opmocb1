Here's the revised and detailed plan based on your updated requirements:

---

## **UPDATED MAIN MENU SYSTEM ARCHITECTURE**

### **1. MAIN MENU (Root Level)**
```
┌─────────────────────────────────────┐
│          GAME TITLE LOGO            │
├─────────────────────────────────────┤
│                                     │
│  [ Single Player ]                  │
│  [ Multiplayer  ]                  │
│  [ Quit         ]                  │
│                                     │
└─────────────────────────────────────┘
```

---

### **2. SINGLE PLAYER FLOW**

#### **2.1 Mode Selection Screen**
```
┌──────────────────────────────────────────────────┐
│      SINGLE PLAYER: Select Game Mode           │
├──────────────────────────────────────────────────┤
│                                                  │
│  Player Mode:  [● VS Computer  ○ 2 Players]    │
│                                                  │
│  [CONTINUE]  [BACK]                              │
└──────────────────────────────────────────────────┘
```
- **Default:** VS Computer selected
- **Toggle switches enemy type:** Computer AI or Human Player 2

#### **2.2 Character Selection Screen**
```
┌─────────────────────────────────────────────────────────┐
│  SELECT YOUR CHARACTER                                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [CHOOSE PRESET]      [CREATE CUSTOM]                 │
│                                                         │
│  Selected: [Empty Slot]                               │
│                                                         │
│  Enemy: [Computer: Normal]  ← Toggle if 2P mode      │
│                                                         │
│  [START GAME]  [BACK]                                  │
└─────────────────────────────────────────────────────────┘

**Interaction:**
- Click **CHOOSE PRESET** → Opens **Full-Screen Character Gallery** (see 2.3)
- Click **CREATE CUSTOM** → Opens **Character Creator** (see 2.4)
- **START GAME** enabled when both sides selected

#### **2.3 Preset Character Gallery (Full Screen)**
```
┌─────────────────────────────────────────────────────────┐
│  CHARACTER GALLERY                          [X] Close │
├─────────────────────────────────────────────────────────┤
│  Search: [_______________________]                    │
│  ┌──────────────────────────────────────────────────┐ │
│  │ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐          │ │
│  │ │Avatar│ │Avatar│ │Avatar│ │Avatar│          │ │
│  │ │Name  │ │Name  │ │Name  │ │Name  │          │ │
│  │ └──────┘ └──────┘ └──────┘ └──────┘          │ │
│  │                                                  │ │
│  │ [Scrollable Grid: 12-20+ characters]           │ │
│  └──────────────────────────────────────────────────┘ │
│                                                         │
│  Selected: [Character Name]        [CONFIRM] [CANCEL] │
│  Stats Preview:                                       │
│  STR: 75 | DEF: 60 | SPD: 50 | ...                    │
└─────────────────────────────────────────────────────────┘
```
- **Scroll bar** for large character roster
- **Search bar** filters by character name
- **Click character** → Shows stats preview
- **Confirm** → Returns to selection screen with character loaded

#### **2.4 Character Creator**
```
┌─────────────────────────────────────────────────────────┐
│  CUSTOM CHARACTER CREATION                  [X] Close │
├─────────────────────────────────────────────────────────┤
│  Name: [________________________]                     │
│                                                       │
│  ATTRIBUTES                                           │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Strength      [==========] 50/100  [-][+]      │ │
│  │ Defense       [=====     ] 30/100  [-][+]      │ │
│  │ Speed         [==========] 50/100  [-][+]      │ │
│  │ Reaction      [====      ] 25/100  [-][+]      │ │
│  │ Endurance     [========  ] 45/100  [-][+]      │ │
│  │ Willpower     [===       ] 20/100  [-][+]      │ │
│  │ Haki          [======    ] 35/100  [-][+]      │ │
│  │ Devil Fruit   [==        ] 10/100  [-][+]      │ │
│  └──────────────────────────────────────────────────┘ │
│  Points: 155/300 Remaining                            │
│                                                       │
│  POWER SELECTION                                      │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Search: [_______] [Filter: All ▼]              │ │
│  │ ┌──────────────────────────────────────────────┐ │ │
│  │ │ [Logia] [Paramecia] [Zoan]                 │ │ │
│  │ │                                            │ │ │
│  │ │  [Elemental] [Physical]                  │ │ │
│  │ │  Logia Powers:                             │ │ │
│  │ │  [Power 1] [Power 2] [Power 3]           │ │ │
│  │ │  [Power 4] [Power 5] [Power 6]           │ │ │
│  │ └──────────────────────────────────────────────┘ │ │
│  │ [Scrollable power grid]                        │ │
│  └──────────────────────────────────────────────────┘ │
│  Selected Power: [Power Name]  [CHANGE]             │
│                                                       │
│  [CANCEL] [SAVE & USE]                              │
└─────────────────────────────────────────────────────────┘
```

**Power Filter System:**
- **Main Categories:** Logia | Paramecia | Zoan
- **Sub-filters:**
  - **Logia:** Elemental (Fire, Ice) | Physical (Smoke, Light)
  - **Paramecia:** Unique/Non-Elemental
  - **Zoan:** Animal | Plant
- **Only ONE power selectable** (radio button behavior)
- **Search bar** filters by power name

---

### **3. MULTIPLAYER HUB**
```
┌─────────────────────────────────────────────────────────┐
│  MULTIPLAYER                                           │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │ [FIND MATCH]    │  │ [CREATE LOBBY]              │ │
│  │ Quick Play      │  │  Lobby Name: [___________]  │ │
│  │                 │  │  Password:   [___________]  │ │
│  │                 │  │  [CREATE]                   │ │
│  └─────────────────┘  └─────────────────────────────┘ │
│                                                       │
│  GLOBAL CHAT                                          │
│  ┌──────────────────────────────────────────────────┐ │
│  │ [Global] [Team]                                  │ │
│  │ Player1: Anyone up for a match?                │ │
│  │ Player2: Creating lobby now                    │ │
│  │                                                  │ │
│  │ [Type message...] [SEND]                       │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  AVAILABLE LOBBIES                                    │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Search: [________________]                     │ │
│  │                                                  │ │
│  │ Lobby Name      | Host        | Status   | Lock│ │
│  │──────────────────────────────────────────────────│ │
│  │ "Epic Duel"     | Luffy_93    | 1/2      | 🔒  │ │
│  │ "Noobs Only"    | ZoroSwords  | 2/2      |     │ │
│  │ [Double-click to join]                         │ │
│  └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

### **4. LOBBY SCREEN (2-Player Room)**

```
┌─────────────────────────────────────────────────────────┐
│  LOBBY: "Epic Duel"  |  Host: Luffy_93               │
├─────────────────────────────────────────────────────────┤
│  PLAYERS                                              │
│  ┌──────────────────┐  ┌──────────────────┐          │
│  │ [HOST] Luffy_93  │  │ [GUEST] ZoroSwords│         │
│  │ Ready: ✓         │  │ Ready: ✗          │         │
│  └──────────────────┘  └──────────────────┘          │
│                                                       │
│  CHAT                                                 │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Luffy_93: Ready when you are!                  │ │
│  │ ZoroSwords: One sec, picking character         │ │
│  │                                                  │ │
│  │ [Type message...] [SEND]                       │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  CHARACTER SELECTION                                  │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Same UI as Single Player:                      │ │
│  │ [CHOOSE PRESET] [CREATE CUSTOM]                │ │
│  │                                                  │ │
│  │ Your Character: [Avatar + Name]                │ │
│  │ Enemy Character: [Avatar + Name]               │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  [LEAVE LOBBY]                    [READY] / [UNREADY] │
└─────────────────────────────────────────────────────────┘
```

**Lobby Features:**
- **Always 2-player capacity** (no max setting needed)
- **Host Admin Options:**
  - **Kick Player:** Confirmation dialog → Guest removed
  - **Set Password:** Can add/remove password after creation
- **Ready System:** Click toggles between [READY] and [UNREADY]
- **Leave Button:** Returns to Multiplayer Hub
- **Chat:** Same functionality as global chat, but lobby-specific
- **Character Selection:** Identical UI to Single Player mode

---

### **5. STATE MANAGEMENT SUMMARY**

**Single Player State:**
```json
{
  "mode": "vs_computer|two_player",
  "player_character": "preset|custom",
  "enemy_character": "preset|custom|computer_ai",
  "game_ready": true
}
```

**Multiplayer State:**
```json
{
  "lobby_id": "unique_string",
  "is_host": false,
  "room_status": "waiting|ready|in_game",
  "players": {
    "host": {"name": "...", "ready": false, "character": null},
    "guest": {"name": "...", "ready": false, "character": null}
  },
  "password_protected": false
}
```

---

### **6. IMPLEMENTATION CHECKLIST**

**Single Player:**
- [ ] Mode selection toggle (Computer vs 2P)
- [ ] Full-screen preset gallery with search/scroll
- [ ] Character creator with 1-power selection
- [ ] Power filter: 3 main types + sub-filters
- [ ] Simple START button (no dual confirmation)

**Multiplayer:**
- [ ] Global chat in hub
- [ ] Lobby creation (name + optional password)
- [ ] Lobby list with search
- [ ] Lobby UI mirroring single player selection
- [ ] Ready toggle button
- [ ] Leave lobby functionality
- [ ] Host kick & password management
- [ ] Lobby chat system

**Both Modes:**
- [ ] Shared character selection UI components
- [ ] Shared character creator
- [ ] Shared power catalog system

This updated plan is streamlined with all unnecessary elements removed and your specific requirements properly integrated. The key is reusing the same character selection UI between single and multiplayer modes for consistency.