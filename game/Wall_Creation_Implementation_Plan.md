# Wall Creation and Reinforcement System - Implementation Plan

## Overview
Implement comprehensive wall creation and reinforcement mechanics with DF stamina costs, range restrictions, phase limits, and full integration with combat systems.

---

## Phase 1: Core Data Structures & Wall System Updates

### 1.1 JSON Configuration (✅ COMPLETE)
- [x] Update `devil_fruits.json` with new wall creation structure
- [x] Remove old tier-based system
- [x] Add configurable costs and labels

**Structure:**
```json
"map_abilities": {
  "wall_creation": {
    "enabled": true,
    "range": 5,
    "creation_cost_per_hp": 1.0,
    "reinforce_cost_per_hp": 1.0,
    "hp_per_click": 10,
    "label": "Wall"
  }
}
```

### 1.2 Controller State Variables (✅ COMPLETE)
- [x] Add wall mode tracking
- [x] Add first tile selection state
- [x] Add reinforcement selection state
- [x] Add operation counters
- [x] Add player wall tracking

**Added Variables:**
- `self.wall_mode` - None/"conjure"/"reinforce"
- `self.wall_first_tile` - (row, col) for placement
- `self.wall_selected_for_reinforce` - (row, col, orientation)
- `self.wall_reinforce_count` - Cumulative reinforcements
- `self.wall_operations_this_phase` - Defense phase limit tracking
- `self.player_created_walls` - List of owned walls

### 1.3 Wall System Enhancements (`walls.py`) (✅ COMPLETE)
**Tasks:**
- [x] Add `creator` field to Wall class (player ID)
- [x] Add `reinforce(hp_amount)` method to Wall
- [x] Add `get_wall_hp(row, col, orientation)` method
- [x] Add `is_player_wall(row, col, orientation, player_id)` method
- [x] Add validation for duplicate wall placement
- [x] Add `has_wall_at(row, col, orientation)` method
- [x] Add `add_player_wall(...)` method for creating player walls
- [x] Add `reinforce_wall(...)` method for reinforcing walls

---

## Phase 2: Controller Methods - Wall Operations (✅ COMPLETE)

### 2.1 Mode Control Methods
**Tasks:**
- [ ] `enter_wall_conjure_mode()` - Switch to conjure, show placement tiles
- [ ] `enter_wall_reinforce_mode()` - Show wall list or enable map clicks
- [ ] `exit_wall_mode()` - Clear state, restore normal highlights

### 2.2 Wall Placement Logic
**Tasks:**
- [ ] `select_wall_tile(row, col)` - Handle 1st and 2nd tile selection
  - First click: Store `wall_first_tile`
  - Second click: Validate adjacency, calculate orientation, create wall
- [ ] `can_place_wall(row, col, orientation)` - Check for duplicates
- [ ] `create_wall_between_tiles(tile1, tile2)` - Create wall, deduct stamina
  - Calculate orientation (same row = vertical, same col = horizontal)
  - Validate range from player position
  - Check DF stamina availability
  - Add to `wall_system` and `player_created_walls`
  - Add to `planned_actions` as ("wall_create", (row, col, orientation, cost))

### 2.3 Wall Reinforcement Logic
**Tasks:**
- [ ] `select_wall_for_reinforce(row, col, orientation)` - Click on wall or list
- [ ] `reinforce_selected_wall()` - Add HP, increment counter
  - Check if already has reinforce action in planned_actions
  - If yes: Update existing action (add cost, increment HP)
  - If no: Create new action ("wall_reinforce", (row, col, orientation, count, cost))
  - Increment `wall_reinforce_count`
- [ ] `get_player_walls_in_range()` - Return walls player can reinforce

### 2.4 Limit Checking
**Tasks:**
- [ ] `check_wall_operation_limit()` - Enforce 3-operation limit in defense
  - Count wall_create actions
  - Count wall_reinforce actions  
  - Show notification if limit reached
- [ ] `can_perform_wall_operation()` - Pre-validation before allowing action

---

## Phase 3: Undo System Integration (✅ COMPLETE)

### 3.1 Undo Wall Creation (✅ COMPLETE)
**Tasks:**
- [x] Detect `("wall_create", ...)` in undo
- [x] Remove wall from `wall_system`
- [x] Remove from `player_created_walls`
- [x] Refund DF stamina
- [x] Decrement `wall_operations_this_phase`
- [x] Recalculate blocked tiles if in defense phase

### 3.2 Undo Wall Reinforcement (✅ COMPLETE)
**Tasks:**
- [x] Detect `("wall_reinforce", ...)` in undo
- [x] Decrement `wall_reinforce_count` by 1
- [x] Reduce wall HP by `hp_per_click`
- [x] Refund DF stamina for 1 reinforcement
- [x] If count reaches 0, remove entire action from planned_actions
- [x] Update planned action display

### 3.3 Cancel Planning (✅ COMPLETE)
**Tasks:**
- [x] Remove all created walls from this planning session
- [x] Refund all DF stamina
- [x] Clear wall mode state
- [x] Reset operation counters

---

## Phase 4: Planned Actions Display (✅ COMPLETE)

### 4.1 Wall Creation Display (✅ COMPLETE)
**Format:** `"  Wall (3C-3D) (100 DF St)"`
- [x] Add wall creation to `get_planned_actions_display()`
- [x] Show tiles between which wall is placed
- [x] Show total DF stamina cost
- [x] Color by chain (if part of chain)

### 4.2 Wall Reinforcement Display (✅ COMPLETE)
**Format:** `"  Wall Reinforce x3 (150 DF St)"`
- [x] Show reinforcement count (number of clicks)
- [x] Show cumulative DF stamina cost
- [x] Use label from JSON
- [x] Update display on each reinforcement click

---

## Phase 5: UI Implementation (screens.rpy) (✅ COMPLETE)

### 5.1 Walls Tab - Button Logic (✅ COMPLETE)
**Tasks:**
- [x] Check if player has wall creation ability
- [x] Show "Conjure" button if no player walls exist
- [x] Show "Conjure" and "Reinforce" if player has walls
- [x] Hide both if attack/defense action is selected
- [x] Disable if not in planning mode

### 5.2 Conjure Mode UI (✅ COMPLETE)
**Tasks:**
- [x] On "Conjure" click: Call `enter_wall_conjure_mode()`
- [x] Highlight tiles in placement range (Phase 6 - map integration)
- [x] Show first selected tile with distinct color (Phase 6)
- [x] Show second tile preview on hover (Phase 6)
- [x] On second click: Create wall, exit mode

### 5.3 Reinforce Mode UI - List (✅ COMPLETE)
**Tasks:**
- [x] On "Reinforce" click without wall selected: Show wall list
- [x] Display all player walls in range
- [x] Format: `"Wall at 3C-3D (HP: 150/150)"`
- [x] On wall click: Enter reinforce mode for that wall

### 5.4 Reinforce Mode UI - Direct Click (✅ COMPLETE)
**Tasks:**
- [x] Make walls clickable on map grid (Phase 6 - map integration)
- [x] On wall click: Auto-switch to Walls tab (Phase 6)
- [x] Enter reinforce mode for clicked wall
- [x] Show single "Reinforce" button
- [x] Each click adds HP, updates planned action display

### 5.5 Wall Highlighting (✅ COMPLETE)
**Tasks:**
- [x] Add `wall_placement_tiles` highlight color (cyan/blue)
- [x] Add `wall_selected_tile` highlight for first tile (green)
- [x] Add `reinforceable_walls` visual indicator (yellow border on wall images)

---

## Phase 6: Combat Integration (✅ COMPLETE)

### 6.1 Attack Pattern Recalculation (✅ COMPLETE)
**Tasks:**
- [x] After wall creation in defense: Recalculate attacker's blocked tiles
- [x] After wall reinforcement in defense: Recalculate (HP might affect breakthrough)
- [x] Update `attack_highlighted_squares`
- [x] Update `breakthrough_squares`

### 6.2 Wall Behavior (✅ COMPLETE)
**Tasks:**
- [x] Ensure created walls block movement (already implemented via wall_system)
- [x] Ensure created walls block attacks (already implemented via is_blocked())
- [x] Ensure created walls show HP on map (already implemented via wall rendering)

### 6.3 Chain Integration (✅ COMPLETE)
**Tasks:**
- [x] Wall operations don't break chains (implemented - not in chain system)
- [x] Wall operations colored by current chain (implemented - generic_color)
- [x] Wall operations receive NO bonuses (implemented - like rotations)
- [x] Verify chain color in planned actions display (verified in Phase 4)

---

## Phase 7: Range and Validation (✅ COMPLETE)

### 7.1 Range Checking (✅ COMPLETE)
**Tasks:**
- [x] Wall placement: Check distance from player to wall midpoint (lines 1512-1517)
- [x] Wall reinforcement: Check distance from player to wall (lines 1620-1624)
- [x] Use `wall_creation.range` from JSON (lines 1510, 1617)
- [x] Show notification if out of range (implemented)

### 7.2 Overlap Prevention (✅ COMPLETE)
**Tasks:**
- [x] Check if wall already exists at (row, col, orientation) (line 1561)
- [x] Prevent placement if duplicate detected (lines 1561-1563)
- [x] Show clear error message (line 1562)

### 7.3 Ownership Validation (✅ COMPLETE)
**Tasks:**
- [x] Can only reinforce player-created walls (line 1611)
- [x] Cannot reinforce enemy walls (implemented via is_player_wall)
- [x] Cannot reinforce game-generated walls (implemented via creator check)
- [x] Show notification if trying to reinforce non-owned wall (line 1612)

---

## Phase 8: Defense Phase Limit (✅ COMPLETE)

### 8.1 Operation Counting (✅ COMPLETE)
**Tasks:**
- [x] Increment `wall_operations_this_phase` on creation (lines 1592-1593)
- [x] Increment on FIRST reinforcement of a wall (lines 1691-1693)
- [x] Reset counter at phase end (line 2341)

### 8.2 Limit Enforcement (✅ COMPLETE)
**Tasks:**
- [x] Check count before allowing conjure (line 1565)
- [x] Check count before allowing first reinforce of new wall (lines 1688-1693)
- [x] Show notification: "Wall limit reached in defensive phase (3 max)" (lines 1734, 1690)
- [x] Allow unlimited operations in attack phase (implemented via phase check)

---

## Phase 9: Testing and Polish

### 9.1 Core Functionality Tests
- [ ] Create wall horizontally (same row)
- [ ] Create wall vertically (same column)
- [ ] Reinforce wall multiple times (cumulative display)
- [ ] Undo wall creation
- [ ] Undo wall reinforcement (one at a time)
- [ ] Verify DF stamina deduction/refund

### 9.2 Limit Tests
- [ ] Defense phase: Create 3 walls, verify block on 4th
- [ ] Defense phase: Create 2 walls, reinforce 1x, verify block
- [ ] Attack phase: Create 5+ walls, verify no limit

### 9.3 Integration Tests
- [ ] Wall blocks movement
- [ ] Wall blocks attack patterns
- [ ] Wall creation recalculates blocked tiles
- [ ] Chain color preserved in planned actions
- [ ] No bonuses applied to wall operations

### 9.4 Edge Cases
- [ ] Try to create wall out of range
- [ ] Try to reinforce enemy wall
- [ ] Try to create overlapping wall
- [ ] Try to place wall diagonally (should fail)
- [ ] Verify walls persist after turn end

---

## Implementation Order

1. **Phase 1** (Data) - Immediate
2. **Phase 2** (Controller Methods) - Core logic
3. **Phase 3** (Undo) - Critical for usability
4. **Phase 4** (Display) - User feedback
5. **Phase 5** (UI) - User interaction
6. **Phase 6** (Combat) - Integration
7. **Phase 7** (Validation) - Safety
8. **Phase 8** (Limits) - Balance
9. **Phase 9** (Testing) - Quality assurance

---

## Key Files Modified

- `controller.py` - 300+ lines (methods, state, undo)
- `screens.rpy` - 150+ lines (UI, buttons, highlights)
- `walls.py` - 50+ lines (reinforcement, ownership)
- `devil_fruits.json` - Already updated

---

## Notes

- Wall operations treated like rotations: no bonuses, preserve chains
- Defense limit applies to OPERATIONS (creation or first reinforce), not clicks
- Each reinforcement click on SAME wall = same action (cumulative cost)
- Walls created during defense trigger immediate recalculation
- Player walls tracked separately for ownership validation
