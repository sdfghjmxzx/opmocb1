"""Push & Bounce system with full vector-based bounce detection."""
from typing import List, Tuple, Optional, Dict

class PushBounce:
    def preview(self, *args, **kwargs):
        return {}

def detect_bounce(path_segment: List[Tuple[int, int]], wall_system, tile_system=None) -> Optional[Dict]:
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

    # Rule: No bounce when the wall is an external/border wall that has a Sea Tile directly adjacent on that edge
    # We determine adjacency by checking the specific border edge against tile_system._sea_tiles
    if tile_system is not None:
        for bw in getattr(wall_system, "_border_walls", []):
            if bw.row == wall_row and bw.col == wall_col and bw.orientation == wall_orient:
                sea_adjacent = False
                # Vertical border walls: left (col=-1 → west), right (col=6 → east)
                if bw.orientation == 'v':
                    if bw.col == -1:  # West external wall
                        for st in getattr(tile_system, "_sea_tiles", []):
                            if st.edge == 'west' and st.position == bw.row:
                                sea_adjacent = True
                                break
                    elif bw.col == 6:  # East external wall
                        for st in getattr(tile_system, "_sea_tiles", []):
                            if st.edge == 'east' and st.position == bw.row:
                                sea_adjacent = True
                                break
                # Horizontal border walls: top (row=-1 → north), bottom (row=6 → south)
                elif bw.orientation == 'h':
                    if bw.row == -1:  # North external wall
                        for st in getattr(tile_system, "_sea_tiles", []):
                            if st.edge == 'north' and st.position == bw.col:
                                sea_adjacent = True
                                break
                    elif bw.row == 6:  # South external wall
                        for st in getattr(tile_system, "_sea_tiles", []):
                            if st.edge == 'south' and st.position == bw.col:
                                sea_adjacent = True
                                break
                if sea_adjacent:
                    print(f"DEBUG BOUNCE: Border wall at ({bw.row},{bw.col},{bw.orientation}) has Sea Tile on its edge - bounce disabled")
                    return None

    # Corner detection: tile with multiple adjacent walls (2+ walls adjacent)
    # Check all walls in system to count how many are adjacent to this tile
    # get_visible_walls() returns tuples (row, col, orient), _border_walls are Wall objects
    visible_walls_tuples = wall_system.get_visible_walls()
    all_walls = []
    
    # Convert visible walls tuples to uniform format
    for w in visible_walls_tuples:
        all_walls.append({'row': w[0], 'col': w[1], 'orient': w[2]})
    
    # Convert border walls to uniform format, skipping those whose OWN edge has a Sea Tile
    for w in wall_system._border_walls:
        if tile_system is not None:
            sea_adjacent = False
            # Vertical border walls: left (col=-1 → west), right (col=6 → east)
            if w.orientation == 'v':
                if w.col == -1:
                    for st in getattr(tile_system, "_sea_tiles", []):
                        if st.edge == 'west' and st.position == w.row:
                            sea_adjacent = True
                            break
                elif w.col == 6:
                    for st in getattr(tile_system, "_sea_tiles", []):
                        if st.edge == 'east' and st.position == w.row:
                            sea_adjacent = True
                            break
            # Horizontal border walls: top (row=-1 → north), bottom (row=6 → south)
            elif w.orientation == 'h':
                if w.row == -1:
                    for st in getattr(tile_system, "_sea_tiles", []):
                        if st.edge == 'north' and st.position == w.col:
                            sea_adjacent = True
                            break
                elif w.row == 6:
                    for st in getattr(tile_system, "_sea_tiles", []):
                        if st.edge == 'south' and st.position == w.col:
                            sea_adjacent = True
                            break
            if sea_adjacent:
                # Do not count this wall for corner classification
                continue
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
    # Enforce approach-side validity based on the specific wall-adjacent tile side
    # For vertical walls: left tile ((wr,wc)) blocks East; right tile ((wr,wc+1)) blocks West
    # For horizontal walls: top tile ((wr,wc)) blocks South; bottom tile ((wr+1,wc)) blocks North
    valid_approach = True
    if wall_orient == 'h':
        if wall_tile[0] == wall_row:
            # Top tile relative to horizontal wall → boundary at row=wall_row; behind if entry_row > wall_row
            valid_approach = (entry_tile[0] <= wall_row)
            print(f"DEBUG BOUNCE: Approach side (h/top): entry_row={entry_tile[0]}, wall_row={wall_row}, valid={valid_approach}")
        elif wall_tile[0] == wall_row + 1:
            # Bottom tile relative to horizontal wall → boundary at row=wall_row; behind if entry_row < wall_row+1
            valid_approach = (entry_tile[0] >= wall_row + 1)
            print(f"DEBUG BOUNCE: Approach side (h/bottom): entry_row={entry_tile[0]}, wall_row={wall_row}, valid={valid_approach}")
        else:
            # Not an adjacent tile to this wall segment
            valid_approach = False
            print(f"DEBUG BOUNCE: Approach side (h): wall_tile_row={wall_tile[0]} not adjacent to wall_row={wall_row}")
    elif wall_orient == 'v':
        if wall_tile[1] == wall_col:
            # Left tile relative to vertical wall → boundary at col=wall_col; behind if entry_col > wall_col
            valid_approach = (entry_tile[1] <= wall_col)
            print(f"DEBUG BOUNCE: Approach side (v/left): entry_col={entry_tile[1]}, wall_col={wall_col}, valid={valid_approach}")
        elif wall_tile[1] == wall_col + 1:
            # Right tile relative to vertical wall → boundary at col=wall_col; behind if entry_col < wall_col+1
            valid_approach = (entry_tile[1] >= wall_col + 1)
            print(f"DEBUG BOUNCE: Approach side (v/right): entry_col={entry_tile[1]}, wall_col={wall_col}, valid={valid_approach}")
        else:
            # Not an adjacent tile to this wall segment
            valid_approach = False
            print(f"DEBUG BOUNCE: Approach side (v): wall_tile_col={wall_tile[1]} not adjacent to wall_col={wall_col}")

    if not valid_approach:
        print("DEBUG BOUNCE: Invalid approach side for non-corner; bounce not allowed")
        return None
    
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
