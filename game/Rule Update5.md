## **REVISED BOUNCE SYSTEM WITH CONTINUOUS CHAINS & CORNER EXCEPTIONS**

---

### **1. CORE CHAIN CONTINUATION RULES**

#### **1.1 Multi-Bounce Chain Continuity**
- **Single-Type Continuity**: A bounce chain can continue through **multiple sequential bounces** without breaking if:
  - **Diagonal chain** continues with **new diagonal bounce**
  - **Cardinal chain** continues with **new cardinal bounce**
- **Directional Lock Update**: Each new bounce **updates the allowed directions** to follow the newest wall's rules
- **Bonus Progression**: The chain's move counter **continues incrementing** through all bounces and movements

#### **1.2 Chain Type Transition Rules**
- **Diagonal → Cardinal**: **BREAKS CHAIN** (except on corner tiles)
- **Cardinal → Diagonal**: **BREAKS CHAIN** (except on corner tiles)
- **Same Type → Same Type**: **CONTINUES CHAIN** (moves count, bonuses scale)

---

### **2. CORNER TILE SPECIAL RULES**

#### **2.1 Corner Tile Definition**
- **Positions**: 1A, 1G, 7A, 7G (board corners)
- **Wall Configuration**: Two perpendicular walls meet

#### **2.2 Type Transition Exception**
On a corner tile **ONLY**, you may:
- Transition from **Diagonal → Cardinal** chain **without breaking**
- Transition from **Cardinal → Diagonal** chain **without breaking**
- **Requirements**:
  1. You must be **physically on the corner square**
  2. You must perform a **valid bounce** off one of the corner walls
  3. The chain continues with **updated directional lock** from the new bounce

#### **2.3 Example: Corner Transition**
```
Position 1A (top-left corner), facing SE
1. Diagonal bounce off North wall → Exit SE (Move 1: -10%, +10%)
2. Move SE → SE → (Chain builds...)
3. Reach East wall at position 1G (corner)
4. Bounce off East wall → Choose Cardinal bounce South
5. Chain CONTINUES (corner exception!) → Now locked to South only
6. Move South (chain continues from previous move count)
```

---

### **3. MULTI-BOUNCE CHAIN EXAMPLES**

#### **3.1 Pure Diagonal Chain**
```
Start: 5D, facing NE
1. Bounce off South wall → Exit NE (Move 1: -10%, +10%)
   Lock: NE or NW (away from South wall)
2. Move NE (Move 2: -15%, +12.5%)
3. Hit East wall → Valid diagonal entry from SW
   Bounce off East wall → Exit NW (Move 3: -20%, +15%)
   Lock UPDATES: NW or SW (away from East wall) ← Chain continues!
4. Move NW (Move 4: -25%, +17.5%)
5. Attack: +17.5% hit bonus
```

#### **3.2 Pure Cardinal Chain**
```
Start: 4D, facing North
1. Bounce off South wall → Exit North (Move 1: -10%, +10%)
   Lock: North only
2. Move North (Move 2: -15%, +12.5%)
3. Hit North wall → Bounce off North wall → Exit South (Move 3: -20%, +15%)
   Lock UPDATES: South only ← Chain continues!
4. Move South (Move 4: -25%, +17.5%)
5. Attack: +17.5% hit bonus
```

#### **3.3 Chain Break Examples**
```
Diagonal → Cardinal (NON-CORNER):
1. Diagonal bounce → Exit NE (chain starts)
2. Move NE (chain continues)
3. Hit East wall → Attempt Cardinal bounce North
   RESULT: CHAIN BREAKS (invalid type transition)

Cardinal → Diagonal (NON-CORNER):
1. Cardinal bounce → Exit North (chain starts)
2. Move North (chain continues)
3. Hit wall → Attempt Diagonal bounce NE
   RESULT: CHAIN BREAKS (invalid type transition)
```

---

### **4. RULE CLARIFICATIONS & EDGE CASES**

#### **4.1 Bounce Entry Validation**
- Each bounce must be **individually valid** (correct entry angle for that wall)
- **Invalid bounce attempt** = Chain breaks immediately
- **Example**: Hitting wall at wrong angle for bounce → Chain breaks, you stop at wall

#### **4.2 Move Counter Clarification**
- **Bounce exit** counts as Move 1 (or next move number)
- **Movement between bounces** counts as moves
- **Reaching cap**: 5 total moves (any mix of bounces/movements) = cap at -30%/+20%

#### **4.3 Bonus Retention on Chain Break**
- **Stamina discounts**: All moves executed **keep** their earned discounts
- **Hit/Dodge bonus**: **Lost entirely** if chain breaks before terminal action
- **Terminal action**: Must be **immediately** after active chain to receive bonus

#### **4.4 Wall Interaction While Maintaining Chain**
- **Must bounce**: If you hit a wall while chain is active, you **must attempt valid bounce**
- **Cannot "stop" at wall**: Either bounce (continues chain) or fail (breaks chain)
- **No "wall slide"**: Cannot move parallel to wall without bouncing if you contact it

---

### **5. STRATEGIC IMPLICATIONS**

#### **5.1 Optimal Pathing**
- **Diagonal chains**: More flexible (2 allowed directions after each bounce)
- **Cardinal chains**: Predictable but can "ping-pong" between parallel walls
- **Corner mastery**: Advanced players use corners to switch chain types strategically

#### **5.2 Rapid Cap Achievement**
Fastest paths to +20% cap:
- **3-wall diagonal chain**: Bounce→Move→Bounce→Move→Bounce→Attack
- **2-wall cardinal chain**: Bounce→Bounce→Move→Move→Attack
- **Corner combo**: Diagonal→corner transition→Cardinal→Attack

#### **5.3 Defensive Applications**
- **Diagonal chains**: Better for evasion (2 escape directions)
- **Cardinal chains**: Better for positioning (straight line control)
- **Corner defense**: Risky (trapped) but enables type transitions

---

### **6. LOGIC GAPS & CLARIFICATIONS NEEDED**

#### **6.1 Potential Issues Identified:**
1. **Chain Type Ambiguity After Multiple Bounces**
   - If chain has mixed history (corner transition), what type is it currently?
   - **Rule**: Current type = last bounce's type. Determines allowed next moves.

2. **Corner Tile "Double Bounce" Possibility**
   - On corner, could bounce off one wall, immediately bounce off perpendicular wall
   - **Rule**: Each bounce is separate move. Chain continues if both valid.

3. **Chain Continuation After Failed Bounce Attempt**
   - If bounce fails (wrong angle), does chain break or can you move away?
   - **Rule**: Failed bounce attempt = immediate chain break. No recovery.

4. **Minimum Movement Between Bounces**
   - Can you bounce, rotate 45°, immediately bounce again?
   - **Rule**: Rotation allowed, doesn't break chain, but doesn't count as move. Must still meet new wall's entry requirements.

5. **Wall Damage During Bounce Chain**
   - If wall breaks during bounce (from attack), what happens?
   - **Rule**: If wall destroyed during chain, future bounces impossible at that location. Chain continues if path clear.

#### **6.2 Missing Rule Clarifications:**
- **Simultaneous multiple walls**: What if you're at intersection of 3 walls?
- **Sea tile adjacency**: If wall adjacent to sea tile, bounce pushes toward sea?
- **Player-created walls**: Same rules apply? (Likely yes)
- **Wall tier differences**: Do fragile/standard/reinforced walls affect bounce? (Likely no)

---

### **7. FINAL RULE SUMMARY**

1. **Chains continue** through multiple same-type bounces
2. **Type transitions break chains** except on corner tiles
3. **Each bounce updates** allowed movement directions
4. **Move counter accumulates** through entire chain (bounces + movements)
5. **Bonuses scale** to cap at 5+ moves (-30% stamina, +20% hit/dodge)
6. **Chain breaks** on: wrong direction, failed bounce, type transition (non-corner)
7. **Corner tiles allow** diagonal↔cardinal transitions without breaking

**The system now supports complex "bounce dancing" where skilled players can chain multiple wall bounces together for escalating bonuses, with corners providing strategic transition points.**