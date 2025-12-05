"""Wall system - Phase 4: HP tiers, placement, breakthrough."""

from typing import List, Tuple, Optional, Dict
import random

class Wall:
    """Represents a wall segment."""
    def __init__(self, row: int, col: int, orientation: str, tier: str, hp: int):
        self.row = row
        self.col = col
        self.orientation = orientation  # 'h' (horizontal) or 'v' (vertical)
        self.tier = tier  # 'border', 'fragile', 'standard', 'reinforced'
        self.max_hp = hp
        self.hp = hp
    
    def take_damage(self, damage: int) -> bool:
        """Apply damage to wall. Returns True if wall is destroyed."""
        if self.tier == 'border':
            return False  # Indestructible
        self.hp -= damage
        return self.hp <= 0

class WallSystem:
    """Manages wall placement, HP, and breakthrough per spec sections 11, 24.2."""
    
    def __init__(self):
        self._walls: List[Wall] = []
        self._border_walls: List[Wall] = []
        self._initialize_border_walls()
    
    def _initialize_border_walls(self) -> None:
        """Create indestructible border walls at map edges."""
        # Border walls are conceptual; not rendered but block movement
        # Per spec 1.2: Border Walls are permanent invisible walls at map edges
        # Create horizontal walls at top (row -1) and bottom (row 6) edges
        # Create vertical walls at left (col -1) and right (col 6) edges
        
        # Top edge: horizontal walls from col 0 to col 6
        for col in range(7):
            wall = Wall(-1, col, 'h', 'border', float('inf'))
            self._border_walls.append(wall)
        
        # Bottom edge: horizontal walls from col 0 to col 6
        for col in range(7):
            wall = Wall(6, col, 'h', 'border', float('inf'))
            self._border_walls.append(wall)
        
        # Left edge: vertical walls from row 0 to row 6
        for row in range(7):
            wall = Wall(row, -1, 'v', 'border', float('inf'))
            self._border_walls.append(wall)
        
        # Right edge: vertical walls from row 0 to row 6
        for row in range(7):
            wall = Wall(row, 6, 'v', 'border', float('inf'))
            self._border_walls.append(wall)
    
    def add_wall(self, row: int, col: int, orientation: str, tier: str, base_hp: int, avg_primary_sum: float) -> None:
        """Add internal wall with dynamic HP per spec 24.2."""
        # Dynamic HP: Base_HP × (1 + AvgPrimarySum / 400)
        hp = int(base_hp * (1 + avg_primary_sum / 400))
        wall = Wall(row, col, orientation, tier, hp)
        self._walls.append(wall)
    
    def spawn_initial_walls(self, avg_primary_sum: float, count: int = 4) -> None:
        """Spawn 3-5 random internal walls per spec 1.2."""
        # Random count between 3 and 5 (guaranteed spawn for testing)
        wall_count = random.randint(3, 5)
        tiers = ['fragile', 'standard', 'reinforced']
        base_hps = {'fragile': 100, 'standard': 150, 'reinforced': 200}
        
        placed = 0
        attempts = 0
        while placed < wall_count and attempts < 50:
            row = random.randint(0, 5)  # 0-5 to ensure wall fits (wall between row and row+1)
            col = random.randint(0, 5)  # 0-5 to ensure wall fits (wall between col and col+1)
            orientation = random.choice(['h', 'v'])
            tier = random.choice(tiers)
            
            # Avoid spawning on player starting positions
            if (row, col) == (5, 3) or (row, col) == (1, 3):
                attempts += 1
                continue
            
            # Add wall (no duplicate check for simplicity)
            self.add_wall(row, col, orientation, tier, base_hps[tier], avg_primary_sum)
            placed += 1
            attempts += 1
    
    def get_visible_walls(self) -> List[Tuple[int, int, str]]:
        """Return list of (row, col, orientation) for rendering."""
        return [(w.row, w.col, w.orientation) for w in self._walls]
    
    def get_wall_at(self, row: int, col: int, orientation: str) -> Optional[Wall]:
        """Get wall at specific position and orientation."""
        for wall in self._walls:
            if wall.row == row and wall.col == col and wall.orientation == orientation:
                return wall
        return None
    
    def get_wall_at_tile(self, row: int, col: int) -> Optional[Tuple[int, int, str]]:
        """Get any wall at or adjacent to this tile for bounce detection.
        Returns (row, col, orientation) tuple if wall found, else None.
        
        For bounce mechanics, we check if the tile has a wall:
        - Horizontal wall at (row, col) or (row-1, col)
        - Vertical wall at (row, col) or (row, col-1)
        """
        # Check internal walls AND border walls
        all_walls = self._walls + self._border_walls
        
        for wall in all_walls:
            if wall.orientation == 'h':
                if (wall.row == row and wall.col == col) or (wall.row == row - 1 and wall.col == col):
                    return (wall.row, wall.col, wall.orientation)
            elif wall.orientation == 'v':
                if (wall.row == row and wall.col == col) or (wall.row == row and wall.col == col - 1):
                    return (wall.row, wall.col, wall.orientation)
        return None
    
    def damage_wall(self, row: int, col: int, orientation: str, damage: int) -> bool:
        """Apply damage to wall. Returns True if wall was destroyed."""
        wall = self.get_wall_at(row, col, orientation)
        if wall and wall.take_damage(damage):
            self._walls.remove(wall)
            return True
        return False
    
    def is_wall_blocking(self, from_row: int, from_col: int, to_row: int, to_col: int) -> bool:
        """Check if wall blocks movement from (from_row, from_col) to (to_row, to_col).
        
        Wall rules:
        - Walls exist BETWEEN two orthogonally adjacent squares
        - Horizontal wall (h) at (row, col): blocks vertical movement between (row,col) and (row+1,col)
        - Vertical wall (v) at (row, col): blocks horizontal movement between (row,col) and (row,col+1)
        - Diagonal movements are NOT blocked by walls (per spec 1.2)
        """
        row_diff = to_row - from_row
        col_diff = to_col - from_col
        
        # Diagonal movements are never blocked by walls
        if abs(row_diff) == 1 and abs(col_diff) == 1:
            return False
        
        # Check internal walls AND border walls
        all_walls = self._walls + self._border_walls
        
        # Check for walls that would block this orthogonal movement
        for wall in all_walls:
            if wall.orientation == 'h':
                # Horizontal wall blocks ONLY pure vertical movement between the two specific squares
                # Wall at (row, col, 'h') blocks between (row,col) and (row+1,col)
                if col_diff == 0 and abs(row_diff) == 1:
                    # Moving down: from (row, col) to (row+1, col)
                    if row_diff == 1 and wall.row == from_row and wall.col == from_col:
                        return True
                    # Moving up: from (row+1, col) to (row, col)
                    if row_diff == -1 and wall.row == to_row and wall.col == to_col:
                        return True
                            
            elif wall.orientation == 'v':
                # Vertical wall blocks ONLY pure horizontal movement between the two specific squares
                # Wall at (row, col, 'v') blocks between (row,col) and (row,col+1)
                if row_diff == 0 and abs(col_diff) == 1:
                    # Moving right: from (row, col) to (row, col+1)
                    if col_diff == 1 and wall.col == from_col and wall.row == from_row:
                        return True
                    # Moving left: from (row, col+1) to (row, col)
                    if col_diff == -1 and wall.col == to_col and wall.row == to_row:
                        return True
        
        return False
