# Controller (UI Adapter) – Phase 1 Vertical Slice
# Theme-agnostic core orchestrated via adapter; no UI animation state in core Player.

from typing import List, Tuple, Optional, Dict, Any
from engine.movement import get_neighbors, is_blocked
from engine.push_bounce import detect_bounce, apply_bounce_discount
from engine.combat import calculate_hit_chance, calculate_damage, get_attack_quality, get_push_distance, calculate_defense_stamina_cost
from engine.devil_fruit import calculate_type_advantage
from engine.haki import calculate_haki_effectiveness, calculate_haki_cost, set_config
from engine.walls import WallSystem
from engine.tiles import TileSystem
from engine.pattern import PatternEvaluator
import json, os, math

class PlanningTerminalError(Exception):
    pass

class Player:
    """Core Player model (no UI state)."""
    def __init__(self, name: str, row: int, col: int, facing: int):
        self.name = name
        self.row = row
        self.col = col
        self.facing = facing  # degrees 0–359
        # Core pools (Phase 3: stub base stats for testing)
        self.health = 100
        self.stamina = 100
        # Phase 3: Base stats (0-100)
        self.strength = 50
        self.defense = 50
        self.speed = 50
        self.reaction = 50
        self.endurance = 50
        self.willpower = 50
        self.combat_instinct = 50
        self.aura = 50
        # Haki stats
        self.haki_armament = 0
        self.haki_observation = 0
        self.haki_conqueror = 0
        # Devil Fruit
        self.devil_fruit_type: Optional[str] = None
        self.devil_fruit_mastery = 0
        self.devil_fruit_type_advantages: Optional[Dict[str, Any]] = None

    def get_position_str(self) -> str:
        return f"{self.row+1}{chr(65+self.col)}"

class UIPlayerState:
    """Controller-owned UI animation state (kept out of core Player)."""
    def __init__(self):
        self.animating = False
        self.rotating = False
        self.hopping = False
        self.attacking = False
        # Hop defaults for get_player_zoom()
        self.hop_base_zoom = 0.09
        self.hop_start_time = 0.0
        self.hop_duration = 0.5
        self.hop_count = 0
        # Rotation helpers
        self.rotation_start_time = 0.0
        self.rotation_old_facing = None
        self.target_facing = None

class CombatGame:
    """
    Controller exposing fields/methods used by the single battle_screen.
    Implements:
    - Ghost planning, path, facing
    - Terminal state enforcement
    - Wheel drag hooks controlling ghost
    - Cost preview endpoints
    - Minimal phase alternation
    - Phase 4: Walls & Tiles integration
    """

    def __init__(self):
        # Starting positions per spec (zero-index): P1 6D → (5,3), facing 270; P2 2D → (1,3), facing 90
        self.player1 = Player("Player 1", 5, 3, 270)
        self.player2 = Player("Player 2", 1, 3, 90)
        self.ui_p1 = UIPlayerState()
        self.ui_p2 = UIPlayerState()
        self.attacker_is_p1 = True

        self.phase: str = "attack"  # 'attack' | 'defense'
        self.game_active: bool = True
        self.winner: Optional[str] = None

        # Planning state
        self.planning_mode: bool = False
        self.movement_mode: bool = False
        self.planning_terminal: bool = False
        self.ghost_row: Optional[int] = None
        self.ghost_col: Optional[int] = None
        self.ghost_facing: Optional[float] = None
        self.highlighted_squares: List[Tuple[int, int]] = []
        self.attack_highlighted_squares: List[Tuple[int, int]] = []
        self.current_path: List[Tuple[int, int]] = []
        self.planned_actions: List[Tuple[str, object]] = []
        self.battle_log: List[str] = []

        # Phase 2: Facing direction chain tracking
        self.facing_chain_length: int = 0
        self.facing_chain_direction: Optional[Tuple[int, int]] = None
        self.bounce_active: bool = False
        self.bounce_discount: float = 0.0
        self.bounce_type: Optional[str] = None
        self.bounce_hit_bonus: float = 0.0
        self.bounce_start_move_idx: Optional[int] = None
        self.bounce_direction: Optional[Tuple[int, int]] = None
        self.bounce_end_move_idx: Optional[int] = None
        # Track facing at each move to detect chain breaks
        self.move_facing_history: List[float] = []  # Facing direction at each move

        # Phase 5: Pattern detection
        self.pattern_evaluator = PatternEvaluator()
        self.pattern_active_bonus: Optional[Dict[str, Any]] = None
        self.pattern_memory: Optional[Dict[str, Any]] = None
        self.pattern_applied_this_phase: bool = False
        self.devils_type_adv: Dict[str, Any] = {}
        self.active_effects: Dict[str, List[str]] = {self.player1.name: [], self.player2.name: []}
        # Haki activation flags for current action
        self.attacker_obs_active = False
        self.attacker_arm_active = False
        self.defender_obs_active = False
        self.defender_arm_active = False

        # Phase 4: Walls & Tiles
        avg_primary_sum = (self.player1.strength + self.player1.defense + 
                          self.player2.strength + self.player2.defense) / 2.0
        self.avg_primary_sum = avg_primary_sum
        self.wall_system = WallSystem()
        self.wall_system.spawn_initial_walls(avg_primary_sum)
        self.tile_system = TileSystem()
        self.tile_system.spawn_initial_tiles(avg_primary_sum)
        # Phase 6: JSON Validation Layer
        self.validator = ValidationLayer()
        try:
            data_dir = os.path.join(os.path.dirname(__file__), 'data')
            status_path = os.path.join(data_dir, 'status_effects.json')
            self.validator.load_status_effects_from_file(status_path)
            devils_path = os.path.join(data_dir, 'devil_fruits.json')
            self.validator.validate_devils_file(devils_path)
            # Optional pattern config
            movement_bonuses_path = os.path.join(data_dir, 'movement_bonuses.json')
            if os.path.exists(movement_bonuses_path):
                with open(movement_bonuses_path, 'r', encoding='utf-8') as f:
                    mb_cfg = json.load(f)
                if isinstance(mb_cfg, dict):
                    self.pattern_evaluator.set_config(mb_cfg)
            # Optional haki config
            haki_cfg_path = os.path.join(data_dir, 'haki_config.json')
            if os.path.exists(haki_cfg_path):
                with open(haki_cfg_path, 'r', encoding='utf-8') as hf:
                    hk_cfg = json.load(hf)
                if isinstance(hk_cfg, dict):
                    set_config(hk_cfg)
            # Optional devil fruits type advantages caching (used when player DF types are set)
            if os.path.exists(devils_path):
                with open(devils_path, 'r', encoding='utf-8') as df:
                    devils_data = json.load(df)
                if isinstance(devils_data, dict):
                    ta = devils_data.get('type_advantages')
                    self.devils_type_adv = ta if isinstance(ta, dict) else {}
                else:
                    self.devils_type_adv = {}
            # Optional tile config
            tile_cfg_path = os.path.join(data_dir, 'tile_config.json')
            if os.path.exists(tile_cfg_path):
                with open(tile_cfg_path, 'r', encoding='utf-8') as tf:
                    tile_cfg = json.load(tf)
                if isinstance(tile_cfg, dict):
                    self.tile_system.set_config(tile_cfg)
            # Optional stats config
            stats_cfg_path = os.path.join(data_dir, 'stats_config.json')
            if os.path.exists(stats_cfg_path):
                with open(stats_cfg_path, 'r', encoding='utf-8') as sf:
                    stats = json.load(sf)
                if isinstance(stats, dict):
                    for key, player in (('player1', self.player1), ('player2', self.player2)):
                        cfg = stats.get(key, {})
                        if isinstance(cfg, dict):
                            for field in ('strength','defense','speed','reaction','endurance','willpower','combat_instinct','aura','haki_armament','haki_observation','haki_conqueror','devil_fruit_mastery'):
                                if field in cfg and isinstance(cfg[field], (int, float)):
                                    setattr(player, field, int(cfg[field]))
                            if 'devil_fruit_type' in cfg and isinstance(cfg['devil_fruit_type'], str):
                                player.devil_fruit_type = cfg['devil_fruit_type']
        except Exception:
            # Do not crash if optional JSON missing; only fail if present and invalid
            pass

        # Wheel state
        self.wheel_dragging: bool = False
        self.wheel_rotation: float = 0.0
        self.wheel_drag_initial_mouse_angle: float = 0.0
        self.wheel_drag_start_facing: float = 0.0
        
        # Combat resolution state
        self.pending_attack: Optional[Dict[str, Any]] = None  # Stores attack details until defense phase completes

    # --- Flow helpers ---
    def get_current_player(self) -> Player:
        if self.phase == "attack":
            return self.player1 if self.attacker_is_p1 else self.player2
        # defense phase → current player is defender (opposite of attacker)
        return self.player2 if self.attacker_is_p1 else self.player1

    def get_opponent(self) -> Player:
        cp = self.get_current_player()
        return self.player2 if cp == self.player1 else self.player1

    # --- Planning ---
    def start_movement_planning(self) -> None:
        if self.planning_mode:
            return
        self.planning_mode = True
        self.movement_mode = True
        p = self.get_current_player()
        self.ghost_row, self.ghost_col = p.row, p.col
        self.ghost_facing = p.facing
        self.current_path = [(p.row, p.col)]
        self.planned_actions = []
        self.planning_terminal = False
        self.move_facing_history = []  # Reset facing history
        self.pattern_active_bonus = None
        self.pattern_applied_this_phase = False
        self._recompute_highlights()
        self._update_pattern_bonus()
        self.battle_log.append(f"Start planning: {p.name} at {p.get_position_str()} facing {p.facing}°")

    def _neighbors(self, r: int, c: int) -> List[Tuple[int, int]]:
        nbrs = get_neighbors(r, c)
        # Phase 2/4: Filter out blocked tiles (opponent, walls, unpassable tiles)
        opponent = self.get_opponent()
        valid = []
        for nr, nc in nbrs:
            if not is_blocked(r, c, nr, nc, opponent, self.wall_system, self.tile_system):
                valid.append((nr, nc))
        return valid

    def _recompute_highlights(self) -> None:
        if self.ghost_row is None:
            self.highlighted_squares = []
            self.attack_highlighted_squares = []
            print("DEBUG: Recompute highlights - ghost_row is None")
            return
        # Movement range (yellow)
        self.highlighted_squares = self._neighbors(self.ghost_row, self.ghost_col)
        # Attack preview (red) - ONLY show when attack is selected
        if self._has_attack_selected():
            print("DEBUG: Attack is selected, computing pattern...")
            self.attack_highlighted_squares = self._compute_attack_pattern_preview()
            print(f"DEBUG: attack_highlighted_squares set to {len(self.attack_highlighted_squares)} tiles")
        else:
            print("DEBUG: No attack selected, clearing attack highlights")
            self.attack_highlighted_squares = []

    def _has_attack_selected(self) -> bool:
        """Check if an attack action has been selected in current planning.
        Also returns True for counter defenses which have attack patterns.
        """
        for action in self.planned_actions:
            if action[0] == "attack":
                print(f"DEBUG: Found attack action: {action}")
                return True
            if action[0] == "defense" and action[1] == "counter":
                print(f"DEBUG: Found counter action: {action}")
                return True
        return False

    def _get_selected_attack_type(self) -> Optional[str]:
        """Get the type of attack selected (quick/normal/heavy).
        For counter defenses, returns 'quick' as counter uses quick attack pattern.
        """
        for action in self.planned_actions:
            if action[0] == "attack":
                return action[1]
            if action[0] == "defense" and action[1] == "counter":
                print("DEBUG: Counter detected, returning 'quick' for pattern")
                return "quick"  # Counter uses quick attack pattern (3 tiles)
        return None

    def _compute_attack_pattern_preview(self) -> List[Tuple[int, int]]:
        """Compute attack pattern based on selected attack type and facing.
        Per ULTRA-COMPREHENSIVE BATTLE SYSTEM Section 7:
        - Quick: 3×1 (range 1)
        - Normal: 3×2 (range 2)  
        - Heavy: 3×3 (range 3)
        Cardinal attacks: 3 tiles wide × range tiles deep
        Diagonal attacks: Use tier algorithm
        """
        tiles: List[Tuple[int, int]] = []
        if self.ghost_row is None:
            print("DEBUG: Attack pattern: ghost_row is None")
            return tiles
        
        attack_type = self._get_selected_attack_type()
        if not attack_type:
            print("DEBUG: Attack pattern: no attack type selected")
            return tiles
        
        # Determine range based on attack type
        if attack_type == "quick":
            attack_range = 1
        elif attack_type == "normal":
            attack_range = 2
        elif attack_type == "heavy":
            attack_range = 3
        else:
            print(f"DEBUG: Attack pattern: unknown type {attack_type}")
            return tiles  # Unknown attack type
        
        r = self.ghost_row
        c = self.ghost_col
        ang = int(self.ghost_facing or 0) % 360
        
        # Check if facing is cardinal or diagonal
        is_cardinal = ang in [0, 90, 180, 270]
        
        print(f"DEBUG: Computing {attack_type} pattern at ({r},{c}) facing {ang}° ({'cardinal' if is_cardinal else 'diagonal'})")
        
        if is_cardinal:
            # Cardinal attack: 3 tiles wide × range tiles deep
            tiles = self._compute_cardinal_attack_pattern(r, c, ang, attack_range)
        else:
            # Diagonal attack: Use tier algorithm
            tiles = self._compute_diagonal_attack_pattern(r, c, ang, attack_range)
        
        print(f"DEBUG: Pattern tiles: {len(tiles)} tiles = {tiles}")
        return tiles
    
    def _compute_cardinal_attack_pattern(self, r: int, c: int, ang: int, attack_range: int) -> List[Tuple[int, int]]:
        """Compute cardinal attack pattern (3 wide × range deep rectangle)."""
        tiles = []
        
        if ang == 0:  # East
            # 3 tiles wide (rows), range tiles deep (cols)
            for depth in range(1, attack_range + 1):
                nc = c + depth
                if nc >= 7:
                    break
                for width_offset in [-1, 0, 1]:
                    nr = r + width_offset
                    if 0 <= nr < 7:
                        tiles.append((nr, nc))
        elif ang == 90:  # South
            # 3 tiles wide (cols), range tiles deep (rows)
            for depth in range(1, attack_range + 1):
                nr = r + depth
                if nr >= 7:
                    break
                for width_offset in [-1, 0, 1]:
                    nc = c + width_offset
                    if 0 <= nc < 7:
                        tiles.append((nr, nc))
        elif ang == 180:  # West
            # 3 tiles wide (rows), range tiles deep (cols)
            for depth in range(1, attack_range + 1):
                nc = c - depth
                if nc < 0:
                    break
                for width_offset in [-1, 0, 1]:
                    nr = r + width_offset
                    if 0 <= nr < 7:
                        tiles.append((nr, nc))
        elif ang == 270:  # North
            # 3 tiles wide (cols), range tiles deep (rows)
            for depth in range(1, attack_range + 1):
                nr = r - depth
                if nr < 0:
                    break
                for width_offset in [-1, 0, 1]:
                    nc = c + width_offset
                    if 0 <= nc < 7:
                        tiles.append((nr, nc))
        
        return tiles
    
    def _compute_diagonal_attack_pattern(self, r: int, c: int, ang: int, attack_range: int) -> List[Tuple[int, int]]:
        """Compute diagonal attack pattern using set-based formula.
        Per Section 7.5 (Updated):
        - Player at position P = (pₓ, pᵧ), facing vector F = (fₓ, fᵧ)
        - Quick (3 tiles): All 3 tiles adjacent to player (L-shape in facing direction)
        - Normal (5 tiles): Quick + 2 tiles extending outward
        - Heavy (8 tiles): Normal + 3 tiles extending further
        - Final: Tiles = { (pₓ + x, pᵧ + y) | (x, y) ∈ S(k) }
        
        Coordinate system:
        - fₓ = col direction, fᵧ = row direction
        - East (0°): fₓ=1, fᵧ=0
        - SE (45°): fₓ=1, fᵧ=1
        - South (90°): fₓ=0, fᵧ=1
        - SW (135°): fₓ=-1, fᵧ=1
        - West (180°): fₓ=-1, fᵧ=0
        - NW (225°): fₓ=-1, fᵧ=-1
        - North (270°): fₓ=0, fᵧ=-1
        - NE (315°): fₓ=1, fᵧ=-1
        """
        tiles = []
        
        # Get facing vector (col_delta, row_delta)
        facing_vec = self._facing_to_vector(float(ang))
        if facing_vec == (999, 999):
            return tiles  # Invalid angle
        
        fx, fy = facing_vec  # fx = col direction, fy = row direction
        
        # Define relative coordinate sets based on attack type
        if attack_range == 1:  # Quick (3 tiles) - All adjacent to player
            relative_coords = [
                (fx, 0),       # Horizontally adjacent (col direction)
                (0, fy),       # Vertically adjacent (row direction)
                (fx, fy)       # Diagonally adjacent
            ]
        elif attack_range == 2:  # Normal (5 tiles)
            relative_coords = [
                # S(1) - Quick tiles (all adjacent)
                (fx, 0),
                (0, fy),
                (fx, fy),
                # Additional Normal tiles (extending outward)
                (2*fx, fy),    # Extension along col+diagonal
                (fx, 2*fy)     # Extension along row+diagonal
            ]
        elif attack_range == 3:  # Heavy (8 tiles)
            relative_coords = [
                # S(1) - Quick tiles (all adjacent)
                (fx, 0),
                (0, fy),
                (fx, fy),
                # S(2) - Normal additional tiles
                (2*fx, fy),
                (fx, 2*fy),
                # S(3) - Heavy additional tiles (extending further)
                (2*fx, 0),     # Further col extension
                (0, 2*fy),     # Further row extension
                (2*fx, 2*fy)   # Diagonal extension
            ]
        else:
            return tiles
        
        # Convert relative coordinates to absolute board positions
        for (dx, dy) in relative_coords:
            target_col = c + dx
            target_row = r + dy
            
            # Check if tile is within board boundaries
            if 0 <= target_row < 7 and 0 <= target_col < 7:
                tiles.append((target_row, target_col))
        
        return tiles

    def add_to_path(self, row: int, col: int) -> None:
        if not self.movement_mode or self.planning_terminal:
            raise PlanningTerminalError("Cannot move after selecting attack/defense")
        if self.current_path and (row, col) in self._neighbors(*self.current_path[-1]):
            self.current_path.append((row, col))
            self.ghost_row, self.ghost_col = row, col
            # Record the facing direction at the time of this move
            self.move_facing_history.append(float(self.ghost_facing))
            # Phase 2: Update facing chain after adding move
            self._update_facing_chain()
            action_data = {
                "tile": f"{row+1}{chr(65+col)}"
            }
            self.planned_actions.append(("move", action_data))
            # Phase 2: Detect bounce
            if len(self.current_path) >= 3:
                print(f"DEBUG: Checking bounce for path segment: {self.current_path[-3:]}")
                bounce_result = detect_bounce(self.current_path[-3:], self.wall_system)
                print(f"DEBUG: Bounce detection result: {bounce_result}")
                if bounce_result:
                    self.bounce_active = True
                    self.bounce_discount = float(bounce_result.get('discount', 0.3))
                    self.bounce_type = bounce_result.get('type')
                    self.bounce_hit_bonus = float(bounce_result.get('hit_bonus', 0.0))
                    # Bounce starts at EXIT (third tile): move index = len(path) - 2
                    self.bounce_start_move_idx = len(self.current_path) - 2
                    # Exit direction vector in controller convention (dc, dr)
                    r1, c1 = self.current_path[-2]
                    r2, c2 = self.current_path[-1]
                    self.bounce_direction = (c2 - c1, r2 - r1)
                    self.bounce_end_move_idx = None
                    self.battle_log.append(f"BOUNCE DETECTED: {self.bounce_type}")
                    print(f"DEBUG: Bounce activated! Type: {self.bounce_type}, discount={self.bounce_discount}, hit_bonus={self.bounce_hit_bonus}, start_idx={self.bounce_start_move_idx}, dir={self.bounce_direction}")
            # Bounce continuity check: bonus only applies on moves AFTER exit while direction matches
            if self.bounce_active and self.bounce_direction is not None:
                cur_idx = len(self.current_path) - 1
                if cur_idx > (self.bounce_start_move_idx or -1):
                    r1, c1 = self.current_path[-2]
                    r2, c2 = self.current_path[-1]
                    move_dir = (c2 - c1, r2 - r1)
                    if move_dir != self.bounce_direction:
                        self.bounce_active = False
                        self.bounce_end_move_idx = cur_idx - 1
            self._recompute_highlights()
            old = self.pattern_active_bonus
            self._update_pattern_bonus()
            if self.pattern_active_bonus and old is None and not self.pattern_applied_this_phase:
                self.battle_log.append(f"Pattern active: {self.pattern_active_bonus['name']}")
            self.battle_log.append(f"Move → {action_data['tile']}")

    def remove_last_step(self) -> None:
        if not self.movement_mode or len(self.current_path) <= 1:
            return
        # Remove last tile from path
        self.current_path.pop()
        self.ghost_row, self.ghost_col = self.current_path[-1]
        # Remove last facing from history
        if self.move_facing_history:
            self.move_facing_history.pop()
        # Remove last move action
        for i in range(len(self.planned_actions) - 1, -1, -1):
            if self.planned_actions[i][0] == "move":
                self.planned_actions.pop(i)
                break
        # Recompute facing chain from scratch based on remaining path and current facing
        self._update_facing_chain()
        self._recompute_highlights()

    def _update_facing_chain(self) -> None:
        """Recompute facing direction chain from move history.
        Chain rules:
        - Chain = contiguous movements where EACH move's direction matched the facing AT THE TIME of that move.
        - Rotations NEVER break chains - they only change facing for FUTURE moves.
        - Hard break = move in direction that does NOT match facing at time of move.
        - Chain is count of tail-contiguous moves that each matched their respective facing.
        """
        # Reset
        self.facing_chain_length = 0
        self.facing_chain_direction = None
        if len(self.current_path) <= 1:
            return
        if len(self.move_facing_history) != len(self.current_path) - 1:
            return
        
        # Walk BACKWARDS from the end to find the contiguous chain
        chain_len = 0
        for i in range(len(self.current_path) - 1, 0, -1):
            r1, c1 = self.current_path[i - 1]
            r2, c2 = self.current_path[i]
            move_dir = (c2 - c1, r2 - r1)
            # Get facing at time of this move
            facing_at_move = self.move_facing_history[i - 1]
            facing_vec = self._facing_to_vector(facing_at_move)
            matches = (move_dir == facing_vec)
            if matches:
                chain_len += 1
                self.facing_chain_direction = move_dir
            else:
                # Hard break - stop counting
                break
        
        self.facing_chain_length = chain_len
    def _facing_to_vector(self, facing: float) -> Tuple[int, int]:
        """Convert facing angle (degrees) to movement direction vector.
        Per ULTRA-COMPREHENSIVE Section 1.1 Facing Vectors:
        - North (270°): (0,-1) = col+0, row-1
        - South (90°): (0,1) = col+0, row+1
        - East (0°): (1,0) = col+1, row+0
        - West (180°): (-1,0) = col-1, row+0
        - NE (315°): (1,-1) = col+1, row-1
        - NW (225°): (-1,-1) = col-1, row-1
        - SE (45°): (1,1) = col+1, row+1
        - SW (135°): (-1,1) = col-1, row+1
        
        Returns (col_delta, row_delta) = (Fx, Fy) for diagonal formula.
        """
        ang = int(facing) % 360
        if ang == 0:  # East
            return (1, 0)
        elif ang == 45:  # SE
            return (1, 1)
        elif ang == 90:  # South
            return (0, 1)
        elif ang == 135:  # SW
            return (-1, 1)
        elif ang == 180:  # West
            return (-1, 0)
        elif ang == 225:  # NW
            return (-1, -1)
        elif ang == 270:  # North
            return (0, -1)
        elif ang == 315:  # NE
            return (1, -1)
        else:
            # Non-standard angle, no chain
            return (999, 999)

    def add_rotation(self, degrees: float) -> None:
        if self.planning_terminal:
            raise PlanningTerminalError("Cannot rotate after selecting attack/defense")
        if not self.planning_mode:
            return
        self.ghost_facing = (float(self.ghost_facing or 0) + degrees) % 360
        self.planned_actions.append(("rotate", degrees))
        # Recompute chain with new facing
        self._update_facing_chain()
        self._recompute_highlights()
        self.battle_log.append(f"Rotate {degrees}°")

    def add_attack(self, kind: str) -> None:
        if not self.planning_mode:
            print(f"DEBUG: add_attack({kind}) - not in planning mode")
            return
        # CRITICAL: Check if attack already selected (per Section 7.3)
        if self._has_attack_selected():
            self.battle_log.append(f"Cannot select multiple attacks! Use UNDO to change attack.")
            return
        self.planning_terminal = True
        self.movement_mode = False
        self.planned_actions.append(("attack", kind))
        print(f"DEBUG: Attack {kind} added to planned_actions, terminal={self.planning_terminal}")
        print(f"DEBUG: planned_actions = {self.planned_actions}")
        self._recompute_highlights()
        self.battle_log.append(f"Attack selected: {kind}")

    def add_defense(self, kind: str) -> None:
        if not self.planning_mode:
            return
        self.planning_terminal = True
        self.movement_mode = False
        self.planned_actions.append(("defense", kind))
        self._recompute_highlights()
        self.battle_log.append(f"Defense selected: {kind}")

    def undo_last_planned_action(self) -> None:
        if not self.planned_actions:
            return
        last = self.planned_actions.pop()
        if last[0] in ("attack", "defense"):
            self.planning_terminal = False
            self.movement_mode = True
            self.battle_log.append(f"Undo {last[0]}")
        elif last[0] == "rotate":
            # Revert facing based on rotation amount (buttons & wheel)
            degrees = last[1]
            self.ghost_facing = (float(self.ghost_facing or 0) - float(degrees)) % 360
            self.battle_log.append(f"Undo rotate {degrees}°")
        elif last[0] == "move":
            # Delegate to movement undo to keep path and chain consistent
            self.remove_last_step()
            self.battle_log.append("Undo move")
            return
        # After undoing non-move actions, recompute chain from current path & facing
        self._update_facing_chain()
        self._recompute_highlights()

    def _update_pattern_bonus(self) -> None:
        """Detect pattern from current path and set active bonus (once per planning phase)."""
        opp = self.get_opponent()
        facing = self.ghost_facing if self.ghost_facing is not None else self.get_current_player().facing
        result = self.pattern_evaluator.evaluate(self.current_path, facing, (opp.row, opp.col))
        self.pattern_active_bonus = result

    def confirm_turn(self) -> None:
        if not self.planning_mode:
            return
        p = self.get_current_player()
        
        # Deduct stamina cost FIRST
        stamina_cost = self.total_cost
        if p.stamina < stamina_cost:
            self.battle_log.append(f"Insufficient stamina! Need {stamina_cost}, have {p.stamina}")
            return
        p.stamina -= stamina_cost
        self.battle_log.append(f"Stamina cost: {stamina_cost} → {p.name} stamina={p.stamina}")
        
        # Apply movement and facing
        if self.current_path:
            p.row, p.col = self.current_path[-1]
            p.facing = int(self.ghost_facing or p.facing) % 360
            # Apply tile effects on landing
            effect = self.tile_system.apply_tile_effect(p, p.row, p.col)
            if effect:
                self.battle_log.append(f"Tile effect: {effect}")
        
        if self.phase == "attack":
            # Determine skip/miss
            skip = any(a for a in self.planned_actions if a[0] == "attack" and a[1] == "skip")
            attack_selected = any(a for a in self.planned_actions if a[0] == "attack" and a[1] != "skip")
            miss = False
            if attack_selected:
                attack_tiles = self._compute_attack_pattern_preview()
                d = self.get_opponent()
                miss = (d.row, d.col) not in attack_tiles
            
            if self.pattern_active_bonus and not self.pattern_applied_this_phase:
                self.pattern_memory = self.pattern_active_bonus
                self.pattern_applied_this_phase = True
                self.battle_log.append(f"Pattern locked: {self.pattern_memory['name']}")
            
            # Store attack for resolution, but DON'T execute yet
            if attack_selected and not skip and not miss:
                attack_type = None
                for action in self.planned_actions:
                    if action[0] == "attack" and action[1] != "skip":
                        attack_type = action[1]
                        break
                if attack_type:
                    # Store attack for resolution after defense phase
                    # Also store current attacker/defender positions and facing
                    attacker = self.get_current_player()
                    defender = self.get_opponent()
                    self.pending_attack = {
                        'type': attack_type,
                        'attacker_row': attacker.row,
                        'attacker_col': attacker.col,
                        'attacker_facing': attacker.facing,
                        'defender_row': defender.row,
                        'defender_col': defender.col,
                        'attacker_is_p1': self.attacker_is_p1
                    }
                    self.battle_log.append(f"Attack confirmed: {attack_type} → Awaiting defense phase")
            
            if skip:
                self.battle_log.append("Attacker skip/rest → defense phase skipped")
            elif miss:
                self.battle_log.append("Attack miss → defense phase skipped")
            
            if skip or miss:
                # Defense phase skipped; defender becomes next attacker
                self.phase = "attack"
                self.attacker_is_p1 = not self.attacker_is_p1
            else:
                # Normal flow: proceed to defense with same attacker
                self.phase = "defense"
        else:
            # Defense phase confirmed - NOW execute the combat resolution
            print(f"DEBUG: Defense phase confirmed, pending_attack={getattr(self, 'pending_attack', None)}")
            if hasattr(self, 'pending_attack') and self.pending_attack:
                attack_info = self.pending_attack
                attack_type = attack_info['type']
                print(f"DEBUG: Executing combat with attack_type={attack_type}")
                
                # Get attacker and defender (roles are based on stored attacker_is_p1)
                if attack_info['attacker_is_p1']:
                    attacker = self.player1
                    defender = self.player2
                else:
                    attacker = self.player2
                    defender = self.player1
                
                # Base damage for all attacks
                base_damage = 20
                
                # Get bonuses (these were from attack phase)
                facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
                bounce_bonus = 0.3 if self.bounce_active else 0.0
                pattern_dmg = 0.0
                if self.pattern_memory:
                    pattern_dmg = self.pattern_memory.get('damage_bonus', 0.0)
                
                # DF multipliers
                df_multipliers = None
                if attacker.devil_fruit_type or defender.devil_fruit_type:
                    df_multipliers = calculate_type_advantage(
                        attacker.devil_fruit_type,
                        defender.devil_fruit_type,
                        attacker.devil_fruit_mastery,
                        defender.devil_fruit_mastery,
                        self.devils_type_adv.get(attacker.devil_fruit_type) if attacker.devil_fruit_type else None
                    )
                
                # Haki (use stored flags if available)
                att_obs_active = getattr(self, 'attacker_obs_active', False)
                def_obs_active = getattr(self, 'defender_obs_active', False)
                att_arm_active = getattr(self, 'attacker_arm_active', False)
                def_arm_active = getattr(self, 'defender_arm_active', False)
                haki_obs_eff_attacker = calculate_haki_effectiveness(attacker.haki_observation, defender.haki_observation, att_obs_active and def_obs_active) if att_obs_active else 0.0
                haki_obs_eff_defender = calculate_haki_effectiveness(defender.haki_observation, attacker.haki_observation, att_obs_active and def_obs_active) if def_obs_active else 0.0
                haki_arm_eff_attacker = calculate_haki_effectiveness(attacker.haki_armament, defender.haki_armament, att_arm_active and def_arm_active) if att_arm_active else 0.0
                haki_arm_eff_defender = calculate_haki_effectiveness(defender.haki_armament, attacker.haki_armament, att_arm_active and def_arm_active) if def_arm_active else 0.0
                
                # Calculate damage
                dmg = calculate_damage(
                    attacker, defender, base_damage, attack_type, None,
                    facing_bonus, bounce_bonus, pattern_dmg,
                    df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                    is_defense_phase=False
                )
                dmg = max(1, int(dmg))
                defender.health = max(0, defender.health - dmg)
                self.battle_log.append(f"Combat resolved: {dmg} damage → {defender.name} health={defender.health}")
                print(f"DEBUG: Damage applied: {dmg}, defender health now: {defender.health}")
                
                # Check for KO
                if defender.health == 0:
                    self.game_active = False
                    self.winner = attacker.name
                    self.battle_log.append(f"KO! Winner: {self.winner}")
                else:
                    # Apply push
                    push_dist = get_push_distance(attack_type)
                    print(f"DEBUG: Push distance for {attack_type}: {push_dist}")
                    if push_dist > 0:
                        # Temporarily set attacker_is_p1 for push calculation
                        old_attacker_flag = self.attacker_is_p1
                        self.attacker_is_p1 = attack_info['attacker_is_p1']
                        print(f"DEBUG: Applying push, attacker facing: {attacker.facing}, defender at ({defender.row},{defender.col})")
                        pushed = self.apply_push_to_defender(push_dist)
                        print(f"DEBUG: Pushed {pushed} tiles")
                        self.attacker_is_p1 = old_attacker_flag
                        if pushed > 0:
                            self.battle_log.append(f"Push: {defender.name} pushed {pushed} tile(s)")
                
                # Clear pending attack
                self.pending_attack = None
            else:
                print("DEBUG: No pending attack found in defense phase!")
            
            # Defense resolved; next attacker is prior defender
            self.phase = "attack"
            self.attacker_is_p1 = not self.attacker_is_p1
        
        self.cancel_planning()
        # Per-turn tile maintenance
        self.tile_system.tick_durations()
        if self.phase == 'attack':
            self.tile_system.spawn_per_turn_tiles(self.avg_primary_sum)
        # Status effects maintenance
        self.tick_status_effects()
        self.battle_log.append(f"Turn confirmed → next phase: {self.phase}, attacker_is_p1={self.attacker_is_p1}")

    def cancel_planning(self) -> None:
        self.planning_mode = False
        self.movement_mode = False
        self.planning_terminal = False
        self.current_path = []
        self.highlighted_squares = []
        self.attack_highlighted_squares = []
        self.ghost_row = None
        self.ghost_col = None
        self.ghost_facing = None
        # Reset Haki activation flags
        self.attacker_obs_active = False
        self.attacker_arm_active = False
        self.defender_obs_active = False
        self.defender_arm_active = False
        # Phase 2: Reset chain and bounce
        self.facing_chain_length = 0
        self.facing_chain_direction = None
        self.bounce_active = False
        self.bounce_discount = 0.0
        self.bounce_type = None
        self.bounce_hit_bonus = 0.0
        self.bounce_start_move_idx = None
        self.bounce_direction = None
        self.bounce_end_move_idx = None
        self.battle_log.append("Planning canceled/reset")

    # --- Wheel controller ---
    def get_wheel_rotation(self) -> float:
        return self.wheel_rotation

    def start_wheel_drag(self, initial_mouse_angle: float) -> None:
        self.wheel_dragging = True
        self.wheel_drag_initial_mouse_angle = initial_mouse_angle
        if self.ghost_facing is None:
            self.ghost_facing = self.get_current_player().facing
        self.wheel_drag_start_facing = float(self.ghost_facing)

    def update_wheel_drag(self, new_wheel_angle: float) -> None:
        """Update wheel rotation with 45° snapping."""
        # Snap to nearest 45° increment
        snapped_angle = round(new_wheel_angle / 45) * 45
        self.wheel_rotation = snapped_angle % 360
        self.ghost_facing = snapped_angle % 360
        # DON'T recompute highlights during drag - only update facing
        # This prevents flickering and maintains terminal state
    
    def end_wheel_drag(self) -> None:
        """End wheel drag and record final rotation."""
        if not self.wheel_dragging:
            return
        self.wheel_dragging = False
        # Calculate total rotation delta from start to end
        if self.wheel_drag_start_facing is not None and self.ghost_facing is not None:
            delta = (self.ghost_facing - self.wheel_drag_start_facing + 360) % 360
            if delta > 180:
                delta -= 360
            # Already snapped, just record if changed
            if delta != 0:
                # Record single rotation action for the entire drag
                self.planned_actions.append(("rotate", delta))
                self.battle_log.append(f"Wheel rotation: {delta}°")
        # Update chain and highlights ONCE after drag completes
        self._update_facing_chain()
        self._recompute_highlights()


    def get_movement_cost(self, steps: int) -> int:
        """Return movement cost using Facing Direction chain rules.
        Chain_Bonus is based ONLY on contiguous facing-supported moves at the END of the path.
        Rotations are ignored; non-facing moves are dead actions and do not start chains.
        """
        base = 15 if self.phase == "attack" else 30
        total = base * max(0, steps)
        # Recompute effective chain length from the tail of current_path.
        effective_chain = 0
        if len(self.current_path) > 1 and self.ghost_facing is not None:
            facing_vec = self._facing_to_vector(self.ghost_facing)
            # Walk backwards from last step until a non-facing move is found.
            for i in range(len(self.current_path) - 1, 0, -1):
                r2, c2 = self.current_path[i]
                r1, c1 = self.current_path[i - 1]
                move_dir = (c2 - c1, r2 - r1)
                if move_dir == facing_vec:
                    effective_chain += 1
                else:
                    break
        chain_bonus_rate = min(0.10 * effective_chain, 0.50) if effective_chain > 0 else 0.0
        if chain_bonus_rate > 0.0:
            total = int(total * (1.0 - chain_bonus_rate))
        # Apply bounce discount ONLY to eligible steps starting from exit
        bounce_steps = 0
        if self.bounce_start_move_idx is not None:
            last_idx = self.bounce_end_move_idx if self.bounce_end_move_idx is not None else (len(self.current_path) - 1)
            bounce_steps = max(0, last_idx - self.bounce_start_move_idx + 1)
        if bounce_steps > 0 and self.bounce_discount > 0.0:
            per_step_after_chain = int(base * (1.0 - chain_bonus_rate))
            total -= int(per_step_after_chain * self.bounce_discount) * bounce_steps
        return max(0, total)

    @property
    def total_cost(self) -> int:
        """Calculate total stamina cost including movement, rotations, and actions."""
        # Movement cost
        steps = max(0, len(self.current_path) - 1)
        movement_cost = self.get_movement_cost(steps)
        
        # Rotation cost: 5 stamina per 45° (per user request)
        rotation_cost = 0
        for action in self.planned_actions:
            if action[0] == "rotate":
                degrees = abs(action[1])
                # Each 45° costs 5 stamina
                rotation_cost += int((degrees / 45) * 5)
        
        # Attack cost
        attack_cost = 0
        for action in self.planned_actions:
            if action[0] == "attack" and action[1] != "skip":
                attack_type = action[1]
                # Quick: 10, Normal: 20, Heavy: 30 (per Section 7.1)
                if attack_type == "quick":
                    attack_cost = 10
                elif attack_type == "normal":
                    attack_cost = 20
                elif attack_type == "heavy":
                    attack_cost = 30
                break
        
        # Defense cost (only in defense phase)
        defense_cost = 0
        if self.phase == "defense":
            for action in self.planned_actions:
                if action[0] == "defense":
                    defense_type = action[1]
                    # Per Section 14.1: Tank: 20, Evade: 20, Defend: 30, Counter-Quick: 25, Counter-Normal: 40
                    if defense_type == "tank":
                        defense_cost = 0
                    elif defense_type == "evade":
                        defense_cost = 20
                    elif defense_type == "defend":
                        defense_cost = 30
                    elif defense_type == "counter":
                        defense_cost = 25  # Default to quick counter
                    break
        
        return movement_cost + rotation_cost + attack_cost + defense_cost

    def get_total_planned_cost(self) -> int:
        """Engine-only: total planned cost for current phase."""
        return self.total_cost

    def get_haki_costs(self, target: str = 'attacker') -> Dict[str, int]:
        """Return current Haki activation costs for target ('attacker' or 'defender')."""
        player = self.get_current_player() if target == 'attacker' else self.get_opponent()
        return {
            'observation': calculate_haki_cost('observation', player.haki_observation),
            'armament': calculate_haki_cost('armament', player.haki_armament),
            'conqueror': calculate_haki_cost('conqueror', player.haki_conqueror),
        }

    def get_move_chain_groups(self) -> List[dict]:
        """Group moves by chains and assign colors.
        Returns list of dicts with: {start_idx, end_idx, chain_len, color, action_indices}
        action_indices maps planned_action index to move index for proper coloring.
        Also includes rotations between chain moves.
        """
        if len(self.current_path) <= 1:
            return []
        
        chain_colors = ["#FF4444", "#44FF44", "#4444FF", "#FFFF44", "#FF44FF", "#44FFFF"]
        groups = []
        current_chain_start = None
        color_idx = 0
        
        # Build action_index mapping (which planned_action corresponds to which move)
        action_to_move_map = []  # List of move indices for each action
        move_idx = 0
        for action in self.planned_actions:
            if action[0] == "move":
                action_to_move_map.append(move_idx)
                move_idx += 1
            else:
                action_to_move_map.append(-1)  # Non-move action
        
        # Track which moves are in chains
        for i in range(len(self.current_path) - 1):
            r1, c1 = self.current_path[i]
            r2, c2 = self.current_path[i + 1]
            move_dir = (c2 - c1, r2 - r1)
            if i < len(self.move_facing_history):
                facing_at_move = self.move_facing_history[i]
                facing_vec = self._facing_to_vector(facing_at_move)
                matches = (move_dir == facing_vec)
            else:
                matches = False
            
            if matches:
                if current_chain_start is None:
                    # Start new chain
                    current_chain_start = i
            else:
                # Break chain
                if current_chain_start is not None:
                    # Close previous chain - find ALL actions from start move to end move (inclusive of rotations)
                    action_indices = []
                    start_move = current_chain_start
                    end_move = i - 1
                    
                    # Find first action for start_move
                    first_act = None
                    for act_idx, mv_idx in enumerate(action_to_move_map):
                        if mv_idx == start_move:
                            first_act = act_idx
                            break
                    
                    # Find last action for end_move
                    last_act = None
                    for act_idx in range(len(action_to_move_map) - 1, -1, -1):
                        if action_to_move_map[act_idx] == end_move:
                            last_act = act_idx
                            break
                    
                    # Include all actions between first and last (moves AND rotations)
                    if first_act is not None and last_act is not None:
                        action_indices = list(range(first_act, last_act + 1))
                    
                    groups.append({
                        "start_idx": current_chain_start,
                        "end_idx": i - 1,
                        "chain_len": i - current_chain_start,
                        "color": chain_colors[color_idx % len(chain_colors)],
                        "action_indices": action_indices
                    })
                    color_idx += 1
                    current_chain_start = None
        
        # Close final chain if active
        if current_chain_start is not None:
            action_indices = []
            start_move = current_chain_start
            end_move = len(self.current_path) - 2
            
            # Find first action for start_move
            first_act = None
            for act_idx, mv_idx in enumerate(action_to_move_map):
                if mv_idx == start_move:
                    first_act = act_idx
                    break
            
            # Find last action for end_move
            last_act = None
            for act_idx in range(len(action_to_move_map) - 1, -1, -1):
                if action_to_move_map[act_idx] == end_move:
                    last_act = act_idx
                    break
            
            # Include all actions between first and last
            if first_act is not None and last_act is not None:
                action_indices = list(range(first_act, last_act + 1))
            
            groups.append({
                "start_idx": current_chain_start,
                "end_idx": len(self.current_path) - 2,
                "chain_len": len(self.current_path) - 1 - current_chain_start,
                "color": chain_colors[color_idx % len(chain_colors)],
                "action_indices": action_indices
            })
        
        return groups

    # --- Phase 3: Combat Preview ---
    def preview_attack_outcome(self, attack_type: str) -> Dict[str, Any]:
        """Preview hit chance and damage for selected attack."""
        attacker = self.get_current_player()
        defender = self.get_opponent()
        
        # Base attack stats
        attack_data = {
            "quick": {"base_damage": 10, "base_hit_chance": 0.70},
            "normal": {"base_damage": 20, "base_hit_chance": 0.70},
            "heavy": {"base_damage": 30, "base_hit_chance": 0.70}
        }
        
        if attack_type not in attack_data:
            return {"error": "Invalid attack type"}
        
        base_damage = attack_data[attack_type]["base_damage"]
        
        # Calculate facing bonus from chain
        facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
        
        # Bounce bonus (stubbed for now)
        bounce_bonus = 0.3 if self.bounce_active else 0.0
        
        # Pattern bonus (Phase 5, stubbed as 0.0)
        pattern_bonus = 0.0
        
        # DF type advantage
        df_multipliers = None
        if attacker.devil_fruit_type or defender.devil_fruit_type:
            df_multipliers = calculate_type_advantage(
                attacker.devil_fruit_type,
                defender.devil_fruit_type,
                attacker.devil_fruit_mastery,
                defender.devil_fruit_mastery,
                self.devils_type_adv.get(attacker.devil_fruit_type)
            )
        
        # Haki effectiveness based on activation flags
        att_obs_active = getattr(self, 'attacker_obs_active', False)
        def_obs_active = getattr(self, 'defender_obs_active', False)
        att_arm_active = getattr(self, 'attacker_arm_active', False)
        def_arm_active = getattr(self, 'defender_arm_active', False)
        haki_obs_eff_attacker = calculate_haki_effectiveness(attacker.haki_observation, defender.haki_observation, att_obs_active and def_obs_active) if att_obs_active else 0.0
        haki_obs_eff_defender = calculate_haki_effectiveness(defender.haki_observation, attacker.haki_observation, att_obs_active and def_obs_active) if def_obs_active else 0.0
        haki_arm_eff_attacker = calculate_haki_effectiveness(attacker.haki_armament, defender.haki_armament, att_arm_active and def_arm_active) if att_arm_active else 0.0
        haki_arm_eff_defender = calculate_haki_effectiveness(defender.haki_armament, attacker.haki_armament, att_arm_active and def_arm_active) if def_arm_active else 0.0
        
        pattern_hit = 0.0
        pattern_dmg = 0.0
        if self.pattern_active_bonus and not self.pattern_applied_this_phase:
            pattern_hit = self.pattern_active_bonus.get('hit_bonus', 0.0)
            pattern_dmg = self.pattern_active_bonus.get('damage_bonus', 0.0)
        elif self.pattern_memory:
            # Memory persists across turns until disrupted
            pattern_hit = self.pattern_memory.get('hit_bonus', 0.0)
            pattern_dmg = self.pattern_memory.get('damage_bonus', 0.0)
        
        # Calculate hit chance
        hit_chance = calculate_hit_chance(
            attacker, defender, attack_type, None,  # No defense_type in attack phase
            facing_bonus, bounce_bonus, pattern_hit,
            df_multipliers, haki_obs_eff_attacker, haki_obs_eff_defender,
            is_defense_phase=False
        )
        
        # Calculate damage
        damage = calculate_damage(
            attacker, defender, base_damage, attack_type, None,  # No defense_type in attack phase
            facing_bonus, bounce_bonus, pattern_dmg,
            df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
            is_defense_phase=False
        )
        
        # Attack quality
        quality = get_attack_quality(damage, base_damage)
        push = get_push_distance(quality)
        
        return {
            "attack_type": attack_type,
            "hit_chance": hit_chance,
            "damage": damage,
            "quality": quality,
            "push_distance": push,
            "facing_bonus": facing_bonus,
            "bounce_bonus": bounce_bonus
        }

    def get_visible_tiles(self) -> List[Tuple[int, int, str]]:
        return self.tile_system.get_all_tiles()

    def get_sea_tiles(self) -> List[Tuple[str, int]]:
        return self.tile_system.get_sea_tiles()

    def get_visible_walls(self) -> List[Tuple[int, int, str]]:
        return self.wall_system.get_visible_walls()

    def apply_push_to_defender(self, distance: int) -> int:
        """Attempt to push defender up to 'distance' tiles along attacker facing.
        Returns actual pushed distance. Applies tile effects on landing.
        """
        if distance <= 0:
            return 0
        attacker = self.get_current_player()
        defender = self.get_opponent()
        facing_vec = self._facing_to_vector(attacker.facing)
        pushed = 0
        for _ in range(distance):
            # Sea tile doom check at edge in cardinal facing
            dir_str = None
            if facing_vec == (0, -1):
                dir_str = 'north'
            elif facing_vec == (0, 1):
                dir_str = 'south'
            elif facing_vec == (1, 0):
                dir_str = 'east'
            elif facing_vec == (-1, 0):
                dir_str = 'west'
            if dir_str and self.tile_system.is_sea_tile_at_edge(defender.row, defender.col, dir_str):
                self.game_active = False
                self.winner = attacker.name
                self.battle_log.append(f"Sea doom! {defender.name} at edge → Winner: {self.winner}")
                break
            to_row = defender.row + facing_vec[1]
            to_col = defender.col + facing_vec[0]
            if not (0 <= to_row < 7 and 0 <= to_col < 7):
                break
            if is_blocked(defender.row, defender.col, to_row, to_col, attacker, self.wall_system, self.tile_system):
                break
            defender.row, defender.col = to_row, to_col
            pushed += 1
            # Apply tile effects after each step
            eff = self.tile_system.apply_tile_effect(defender, defender.row, defender.col)
            if eff:
                self.battle_log.append(f"Defender tile effect: {eff}")
        if pushed:
            self.battle_log.append(f"Defender pushed {pushed} tile(s)")
        return pushed

    def execute_attack(self, attack_type: str, force_hit: Optional[bool] = None) -> Dict[str, Any]:
        """Execute attack resolution using preview formulas.
        If force_hit is None, does not apply state changes; returns preview only.
        If force_hit is True, applies damage and push; if False, logs miss.
        """
        if self.phase != 'attack':
            return {"error": "Not in attack phase"}
        # Ensure an attack was selected
        if not any(a for a in self.planned_actions if a[0] == 'attack'):
            return {"error": "No attack selected"}
        # Check defender is within attack tiles
        attack_tiles = self._compute_attack_pattern_preview()
        defender = self.get_opponent()
        if (defender.row, defender.col) not in attack_tiles:
            return {"error": "Defender not in attack tile (miss)"}
        outcome = self.preview_attack_outcome(attack_type)
        if force_hit is None:
            # Return preview only
            return {"preview": outcome}
        if not force_hit:
            self.battle_log.append("Attack resolved: miss")
            return {"result": "miss", **outcome}
        # Apply damage (base 20 for all attacks)
        base_damage = 20
        attacker = self.get_current_player()
        defender = self.get_opponent()
        
        # Get bonuses
        facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
        bounce_bonus = 0.3 if self.bounce_active else 0.0
        pattern_dmg = 0.0
        if self.pattern_active_bonus and not self.pattern_applied_this_phase:
            pattern_dmg = self.pattern_active_bonus.get('damage_bonus', 0.0)
        elif self.pattern_memory:
            pattern_dmg = self.pattern_memory.get('damage_bonus', 0.0)
        
        # DF multipliers
        df_multipliers = None
        if attacker.devil_fruit_type or defender.devil_fruit_type:
            df_multipliers = calculate_type_advantage(
                attacker.devil_fruit_type,
                defender.devil_fruit_type,
                attacker.devil_fruit_mastery,
                defender.devil_fruit_mastery,
                self.devils_type_adv.get(attacker.devil_fruit_type)
            )
        
        # Haki
        att_obs_active = getattr(self, 'attacker_obs_active', False)
        def_obs_active = getattr(self, 'defender_obs_active', False)
        att_arm_active = getattr(self, 'attacker_arm_active', False)
        def_arm_active = getattr(self, 'defender_arm_active', False)
        haki_obs_eff_attacker = calculate_haki_effectiveness(attacker.haki_observation, defender.haki_observation, att_obs_active and def_obs_active) if att_obs_active else 0.0
        haki_obs_eff_defender = calculate_haki_effectiveness(defender.haki_observation, attacker.haki_observation, att_obs_active and def_obs_active) if def_obs_active else 0.0
        haki_arm_eff_attacker = calculate_haki_effectiveness(attacker.haki_armament, defender.haki_armament, att_arm_active and def_arm_active) if att_arm_active else 0.0
        haki_arm_eff_defender = calculate_haki_effectiveness(defender.haki_armament, attacker.haki_armament, att_arm_active and def_arm_active) if def_arm_active else 0.0
        
        # Calculate damage using new signature
        dmg = calculate_damage(
            attacker, defender, base_damage, attack_type, None,
            facing_bonus, bounce_bonus, pattern_dmg,
            df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
            is_defense_phase=False
        )
        dmg = max(1, int(dmg))
        defender.health = max(0, defender.health - dmg)
        self.battle_log.append(f"Attack hit: {dmg} damage → {defender.name} health={defender.health}")
        if defender.health == 0:
            self.game_active = False
            self.winner = self.get_current_player().name
            self.battle_log.append(f"KO! Winner: {self.winner}")
            return {"result": "ko", "winner": self.winner, **outcome}
        # Apply push
        push = int(outcome.get('push_distance', 0))
        pushed = self.apply_push_to_defender(push)
        if pushed > 0 and self.pattern_memory:
            self.clear_pattern_memory()
        return {"result": "hit", "pushed": pushed, **outcome}

    def apply_status_effect(self, effect: str, target: str) -> bool:
        """Apply a validated status effect name to 'attacker' or 'defender'.
        Returns True if applied; logs and stores effect tag only (no stat changes).
        """
        if effect not in getattr(self, 'validator', ValidationLayer()).loaded_effects:
            self.battle_log.append(f"Status effect ignored (unknown): {effect}")
            return False
        player = self.get_current_player() if target == 'attacker' else self.get_opponent()
        self.active_effects[player.name].append(effect)
        self.battle_log.append(f"Status effect applied to {player.name}: {effect}")
        return True

    def get_active_effects(self, player_name: str) -> List[str]:
        return list(self.active_effects.get(player_name, []))

    def get_attack_tiles(self) -> List[Tuple[int, int]]:
        return list(self.attack_highlighted_squares)

    def execute_defense(self, defense_type: str) -> Dict[str, Any]:
        """Resolve defense per Rule Update.md Section 14.1 and 14.4.
        defense_type: 'tank', 'evade', 'defend', 'counter'
        """
        if self.phase != 'defense':
            return {"error": "Not in defense phase"}
        if not any(a for a in self.planned_actions if a[0] == 'defense'):
            return {"error": "No defense selected"}
        
        attacker = self.get_opponent()  # In defense phase, opponent is the attacker
        defender = self.get_current_player()
        
        # Get attack type from attacker's previous actions
        attack_type = "normal"  # default
        for action in self.planned_actions:
            if action[0] == 'attack':
                attack_type = action[1]
                break
        
        # Base damage for all attacks
        base_damage = 20
        
        # Calculate facing bonus from defender's chain
        facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
        bounce_bonus = 0.3 if self.bounce_active else 0.0
        
        # Pattern bonus for defender
        pattern_hit = 0.0
        pattern_dmg = 0.0
        if self.pattern_active_bonus and not self.pattern_applied_this_phase:
            pattern_hit = self.pattern_active_bonus.get('hit_bonus', 0.0)
            pattern_dmg = self.pattern_active_bonus.get('damage_bonus', 0.0)
        elif self.pattern_memory:
            pattern_hit = self.pattern_memory.get('hit_bonus', 0.0)
            pattern_dmg = self.pattern_memory.get('damage_bonus', 0.0)
        
        # DF multipliers
        df_multipliers = None
        if attacker.devil_fruit_type or defender.devil_fruit_type:
            df_multipliers = calculate_type_advantage(
                attacker.devil_fruit_type,
                defender.devil_fruit_type,
                attacker.devil_fruit_mastery,
                defender.devil_fruit_mastery,
                self.devils_type_adv.get(attacker.devil_fruit_type)
            )
        
        # Haki effectiveness
        att_obs_active = getattr(self, 'attacker_obs_active', False)
        def_obs_active = getattr(self, 'defender_obs_active', False)
        att_arm_active = getattr(self, 'attacker_arm_active', False)
        def_arm_active = getattr(self, 'defender_arm_active', False)
        haki_obs_eff_attacker = calculate_haki_effectiveness(attacker.haki_observation, defender.haki_observation, att_obs_active and def_obs_active) if att_obs_active else 0.0
        haki_obs_eff_defender = calculate_haki_effectiveness(defender.haki_observation, attacker.haki_observation, att_obs_active and def_obs_active) if def_obs_active else 0.0
        haki_arm_eff_attacker = calculate_haki_effectiveness(attacker.haki_armament, defender.haki_armament, att_arm_active and def_arm_active) if att_arm_active else 0.0
        haki_arm_eff_defender = calculate_haki_effectiveness(defender.haki_armament, attacker.haki_armament, att_arm_active and def_arm_active) if def_arm_active else 0.0
        
        # Calculate hit chance (defense phase)
        hit_chance = calculate_hit_chance(
            attacker, defender, attack_type, defense_type,
            facing_bonus, bounce_bonus, pattern_hit,
            df_multipliers, haki_obs_eff_attacker, haki_obs_eff_defender,
            is_defense_phase=True
        )
        
        # Calculate stamina cost
        base_cost = self.get_movement_cost(max(0, len(self.current_path) - 1))
        stamina_cost = calculate_defense_stamina_cost(base_cost, hit_chance, def_obs_active)
        
        if defender.stamina < stamina_cost:
            self.battle_log.append(f"Defense failed: insufficient stamina (need {stamina_cost})")
            return {"error": "insufficient stamina", "cost": stamina_cost}
        
        defender.stamina -= stamina_cost
        self.battle_log.append(f"Defense {defense_type}: stamina cost {stamina_cost}")
        
        # Resolve defense type
        result = {"defense": defense_type, "stamina_cost": stamina_cost, "hit_chance": hit_chance}
        
        if defense_type == "tank":
            # Tank: take full damage, gain +30 stamina
            damage = calculate_damage(
                attacker, defender, base_damage, attack_type, None,
                facing_bonus, bounce_bonus, pattern_dmg,
                df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                is_defense_phase=False
            )
            defender.health = max(0, defender.health - damage)
            defender.stamina = min(defender.stamina + 30, 100)
            self.battle_log.append(f"Tank: took {damage} damage, gained 30 stamina")
            result["damage"] = damage
            result["stamina_gain"] = 30
        
        elif defense_type == "evade":
            # Evade: roll dodge, success = 0 damage, fail = apply damage formula
            import random
            dodge_success = random.random() <= (1.0 - hit_chance)
            if dodge_success:
                self.battle_log.append("Evade: dodge successful, 0 damage")
                result["dodged"] = True
                result["damage"] = 0
            else:
                damage = calculate_damage(
                    attacker, defender, base_damage, attack_type, defense_type,
                    facing_bonus, bounce_bonus, pattern_dmg,
                    df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                    is_defense_phase=True
                )
                defender.health = max(0, defender.health - damage)
                self.battle_log.append(f"Evade: dodge failed, took {damage} damage")
                result["dodged"] = False
                result["damage"] = damage
        
        elif defense_type == "defend":
            # Defend: always take reduced damage
            damage = calculate_damage(
                attacker, defender, base_damage, attack_type, defense_type,
                facing_bonus, bounce_bonus, pattern_dmg,
                df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                is_defense_phase=True
            )
            defender.health = max(0, defender.health - damage)
            self.battle_log.append(f"Defend: took {damage} reduced damage")
            result["damage"] = damage
        
        elif defense_type == "counter":
            # Counter: take damage first, then trigger counter-attack if alive
            damage = calculate_damage(
                attacker, defender, base_damage, attack_type, defense_type,
                facing_bonus, bounce_bonus, pattern_dmg,
                df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                is_defense_phase=True
            )
            defender.health = max(0, defender.health - damage)
            self.battle_log.append(f"Counter: took {damage} damage")
            result["damage"] = damage
            
            if defender.health > 0:
                # Trigger counter-attack (base 10 damage)
                counter_damage = calculate_damage(
                    defender, attacker, 10, "normal", "counter",
                    0.0, 0.0, 0.0,
                    None, haki_arm_eff_defender, haki_arm_eff_attacker,
                    is_defense_phase=True
                )
                attacker.health = max(0, attacker.health - counter_damage)
                self.battle_log.append(f"Counter-attack: dealt {counter_damage} damage")
                result["counter_damage"] = counter_damage
        
        # Check KO
        if defender.health == 0:
            self.game_active = False
            self.winner = attacker.name
            self.battle_log.append(f"KO! Winner: {self.winner}")
            result["ko"] = True
            result["winner"] = self.winner
        elif defense_type == "counter" and attacker.health == 0:
            self.game_active = False
            self.winner = defender.name
            self.battle_log.append(f"Counter KO! Winner: {self.winner}")
            result["counter_ko"] = True
            result["winner"] = self.winner
        
        return result

    def activate_haki(self, haki_type: str, target: str) -> Dict[str, Any]:
        """Activate Haki for current action; deduct stamina per cost.
        target: 'attacker' or 'defender'. haki_type: 'observation' or 'armament'.
        """
        if haki_type not in ('observation', 'armament'):
            return {"error": "Invalid haki type"}
        player = self.get_current_player() if target == 'attacker' else self.get_opponent()
        stat = player.haki_observation if haki_type == 'observation' else player.haki_armament
        cost = calculate_haki_cost(haki_type, stat)
        if player.stamina < cost:
            self.battle_log.append(f"Haki activation failed ({haki_type}): insufficient stamina")
            return {"error": "insufficient stamina", "cost": cost}
        player.stamina -= cost
        if target == 'attacker':
            if haki_type == 'observation':
                self.attacker_obs_active = True
            else:
                self.attacker_arm_active = True
        else:
            if haki_type == 'observation':
                self.defender_obs_active = True
            else:
                self.defender_arm_active = True
        self.battle_log.append(f"Haki activated for {player.name}: {haki_type} (cost {cost})")
        return {"ok": True, "cost": cost, "stamina": player.stamina}

    def deactivate_haki(self, haki_type: str, target: str) -> None:
        if target == 'attacker':
            if haki_type == 'observation':
                self.attacker_obs_active = False
            elif haki_type == 'armament':
                self.attacker_arm_active = False
        else:
            if haki_type == 'observation':
                self.defender_obs_active = False
            elif haki_type == 'armament':
                self.defender_arm_active = False
        self.battle_log.append(f"Haki deactivated: {haki_type} for {target}")

    def is_game_over(self) -> bool:
        return not self.game_active

    def get_winner(self) -> Optional[str]:
        return self.winner

    def get_pattern_status(self) -> Dict[str, Any]:
        return {
            "active": self.pattern_active_bonus or None,
            "memory": self.pattern_memory or None,
            "applied_this_phase": self.pattern_applied_this_phase
        }

    def clear_pattern_memory(self) -> None:
        self.pattern_memory = None
        self.battle_log.append("Pattern memory cleared")

    def get_battle_log(self) -> List[str]:
        return list(self.battle_log)

    def get_players_state(self) -> Dict[str, Dict[str, int]]:
        p1 = self.player1
        p2 = self.player2
        return {
            p1.name: {"row": p1.row, "col": p1.col, "facing": p1.facing, "health": p1.health, "stamina": p1.stamina},
            p2.name: {"row": p2.row, "col": p2.col, "facing": p2.facing, "health": p2.health, "stamina": p2.stamina},
        }

    def face_opponent(self) -> None:
        """Snap ghost_facing to the 45° direction toward the opponent (adapter utility)."""
        cp = self.get_current_player()
        base_row, base_col = (self.ghost_row, self.ghost_col) if self.ghost_row is not None else (cp.row, cp.col)
        op = self.get_opponent()
        dx = op.col - base_col
        dy = op.row - base_row
        ang = None
        if dx == 1 and dy == 0:
            ang = 0
        elif dx == 1 and dy == 1:
            ang = 45
        elif dx == 0 and dy == 1:
            ang = 90
        elif dx == -1 and dy == 1:
            ang = 135
        elif dx == -1 and dy == 0:
            ang = 180
        elif dx == -1 and dy == -1:
            ang = 225
        elif dx == 0 and dy == -1:
            ang = 270
        elif dx == 1 and dy == -1:
            ang = 315
        if ang is not None:
            self.ghost_facing = float(ang)
            self._update_facing_chain()
            self._recompute_highlights()
            self.battle_log.append(f"Face opponent → {ang}°")

    def get_cost_breakdown(self) -> Dict[str, Any]:
        steps = max(0, len(self.current_path) - 1)
        base = 15 if self.phase == 'attack' else 30
        facing_vec = self._facing_to_vector(self.ghost_facing) if self.ghost_facing is not None else (999, 999)
        effective_chain = 0
        for i in range(len(self.current_path) - 1, 0, -1):
            r2, c2 = self.current_path[i]
            r1, c1 = self.current_path[i - 1]
            move_dir = (c2 - c1, r2 - r1)
            if move_dir == facing_vec:
                effective_chain += 1
            else:
                break
        chain_bonus = min(0.10 * effective_chain, 0.50) if effective_chain > 0 else 0.0
        subtotal = int(base * steps * (1.0 - chain_bonus))
        total = int(subtotal * (0.7 if self.bounce_active else 1.0))
        return {
            'steps': steps,
            'base_per_step': base,
            'effective_chain': effective_chain,
            'chain_bonus_fraction': chain_bonus,
            'bounce_active': self.bounce_active,
            'subtotal_after_chain': subtotal,
            'total_after_bounce': total,
        }

    def get_board_state(self) -> Dict[str, Any]:
        return {
            'phase': self.phase,
            'attacker_is_p1': self.attacker_is_p1,
            'ghost': {'row': self.ghost_row, 'col': self.ghost_col, 'facing': self.ghost_facing},
            'highlights': list(self.highlighted_squares),
            'attack_tiles': list(self.attack_highlighted_squares),
            'path': list(self.current_path),
            'chain': {'length': self.facing_chain_length, 'direction': self.facing_chain_direction},
            'bounce': {'active': self.bounce_active, 'discount': self.bounce_discount},
        }

    def get_square_size(self) -> int:
        return 80

    def get_board_size(self) -> int:
        return 7

    def reload_configs(self) -> None:
        try:
            data_dir = os.path.join(os.path.dirname(__file__), 'data')
            # Pattern config
            movement_bonuses_path = os.path.join(data_dir, 'movement_bonuses.json')
            if os.path.exists(movement_bonuses_path):
                with open(movement_bonuses_path, 'r', encoding='utf-8') as f:
                    mb_cfg = json.load(f)
                if isinstance(mb_cfg, dict):
                    self.pattern_evaluator.set_config(mb_cfg)
            # Haki config
            haki_cfg_path = os.path.join(data_dir, 'haki_config.json')
            if os.path.exists(haki_cfg_path):
                with open(haki_cfg_path, 'r', encoding='utf-8') as hf:
                    hk_cfg = json.load(hf)
                if isinstance(hk_cfg, dict):
                    set_config(hk_cfg)
            # Devil fruits type advantages
            devils_path = os.path.join(data_dir, 'devil_fruits.json')
            if os.path.exists(devils_path):
                with open(devils_path, 'r', encoding='utf-8') as df:
                    devils_data = json.load(df)
                if isinstance(devils_data, dict):
                    ta = devils_data.get('type_advantages')
                    self.devils_type_adv = ta if isinstance(ta, dict) else {}
                else:
                    self.devils_type_adv = {}
            # Tile config
            tile_cfg_path = os.path.join(data_dir, 'tile_config.json')
            if os.path.exists(tile_cfg_path):
                with open(tile_cfg_path, 'r', encoding='utf-8') as tf:
                    tile_cfg = json.load(tf)
                if isinstance(tile_cfg, dict):
                    self.tile_system.set_config(tile_cfg)
            # Stats config
            stats_cfg_path = os.path.join(data_dir, 'stats_config.json')
            if os.path.exists(stats_cfg_path):
                with open(stats_cfg_path, 'r', encoding='utf-8') as sf:
                    stats = json.load(sf)
                if isinstance(stats, dict):
                    for key, player in (('player1', self.player1), ('player2', self.player2)):
                        cfg = stats.get(key, {})
                        if isinstance(cfg, dict):
                            for field in ('strength','defense','speed','reaction','endurance','willpower','combat_instinct','aura','haki_armament','haki_observation','haki_conqueror','devil_fruit_mastery'):
                                if field in cfg and isinstance(cfg[field], (int, float)):
                                    setattr(player, field, int(cfg[field]))
                            if 'devil_fruit_type' in cfg and isinstance(cfg['devil_fruit_type'], str):
                                player.devil_fruit_type = cfg['devil_fruit_type']
            # Recompute average primary sum
            self.avg_primary_sum = (self.player1.strength + self.player1.defense + self.player2.strength + self.player2.defense) / 2.0
        except Exception:
            pass

    def restart_battle(self) -> None:
        # Reset players
        self.player1.row, self.player1.col, self.player1.facing = 5, 3, 270
        self.player2.row, self.player2.col, self.player2.facing = 1, 3, 90
        self.player1.health = 100; self.player1.stamina = 100
        self.player2.health = 100; self.player2.stamina = 100
        # Reset flow
        self.attacker_is_p1 = True
        self.phase = 'attack'
        self.game_active = True
        self.winner = None
        # Reset planning
        self.planning_mode = False
        self.movement_mode = False
        self.planning_terminal = False
        self.current_path = []
        self.planned_actions = []
        self.highlighted_squares = []
        self.attack_highlighted_squares = []
        self.ghost_row = None
        self.ghost_col = None
        self.ghost_facing = None
        self.facing_chain_length = 0
        self.facing_chain_direction = None
        self.bounce_active = False
        self.bounce_discount = 0.0
        self.pattern_active_bonus = None
        self.pattern_memory = None
        self.pattern_applied_this_phase = False
        self.active_effects[self.player1.name] = []
        self.active_effects[self.player2.name] = []
        # Recreate walls/tiles and apply configs
        self.wall_system = WallSystem()
        self.wall_system.spawn_initial_walls(self.avg_primary_sum)
        self.tile_system = TileSystem()
        self.tile_system.spawn_initial_tiles(self.avg_primary_sum)
        self.reload_configs()
        self.battle_log.clear()
        self.battle_log.append('Battle restarted')

    def set_facing(self, angle: float) -> None:
        if not self.planning_mode:
            return
        self.ghost_facing = float(angle) % 360
        self._update_facing_chain()
        self._recompute_highlights()
        self.battle_log.append(f"Set facing → {int(self.ghost_facing)}°")

    def remove_status_effect(self, effect: str, target: str) -> bool:
        player = self.get_current_player() if target == 'attacker' else self.get_opponent()
        if effect in self.active_effects.get(player.name, []):
            self.active_effects[player.name] = [e for e in self.active_effects[player.name] if e != effect]
            self.battle_log.append(f"Status effect removed from {player.name}: {effect}")
            return True
        return False

    def tick_status_effects(self) -> None:
        """Advance status effects by one tick (no-op without durations)."""
        # Without durations specified, we log the tick only.
        self.battle_log.append("Status effects ticked")

    def get_effects_registry(self) -> List[str]:
        return sorted(list(getattr(self, 'validator', ValidationLayer()).loaded_effects))

    def get_game_over_state(self) -> Optional[Dict[str, Any]]:
        if self.game_active:
            return None
        return {"winner": self.winner}

    def get_ui_payload(self) -> Dict[str, Any]:
        return {
            'players': self.get_players_state(),
            'board': self.get_board_state(),
            'tiles': self.get_visible_tiles(),
            'sea_tiles': self.get_sea_tiles(),
            'walls': self.get_visible_walls(),
            'pattern': self.get_pattern_status(),
            'costs': self.get_cost_breakdown(),
            'haki_costs': {
                'attacker': self.get_haki_costs('attacker'),
                'defender': self.get_haki_costs('defender'),
            },
            'battle_log': self.get_battle_log(),
            'game_over': self.get_game_over_state(),
            'square_size': self.get_square_size(),
            'board_size': self.get_board_size(),
        }

    # --- Animation placeholders (adapter-only) ---
    def check_animation_completion(self) -> None:
        pass

    def start_next_animation(self, player: Player) -> None:
        pass

# ValidationLayer stub (Phase 1)
class ValidationLayer:
    def __init__(self):
        self.loaded_effects = set()

    def load_status_effects(self, effects: dict) -> None:
        self.loaded_effects = set(effects.keys())

    def load_status_effects_from_file(self, path: str) -> None:
        """Load status_effects.json from file path if it exists."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            self.loaded_effects = set(data.keys())
        else:
            self.loaded_effects = set()

    def validate_devils(self, devils: dict) -> None:
        """Validate that all 'effect' strings in devil_fruits.json exist in loaded effects.
        Scans type_advantages (vs/weak_vs) and buffs/map_abilities blocks for 'effect' keys.
        """
        missing: set = set()
        def collect_effects(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == 'effect' and isinstance(v, str):
                        if v not in self.loaded_effects:
                            missing.add(v)
                    else:
                        collect_effects(v)
            elif isinstance(obj, list):
                for item in obj:
                    collect_effects(item)
        collect_effects(devils)
        if missing:
            raise ValueError(f"devil_fruits.json references undefined effects: {sorted(missing)}")

    def validate_devils_file(self, path: str) -> None:
        """Load and validate devils file if it exists. Fails only when file exists and invalid."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)
