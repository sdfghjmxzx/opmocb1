"""Wall system - Phase 4: HP tiers, placement, breakthrough."""

from typing import List, Tuple, Optional, Dict
import random

class Wall:
    """Represents a wall segment."""
    def __init__(self, row: int, col: int, orientation: str, tier: str, hp: int, creator: Optional[str] = None):
        self.row = row
        self.col = col
        self.orientation = orientation  # 'h' (horizontal) or 'v' (vertical)
        self.tier = tier  # 'border', 'fragile', 'standard', 'reinforced'
        self.max_hp = hp
        self.hp = hp
        self.creator = creator  # Player ID who created this wall (None for game-spawned walls)
    
    def take_damage(self, damage: int) -> bool:
        """Apply damage to wall. Returns True if wall is destroyed."""
        if self.tier == 'border':
            return False  # Indestructible
        
        old_hp = self.hp
        self.hp -= damage
        destroyed = self.hp <= 0
        
        print(f"[WALL] Wall at ({self.row},{self.col},{self.orientation}) took {damage} dmg: {old_hp} → {self.hp} (destroyed={destroyed})")
        return destroyed
    
    def reinforce(self, hp_amount: int) -> None:
        """Add HP to wall through reinforcement. Increases max_hp for player walls."""
        old_hp = self.hp
        self.hp += hp_amount
        # For player-created walls, increase max_hp along with current HP
        if self.creator is not None:
            self.max_hp += hp_amount
        # For game-spawned walls, respect max_hp cap
        elif self.max_hp != float('inf'):
            self.hp = min(self.hp, self.max_hp)
        print(f"[WALL] Wall at ({self.row},{self.col},{self.orientation}) reinforced: {old_hp} → {self.hp} (+{hp_amount} HP)")

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
        # Random count between 1 and 3 (guaranteed spawn for testing)
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
    
    def get_all_horizontal_walls(self) -> List[Tuple[int, int, int]]:
        """Get all horizontal walls (internal only, not border walls). Returns list of (row, col, hp) tuples."""
        h_walls = []
        for wall in self._walls:
            if wall.orientation == 'h':
                h_walls.append((wall.row, wall.col, wall.hp))
        return h_walls
    
    def get_all_vertical_walls(self) -> List[Tuple[int, int, int]]:
        """Get all vertical walls (internal only, not border walls). Returns list of (row, col, hp) tuples."""
        v_walls = []
        for wall in self._walls:
            if wall.orientation == 'v':
                v_walls.append((wall.row, wall.col, wall.hp))
        return v_walls
    
    def get_wall(self, row: int, col: int, orientation: str) -> Optional[Wall]:
        """Get wall object at specified position. Alias for get_wall_at for API consistency."""
        return self.get_wall_at(row, col, orientation)
    
    def damage_wall(self, row: int, col: int, orientation: str, damage: int) -> bool:
        """Apply damage to wall. Returns True if wall was destroyed."""
        wall = self.get_wall_at(row, col, orientation)
        if wall and wall.take_damage(damage):
            print(f"[WALL_SYSTEM] Removing destroyed wall at ({row},{col},{orientation}) from list")
            self._walls.remove(wall)
            print(f"[WALL_SYSTEM] Walls remaining: {len(self._walls)}")
            return True
        return False
    
    def get_wall_hp(self, row: int, col: int, orientation: str) -> Optional[int]:
        """Get current HP of wall at specified position. Returns None if no wall exists."""
        wall = self.get_wall_at(row, col, orientation)
        return wall.hp if wall else None
    
    def is_player_wall(self, row: int, col: int, orientation: str, player_id: str) -> bool:
        """Check if wall at position was created by specified player."""
        wall = self.get_wall_at(row, col, orientation)
        return wall is not None and wall.creator == player_id
    
    def has_wall_at(self, row: int, col: int, orientation: str) -> bool:
        """Check if any wall (including border walls) exists at specified position."""
        # Check internal walls
        if self.get_wall_at(row, col, orientation) is not None:
            return True
        # Check border walls
        for border_wall in self._border_walls:
            if (border_wall.row == row and border_wall.col == col and 
                border_wall.orientation == orientation):
                return True
        return False
    
    def add_player_wall(self, row: int, col: int, orientation: str, hp: int, player_id: str) -> bool:
        """Create a player-owned wall with specified HP. Returns False if duplicate exists."""
        # Check for duplicate placement
        if self.has_wall_at(row, col, orientation):
            print(f"[WALL_SYSTEM] Cannot create wall at ({row},{col},{orientation}) - wall already exists")
            return False
        
        # Create player wall with 'player' tier and specified HP
        wall = Wall(row, col, orientation, 'player', hp, creator=player_id)
        self._walls.append(wall)
        print(f"[WALL_SYSTEM] Player {player_id} created wall at ({row},{col},{orientation}) with {hp} HP")
        return True
    
    def reinforce_wall(self, row: int, col: int, orientation: str, hp_amount: int) -> bool:
        """Reinforce existing wall by adding HP. Returns False if wall doesn't exist."""
        wall = self.get_wall_at(row, col, orientation)
        if wall is None:
            print(f"[WALL_SYSTEM] Cannot reinforce - no wall at ({row},{col},{orientation})")
            return False
        
        wall.reinforce(hp_amount)
        return True
    
    def is_wall_blocking(self, from_row: int, from_col: int, to_row: int, to_col: int) -> bool:
        """Check if wall blocks movement from (from_row, from_col) to (to_row, to_col).
        
        Wall rules:
        - Walls exist BETWEEN two orthogonally adjacent squares
        - Horizontal wall (h) at (row, col): blocks vertical movement between (row,col) and (row+1,col)
        - Vertical wall (v) at (row, col): blocks horizontal movement between (row,col) and (row,col+1)
        - Diagonal movements through perpendicular wall corners are blocked (e.g., W+S walls block SW diagonal)
        """
        row_diff = to_row - from_row
        col_diff = to_col - from_col
        
        # Check internal walls AND border walls
        all_walls = self._walls + self._border_walls
        
        # Diagonal movement: check for perpendicular wall corners blocking the path
        if abs(row_diff) == 1 and abs(col_diff) == 1:
            # Moving diagonally; check for L/C-shaped wall configurations
            # Example: SW diagonal from (r,c) to (r+1,c-1)
            #   Blocked if: vertical wall at (r,c-1) AND horizontal wall at (r,c-1)
            #   (West wall + South wall form corner blocking SW)
            
            # Identify which two orthogonal walls would form the blocking corner
            # For each diagonal, there are two possible "intermediate" tiles
            # We check if perpendicular walls meet at either intermediate point
            
            # Intermediate tiles for diagonal (from_row, from_col) -> (to_row, to_col):
            # Option 1: (from_row, to_col) - moved col first
            # Option 2: (to_row, from_col) - moved row first
            
            # Check option 1: horizontal step first, then vertical
            h_step_row = from_row
            h_step_col = to_col
            # Check option 2: vertical step first, then horizontal
            v_step_row = to_row
            v_step_col = from_col
            
            # For a corner to block diagonal, we need TWO perpendicular walls:
            # Example NE diagonal (row-1, col+1): needs North wall (h at row-1) AND East wall (v at col)
            # Example SE diagonal (row+1, col+1): needs South wall (h at row) AND East wall (v at col)
            # Example SW diagonal (row+1, col-1): needs South wall (h at row) AND West wall (v at col-1)
            # Example NW diagonal (row-1, col-1): needs North wall (h at row-1) AND West wall (v at col-1)
            
            blocked_by_corner = False
            
            # Build wall lookup for fast checking
            h_walls = set()
            v_walls = set()
            for wall in all_walls:
                if wall.orientation == 'h':
                    h_walls.add((wall.row, wall.col))
                elif wall.orientation == 'v':
                    v_walls.add((wall.row, wall.col))
            
            # Determine diagonal direction and check for blocking corner
            if row_diff == -1 and col_diff == 1:
                # NE diagonal: from (r,c) to (r-1,c+1)
                # Needs: h-wall at (r-1, c) AND v-wall at (r-1, c)
                if (to_row, from_col) in h_walls and (to_row, from_col) in v_walls:
                    blocked_by_corner = True
            elif row_diff == 1 and col_diff == 1:
                # SE diagonal: from (r,c) to (r+1,c+1)
                # Needs: h-wall at (r, c) AND v-wall at (r, c)
                if (from_row, from_col) in h_walls and (from_row, from_col) in v_walls:
                    blocked_by_corner = True
            elif row_diff == 1 and col_diff == -1:
                # SW diagonal: from (r,c) to (r+1,c-1)
                # Needs: h-wall at (r, c-1) AND v-wall at (r, c-1)
                if (from_row, to_col) in h_walls and (from_row, to_col) in v_walls:
                    blocked_by_corner = True
            elif row_diff == -1 and col_diff == -1:
                # NW diagonal: from (r,c) to (r-1,c-1)
                # Needs: h-wall at (r-1, c-1) AND v-wall at (r-1, c-1)
                if (to_row, to_col) in h_walls and (to_row, to_col) in v_walls:
                    blocked_by_corner = True
            
            return blocked_by_corner
        
        # Orthogonal movement: check for walls blocking the direct path
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
