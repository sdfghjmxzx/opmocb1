## **REVISED BOUNCE SYSTEM WITH SCALING**

### **Core Architecture Change**

Bounce bonuses now **scale progressively** from the exit tile onward, following the same formula for both Cardinal and Diagonal bounces. The exit tile counts as **Move 1** in the chain.

---

## **1. CARDINAL BOUNCE SCALING & CONTINUATION**

### **Directional Rule**
- **Exit Direction**: Must match the **cardinal direction** you entered the wall from (North, South, East, West)
- **Continuation**: **Every subsequent move** must be the **exact same cardinal direction** as the exit
- **Chain Break**: Moving in any other direction (including diagonals) terminates the bounce state

**Example**: Bounce off a **South wall** → Enter moving **North** → Exit to **North** → Chain requires **all future moves to be North**. Moving NE, NW, or any other direction breaks the chain.

---

## **2. DIAGONAL BOUNCE SCALING & CONTINUATION**

### **Directional Rule** (Unchanged)
- **Exit Direction**: Must be a **permissible deflection** (90° or 270° from entry)
- **Continuation**: Must continue moving **diagonally away from the wall** in either valid diagonal direction for that wall orientation
- **Chain Break**: Moving cardinally or diagonally **toward** the wall breaks the chain

**Example (Horizontal Wall South)**: Exit **NE** or **NW** → Continue with **NE** or **NW** only. Moving SE, SW, or any cardinal direction breaks the chain.

---

## **3. BONUS SCALING TABLE**

| Move # | Stamina Discount | Hit Chance Bonus (Attack) | Dodge Chance Bonus (Defense) |
|--------|------------------|---------------------------|------------------------------|
| 1 (Exit Tile) | **-10%** | **+10%** | **+10%** |
| 2 | **-15%** | **+12.5%** | **+12.5%** |
| 3 | **-20%** | **+15%** | **+15%** |
| 4 | **-25%** | **+17.5%** | **+17.5%** |
| 5+ (Cap) |  **-30%**  |  **+20%**  |  **+20%**  |

---

## **4. CHAIN BREAK CONSEQUENCES**

### **Stamina Discounts**
- **Retained**: All moves already executed in the chain **keep their earned discounts**
- **Lost**: Future moves after the break **no longer receive discounts**

### **Hit/Dodge Bonus**
- **Retained**: Only if your **terminal attack/defense is the immediate next action** after a **valid chain of any length**
- **Lost**: If you break the chain **before** executing your terminal action, you **forfeit the hit/dodge bonus**

**Example**: Exit (Move 1, -10%/+10%) → Move 2 (-15%/+12.5%) → **Break with cardinal move** → Attack: You keep the discounts on Moves 1-2, but **attack gets no bonus** because chain was broken.

---

## **5. DEFENSE PHASE APPLICATION**

During your **defense phase**, the bounce bonuses convert:

| Bonus Type | Application | Scaling |
|------------|-------------|---------|
| **Stamina Discount** | **All defensive movements** | Same progression (10% → 30%) |
| **Hit Chance → Dodge** | **Adds to dodge chance** | Same values (10% → 20%) |
| **Damage Reduction** | **None** | Not applicable |

**Result**: A defender who chains 5+ bounce moves gains **+20% dodge chance** against the incoming attack and **-30% stamina cost** on all defensive movements.

---

## **6. SPECIAL RULES**

### **Rotations**
- **Cost**: Always eligible for **current chain's stamina discount**
- **Chain Impact**: **Never break** bounce chains (direction-agnostic)
- **Bonus Contribution**: Rotations **do not count** toward the 5-move progression

### **Standing Still**
- **Chain Status**: **Paused, not broken**
- **Stamina Discount**: **Not consumed** (no movement, no cost)
- **Bonus Retention**: Maintains current progression level (e.g., "stuck" at Move 3 bonuses until you move again)

### **Ghost Facing Independence**
- Bounce activation and continuation **do not modify** ghost facing
- Facing Direction chains **operate separately** and can break/be maintained independently

---

## **7. COMPARISON: CARDINAL VS DIAGONAL**

| Feature | Cardinal Bounce | Diagonal Bounce |
|---------|----------------|-----------------|
| **Entry Direction** | Exact opposite wall face | Diagonal angular approach |
| **Exit Direction** | Same as entry (cardinal) | 90°/270° deflection |
| **Continuation** | **Exact same cardinal** | **Away from wall diagonally** |
| **Scaling** | 10% → 30% stamina, 10% → 20% hit/dodge | Identical |
| **Chain Break** | Any non-matching direction | Moving toward wall or cardinally |

---

## **8. EXAMPLE: FULL CHAIN**

**Scenario**: Cardinal bounce off South wall at position 5D

| Move # | Action | Direction | Stamina Cost | Hit Bonus | Chain Active? |
|--------|--------|-----------|--------------|-----------|---------------|
| 1 | Move into wall | North | 15 (full) | — | ✅ |
| 2 | Exit wall | **North** | 13.5 (-10%) | +10% | ✅ |
| 3 | Continue | **North** | 12.75 (-15%) | +12.5% | ✅ |
| 4 | Continue | **North** | 12.0 (-20%) | +15% | ✅ |
| 5 | Continue | **North** | 11.25 (-25%) | +17.5% | ✅ |
| 6 | Continue | **North** | 10.5 (-30%) | +20% ✅ | ✅ |
| 7 | Attack | — | Terminal | **+20%** | ✅ |

If Move 3 had been **NE** instead of **North**: Chain breaks at Move 3. Moves 1-2 keep discounts, but attack receives **no hit bonus**.