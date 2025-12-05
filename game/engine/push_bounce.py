"""Push & Bounce system with full vector-based bounce detection."""
from typing import List, Tuple, Optional, Dict

class PushBounce:
    def preview(self, *args, **kwargs):
        return {}

def detect_bounce(path_segment: List[Tuple[int, int]], wall_system) -> Optional[Dict]:
    """Detect bounce pattern in last 3 tiles (entry → wall → exit).
    Returns bounce info dict if valid bounce detected, else None.
    
    Per ULTRA-COMPREHENSIVE BATTLE SYSTEM Section 4:
    - Entry tile → Wall tile → Exit tile in three consecutive actions
    - Only entry and exit direction vectors determine validity
    - Cardinal bounce: linear rebound (same direction in/out)
    - Diagonal bounce: angular deflection (90° or 270° rotation)
    - Corner exception: relaxed entry constraints
    - Silent failure: invalid bounce = standard movement, no penalty
    """
    if len(path_segment) < 3:
        return None
    
    entry_tile = path_segment[0]
    wall_tile = path_segment[1]
    exit_tile = path_segment[2]
    
    print(f"DEBUG BOUNCE: Entry={entry_tile}, Wall={wall_tile}, Exit={exit_tile}")
    
    # Calculate entry and exit vectors
    entry_vec = (wall_tile[0] - entry_tile[0], wall_tile[1] - entry_tile[1])
    exit_vec = (exit_tile[0] - wall_tile[0], exit_tile[1] - wall_tile[1])
    
    print(f"DEBUG BOUNCE: Entry vector={entry_vec}, Exit vector={exit_vec}")
    
    # Check if wall_tile has a wall (must pass through a wall tile)
    # Wall system stores walls as (row, col, orientation)
    # We need to check if there's a wall AT this tile or blocking entry/exit
    wall_at_tile = wall_system.get_wall_at_tile(wall_tile[0], wall_tile[1])
    print(f"DEBUG BOUNCE: Wall at tile {wall_tile}: {wall_at_tile}")
    
    if not wall_at_tile:
        print(f"DEBUG BOUNCE: No wall found at tile, checking all walls...")
        all_walls = wall_system.get_visible_walls()
        print(f"DEBUG BOUNCE: All walls in system: {all_walls}")
        return None
    
    wall_row, wall_col, wall_orient = wall_at_tile
    
    print(f"DEBUG BOUNCE: Wall orientation={wall_orient}")
    
    # Corner detection: tile with multiple adjacent walls (2+ walls adjacent)
    # Check all walls in system to count how many are adjacent to this tile
    # get_visible_walls() returns tuples (row, col, orient), _border_walls are Wall objects
    visible_walls_tuples = wall_system.get_visible_walls()
    all_walls = []
    
    # Convert visible walls tuples to uniform format
    for w in visible_walls_tuples:
        all_walls.append({'row': w[0], 'col': w[1], 'orient': w[2]})
    
    # Convert border walls to uniform format
    for w in wall_system._border_walls:
        all_walls.append({'row': w.row, 'col': w.col, 'orient': w.orientation})
    
    adjacent_wall_count = 0
    for w in all_walls:
        w_row, w_col, w_orient = w['row'], w['col'], w['orient']
        # Check if wall is adjacent to wall_tile
        if w_orient == 'h':
            # Horizontal wall at (r,c) is adjacent to tiles (r,c) and (r+1,c)
            if (w_row == wall_tile[0] or w_row == wall_tile[0] - 1) and w_col == wall_tile[1]:
                adjacent_wall_count += 1
        elif w_orient == 'v':
            # Vertical wall at (r,c) is adjacent to tiles (r,c) and (r,c+1)
            if w_row == wall_tile[0] and (w_col == wall_tile[1] or w_col == wall_tile[1] - 1):
                adjacent_wall_count += 1
    
    is_corner = adjacent_wall_count >= 2
    print(f"DEBUG BOUNCE: Adjacent wall count: {adjacent_wall_count}, Is corner tile: {is_corner}")
    
    # Per Section 4.4: Corner Exception - entry direction unconstrained, exit determines type
    if is_corner:
        print(f"DEBUG BOUNCE: Corner tile - exit determines bounce type")
        # Check if exit is cardinal (one component zero) or diagonal (both non-zero)
        is_cardinal_exit = (exit_vec[0] == 0 or exit_vec[1] == 0)
        is_diagonal_exit = (exit_vec[0] != 0 and exit_vec[1] != 0)
        
        if is_cardinal_exit:
            print(f"DEBUG BOUNCE: Corner cardinal bounce - exit is cardinal direction")
            return {'type': 'cardinal', 'discount': 0.3, 'hit_bonus': 0.2}
        elif is_diagonal_exit:
            print(f"DEBUG BOUNCE: Corner diagonal bounce - exit is diagonal direction")
            return {'type': 'diagonal', 'discount': 0.3, 'hit_bonus': 0.2}
    
    # Non-corner tiles: Check standard bounce rules
    
    # Check cardinal bounce (linear rebound)
    # Rule: Exit back to the same tile you entered from
    # Wall must block the direction you're moving (not parallel to it)
    if exit_tile == entry_tile:
        print(f"DEBUG BOUNCE: Exit tile equals entry tile - checking cardinal bounce")
        
        # Check if wall orientation matches movement direction
        # Vector format: (row_delta, col_delta)
        # Vertical movement (N/S): row changes, col stays → (±1, 0)
        # Horizontal movement (E/W): row stays, col changes → (0, ±1)
        is_horizontal_entry = (entry_vec[0] == 0 and entry_vec[1] != 0)  # Moving East/West
        is_vertical_entry = (entry_vec[0] != 0 and entry_vec[1] == 0)    # Moving North/South
        
        if is_horizontal_entry and wall_orient == 'v':
            # Horizontal movement (E/W) requires vertical wall to bounce
            print(f"DEBUG BOUNCE: Cardinal bounce VALID - horizontal entry off vertical wall")
            return {'type': 'cardinal', 'discount': 0.3, 'hit_bonus': 0.2}
        elif is_vertical_entry and wall_orient == 'h':
            # Vertical movement (N/S) requires horizontal wall to bounce
            print(f"DEBUG BOUNCE: Cardinal bounce VALID - vertical entry off horizontal wall")
            return {'type': 'cardinal', 'discount': 0.3, 'hit_bonus': 0.2}
        else:
            print(f"DEBUG BOUNCE: Cardinal bounce INVALID - wall orientation doesn't match entry direction")
    
    # Check diagonal bounce (angular deflection)
    # Exit must be 90° or 270° rotation of entry vector
    # Per Section 4.3: Must enter from valid diagonal direction
    # Per Section 4.4 Corner Exception: On corners, exit determines type (cardinal or diagonal)
    
    # Rotation formulas:
    # 90° clockwise: (x, y) → (y, -x)
    # 270° clockwise (or 90° counter): (x, y) → (-y, x)
    
    def rotate_90_cw(vec):
        return (vec[1], -vec[0])
    
    def rotate_270_cw(vec):
        return (-vec[1], vec[0])
    
    # Check if entry is diagonal (both components non-zero)
    is_diagonal_entry = (entry_vec[0] != 0 and entry_vec[1] != 0)
    is_diagonal_exit = (exit_vec[0] != 0 and exit_vec[1] != 0)
    
    print(f"DEBUG BOUNCE: Entry diagonal: {is_diagonal_entry}, Exit diagonal: {is_diagonal_exit}")
    
    # For diagonal bounce, entry MUST be diagonal (not cardinal skimming)
    if not is_diagonal_entry:
        print(f"DEBUG BOUNCE: Skipping diagonal check - entry is not diagonal (skimming detected)")
    else:
        valid_exits = [rotate_90_cw(entry_vec), rotate_270_cw(entry_vec)]
        print(f"DEBUG BOUNCE: Checking diagonal bounce - valid exits: {valid_exits}")
        
        if exit_vec in valid_exits:
            print(f"DEBUG BOUNCE: Diagonal bounce detected! Exit vector matches rotation.")
            return {'type': 'diagonal', 'discount': 0.3, 'hit_bonus': 0.2}
    
    print(f"DEBUG BOUNCE: No valid bounce pattern detected")
    # No valid bounce pattern detected
    return None

def apply_bounce_discount(cost: int) -> int:
    """Apply 30% bounce discount to movement cost."""
    return int(cost * 0.7)
