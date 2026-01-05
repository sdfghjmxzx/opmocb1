## **Status Effect UI Design (Stacking-Aware)**

Here's a complete UI representation system that handles all stacking rules:

---

### **Active Effects Panel**

```
╔════════════════════════════════════════════════╗
║  ACTIVE EFFECTS                                ║
╠════════════════════════════════════════════════╣
║  DEBUFFS                                       ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ║
║                                                ║
║  🔥 Burn DoT                                   ║
║  └─ 5 dmg/turn  [3 turns]                      ║
║                          
║                                                ║
║  🐌 Slow                                       ║
║  └─ Speed -10%  [2 turns]  × 3 STACKS          ║
║                         
║                                                ║
║  💀 Poison                                     ║
║  └─ 8 dmg/turn  [4 turns]                      ║
║                          
║                                                ║
║  ⚡ Stamina Drain                              ║
║  └─ +25% stamina cost  [5 turns]               ║
║                          
║                                                ║
║  BUFFS                                         ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ║
║                                                ║
║  ❄️ Ice Armor                                   ║
║  └─ Defense +15%  [3 turns]                    ║
║                                                ║
║  💨 Speed Boost                                ║
║  └─ Speed +20%  [2 turns]                      ║
║                          
╚════════════════════════════════════════════════╝
```

---

## **Effect Row Components Breakdown**

Each effect displays **4 critical elements**:

### **1. Icon & Name**
```
🔥 Burn DoT
```
- **Unique icon** per effect type
- **Color-coded:** Red = damage, Blue = debuff, Green = buff

### **2. Magnitude & Duration**
```
5 dmg/turn  [3 turns]
```
- **Left side:** Current effect magnitude
- **Right side:** `[X turns]` remaining duration
- **Real-time countdown:** Updates at turn start

### **3. Stack Counter (ONLY for stackable effects)**
```
× 3 STACKS
```
- **Appears ONLY** for `stat_debuff` and `instant_damage` categories
- **Shows current stack count** (1-5 for stat debuffs, ∞ for instant)
- **Red highlight when at max** (e.g., × 5 STACKS turns orange)



## **Stacking Visual States**

### **A. Non-Stackable Effect (DoT) - REFRESH Behavior**
```
Initial:  🔥 Burn DoT  5 dmg/turn  [3 turns]

Step again (Turn 2):
🔥 Burn DoT  5 dmg/turn  [3 turns]

```
- **No new row** - same effect updates
- **Duration resets** to max
- **Visual pulse** on refresh

### **B. Stackable Stat Debuff - ADDITIVE Behavior**
```
Initial:  🐌 Slow  Speed -10%  [2 turns]  × 1 STACK

Get hit again with Slow:
🐌 Slow  Speed -10%  [2 turns]  × 2 STACKS


Max stacks (5x):
🐌 Slow  Speed -10%  [2 turns]  × 5 STACKS  [MAX]
```
- **Same row** updates stack count
- **Magnitude adds up** in real-time
- **MAX indicator** when limit reached

### **C. Instant Damage Stacking - INSTANT Behavior**
```
First trap:  💥 Fire Burst  -15 HP  [instant]

Second trap (same turn):
💥 Fire Burst  -15 HP  [instant]  × 2 STACKS
└─ Total: -30 HP

Third trap:
💥 Fire Burst  -15 HP  [instant]  × 3 STACKS
└─ Total: -45 HP
```
- **Stacks infinitely** (no cap)
- **Shows "Total:"** for clarity
- **[instant]** duration tag instead of turns
- **Disappears immediately** after applying damage

---

## **Tile-Specific UI Mockups**

### **Continuous Trap (Purple Skull - Permanent)**
**On Map:**
```
   ┌─────┐
   │  💀  │  [∞]  ← No duration pulse
   └─────┘
```
**In Effects Panel:**
```
💀 Poison
└─ 8 dmg/turn  [∞ permanent]  ← No turn countdown
   └─ Refreshed: 1s ago        ← Still shows refresh
```

### **Momentary Trap (Purple Pulsing - Temporary)**
**On Map:**
```
   ┌─────┐
   │  💀  │  [2 turns]  ← Yellow pulse, shrinking
   └─────┘
```
**In Effects Panel:**
```
💀 Poison
└─ 8 dmg/turn  [2 turns]  ← Counts down each turn
   └─ Refreshed: 1s ago    ← Refresh possible before expiry
```

### **Momentary Drop (Green +, Pulsing)**
**On Map:**
```
   ┌─────┐
   │  💚  │  [1 turn]  ← Pulsing green
   └─────┘
```
**In Effects Panel:**
```
💚 Health drop (collected)
└─ +30 HP  [instant]  ← Moves to "Recent Effects" history
   └─ Tile destroyed
```

---

## **Stacking Conflict Resolution UI**

When you **cannot stack** an effect (e.g., re-applying DoT):

```
Warning Toast:
"You step on a Burning Ground trap, but Burn is already active."
"Duration refreshed to 3 turns."
[OK]
```

When you **hit max stacks** (e.g., 5x Slow):

```
Warning Toast:
"Slow is at maximum stacks (5)."
"Duration refreshed but no additional effect."
[OK]
```

---

## **Status Effect History (Optional)**
For instant/stacking effects, show a **collapsible "Recent" section**:
```
Recent Effects (last turn):
├─ 💥 Fire Burst  -15 HP  × 2
├─ 💥 Ice Burst   -10 HP  × 1
└─ 🌿 Regrowth    +20 HP  × 1
```

---

## **Visual Design Specifications**

### **Color Coding**
- **Red border:** Damage effects (burn, poison, instant)
- **Blue border:** Debuff effects (slow, freeze)
- **Green border:** Buff effects (heal, speed boost)
- **Purple border:** Mixed effects (damage + debuff)

### **Animation Triggers**
- **Refresh:** Icon **pulses blue** when duration resets
- **Stack added:** Number **slides up +1** with "pop" effect
- **MAX reached:** Stack counter **glows orange**
- **Tick down:** Duration number **counts like a timer**

### **Compact Mode (for mobile/small screens)**
```
🔥 Burn  5  [3]
🐌 Slow  10%  ×3  [2]
💀 Poison  8  [4]
```

Where:
- `5` = magnitude
- `[3]` = duration
- `×3` = stacks (if stackable)

---

## **Tooltip Details (On Hover)**

```
💀 Poison
━━━━━━━━━━━━━━━━━━━━━━━
Type: Damage Over Time
Category: Cannot stack
Stacking: Duration refresh only
Magnitude: 8 damage per turn
Duration: 4 turns remaining
Applied by: Gomu Gomu no Mi
Applied at: Position 3D
Total damage: 32 (if full duration)
```

---

## **Stacking Summary Table**

| Effect | Stacks? | Max | UI Shows | Refresh Behavior |
|--------|---------|-----|----------|------------------|
| Burn DoT | No | 1 | Single row, "Refreshed" timestamp | Duration resets |
| Poison DoT | No | 1 | Single row, "Refreshed" timestamp | Duration resets |
| Slow (stat) | Yes | 5 | Stack counter, "Total:" line | Adds stack, resets duration |
| Freeze (instant) | Yes | ∞ | Stack counter, "Total:" line | Each is separate instance |
| Stamina Drain | No | 1 | Single row, "Refreshed" timestamp | Duration resets |

This UI ensures players instantly understand:
- **What effects are active**
- **Which ones can stack** (and how much)
- **When effects refresh vs add power**
- **Total combined impact** of stacked debuffs