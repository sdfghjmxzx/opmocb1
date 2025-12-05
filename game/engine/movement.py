"""Movement module (theme-agnostic).
Phase 1: neighbor generation (Chebyshev-1).
Phase 2: blockers and cost modifiers.
"""
from .grid import in_bounds
from typing import List, Tuple

def get_neighbors(row: int, col: int) -> List[Tuple[int, int]]:
    """Returns all Chebyshev-1 neighbors (8 dirs) within board bounds."""
    nbrs = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr = row + dr
            nc = col + dc
            if in_bounds(nr, nc):
                nbrs.append((nr, nc))
    return nbrs

def neighbors(row: int, col: int):
    """Legacy generator alias for get_neighbors."""
    for nr, nc in get_neighbors(row, col):
        yield (nr, nc)

def is_blocked(from_row: int, from_col: int, to_row: int, to_col: int, opponent, wall_system, tile_system=None) -> bool:
    """Phase 2/4: Check if movement from (from_row, from_col) to (to_row, to_col) is blocked.
    Blockers: opponent position, walls between tiles, unpassable tiles, border edges (handled by in_bounds).
    """
    # Opponent occupies target
    if opponent.row == to_row and opponent.col == to_col:
        return True
    
    # Check if target tile is unpassable
    if tile_system and tile_system.is_tile_blocking_movement(to_row, to_col):
        return True
    
    # Check if wall blocks movement between from and to
    if wall_system and wall_system.is_wall_blocking(from_row, from_col, to_row, to_col):
        return True
    
    return False
