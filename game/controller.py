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
from engine.effects import EffectsEngine, StatusEffect
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
        self.strength = 100
        self.defense = 100
        self.speed = 100
        self.reaction = 100
        self.endurance = 100
        self.willpower = 100
        self.combat_instinct = 100
        self.aura = 100
        # Haki stats
        self.haki_armament = 100
        self.haki_observation = 100
        self.haki_conqueror = 100
        # Haki Stamina Pool (per spec 2.2: TotalStats × 0.5, max 300)
        self.haki_stamina = self._calculate_max_haki_stamina()
        # Devil Fruit
        self.devil_fruit_type: Optional[str] = None
        self.devil_fruit_mastery = 100
        self.devil_fruit_type_advantages: Optional[Dict[str, Any]] = None
        self.devil_fruit_data: Optional[Dict[str, Any]] = None  # Full fruit data from JSON
        # Devil Fruit Stamina Pool (per spec 2.2: (mastery × 2.0) + (mastery × (aura / 150) × 0.5))
        self.devil_fruit_stamina = self._calculate_max_df_stamina()
    
    def _calculate_max_haki_stamina(self) -> float:
        """Calculate max Haki stamina per spec 2.2: (STR+DEF+SPD+REA+END+WIL) × 0.5"""
        total_stats = (self.strength + self.defense + self.speed + 
                      self.reaction + self.endurance + self.willpower)
        return total_stats * 0.5
    
    def recover_haki_stamina(self) -> float:
        """Recover Haki stamina per spec 2.3: RestorationRate = 0.20 × (TotalStats / 300)"""
        total_stats = (self.strength + self.defense + self.speed + 
                      self.reaction + self.endurance + self.willpower)
        max_haki = self._calculate_max_haki_stamina()
        restoration_rate = 0.20 * (total_stats / 300.0)
        recovery = max_haki * restoration_rate
        self.haki_stamina = min(self.haki_stamina + recovery, max_haki)
        return recovery
    
    def _calculate_max_df_stamina(self) -> float:
        """Calculate max DF stamina per spec 2.2: (mastery × 2.0) + (mastery × (aura / 150) × 0.5)"""
        return (self.devil_fruit_mastery * 2.0) + (self.devil_fruit_mastery * (self.aura / 150.0) * 0.5)
    
    def recover_df_stamina(self) -> float:
        """Recover DF stamina per spec 2.3: MaxDFStamina × (mastery × 0.002)"""
        max_df = self._calculate_max_df_stamina()
        recovery = max_df * (self.devil_fruit_mastery * 0.002)
        self.devil_fruit_stamina = min(self.devil_fruit_stamina + recovery, max_df)
        return recovery

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
        
        # Assign devil fruits
        self.player1.devil_fruit_type = "mera_mera"
        self.player2.devil_fruit_type = "gura_gura"
        
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
        self.breakthrough_squares: List[Tuple[int, int]] = []  # Breakthrough tiles overlay on blocked tiles
        self.wall_placement_tiles: List[Tuple[int, int]] = []  # Tiles in range for wall placement
        self.wall_first_tile_highlight: Optional[Tuple[int, int]] = None  # First selected tile for wall creation
        self.blocked_tiles_map: Dict[Tuple[int, int], List[Tuple[int, int, str]]] = {}  # Maps blocked tile -> list of blocking walls
        
        # Defender counter pattern storage (for defensive phase with counter)
        self.defender_counter_attack_tiles: List[Tuple[int, int]] = []
        self.defender_counter_breakthrough_tiles: List[Tuple[int, int]] = []
        self.defender_counter_blocked_map: Dict[Tuple[int, int], List[Tuple[int, int, str]]] = {}
        
        self.current_path: List[Tuple[int, int]] = []
        self.planned_actions: List[Tuple[str, object]] = []
        self.battle_log: List[str] = []
        self.debug_last_display: str = ""
        
        # Alloy system state
        self.selected_alloy_tab = "attack"  # "attack", "defense", "devil_fruit", "haki"
        self.applied_haki_alloys = set()  # Track which Haki types are applied: {"armament", "observation", "conqueror"}
        self.haki_alloy_costs = {}  # Track costs per type for refund: {"armament": cost, ...}
        self.applied_df_alloys = set()  # Track which DF alloy types are applied: {"damage_alloy", "hit_alloy", etc.}
        self.df_alloy_costs = {}  # Track costs per type for refund: {"damage_alloy": cost, ...}
        self.df_sub_tab = "special_attacks"  # "special_attacks", "alloys", "walls", "tiles" - controls DF sub-tab display
        self.df_alloy_level_select = None  # Stores alloy type when selecting level: "width_boost" or "length_boost"
        
        # Wall creation/reinforcement state
        self.wall_mode = None  # None, "conjure", "reinforce"
        self.wall_first_tile = None  # (row, col) for first tile in wall placement
        self.wall_selected_for_reinforce = None  # (row, col, orientation) of wall being reinforced
        self.wall_reinforce_count = 0  # Number of times current wall has been reinforced this action
        self.wall_operations_this_phase = 0  # Tracks creations + reinforcements in defense phase
        self.player_created_walls = []  # List of (row, col, orientation) tuples for walls created by current player
                
        # Tile creation state
        self.tile_mode = False  # True when in tile placement mode
        self.selected_tile_type = None  # Tile type being placed (e.g., "burning_ground")
        self.planned_tile_creation = None  # {"tile_type": str, "row": int, "col": int, "df_cost": int}

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
        # Bounce chain tracking per Rule Update5
        self.bounce_chain_length: int = 0
        self.bounce_chain_type: Optional[str] = None
        self.bounce_allowed_dirs: Optional[List[Tuple[int, int]]] = None
        # Track facing at each move to detect chain breaks
        self.move_facing_history: List[float] = []  # Facing direction at each move
        # Persisted bounce segments for display locking
        self.bounce_segments: List[Dict[str, Any]] = []

        # Phase 5: Pattern detection
        self.pattern_evaluator = PatternEvaluator()
        self.pattern_active_bonus: Optional[Dict[str, Any]] = None
        self.pattern_memory: Optional[Dict[str, Any]] = None
        self.pattern_applied_this_phase: bool = False
        # Pattern chain tracking (path indices covered by active pattern)
        self.pattern_start_move_idx: Optional[int] = None
        self.pattern_end_move_idx: Optional[int] = None
        self.pattern_name: Optional[str] = None
        self.devils_type_adv: Dict[str, Any] = {}
        self.active_effects: Dict[str, List[StatusEffect]] = {self.player1.name: [], self.player2.name: []}
        # Haki activation flags for current action
        self.attacker_obs_active = False
        self.attacker_arm_active = False
        self.defender_obs_active = False
        self.defender_arm_active = False
        
        # Effects Engine
        self.effects_engine = EffectsEngine()

        # Phase 4: Walls & Tiles
        avg_primary_sum = (self.player1.strength + self.player1.defense + 
                          self.player2.strength + self.player2.defense) / 2.0
        self.avg_primary_sum = avg_primary_sum
        self.wall_system = WallSystem()
        self.wall_system.spawn_initial_walls(avg_primary_sum)
        self.tile_system = TileSystem()
        self.tile_system.spawn_initial_tiles(avg_primary_sum)
        
        # Initialize Effects Engine
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        self.effects_engine.load_from_files(data_dir)
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
            
            # Load devil fruits data
            df_path = os.path.join(data_dir, 'devil_fruits.json')
            if os.path.exists(df_path):
                with open(df_path, 'r', encoding='utf-8') as df:
                    df_data = json.load(df)
                if isinstance(df_data, dict) and 'fruits' in df_data:
                    # Map fruit data to players
                    for player in (self.player1, self.player2):
                        if player.devil_fruit_type:
                            for fruit in df_data['fruits']:
                                if fruit.get('id') == player.devil_fruit_type:
                                    player.devil_fruit_data = fruit
                                    player.devil_fruit_type_advantages = fruit.get('type_advantages')
                                    break
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
        # Only enable movement if not in wall mode
        if not self.wall_mode:
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
            self.breakthrough_squares = []
            print("DEBUG: Recompute highlights - ghost_row is None")
            return
        # Movement range (yellow)
        self.highlighted_squares = self._neighbors(self.ghost_row, self.ghost_col)
        # Attack preview (red) - ONLY show when attack is selected
        if self._has_attack_selected():
            print("DEBUG: Attack is selected, computing pattern...")
            all_pattern_tiles = self._compute_attack_pattern_preview()
            # Separate normal attack tiles from breakthrough tiles
            self.attack_highlighted_squares, self.breakthrough_squares = self._separate_breakthrough_tiles(all_pattern_tiles)
            print(f"DEBUG: attack_highlighted_squares set to {len(self.attack_highlighted_squares)} tiles")
            print(f"DEBUG: breakthrough_squares set to {len(self.breakthrough_squares)} tiles")
        else:
            print("DEBUG: No attack selected, clearing attack highlights")
            self.attack_highlighted_squares = []
            self.breakthrough_squares = []

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
                attack_type = action[1]
                # Skip is not an attack type for pattern purposes
                if attack_type == "skip":
                    return None
                return attack_type
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
        Special attacks: Use custom pattern from devil_fruit_data
        """
        tiles: List[Tuple[int, int]] = []
        if self.ghost_row is None:
            print("DEBUG: Attack pattern: ghost_row is None")
            return tiles
        
        attack_type = self._get_selected_attack_type()
        if not attack_type:
            print("DEBUG: Attack pattern: no attack type selected")
            return tiles
        
        r = self.ghost_row
        c = self.ghost_col
        ang = int(self.ghost_facing if self.ghost_facing is not None else 0) % 360
        
        # Check if this is a special attack
        if attack_type.startswith("special:"):
            special_name = attack_type.split(":", 1)[1]
            player = self.get_current_player()
            
            if player.devil_fruit_data:
                phase_key = "special_attacks" if self.phase == "attack" else "special_defenses"
                special_actions = player.devil_fruit_data.get(phase_key, {})
                
                if special_name in special_actions:
                    special_data = special_actions[special_name]
                    
                    # Check if facing is cardinal or diagonal
                    is_cardinal = ang in [0, 90, 180, 270]
                    
                    # Select appropriate pattern based on facing
                    if is_cardinal:
                        pattern = special_data.get('pattern', [])
                    else:
                        pattern = special_data.get('pattern_diagonal', [])
                    
                    if not pattern:
                        print(f"DEBUG: No {'cardinal' if is_cardinal else 'diagonal'} pattern defined for {special_name}")
                        return tiles
                    
                    if is_cardinal:
                        # Cardinal pattern: [col_offset, row_offset] format
                        for offset in pattern:
                            col_offset, row_offset = offset[0], offset[1]
                            
                            print(f"DEBUG SPECIAL CARDINAL: base pattern offset [{col_offset}, {row_offset}] at angle {ang}°")
                            
                            # Apply directional transformation matching cardinal attack logic
                            if ang == 0:  # East
                                tile_c = c + row_offset
                                tile_r = r + col_offset
                            elif ang == 90:  # South
                                tile_r = r + row_offset
                                tile_c = c + col_offset
                            elif ang == 180:  # West
                                tile_c = c - row_offset
                                tile_r = r + col_offset
                            elif ang == 270:  # North
                                tile_r = r - row_offset
                                tile_c = c + col_offset
                            
                            print(f"DEBUG SPECIAL CARDINAL: -> tile (row={tile_r}, col={tile_c})")
                            
                            if 0 <= tile_r < 7 and 0 <= tile_c < 7:
                                tiles.append((tile_r, tile_c))
                            else:
                                print(f"DEBUG SPECIAL CARDINAL: TILE OUT OF BOUNDS")
                        
                        print(f"DEBUG SPECIAL CARDINAL: Final pattern for {special_name} at ({r},{c}) facing {ang}°: {tiles}")
                        tiles = self._filter_cardinal_attack_pattern_by_walls(tiles, r, c, ang)
                        print(f"DEBUG SPECIAL CARDINAL: After cardinal wall filtering: {tiles}")
                    
                    else:
                        # Diagonal pattern: use facing vector like diagonal attacks
                        facing_vec = self._facing_to_vector(float(ang))
                        if facing_vec == (999, 999):
                            print(f"DEBUG SPECIAL DIAGONAL: Invalid facing angle {ang}")
                            return tiles
                        
                        fx, fy = facing_vec
                        
                        print(f"DEBUG SPECIAL DIAGONAL: Processing pattern at ({r},{c}) facing {ang}°, vector=({fx},{fy})")
                        
                        # Pattern uses relative coordinates
                        for offset in pattern:
                            dx, dy = offset[0], offset[1]  # dx=col offset, dy=row offset
                            
                            # Apply facing transformation
                            tile_c = c + dx * fx
                            tile_r = r + dy * fy
                            
                            print(f"DEBUG SPECIAL DIAGONAL: offset [{dx}, {dy}] -> tile (row={tile_r}, col={tile_c})")
                            
                            if 0 <= tile_r < 7 and 0 <= tile_c < 7:
                                tiles.append((tile_r, tile_c))
                            else:
                                print(f"DEBUG SPECIAL DIAGONAL: TILE OUT OF BOUNDS")
                        
                        print(f"DEBUG SPECIAL DIAGONAL: Final pattern for {special_name}: {tiles}")
                        
                        # Apply diagonal wall blocking
                        # Need to determine attack_range for filtering - use max extent of pattern
                        max_extent = max([max(abs(offset[0]), abs(offset[1])) for offset in pattern], default=1)
                        attack_range = min(3, max(1, max_extent))  # Clamp to 1-3
                        
                        tiles = self._filter_diagonal_attack_pattern_by_walls(tiles, r, c, attack_range, ang)
                        print(f"DEBUG SPECIAL DIAGONAL: After diagonal wall filtering: {tiles}")
                    
                    return tiles
        
        # Regular attack types (quick/normal/heavy)
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
        
        # Apply wall blocking per Section 7.6 (internal walls only)
        tiles = self._filter_cardinal_attack_pattern_by_walls(tiles, r, c, ang)
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
        
        # Apply wall blocking per Section 7.6 (internal walls only)
        tiles = self._filter_diagonal_attack_pattern_by_walls(tiles, r, c, attack_range, ang)
        return tiles
    
    def _separate_breakthrough_tiles(self, unblocked_tiles: List[Tuple[int, int]]) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        """Find blocked tiles that will breakthrough using tracked blocking data.
        
        Uses self.blocked_tiles_map populated during wall filtering.
        For multi-wall blocks, ALL walls must break for breakthrough.
        
        Returns: (normal_attack_tiles, breakthrough_tiles)
        """
        if not self.blocked_tiles_map:
            return unblocked_tiles, []
        
        attack_type = self._get_selected_attack_type()
        if not attack_type:
            return unblocked_tiles, []
        
        # Calculate attack damage
        attack_base_damage = {'quick': 10, 'normal': 20, 'heavy': 30}.get(attack_type, 20)
        facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
        bounce_bonus = 0.0
        if self.bounce_active:
            hits = [0.10, 0.125, 0.15, 0.175, 0.20]
            idx = min(max(1, self.bounce_chain_length), 5) - 1
            bounce_bonus = hits[idx]
        pattern_dmg = 0.0
        if self.pattern_active_bonus and not self.pattern_applied_this_phase:
            pattern_dmg = self.pattern_active_bonus.get('damage_bonus', 0.0)
        elif self.pattern_memory:
            pattern_dmg = self.pattern_memory.get('damage_bonus', 0.0)
        
        wall_damage = int(attack_base_damage * (1.0 + facing_bonus + bounce_bonus + pattern_dmg))
        
        print(f"[BREAKTHROUGH] Blocked tiles to check: {len(self.blocked_tiles_map)}")
        print(f"[BREAKTHROUGH] Attack damage: {wall_damage}")
        
        breakthrough_tiles = []
        
        for blocked_tile, blocking_wall_list in self.blocked_tiles_map.items():
            print(f"[BREAKTHROUGH] Tile {blocked_tile}: blocked by {len(blocking_wall_list)} wall(s)")
            
            # Get wall objects
            walls = []
            for wall_row, wall_col, wall_orient in blocking_wall_list:
                wall = self.wall_system.get_wall_at(wall_row, wall_col, wall_orient)
                if wall and wall.tier != 'border':
                    walls.append(wall)
                    print(f"[BREAKTHROUGH]   Wall ({wall_row},{wall_col},{wall_orient}): HP={wall.hp}")
            
            if not walls:
                continue
            
            # Check if ALL walls will break
            all_break = all(wall.hp < wall_damage for wall in walls)
            
            if all_break:
                breakthrough_tiles.append(blocked_tile)
                if len(walls) > 1:
                    avg_hp = sum(wall.hp for wall in walls) / len(walls)
                    print(f"[BREAKTHROUGH]   BREAKTHROUGH (multi-wall): avg HP={avg_hp:.1f}")
                else:
                    print(f"[BREAKTHROUGH]   BREAKTHROUGH: HP={walls[0].hp}")
            else:
                not_breaking = [w for w in walls if w.hp >= wall_damage]
                print(f"[BREAKTHROUGH]   NOT breakthrough: {len(not_breaking)} wall(s) survive")
        
        print(f"[BREAKTHROUGH] Result: {len(unblocked_tiles)} normal, {len(breakthrough_tiles)} breakthrough")
        return unblocked_tiles, breakthrough_tiles
    
    def _get_wall_blocking_tile(self, tile: Tuple[int, int]) -> Optional[Tuple[int, int, str]]:
        """Check if a wall blocks this attack tile.
        Returns (wall_row, wall_col, orientation) if wall blocks, None otherwise.
        """
        row, col = tile
        
        # Get attacker position and facing
        if self.ghost_row is None or self.ghost_col is None:
            return None
        
        attacker_row = self.ghost_row
        attacker_col = self.ghost_col
        
        # Check all walls to see if they block this tile
        all_walls = self.wall_system._walls + self.wall_system._border_walls
        
        for wall in all_walls:
            # Check if wall blocks the path from attacker to this tile
            # For simplicity, check if wall's affected tiles overlap with attack pattern
            affected_tiles = []
            if wall.orientation == 'h':
                affected_tiles = [(wall.row, wall.col), (wall.row + 1, wall.col)]
            elif wall.orientation == 'v':
                affected_tiles = [(wall.row, wall.col), (wall.row, wall.col + 1)]
            
            # If tile is one of the affected tiles, wall blocks it
            if tile in affected_tiles:
                return (wall.row, wall.col, wall.orientation)
        
        return None

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
            
            # Bounce detection FIRST, then continuity check
            continuing_chain = False
            
            # Phase 1: Detect NEW bounce
            if len(self.current_path) >= 3:
                bounce_result = detect_bounce(self.current_path[-3:], self.wall_system)
                if bounce_result:
                    new_bounce_type = bounce_result.get('type')
                    r1, c1 = self.current_path[-2]
                    r2, c2 = self.current_path[-1]
                    exit_vec = (c2 - c1, r2 - r1)
                    print(f"DEBUG NEW BOUNCE EXIT_VEC: {exit_vec}")
                    wr, wc = self.current_path[-2]
                    wall_info = self.wall_system.get_wall_at_tile(wr, wc)
                    wall_orient = wall_info[2] if wall_info else None
                    self.bounce_wall_orient = wall_orient
                    
                    prev_allowed = list(self.bounce_allowed_dirs or [])
                    can_continue_chain = False
                    is_corner_tile = (wr, wc) in [(0,0),(0,6),(6,0),(6,6)]
                    if self.bounce_active:
                        if prev_allowed and exit_vec in prev_allowed:
                            can_continue_chain = True
                        elif is_corner_tile:
                            can_continue_chain = True
                        else:
                            self.bounce_end_move_idx = max(0, len(self.current_path) - 3)
                    
                    if can_continue_chain:
                        self.bounce_active = True
                        self.bounce_chain_length += 1
                        if self.bounce_start_move_idx is None:
                            self.bounce_start_move_idx = len(self.current_path) - 2
                        self.bounce_end_move_idx = None
                        print(f"DEBUG CONT AFTER NEW BOUNCE: CONTINUE chain_len={self.bounce_chain_length}")
                    else:
                        # Break and start a NEW bounce; persist previous segment if any
                        if self.bounce_start_move_idx is not None and self.bounce_chain_length > 0:
                            prev_end = max(0, len(self.current_path) - 3)
                            try:
                                self.bounce_segments.append({
                                    "start": self.bounce_start_move_idx,
                                    "end": prev_end,
                                    "rate": self.bounce_discount,
                                    "type": self.bounce_chain_type or new_bounce_type,
                                    "label": ('Bd' if (self.bounce_chain_type or new_bounce_type) == 'diagonal' else ('Bc' if (self.bounce_chain_type or new_bounce_type) == 'cardinal' else ''))
                                })
                            except Exception:
                                pass
                        self.bounce_active = True
                        self.bounce_chain_length = 1
                        self.bounce_start_move_idx = len(self.current_path) - 2
                        self.bounce_end_move_idx = None
                        print(f"DEBUG CONT AFTER NEW BOUNCE: NEW chain_len={self.bounce_chain_length}")
                    
                    self.bounce_type = new_bounce_type
                    self.bounce_chain_type = new_bounce_type
                    self.bounce_direction = exit_vec
                    
                    if new_bounce_type == 'cardinal':
                        self.bounce_allowed_dirs = [exit_vec]
                        print(f"DEBUG ALLOWED UPDATED (cardinal): {self.bounce_allowed_dirs}")
                    else:
                        if wall_orient == 'h':
                            self.bounce_allowed_dirs = [(1, exit_vec[1]), (-1, exit_vec[1])]
                        elif wall_orient == 'v':
                            self.bounce_allowed_dirs = [(exit_vec[0], 1), (exit_vec[0], -1)]
                        else:
                            self.bounce_allowed_dirs = [exit_vec, (-exit_vec[0], -exit_vec[1])]
                        print(f"DEBUG ALLOWED UPDATED (diagonal-{wall_orient}): {self.bounce_allowed_dirs}")
                    
                    rates = [0.10, 0.125, 0.15, 0.175, 0.20]
                    hits = [0.10, 0.125, 0.15, 0.175, 0.20]
                    idx = min(self.bounce_chain_length, 5) - 1
                    self.bounce_discount = rates[idx]
                    self.bounce_hit_bonus = hits[idx]
                    self.battle_log.append(f"BOUNCE DETECTED: {self.bounce_type} (Chain: {self.bounce_chain_length})")
                    continuing_chain = True

            # Phase 2: Check continuity ONLY if no new bounce
            if not continuing_chain and self.bounce_active and len(self.current_path) >= 2:
                print(f"DEBUG CONT STATE: active={self.bounce_active}, chain_len={self.bounce_chain_length}")
                allowed_local = []
                if self.bounce_type == 'cardinal' and self.bounce_direction is not None:
                    allowed_local = [self.bounce_direction]
                elif self.bounce_type == 'diagonal' and self.bounce_direction is not None:
                    # Rule Update4 line 24: "continue moving diagonally away from the wall in either valid diagonal direction for that wall orientation"
                    # Horizontal wall: both NE and NW (or both SE and SW depending on which side)
                    # Vertical wall: both NE and SE (or both NW and SW depending on which side)
                    bwo = getattr(self, 'bounce_wall_orient', None)
                    d = self.bounce_direction
                    print(f"DEBUG DIAGONAL ALLOWED CALC: exit_dir={d}, wall_orient={bwo}")
                    if bwo == 'h':
                        # Horizontal wall: maintain row sign (away from wall), col can be ±1
                        # If exit is NE (1,-1) or NW (-1,-1), both are valid continuations
                        allowed_local = [(1, d[1]), (-1, d[1])]
                        print(f"DEBUG DIAGONAL ALLOWED (h-wall): row_sign={d[1]}, allowed={(1, d[1]), (-1, d[1])}")
                    elif bwo == 'v':
                        # Vertical wall: maintain col sign (away from wall), row can be ±1
                        # If exit is NE (1,-1) or SE (1,1), both are valid continuations
                        allowed_local = [(d[0], 1), (d[0], -1)]
                        print(f"DEBUG DIAGONAL ALLOWED (v-wall): col_sign={d[0]}, allowed={(d[0], 1), (d[0], -1)}")
                    else:
                        # Fallback: same diagonal line
                        allowed_local = [d, (-d[0], -d[1])]
                        print(f"DEBUG DIAGONAL ALLOWED (fallback): allowed={allowed_local}")
                else:
                    allowed_local = list(self.bounce_allowed_dirs or [])
                # Persist the computed allowed set to avoid stale values
                self.bounce_allowed_dirs = allowed_local
                print(f"DEBUG CONT DERIVED: type={self.bounce_type}, bounce_dir={self.bounce_direction}, wall_orient={getattr(self,'bounce_wall_orient',None)}, allowed_local={allowed_local}")
                r1, c1 = self.current_path[-2]
                r2, c2 = self.current_path[-1]
                move_dir = (c2 - c1, r2 - r1)
                print(f"DEBUG CONT MOVE_DIR: {move_dir}, allowed(newest)={allowed_local}")

                matched = (move_dir in allowed_local)
                print(f"DEBUG CONT MATCH: {matched}")
                if matched:
                    # Continue chain, update scaling
                    rates = [0.10, 0.125, 0.15, 0.175, 0.20]
                    hits = [0.10, 0.125, 0.15, 0.175, 0.20]
                    self.bounce_chain_length += 1
                    idx = min(self.bounce_chain_length, 5) - 1
                    self.bounce_discount = rates[idx]
                    self.bounce_hit_bonus = hits[idx]
                    print(f"DEBUG CONT CONTINUE: chain_len={self.bounce_chain_length}")

                else:
                    # Finalize current bounce segment and persist
                    if self.bounce_start_move_idx is not None:
                        seg_end = max(0, len(self.current_path) - 3)
                        self.bounce_end_move_idx = seg_end
                        try:
                            self.bounce_segments.append({
                                "start": self.bounce_start_move_idx,
                                "end": seg_end,
                                "rate": self.bounce_discount,
                                "type": self.bounce_type,
                                "label": ('Bd' if self.bounce_type == 'diagonal' else ('Bc' if self.bounce_type == 'cardinal' else ''))
                            })
                        except Exception:
                            pass
                    self.bounce_active = False
                    self.bounce_chain_type = None
                    print(f"DEBUG FINALIZE BREAK: end_idx={self.bounce_end_move_idx}")

            self._recompute_highlights()
            old = self.pattern_active_bonus
            self._update_pattern_bonus()
            if self.pattern_active_bonus and old is None and not self.pattern_applied_this_phase:
                self.battle_log.append(f"Pattern active: {self.pattern_active_bonus['name']}")
            self.battle_log.append(f"Move → {action_data['tile']}")
            self.debug_planned_actions_display()
            
            # Update wall placement tiles if in wall conjure mode
            if self.wall_mode == "conjure":
                player = self.get_current_player()
                wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
                if wall_config:
                    placement_range = wall_config.get("range", 5)
                    player_pos = (self.ghost_row, self.ghost_col)
                    self.wall_placement_tiles = []
                    for row in range(7):
                        for col in range(7):
                            distance = abs(row - player_pos[0]) + abs(col - player_pos[1])
                            if distance <= placement_range:
                                self.wall_placement_tiles.append((row, col))

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
        
        # Update wall placement tiles if in wall conjure mode
        if self.wall_mode == "conjure":
            player = self.get_current_player()
            wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
            if wall_config:
                placement_range = wall_config.get("range", 5)
                player_pos = (self.ghost_row, self.ghost_col)
                self.wall_placement_tiles = []
                for row in range(7):
                    for col in range(7):
                        distance = abs(row - player_pos[0]) + abs(col - player_pos[1])
                        if distance <= placement_range:
                            self.wall_placement_tiles.append((row, col))

    def _recompute_bounce_state(self) -> None:
        """Recompute bounce state from scratch based on current path.
        Walk forward through path detecting bounces and checking continuity.
        """
        # Reset all bounce state
        self.bounce_active = False
        self.bounce_discount = 0.0
        self.bounce_type = None
        self.bounce_hit_bonus = 0.0
        self.bounce_start_move_idx = None
        self.bounce_direction = None
        self.bounce_end_move_idx = None
        self.bounce_chain_length = 0
        self.bounce_chain_type = None
        self.bounce_allowed_dirs = None
        self.bounce_segments = []
        
        if len(self.current_path) < 3:
            return
        
        # Walk through path and detect bounces + continuity
        for i in range(2, len(self.current_path)):
            triplet = [self.current_path[i-2], self.current_path[i-1], self.current_path[i]]
            bounce_result = detect_bounce(triplet, self.wall_system)
            if bounce_result:
                new_bounce_type = bounce_result.get('type')
                r1, c1 = triplet[1]
                r2, c2 = triplet[2]
                exit_vec = (c2 - c1, r2 - r1)
                wr, wc = triplet[1]
                wall_info = self.wall_system.get_wall_at_tile(wr, wc)
                wall_orient = wall_info[2] if wall_info else None
                self.bounce_wall_orient = wall_orient
                
                prev_allowed = list(self.bounce_allowed_dirs or [])
                can_continue_chain = False
                is_corner_tile = (wr, wc) in [(0,0),(0,6),(6,0),(6,6)]
                if self.bounce_active:
                    if prev_allowed and exit_vec in prev_allowed:
                        can_continue_chain = True
                    elif is_corner_tile:
                        can_continue_chain = True
                    else:
                        # Break chain, persist segment
                        if self.bounce_start_move_idx is not None and self.bounce_chain_length > 0:
                            prev_end = i - 3 if i >= 3 else 0
                            try:
                                self.bounce_segments.append({
                                    "start": self.bounce_start_move_idx,
                                    "end": prev_end,
                                    "rate": self.bounce_discount,
                                    "type": self.bounce_chain_type or new_bounce_type,
                                    "label": ('Bd' if (self.bounce_chain_type or new_bounce_type) == 'diagonal' else ('Bc' if (self.bounce_chain_type or new_bounce_type) == 'cardinal' else ''))
                                })
                            except Exception:
                                pass
                
                if can_continue_chain:
                    self.bounce_active = True
                    self.bounce_chain_length += 1
                    if self.bounce_start_move_idx is None:
                        self.bounce_start_move_idx = i - 2
                    self.bounce_end_move_idx = None
                else:
                    # Start new bounce
                    self.bounce_active = True
                    self.bounce_chain_length = 1
                    self.bounce_start_move_idx = i - 2
                    self.bounce_end_move_idx = None
                
                self.bounce_type = new_bounce_type
                self.bounce_chain_type = new_bounce_type
                self.bounce_direction = exit_vec
                
                if new_bounce_type == 'cardinal':
                    self.bounce_allowed_dirs = [exit_vec]
                else:
                    if wall_orient == 'h':
                        self.bounce_allowed_dirs = [(1, exit_vec[1]), (-1, exit_vec[1])]
                    elif wall_orient == 'v':
                        self.bounce_allowed_dirs = [(exit_vec[0], 1), (exit_vec[0], -1)]
                    else:
                        self.bounce_allowed_dirs = [exit_vec, (-exit_vec[0], -exit_vec[1])]
                
                rates = [0.10, 0.125, 0.15, 0.175, 0.20]
                hits = [0.10, 0.125, 0.15, 0.175, 0.20]
                idx = min(self.bounce_chain_length, 5) - 1
                self.bounce_discount = rates[idx]
                self.bounce_hit_bonus = hits[idx]
            elif self.bounce_active and i >= 2:
                # No new bounce; check continuity
                r1, c1 = self.current_path[i-1]
                r2, c2 = self.current_path[i]
                move_dir = (c2 - c1, r2 - r1)
                allowed_local = list(self.bounce_allowed_dirs or [])
                matched = (move_dir in allowed_local)
                if matched:
                    # Continue chain
                    rates = [0.10, 0.125, 0.15, 0.175, 0.20]
                    hits = [0.10, 0.125, 0.15, 0.175, 0.20]
                    self.bounce_chain_length += 1
                    idx = min(self.bounce_chain_length, 5) - 1
                    self.bounce_discount = rates[idx]
                    self.bounce_hit_bonus = hits[idx]
                else:
                    # Break and persist segment
                    if self.bounce_start_move_idx is not None:
                        seg_end = i - 3 if i >= 3 else 0
                        self.bounce_end_move_idx = seg_end
                        try:
                            self.bounce_segments.append({
                                "start": self.bounce_start_move_idx,
                                "end": seg_end,
                                "rate": self.bounce_discount,
                                "type": self.bounce_type,
                                "label": ('Bd' if self.bounce_type == 'diagonal' else ('Bc' if self.bounce_type == 'cardinal' else ''))
                            })
                        except Exception:
                            pass
                    self.bounce_active = False
                    self.bounce_chain_type = None

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
        old_facing = self.ghost_facing if self.ghost_facing is not None else 0
        new_facing = (float(self.ghost_facing if self.ghost_facing is not None else 0) + degrees) % 360
        # Handle 360 -> 0 normalization
        if new_facing >= 360:
            new_facing = 0
        print(f"DEBUG ROTATION: old_facing={old_facing}, degrees={degrees}, new_facing={new_facing}")
        self.ghost_facing = new_facing
        self.planned_actions.append(("rotate", degrees))
        # Recompute chain with new facing
        self._update_facing_chain()
        self._recompute_highlights()
        self.battle_log.append(f"Rotate {degrees}°")
        print(f"DEBUG ROTATION: ghost_facing is now {self.ghost_facing}, wheel_rotation={self.wheel_rotation}")
        self.debug_planned_actions_display()

    def add_attack(self, kind: str) -> None:
        if not self.planning_mode:
            print(f"DEBUG: add_attack({kind}) - not in planning mode")
            return
        # If attack already selected, replace it instead of blocking
        if self._has_attack_selected():
            # Remove existing attack from planned_actions
            self.planned_actions = [a for a in self.planned_actions if a[0] != "attack"]
            self.battle_log.append(f"Attack replaced: {kind}")
        else:
            self.battle_log.append(f"Attack selected: {kind}")
        self.planning_terminal = True
        self.movement_mode = False
        self.planned_actions.append(("attack", kind))
        print(f"DEBUG: Attack {kind} added to planned_actions, terminal={self.planning_terminal}")
        print(f"DEBUG: planned_actions = {self.planned_actions}")
        self._recompute_highlights()
        self.debug_planned_actions_display()
    
    def add_special_attack(self, special_name: str) -> None:
        """Add a Devil Fruit special attack action."""
        if not self.planning_mode:
            print(f"DEBUG: add_special_attack({special_name}) - not in planning mode")
            return
        
        # Check if player has DF data and the special attack exists
        player = self.get_current_player()
        if not player.devil_fruit_data:
            print(f"DEBUG: Player has no devil fruit data")
            return
        
        phase_key = "special_attacks" if self.phase == "attack" else "special_defenses"
        special_actions = player.devil_fruit_data.get(phase_key, {})
        
        if special_name not in special_actions:
            print(f"DEBUG: Special attack {special_name} not found in {phase_key}")
            return
        
        # Check DF stamina cost
        special_data = special_actions[special_name]
        df_cost = special_data.get('df_stamina_cost', 0)
        max_df = player._calculate_max_df_stamina()
        current_df_pct = (player.devil_fruit_stamina / max_df) * 100 if max_df > 0 else 0
        
        if current_df_pct < df_cost:
            self.battle_log.append(f"Insufficient DF stamina for {special_name}")
            return
        
        # If attack already selected, replace it
        if self._has_attack_selected():
            self.planned_actions = [a for a in self.planned_actions if a[0] != "attack"]
            self.battle_log.append(f"Attack replaced: {special_name}")
        else:
            self.battle_log.append(f"Special attack selected: {special_name}")
        
        self.planning_terminal = True
        self.movement_mode = False
        # Store as ("attack", "special:<special_name>") to distinguish from normal attacks
        self.planned_actions.append(("attack", f"special:{special_name}"))
        print(f"DEBUG: Special attack {special_name} added to planned_actions")
        self._recompute_highlights()
        self.debug_planned_actions_display()

    def add_defense(self, kind: str) -> None:
        if not self.planning_mode:
            return
        # If defense already selected, replace it instead of blocking
        has_defense = any(a for a in self.planned_actions if a[0] == "defense")
        if has_defense:
            # Remove existing defense from planned_actions
            self.planned_actions = [a for a in self.planned_actions if a[0] != "defense"]
            self.battle_log.append(f"Defense replaced: {kind}")
        else:
            self.battle_log.append(f"Defense selected: {kind}")
        self.planning_terminal = True
        self.movement_mode = False
        self.planned_actions.append(("defense", kind))
        self._recompute_highlights()
        self.debug_planned_actions_display()
    
    def add_special_defense(self, special_name: str) -> None:
        """Add a Devil Fruit special defense action."""
        if not self.planning_mode:
            print(f"DEBUG: add_special_defense({special_name}) - not in planning mode")
            return
        
        # Check if player has DF data and the special defense exists
        player = self.get_current_player()
        if not player.devil_fruit_data:
            print(f"DEBUG: Player has no devil fruit data")
            return
        
        special_defenses = player.devil_fruit_data.get('special_defenses', {})
        
        if special_name not in special_defenses:
            print(f"DEBUG: Special defense {special_name} not found")
            return
        
        # Check DF stamina cost
        special_data = special_defenses[special_name]
        df_cost = special_data.get('df_stamina_cost', 0)
        max_df = player._calculate_max_df_stamina()
        current_df_pct = (player.devil_fruit_stamina / max_df) * 100 if max_df > 0 else 0
        
        if current_df_pct < df_cost:
            self.battle_log.append(f"Insufficient DF stamina for {special_name}")
            return
        
        # If defense already selected, replace it
        has_defense = any(a for a in self.planned_actions if a[0] == "defense")
        if has_defense:
            self.planned_actions = [a for a in self.planned_actions if a[0] != "defense"]
            self.battle_log.append(f"Defense replaced: {special_name}")
        else:
            self.battle_log.append(f"Special defense selected: {special_name}")
        
        self.planning_terminal = True
        self.movement_mode = False
        # Store as ("defense", "special:<special_name>")
        self.planned_actions.append(("defense", f"special:{special_name}"))
        print(f"DEBUG: Special defense {special_name} added to planned_actions")
        self._recompute_highlights()
        self.debug_planned_actions_display()
    
    def apply_haki_alloy(self, haki_type: str) -> None:
        """Apply Haki alloy to current attack/defense action. Limited to 1 alloy per action.
        Clicking a new alloy replaces the current one.
        """
        if not self.planning_mode:
            return
        # Check if attack or defense exists
        has_action = any(a[0] in ("attack", "defense") for a in self.planned_actions)
        if not has_action:
            self.battle_log.append("Haki alloy: No action selected")
            return
        
        # If an alloy is already applied, remove and refund it first
        if self.applied_haki_alloys:
            player = self.get_current_player()
            # Get the current alloy type
            old_haki_type = next(iter(self.applied_haki_alloys))
            cost = self.haki_alloy_costs.get(old_haki_type, 0)
            player.haki_stamina += cost
            # Remove from state
            self.applied_haki_alloys.clear()
            self.haki_alloy_costs.clear()
            # Remove from planned_actions
            self.planned_actions = [a for a in self.planned_actions if a[0] != "haki"]
            self.battle_log.append(f"Haki alloy replaced: {old_haki_type} removed (+{cost} refund)")
        
        player = self.get_current_player()
        
        # Calculate Haki cost
        stat_map = {
            "armament": player.haki_armament,
            "observation": player.haki_observation,
            "conqueror": player.haki_conqueror
        }
        stat = stat_map.get(haki_type, 0)
        cost = calculate_haki_cost(haki_type, stat)
        
        # Check if player has enough Haki stamina
        if player.haki_stamina < cost:
            self.battle_log.append(f"Haki alloy failed: insufficient Haki stamina (need {cost})")
            return
        
        # Deduct Haki stamina
        player.haki_stamina -= cost
        
        # Add to applied set and track cost
        self.applied_haki_alloys.add(haki_type)
        self.haki_alloy_costs[haki_type] = cost
        
        # Add haki action to planned_actions for undo tracking
        self.planned_actions.append(("haki", haki_type))
        
        self.battle_log.append(f"Haki alloy applied: {haki_type} (-{cost} Haki stamina)")
        self.debug_planned_actions_display()

    def apply_df_alloy(self, alloy_type: str, level: int = 1) -> None:
        """Apply DF alloy to current attack/defense action. Limited to 1 alloy per action.
        Clicking a new alloy replaces the current one.
        
        Args:
            alloy_type: Type of alloy (damage_alloy, hit_alloy, defense_alloy, width_boost, length_boost)
            level: Level for width_boost (1-2) or length_boost (1-6), ignored for others
        """
        if not self.planning_mode:
            return
        
        # Check if attack or defense exists
        has_action = any(a[0] in ("attack", "defense") for a in self.planned_actions)
        if not has_action:
            self.battle_log.append("DF alloy: No action selected")
            return
        
        # If an alloy is already applied, remove and refund it first
        if self.applied_df_alloys:
            player = self.get_current_player()
            # Get the current alloy key
            old_alloy_key = next(iter(self.applied_df_alloys))
            cost = self.df_alloy_costs.get(old_alloy_key, 0)
            player.devil_fruit_stamina += cost
            # Remove from state
            self.applied_df_alloys.clear()
            self.df_alloy_costs.clear()
            # Remove from planned_actions
            self.planned_actions = [a for a in self.planned_actions if a[0] != "df_alloy"]
            self.battle_log.append(f"DF alloy replaced: {old_alloy_key} removed (+{cost:.1f} refund)")
        
        player = self.get_current_player()
        
        # Check if player has a Devil Fruit
        if not player.devil_fruit_data:
            self.battle_log.append("DF alloy failed: No Devil Fruit")
            return
        
        # Get alloy cost from devil_fruits.json
        alloys_available = player.devil_fruit_data.get("alloys_available", {})
        alloy_data = alloys_available.get(alloy_type, {})
        
        if not alloy_data.get("enabled", False):
            self.battle_log.append(f"DF alloy failed: {alloy_type} not available")
            return
        
        # Filter by phase: check if alloy is allowed in current phase
        alloy_phase = alloy_data.get("phase", "attack")
        current_phase = self.phase  # "attack" or "defense"
        
        # Get current action type to check for counter
        action_type = None
        for action in self.planned_actions:
            if action[0] == "defense":
                action_type = action[1]
                break
        
        # Defense alloys only for defense phase, attack alloys only for attack phase OR counter
        if alloy_phase == "defense" and current_phase == "attack":
            self.battle_log.append(f"DF alloy failed: {alloy_type} only for defense phase")
            return
        elif alloy_phase == "attack" and current_phase == "defense" and action_type != "counter":
            self.battle_log.append(f"DF alloy failed: {alloy_type} only for attack phase or counter")
            return
        
        # Calculate cost based on alloy type
        if "df_cost_per_level" in alloy_data:
            # Width or Length boost with levels
            cost_map = alloy_data["df_cost_per_level"]
            cost = cost_map.get(str(level), 0)
            if cost == 0:
                self.battle_log.append(f"DF alloy failed: invalid level {level} for {alloy_type}")
                return
        else:
            # Fixed cost alloys
            cost = alloy_data.get("df_cost", 0)
        
        # Apply mastery reduction to cost
        mastery_reduction = 1 - (player.devil_fruit_mastery * 0.003)
        actual_cost = cost * mastery_reduction
        
        # Check if player has enough DF stamina
        if player.devil_fruit_stamina < actual_cost:
            self.battle_log.append(f"DF alloy failed: insufficient DF stamina (need {actual_cost:.1f})")
            return
        
        # Deduct DF stamina
        player.devil_fruit_stamina -= actual_cost
        
        # Add to applied set and track cost
        # Store alloy with level for width/length boosts
        alloy_key = f"{alloy_type}:{level}" if "df_cost_per_level" in alloy_data else alloy_type
        self.applied_df_alloys.add(alloy_key)
        self.df_alloy_costs[alloy_key] = actual_cost
        
        # Add df_alloy action to planned_actions for undo tracking
        self.planned_actions.append(("df_alloy", alloy_key))
        
        self.battle_log.append(f"DF alloy applied: {alloy_key} (-{actual_cost:.1f} DF stamina)")
        self.debug_planned_actions_display()
    
    def select_df_alloy_for_level(self, alloy_type: str) -> None:
        """Enter level selection mode for width/length boost alloys."""
        self.df_alloy_level_select = alloy_type
    
    def cancel_df_alloy_level_select(self) -> None:
        """Exit level selection mode."""
        self.df_alloy_level_select = None
    
    # ========== Wall Creation and Reinforcement Methods ==========
    
    def enter_wall_conjure_mode(self) -> None:
        """Enter wall conjure mode - shows placement tiles in range."""
        if not self.planning_mode:
            self.battle_log.append("Wall conjure failed: Turn planning not active")
            return
        
        player = self.get_current_player()
        if not player.devil_fruit_data:
            self.battle_log.append("Wall conjure failed: No Devil Fruit")
            return
        
        wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
        if not wall_config or not wall_config.get("enabled"):
            self.battle_log.append("Wall conjure failed: Wall creation not available")
            return
        
        # Check if attack/defense is selected
        for action in self.planned_actions:
            if action[0] in ["attack", "defense"]:
                self.battle_log.append("Wall conjure failed: Cannot conjure while attack/defense selected")
                return
        
        self.wall_mode = "conjure"
        self.wall_first_tile = None
        self.wall_first_tile_highlight = None
        # Disable movement in wall mode
        self.movement_mode = False
        
        # Calculate tiles in range for wall placement based on ghost position
        placement_range = wall_config.get("range", 5)
        # Use ghost position if available (planning mode), otherwise use actual position
        if self.ghost_row is not None and self.ghost_col is not None:
            player_pos = (self.ghost_row, self.ghost_col)
        else:
            player_pos = (player.row, player.col)
        self.wall_placement_tiles = []
        for row in range(7):
            for col in range(7):
                distance = abs(row - player_pos[0]) + abs(col - player_pos[1])
                if distance <= placement_range:
                    self.wall_placement_tiles.append((row, col))
        
        self.battle_log.append("Wall conjure mode: Select first tile")
    
    def enter_wall_reinforce_mode(self) -> None:
        """Enter wall reinforce mode - shows available walls or enables map clicks."""
        if not self.planning_mode:
            self.battle_log.append("Wall reinforce failed: Turn planning not active")
            return
        
        player = self.get_current_player()
        if not player.devil_fruit_data:
            self.battle_log.append("Wall reinforce failed: No Devil Fruit")
            return
        
        wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
        if not wall_config or not wall_config.get("enabled"):
            self.battle_log.append("Wall reinforce failed: Wall creation not available")
            return
        
        # Check if attack/defense is selected
        for action in self.planned_actions:
            if action[0] in ["attack", "defense"]:
                self.battle_log.append("Wall reinforce failed: Cannot reinforce while attack/defense selected")
                return
        
        self.wall_mode = "reinforce"
        # Disable movement in wall mode
        self.movement_mode = False
        self.battle_log.append("Wall reinforce mode: Select wall to reinforce")
    
    def exit_wall_mode(self) -> None:
        """Exit wall mode and restore normal state."""
        self.wall_mode = None
        self.wall_first_tile = None
        self.wall_selected_for_reinforce = None
        self.wall_placement_tiles = []
        self.wall_first_tile_highlight = None
        # Re-enable movement
        self.movement_mode = True
        self.battle_log.append("Exited wall mode")
    
    def select_wall_tile(self, row: int, col: int) -> None:
        """Handle tile selection for wall placement."""
        if self.wall_mode != "conjure":
            return
        
        player = self.get_current_player()
        wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
        placement_range = wall_config.get("range", 5)
        
        # Check if tile is in range from player position
        player_pos = (player.row, player.col)
        distance = abs(row - player_pos[0]) + abs(col - player_pos[1])
        if distance > placement_range:
            self.battle_log.append(f"Wall placement failed: Tile ({row},{col}) out of range ({distance} > {placement_range})")
            return
        
        if self.wall_first_tile is None:
            # First tile selection
            self.wall_first_tile = (row, col)
            self.wall_first_tile_highlight = (row, col)
            self.battle_log.append(f"First tile selected: ({row},{col}). Select adjacent tile.")
        else:
            # Second tile selection - create wall
            self.create_wall_between_tiles(self.wall_first_tile, (row, col))
            self.wall_first_tile = None
            self.wall_first_tile_highlight = None
    
    def can_place_wall(self, row: int, col: int, orientation: str) -> bool:
        """Check if wall can be placed at position (no duplicates)."""
        return not self.wall_system.has_wall_at(row, col, orientation)
    
    def create_wall_between_tiles(self, tile1: Tuple[int, int], tile2: Tuple[int, int]) -> None:
        """Create wall between two adjacent tiles."""
        row1, col1 = tile1
        row2, col2 = tile2
        
        # Validate adjacency (must be orthogonally adjacent)
        row_diff = abs(row2 - row1)
        col_diff = abs(col2 - col1)
        
        if not ((row_diff == 1 and col_diff == 0) or (row_diff == 0 and col_diff == 1)):
            self.battle_log.append(f"Wall creation failed: Tiles ({row1},{col1}) and ({row2},{col2}) not adjacent")
            return
        
        # Calculate wall position and orientation
        # Same row = vertical wall, same column = horizontal wall
        if row1 == row2:
            # Vertical wall between columns
            orientation = 'v'
            wall_row = row1
            wall_col = min(col1, col2)
        else:
            # Horizontal wall between rows
            orientation = 'h'
            wall_row = min(row1, row2)
            wall_col = col1
        
        # Check for duplicate
        if not self.can_place_wall(wall_row, wall_col, orientation):
            self.battle_log.append(f"Wall creation failed: Wall already exists at ({wall_row},{wall_col},{orientation})")
            return
        
        # Check defense phase limit
        if not self.can_perform_wall_operation():
            return
        
        player = self.get_current_player()
        wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
        hp_per_click = wall_config.get("hp_per_click", 10)
        creation_cost_per_hp = wall_config.get("creation_cost_per_hp", 1.0)
        total_cost = hp_per_click * creation_cost_per_hp
        
        # Check DF stamina
        if player.devil_fruit_stamina < total_cost:
            self.battle_log.append(f"Wall creation failed: Insufficient DF stamina ({player.devil_fruit_stamina:.1f} < {total_cost:.1f})")
            return
        
        # Deduct stamina
        player.devil_fruit_stamina -= total_cost
        
        # Create wall in wall system
        player_id = "player1" if self.attacker_is_p1 else "player2"
        self.wall_system.add_player_wall(wall_row, wall_col, orientation, hp_per_click, player_id)
        
        self.battle_log.append(f"WALL_DEBUG: Wall created at ({wall_row},{wall_col},{orientation}) with {hp_per_click} HP")
        
        # Track wall creation
        self.player_created_walls.append((wall_row, wall_col, orientation))
        
        # Add to planned actions
        self.planned_actions.append(("wall_create", (wall_row, wall_col, orientation, total_cost)))
        
        # Increment operation counter for defense phase
        if self.phase == "defense":
            self.wall_operations_this_phase += 1
        
        self.battle_log.append(f"Wall created at ({wall_row},{wall_col},{orientation}) - {hp_per_click} HP, -{total_cost:.1f} DF stamina")
        self.debug_planned_actions_display()
        
        # Recalculate blocked tiles if in defense phase
        if self.phase == "defense":
            self.recalculate_enemy_patterns()
    
    def select_wall_for_reinforce(self, row: int, col: int, orientation: str) -> None:
        """Handle wall clicks: enters reinforce mode on first click (normal planning), reinforces on subsequent clicks."""
        player = self.get_current_player()
        player_id = "player1" if self.attacker_is_p1 else "player2"
        
        # Check if wall exists and is owned by player
        if not self.wall_system.is_player_wall(row, col, orientation, player_id):
            self.battle_log.append(f"Wall reinforce failed: No player wall at ({row},{col},{orientation})")
            return
        
        # Check range
        wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
        if not wall_config:
            return
        
        reinforcement_range = wall_config.get("range", 5)
        # Use ghost position if available (planning mode), otherwise use actual position
        if self.ghost_row is not None and self.ghost_col is not None:
            player_pos = (self.ghost_row, self.ghost_col)
        else:
            player_pos = (player.row, player.col)
        
        # Calculate distance to wall (use wall's grid position)
        distance = abs(row - player_pos[0]) + abs(col - player_pos[1])
        if distance > reinforcement_range:
            self.battle_log.append(f"Wall reinforce failed: Wall out of range ({distance} > {reinforcement_range})")
            return
        
        # In conjure mode: reinforce without switching mode
        if self.wall_mode == "conjure":
            self.wall_selected_for_reinforce = (row, col, orientation)
            self.reinforce_selected_wall()
        # In reinforce mode: reinforce
        elif self.wall_mode == "reinforce":
            self.wall_selected_for_reinforce = (row, col, orientation)
            self.reinforce_selected_wall()
        else:
            # Not in wall mode: first click only enters reinforce mode
            self.wall_mode = "reinforce"
            self.movement_mode = False
            self.wall_selected_for_reinforce = (row, col, orientation)
            self.battle_log.append(f"Wall reinforce mode activated: ({row},{col},{orientation})")
    
    def enter_tile_mode(self, tile_type_key: str) -> None:
        """Enter tile placement mode for specified tile type."""
        if not self.planning_mode:
            return
        
        # Check if attack/defense already selected
        has_action = any(a[0] in ("attack", "defense") for a in self.planned_actions)
        if has_action:
            self.battle_log.append("Tile creation failed: Cannot create tiles while attack/defense selected")
            return
        
        # Check 3-action limit in defense phase
        if self.phase == "defense" and self.wall_operations_this_phase >= 3:
            self.battle_log.append("Tile creation failed: 3 map manipulation actions limit reached")
            return
        
        player = self.get_current_player()
        if not player.devil_fruit_data:
            return
        
        tiles_available = player.devil_fruit_data.get("map_abilities", {}).get("tiles_available", {})
        if tile_type_key not in tiles_available:
            return
        
        self.tile_mode = True
        self.selected_tile_type = tile_type_key
        # Disable movement and wall modes in tile mode
        self.movement_mode = False
        self.wall_mode = None
        self.battle_log.append(f"Tile placement mode: {tiles_available[tile_type_key]['label']}")
    
    def exit_tile_mode(self) -> None:
        """Exit tile placement mode and restore normal state. Cancel clears planned tile."""
        # Clear planned tile and action ONLY if called from cancel button
        # Do NOT clear if called from confirmation (double-click or active button)
        if self.planned_tile_creation:
            self.planned_tile_creation = None
            # Remove tile action from planned actions
            self.planned_actions = [a for a in self.planned_actions if a[0] != "tile_creation"]
            self.battle_log.append("Tile creation cancelled")
        
        self.tile_mode = False
        self.selected_tile_type = None
        # Re-enable movement (like wall mode)
        if self.planning_mode:
            self.movement_mode = True
        self.battle_log.append("Tile placement mode exited")
    
    def confirm_tile_placement(self) -> None:
        """Confirm tile placement and exit tile mode without cancelling."""
        if not self.tile_mode or not self.planned_tile_creation:
            return
        
        # Exit tile mode but keep tile planned (like wall mode)
        self.tile_mode = False
        self.selected_tile_type = None
        # Re-enable movement (like wall mode)
        if self.planning_mode:
            self.movement_mode = True
        self.battle_log.append("Tile confirmed")
    
    def select_tile_position(self, row: int, col: int, double_click: bool = False) -> None:
        """Place or replace tile at selected position. Double-click confirms and exits tile mode."""
        if not self.tile_mode or not self.selected_tile_type:
            return
        
        player = self.get_current_player()
        tiles_available = player.devil_fruit_data.get("map_abilities", {}).get("tiles_available", {})
        tile_config = tiles_available.get(self.selected_tile_type)
        
        if not tile_config:
            return
        
        # Check range from GHOST position if in planning mode, otherwise actual position
        tile_range = tile_config.get("range", 5)
        if self.ghost_row is not None and self.ghost_col is not None:
            player_pos = (self.ghost_row, self.ghost_col)
        else:
            player_pos = (player.row, player.col)
        
        distance = abs(player_pos[0] - row) + abs(player_pos[1] - col)
        if distance > tile_range:
            self.battle_log.append(f"Tile placement failed: Out of range ({distance} > {tile_range})")
            return
        
        # Check DF stamina
        df_cost = tile_config.get("df_cost", 0)
        max_df = player._calculate_max_df_stamina()
        current_df_pct = (player.devil_fruit_stamina / max_df) * 100 if max_df > 0 else 0
        
        if current_df_pct < df_cost:
            self.battle_log.append(f"Insufficient DF stamina for tile placement")
            return
        
        # Replace existing planned tile or create new one
        if self.planned_tile_creation:
            old_row, old_col = self.planned_tile_creation["row"], self.planned_tile_creation["col"]
            self.battle_log.append(f"Tile moved from ({old_row},{old_col}) to ({row},{col})")
        else:
            self.battle_log.append(f"Tile placed at ({row},{col})")
        
        self.planned_tile_creation = {
            "tile_type": self.selected_tile_type,
            "row": row,
            "col": col,
            "df_cost": df_cost,
            "tile_config": tile_config
        }
        
        # Add to planned actions if not already there
        tile_action_exists = any(a[0] == "tile_creation" for a in self.planned_actions)
        if not tile_action_exists:
            self.planned_actions.append(("tile_creation", self.selected_tile_type, row, col))
        else:
            # Update existing tile action
            self.planned_actions = [(a if a[0] != "tile_creation" else ("tile_creation", self.selected_tile_type, row, col)) for a in self.planned_actions]
        
        # If double-click, confirm and exit tile mode
        if double_click:
            self.confirm_tile_placement()
        
        self.debug_planned_actions_display()
    
    def reinforce_selected_wall(self) -> None:
        """Reinforce the currently selected wall without changing mode state."""
        if self.wall_selected_for_reinforce is None:
            return
        
        row, col, orientation = self.wall_selected_for_reinforce
        
        # Check if can perform operation (defense phase limit)
        if not self.can_perform_wall_operation():
            return
        
        player = self.get_current_player()
        wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
        hp_per_click = wall_config.get("hp_per_click", 10)
        reinforce_cost_per_hp = wall_config.get("reinforce_cost_per_hp", 1.0)
        click_cost = hp_per_click * reinforce_cost_per_hp
        
        # Check DF stamina
        if player.devil_fruit_stamina < click_cost:
            self.battle_log.append(f"Wall reinforce failed: Insufficient DF stamina ({player.devil_fruit_stamina:.1f} < {click_cost:.1f})")
            return
        
        # Deduct stamina
        player.devil_fruit_stamina -= click_cost
        
        # Add HP to wall in wall system
        wall_obj = self.wall_system.get_wall(row, col, orientation)
        old_hp = wall_obj.hp if wall_obj else 0
        self.wall_system.reinforce_wall(row, col, orientation, hp_per_click)
        new_hp = wall_obj.hp if wall_obj else 0
        
        self.battle_log.append(f"WALL_DEBUG: Wall reinforced at ({row},{col},{orientation}): {old_hp} → {new_hp} HP (+{hp_per_click})")
        
        # Increment operation counter for defense phase limit
        if self.phase == "defense":
            self.wall_operations_this_phase += 1
        
        # Update or create planned action
        # Check if there's already a reinforce action for this wall
        existing_action = None
        for i, action in enumerate(self.planned_actions):
            if action[0] == "wall_reinforce" and action[1][:3] == (row, col, orientation):
                existing_action = i
                break
        
        if existing_action is not None:
            # Update existing action
            old_row, old_col, old_orient, old_count, old_cost = self.planned_actions[existing_action][1]
            new_count = old_count + 1
            new_cost = old_cost + click_cost
            self.planned_actions[existing_action] = ("wall_reinforce", (row, col, orientation, new_count, new_cost))
            self.wall_reinforce_count = new_count
            self.battle_log.append(f"Wall reinforced: +{hp_per_click} HP (total: {new_count} clicks, -{new_cost:.1f} DF stamina)")
        else:
            # Create new action
            self.planned_actions.append(("wall_reinforce", (row, col, orientation, 1, click_cost)))
            self.wall_reinforce_count = 1
            self.battle_log.append(f"Wall reinforced: +{hp_per_click} HP (1 click, -{click_cost:.1f} DF stamina)")
        
        self.debug_planned_actions_display()
        
        # Recalculate blocked tiles if in defense phase
        if self.phase == "defense":
            self.recalculate_enemy_patterns()
    
    def get_player_walls_in_range(self) -> List[Tuple[int, int, str]]:
        """Get list of player-owned walls within reinforcement range of ghost position."""
        player = self.get_current_player()
        player_id = "player1" if self.attacker_is_p1 else "player2"
        
        wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
        if not wall_config:
            return []
        
        reinforcement_range = wall_config.get("range", 5)
        # Use ghost position if available (planning mode), otherwise use actual position
        if self.ghost_row is not None and self.ghost_col is not None:
            player_pos = (self.ghost_row, self.ghost_col)
        else:
            player_pos = (player.row, player.col)
        
        walls_in_range = []
        for wall_pos in self.player_created_walls:
            row, col, orientation = wall_pos
            # Check ownership
            if self.wall_system.is_player_wall(row, col, orientation, player_id):
                # Check range
                distance = abs(row - player_pos[0]) + abs(col - player_pos[1])
                if distance <= reinforcement_range:
                    walls_in_range.append(wall_pos)
        
        return walls_in_range
    
    def check_wall_operation_limit(self) -> bool:
        """Check if wall operation limit is reached in defense phase."""
        if self.phase != "defense":
            return False  # No limit in attack phase
        return self.wall_operations_this_phase >= 3
    
    def can_perform_wall_operation(self) -> bool:
        """Check if player can perform wall operation (respects defense limit)."""
        if self.phase != "defense":
            return True  # No limit in attack phase
        
        if self.wall_operations_this_phase >= 3:
            self.battle_log.append("Wall operation failed: Limit reached in defense phase (3 max)")
            return False
        return True
    
    def recalculate_enemy_patterns(self) -> None:
        """Recalculate attack patterns and blocked tiles after wall changes in defensive phase.
        This includes both the enemy's attack AND the defender's counter attack if selected.
        """
        # Only recalculate if we're in defense phase
        if self.phase != "defense":
            return
        
        self.battle_log.append("WALL_DEBUG: Recalculating patterns after wall change")
        
        # Log current wall state
        h_walls = self.wall_system.get_all_horizontal_walls()
        v_walls = self.wall_system.get_all_vertical_walls()
        self.battle_log.append(f"WALL_DEBUG: Current walls: {len(h_walls)} horizontal, {len(v_walls)} vertical")
        
        # === PART 1: Recalculate ENEMY attack pattern ===
        if hasattr(self, 'pending_attack') and self.pending_attack:
            print(f"\n=== RECALCULATING ENEMY ATTACK PATTERN ===")
            print(f"Pending attack: {self.pending_attack}")
            
            before_count = len(self.attack_highlighted_squares)
            before_blocked = len(self.blocked_tiles_map)
            before_breakthrough = len(self.breakthrough_squares)
            
            # Compute the full enemy attack pattern from stored attack
            all_pattern_tiles = self._compute_attack_pattern_from_stored(self.pending_attack)
            print(f"Enemy attack pattern: {len(all_pattern_tiles)} tiles = {all_pattern_tiles}")
            
            # Separate normal attack tiles from breakthrough tiles
            # This will re-filter walls and populate blocked_tiles_map
            self.attack_highlighted_squares, self.breakthrough_squares = self._separate_breakthrough_tiles(all_pattern_tiles)
            
            after_count = len(self.attack_highlighted_squares)
            after_blocked = len(self.blocked_tiles_map)
            after_breakthrough = len(self.breakthrough_squares)
            
            print(f"Enemy pattern after: {after_count} attack, {after_breakthrough} breakthrough, {after_blocked} blocked")
            self.battle_log.append(f"WALL_DEBUG: Enemy pattern: {after_count} attack, {after_blocked} blocked, {after_breakthrough} breakthrough")
            self.battle_log.append(f"WALL_DEBUG: Enemy change: {after_count - before_count:+d} attack, {after_blocked - before_blocked:+d} blocked, {after_breakthrough - before_breakthrough:+d} breakthrough")
        else:
            self.battle_log.append("WALL_DEBUG: No enemy pending_attack to recalculate")
        
        # === PART 2: Recalculate DEFENDER counter attack pattern (if counter selected) ===
        has_counter = any(a for a in self.planned_actions if a[0] == "defense" and a[1] == "counter")
        if has_counter:
            print(f"\n=== RECALCULATING DEFENDER COUNTER PATTERN ===")
            
            # Store enemy pattern temporarily
            enemy_attack_tiles = list(self.attack_highlighted_squares)
            enemy_breakthrough_tiles = list(self.breakthrough_squares)
            enemy_blocked_map = dict(self.blocked_tiles_map)
            
            # Compute defender's counter attack pattern using current ghost position
            if self.ghost_row is not None and self.ghost_col is not None:
                # Counter uses quick attack pattern (range 1)
                counter_pattern = self._compute_attack_pattern_preview()
                print(f"Defender counter pattern (raw): {len(counter_pattern)} tiles = {counter_pattern}")
                
                # Separate counter attack tiles with wall filtering
                counter_attack_tiles, counter_breakthrough_tiles = self._separate_breakthrough_tiles(counter_pattern)
                
                print(f"Defender counter after separation: {len(counter_attack_tiles)} attack, {len(counter_breakthrough_tiles)} breakthrough")
                self.battle_log.append(f"WALL_DEBUG: Defender counter: {len(counter_attack_tiles)} attack, {len(self.blocked_tiles_map)} blocked, {len(counter_breakthrough_tiles)} breakthrough")
                
                # Store defender's counter pattern separately for UI display
                # When hovering over enemy, we show enemy pattern
                # When not hovering, we show defender's counter pattern
                self.defender_counter_attack_tiles = counter_attack_tiles
                self.defender_counter_breakthrough_tiles = counter_breakthrough_tiles
                self.defender_counter_blocked_map = dict(self.blocked_tiles_map)
                
                # Restore enemy pattern as primary display (will be overridden by hover)
                self.attack_highlighted_squares = enemy_attack_tiles
                self.breakthrough_squares = enemy_breakthrough_tiles
                self.blocked_tiles_map = enemy_blocked_map
                
                print(f"Stored defender counter separately, restored enemy as primary")
            else:
                print(f"No ghost position for counter pattern calculation")
        
        print(f"=== RECALCULATION COMPLETE ===\n")

    def undo_last_planned_action(self) -> None:
        if not self.planned_actions:
            return
        last = self.planned_actions.pop()
        if last[0] == "haki":
            # Undo specific Haki alloy application - refund cost
            haki_type = last[1]
            player = self.get_current_player()
            cost = self.haki_alloy_costs.get(haki_type, 0)
            player.haki_stamina += cost
            self.applied_haki_alloys.discard(haki_type)
            self.haki_alloy_costs.pop(haki_type, None)
            self.battle_log.append(f"Undo Haki alloy: {haki_type} (+{cost} refund)")
        elif last[0] == "df_alloy":
            # Undo specific DF alloy application - refund cost
            alloy_type = last[1]
            player = self.get_current_player()
            cost = self.df_alloy_costs.get(alloy_type, 0)
            player.devil_fruit_stamina += cost
            self.applied_df_alloys.discard(alloy_type)
            self.df_alloy_costs.pop(alloy_type, None)
            self.battle_log.append(f"Undo DF alloy: {alloy_type} (+{cost:.1f} refund)")
        elif last[0] == "wall_create":
            # Undo wall creation
            wall_row, wall_col, orientation, cost = last[1]
            player = self.get_current_player()
            
            # Remove wall from wall system
            wall = self.wall_system.get_wall_at(wall_row, wall_col, orientation)
            if wall:
                self.wall_system._walls.remove(wall)
            
            # Remove from player created walls
            wall_tuple = (wall_row, wall_col, orientation)
            if wall_tuple in self.player_created_walls:
                self.player_created_walls.remove(wall_tuple)
            
            # Refund DF stamina
            player.devil_fruit_stamina += cost
            
            # Decrement operation counter
            if self.phase == "defense":
                self.wall_operations_this_phase = max(0, self.wall_operations_this_phase - 1)
            
            self.battle_log.append(f"Undo wall creation at ({wall_row},{wall_col},{orientation}) (+{cost:.1f} DF stamina)")
            
            # Recalculate blocked tiles if in defense phase
            if self.phase == "defense":
                self.recalculate_enemy_patterns()
        elif last[0] == "wall_reinforce":
            # Undo wall reinforcement (single click)
            wall_row, wall_col, orientation, count, total_cost = last[1]
            player = self.get_current_player()
            
            wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
            hp_per_click = wall_config.get("hp_per_click", 10)
            reinforce_cost_per_hp = wall_config.get("reinforce_cost_per_hp", 1.0)
            click_cost = hp_per_click * reinforce_cost_per_hp
            
            # Reduce wall HP
            wall = self.wall_system.get_wall_at(wall_row, wall_col, orientation)
            if wall:
                wall.hp = max(0, wall.hp - hp_per_click)
            
            # Refund DF stamina for 1 reinforcement
            player.devil_fruit_stamina += click_cost
            
            # Decrement count
            new_count = count - 1
            self.wall_reinforce_count = new_count
            
            if new_count > 0:
                # Update action with new count and cost
                new_cost = total_cost - click_cost
                self.planned_actions.append(("wall_reinforce", (wall_row, wall_col, orientation, new_count, new_cost)))
                self.battle_log.append(f"Undo wall reinforce ({wall_row},{wall_col},{orientation}): {new_count} clicks remaining (+{click_cost:.1f} DF stamina)")
            else:
                # Remove entire action
                self.wall_selected_for_reinforce = None
                self.wall_reinforce_count = 0
                # Decrement operation counter only when entire action is removed
                if self.phase == "defense":
                    self.wall_operations_this_phase = max(0, self.wall_operations_this_phase - 1)
                self.battle_log.append(f"Undo wall reinforce at ({wall_row},{wall_col},{orientation}) - action removed (+{click_cost:.1f} DF stamina)")
            
            # Recalculate blocked tiles if in defense phase
            if self.phase == "defense":
                self.recalculate_enemy_patterns()
        elif last[0] == "tile_creation":
            # Undo tile creation
            self.planned_tile_creation = None
            self.battle_log.append("Undo tile creation")
        elif last[0] in ("attack", "defense"):
            self.planning_terminal = False
            self.movement_mode = True
            # When undoing attack/defense, also remove and refund ALL applied Haki alloys
            if self.applied_haki_alloys:
                player = self.get_current_player()
                total_refund = sum(self.haki_alloy_costs.values())
                player.haki_stamina += total_refund
                self.battle_log.append(f"All Haki alloys removed (+{total_refund} refund)")
                # Remove all haki actions
                self.planned_actions = [a for a in self.planned_actions if a[0] != "haki"]
            # Also remove and refund ALL applied DF alloys
            if self.applied_df_alloys:
                player = self.get_current_player()
                total_refund = sum(self.df_alloy_costs.values())
                player.devil_fruit_stamina += total_refund
                self.battle_log.append(f"All DF alloys removed (+{total_refund:.1f} refund)")
                # Remove all df_alloy actions
                self.planned_actions = [a for a in self.planned_actions if a[0] != "df_alloy"]
            # Reset Haki alloy state when undoing attack/defense
            self.applied_haki_alloys.clear()
            self.haki_alloy_costs.clear()
            # Reset DF alloy state when undoing attack/defense
            self.applied_df_alloys.clear()
            self.df_alloy_costs.clear()
            self.battle_log.append(f"Undo {last[0]}")
        elif last[0] == "rotate":
            # Revert facing based on rotation amount (buttons & wheel)
            degrees = last[1]
            self.ghost_facing = (float(self.ghost_facing if self.ghost_facing is not None else 0) - float(degrees)) % 360
            # Remove from facing history if any rotation was tracked (edge case)
            self.battle_log.append(f"Undo rotate {degrees}°")
        elif last[0] == "move":
            # Remove last tile from path and facing history
            if len(self.current_path) > 1:
                self.current_path.pop()
                self.ghost_row, self.ghost_col = self.current_path[-1]
            if self.move_facing_history:
                self.move_facing_history.pop()
            # Recompute ALL chain state from scratch
            self._recompute_bounce_state()
            self._update_facing_chain()
            self._update_pattern_bonus()  # Recompute pattern state after path change
            self.battle_log.append("Undo move")
        # After undoing non-move actions, recompute chain from current path & facing
        self._update_facing_chain()
        self._update_pattern_bonus()  # Recompute pattern state for all undo types
        self._recompute_highlights()
        self.debug_planned_actions_display()

    def _update_pattern_bonus(self) -> None:
        """Detect pattern from current path and set active bonus (once per planning phase).
        Also track which path indices belong to the pattern for display coloring.
        """
        opp = self.get_opponent()
        facing = self.ghost_facing if self.ghost_facing is not None else self.get_current_player().facing
        result = self.pattern_evaluator.evaluate(self.current_path, facing, (opp.row, opp.col))
        self.pattern_active_bonus = result
        
        if result:
            # Pattern detected - track path range for coloring
            # Pattern covers all moves that contributed to detection
            self.pattern_name = result.get('name')
            path_len = len(self.current_path)
            if path_len > 1:
                # For now, mark all moves as part of pattern (patterns cover the whole path up to current point)
                # More sophisticated logic can track exact contributing moves per pattern type
                self.pattern_start_move_idx = 0
                self.pattern_end_move_idx = path_len - 2  # Last move index (path indices go 0 to len-2)
        else:
            # No pattern active
            self.pattern_start_move_idx = None
            self.pattern_end_move_idx = None
            self.pattern_name = None

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
        
        # Deduct DF stamina for special attacks/defenses
        for action in self.planned_actions:
            if action[0] in ("attack", "defense") and isinstance(action[1], str) and action[1].startswith("special:"):
                special_name = action[1].replace("special:", "")
                
                # Get the special action data
                phase_key = "special_attacks" if action[0] == "attack" else "special_defenses"
                special_actions = p.devil_fruit_data.get(phase_key, {}) if p.devil_fruit_data else {}
                
                if special_name in special_actions:
                    special_data = special_actions[special_name]
                    base_df_cost = special_data.get('df_stamina_cost', 0)  # Absolute points
                    
                    # Apply mastery cost reduction
                    mastery_reduction = 1 - (p.devil_fruit_mastery * 0.003)
                    actual_df_cost = base_df_cost * mastery_reduction
                    
                    # Get max DF stamina for display calculation
                    max_df = p._calculate_max_df_stamina()
                    
                    # Deduct actual DF stamina points
                    p.devil_fruit_stamina = max(0, p.devil_fruit_stamina - actual_df_cost)
                    
                    # Log the deduction
                    df_display_after = int((p.devil_fruit_stamina / max_df) * 100) if max_df > 0 else 0
                    self.battle_log.append(f"DF cost: {base_df_cost} pts (reduced to {actual_df_cost:.1f}) → {df_display_after}%")
        
        # Apply movement and facing
        if self.current_path:
            p.row, p.col = self.current_path[-1]
            p.facing = int(self.ghost_facing if self.ghost_facing is not None else p.facing) % 360
            
            # Apply tile effects for each position in path
            for path_pos in self.current_path:
                path_row, path_col = path_pos
                # Get tile at position to retrieve its config
                tile_at_pos = self.tile_system.get_tile_at(path_row, path_col)
                tile_cfg = getattr(tile_at_pos, 'tile_config', None) if tile_at_pos else None
                
                tile_effect_result = self.tile_system.apply_tile_effect(p, path_row, path_col, self.effects_engine, tile_cfg)
                
                if tile_effect_result:
                    # Handle effect based on type
                    if isinstance(tile_effect_result, dict) and 'effect_obj' in tile_effect_result:
                        # Status effect (trap)
                        effect = tile_effect_result['effect_obj']
                        effect_type = tile_effect_result['effect_type']
                        
                        # Apply instant damage if applicable
                        if effect.category == "instant_damage":
                            instant_dmg = self.effects_engine.apply_instant_effect(effect, p)
                            self.battle_log.append(f"Tile {effect_type}: {instant_dmg} instant damage → {p.name}")
                            
                            if p.health == 0:
                                self.game_active = False
                                opponent = self.get_opponent()
                                self.winner = opponent.name
                                self.battle_log.append(f"KO from tile effect! Winner: {self.winner}")
                                return
                        else:
                            # Add to active effects (DoT, debuffs, stamina drain)
                            if self.effects_engine.should_stack_effect(self.active_effects[p.name], effect):
                                self.active_effects[p.name].append(effect)
                                self.battle_log.append(f"Tile effect applied: {effect_type} → {p.name}")
                    elif isinstance(tile_effect_result, str):
                        # Simple effect type (health/stamina restore)
                        self.battle_log.append(f"Tile effect: {tile_effect_result} → {p.name}")
        
        # Execute tile creation if planned
        if self.planned_tile_creation:
            tile_data = self.planned_tile_creation
            tile_row = tile_data["row"]
            tile_col = tile_data["col"]
            tile_config = tile_data["tile_config"]
            
            # Get HP from config
            hp_range = tile_config.get("hp_range", [100, 100])
            if isinstance(hp_range, list) and len(hp_range) >= 2:
                tile_hp = hp_range[1]  # Use max HP for created tiles
            else:
                tile_hp = 100
            
            # Get tile type
            tile_type = tile_config.get("tile_type", "trap_continuous")
            
            # Create tile in tile_system
            from engine.tiles import Tile
            new_tile = Tile(tile_row, tile_col, tile_type, tile_hp, duration=None)
            # Store tile config reference for effect lookup
            new_tile.tile_config = tile_config
            self.tile_system._tiles[(tile_row, tile_col)] = new_tile
            
            # Deduct DF stamina
            df_cost = tile_data["df_cost"]
            max_df = p._calculate_max_df_stamina()
            actual_df_cost = (df_cost / 100.0) * max_df if max_df > 0 else 0
            p.devil_fruit_stamina = max(0, p.devil_fruit_stamina - actual_df_cost)
            
            self.battle_log.append(f"Tile created at ({tile_row},{tile_col}): {tile_type} ({tile_hp} HP)")
            
            # Clear planned tile
            self.planned_tile_creation = None
        
        if self.phase == "attack":
            # Determine skip/miss - if no attack selected, treat as skip
            skip = any(a for a in self.planned_actions if a[0] == "attack" and a[1] == "skip")
            attack_selected = any(a for a in self.planned_actions if a[0] == "attack" and a[1] != "skip")
            
            # If no attack action selected at all, treat as skip
            if not skip and not attack_selected:
                skip = True
                p.stamina = min(p.stamina + 30, 100)
                self.battle_log.append("No attack selected - treated as Skip (+30 stamina)")
            
            miss = False
            if attack_selected:
                # Get both normal attack tiles AND breakthrough tiles
                attack_tiles = self.attack_highlighted_squares if self.attack_highlighted_squares else self._compute_attack_pattern_preview()
                breakthrough_tiles = self.breakthrough_squares if self.breakthrough_squares else []
                
                d = self.get_opponent()
                defender_pos = (d.row, d.col)
                
                # Defender is HIT if on normal attack tiles OR breakthrough tiles
                miss = defender_pos not in attack_tiles and defender_pos not in breakthrough_tiles
                
                print(f"\n=== MISS CHECK ===")
                print(f"Defender position: {defender_pos}")
                print(f"Attack tiles ({len(attack_tiles)}): {attack_tiles}")
                print(f"Breakthrough tiles ({len(breakthrough_tiles)}): {breakthrough_tiles}")
                print(f"Miss: {miss}")
                print(f"=== MISS CHECK END ===")
            
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
                    attacker = self.get_current_player()
                    defender = self.get_opponent()
                    
                    # Set Haki activation flags based on applied alloys
                    if "armament" in self.applied_haki_alloys:
                        self.attacker_arm_active = True
                    if "observation" in self.applied_haki_alloys:
                        self.attacker_obs_active = True
                    
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
                # Skip/Rest: gain +30 stamina
                p.stamina = min(p.stamina + 30, 100)
                self.battle_log.append(f"Attacker skip/rest → defense phase skipped, gained 30 stamina")
                # Clear any pending attack from previous turn
                self.pending_attack = None
            elif miss:
                self.battle_log.append("Attack miss → defense phase skipped")
                # Clear pending attack on miss
                self.pending_attack = None
            
            if skip or miss:
                # Defense phase skipped, but STILL apply wall damage if attack was selected
                if attack_selected and not skip:  # Only on miss, NOT skip
                    # Miss: Apply wall damage before ending turn
                    attack_type = None
                    for action in self.planned_actions:
                        if action[0] == "attack" and action[1] != "skip":
                            attack_type = action[1]
                            break
                    if attack_type:
                        attacker = self.get_current_player()
                        
                        # Get bonuses
                        facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
                        bounce_bonus = 0.0
                        if self.bounce_active:
                            hits = [0.10, 0.125, 0.15, 0.175, 0.20]
                            idx = min(max(1, self.bounce_chain_length), 5) - 1
                            bounce_bonus = hits[idx]
                        pattern_dmg = 0.0
                        if self.pattern_memory:
                            pattern_dmg = self.pattern_memory.get('damage_bonus', 0.0)
                        
                        # Compute attack pattern
                        attack_info = {
                            'type': attack_type,
                            'attacker_row': attacker.row,
                            'attacker_col': attacker.col,
                            'attacker_facing': attacker.facing
                        }
                        attack_tiles = self._compute_attack_pattern_from_stored(attack_info)
                        
                        print(f"\n--- WALL DAMAGE (MISS - NO DEFENSE) ---")
                        print(f"DEBUG WALL: Attack={attack_type}, Pattern tiles={len(attack_tiles)}")
                        
                        attack_base_damage = {'quick': 10, 'normal': 20, 'heavy': 30}.get(attack_type, 20)
                        wall_damage = int(attack_base_damage * (1.0 + facing_bonus + bounce_bonus + pattern_dmg))
                        
                        print(f"DEBUG WALL: Base={attack_base_damage}, Bonuses: face={facing_bonus:.2f}, bounce={bounce_bonus:.2f}, ptt={pattern_dmg:.2f}")
                        print(f"DEBUG WALL: Final wall damage={wall_damage} (no strength mult)")
                        
                        breakthrough_tiles_damage = self._apply_wall_damage_to_pattern(attack_tiles, wall_damage)
                        print(f"--- WALL DAMAGE END ---\n")
                        # Note: No player damage on miss, breakthrough doesn't matter here
                
                # Defense phase skipped; defender becomes next attacker
                self.phase = "attack"
                self.attacker_is_p1 = not self.attacker_is_p1
            else:
                # Normal flow: proceed to defense with same attacker
                self.phase = "defense"
        else:
            # Defense phase confirmed - NOW execute the combat resolution
            print(f"\n{'='*60}")
            print(f"DEBUG DEFENSE PHASE: pending_attack={getattr(self, 'pending_attack', None)}")
            print(f"DEBUG DEFENSE PHASE: Current phase={self.phase}, attacker_is_p1={self.attacker_is_p1}")
            
            # HARD CHECK: If no pending_attack, skip defense entirely
            if not hasattr(self, 'pending_attack') or not self.pending_attack:
                print("DEBUG DEFENSE PHASE: No pending attack - FORCE SKIP defense phase")
                print(f"{'='*60}\n")
                # Skip to next attack phase
                self.phase = "attack"
                self.attacker_is_p1 = not self.attacker_is_p1
                self.cancel_planning()
                self.battle_log.append(f"Defense skipped (no attack) → next phase: {self.phase}, attacker_is_p1={self.attacker_is_p1}")
                return
            
            # Check if defense action selected - if not, treat as Tank
            defense_selected = any(a for a in self.planned_actions if a[0] == "defense")
            if not defense_selected:
                defender = self.get_opponent()
                defender.stamina = min(defender.stamina + 30, 100)
                self.battle_log.append("No defense selected - treated as Tank (+30 stamina)")
            
            if hasattr(self, 'pending_attack') and self.pending_attack:
                attack_info = self.pending_attack
                attack_type = attack_info['type']
                print(f"DEBUG DEFENSE PHASE: Executing combat with attack_type={attack_type}")
                print(f"DEBUG DEFENSE PHASE: Attack info: {attack_info}")
                
                # Get attacker and defender (roles are based on stored attacker_is_p1)
                if attack_info['attacker_is_p1']:
                    attacker = self.player1
                    defender = self.player2
                else:
                    attacker = self.player2
                    defender = self.player1
                
                # Set defender Haki activation flags based on applied alloys
                if "armament" in self.applied_haki_alloys:
                    self.defender_arm_active = True
                if "observation" in self.applied_haki_alloys:
                    self.defender_obs_active = True
                
                # Base damage for all attacks
                # Base damage before special modifiers
                base_damage = 20
                
                # Get bonuses (from attack phase planning)
                facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
                bounce_bonus = 0.0
                if self.bounce_active:
                    hits = [0.10, 0.125, 0.15, 0.175, 0.20]
                    idx = min(max(1, self.bounce_chain_length), 5) - 1
                    bounce_bonus = hits[idx]
                pattern_hit = 0.0
                pattern_dmg = 0.0
                if self.pattern_memory:
                    pattern_hit = self.pattern_memory.get('hit_bonus', 0.0)
                    pattern_dmg = self.pattern_memory.get('damage_bonus', 0.0)

                # Special Devil Fruit attacks: apply JSON-driven damage & hit modifiers
                calc_attack_type = attack_type
                if isinstance(attack_type, str) and attack_type.startswith("special:"):
                    special_name = attack_type.split(":", 1)[1]
                    special_data = None
                    if attacker.devil_fruit_data:
                        special_actions = attacker.devil_fruit_data.get("special_attacks", {})
                        special_data = special_actions.get(special_name)
                    if special_data:
                        df_dmg_mod = special_data.get('damage_modifier', 0)
                        df_hit_mod = special_data.get('hit_chance_modifier', 0)
                        # Damage modifier is a percentage applied to the universal base (20)
                        base_damage = max(1, int(round(base_damage * (1.0 + df_dmg_mod / 100.0))))
                        # Hit chance modifier is absolute percentage points (e.g. -10 → -0.10)
                        pattern_hit += df_hit_mod / 100.0
                    # Specials use neutral attack type for quick/normal/heavy modifiers
                    calc_attack_type = "normal"
                
                # Apply wall damage BEFORE player damage calculation
                attack_tiles = self._compute_attack_pattern_from_stored(attack_info)
                print(f"\n--- WALL DAMAGE (DEFENSE PHASE) ---")
                print(f"DEBUG WALL: Attack pattern tiles ({len(attack_tiles)}): {attack_tiles}")
                
                attack_base_damage = {'quick': 10, 'normal': 20, 'heavy': 30}.get(attack_type, 20)
                wall_damage = int(attack_base_damage * (1.0 + facing_bonus + bounce_bonus + pattern_dmg))
                
                print(f"DEBUG WALL: Attack={attack_type}, Base={attack_base_damage}")
                print(f"DEBUG WALL: Bonuses -> face={facing_bonus:.2f}, bounce={bounce_bonus:.2f}, ptt={pattern_dmg:.2f}")
                print(f"DEBUG WALL: Final wall damage={wall_damage} (no strength mult)")
                print(f"DEBUG WALL: Blocked tiles BEFORE damage: {list(self.blocked_tiles_map.keys())}")
                
                breakthrough_tiles_damage = self._apply_wall_damage_to_pattern(attack_tiles, wall_damage)
                
                print(f"--- WALL DAMAGE END ---\n")
                print(f"\n=== BREAKTHROUGH CALCULATION RESULT ===")
                print(f"Total breakthrough tiles: {len(breakthrough_tiles_damage)}")
                print(f"Breakthrough tiles with passthrough damage: {breakthrough_tiles_damage}")
                print(f"Blocked tiles map AFTER damage (walls survived): {list(self.blocked_tiles_map.keys())}")
                print(f"=== BREAKTHROUGH CALCULATION END ===")
                
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
                
                # Hit chance (attack vs defender on pattern/breakthrough)
                hit_chance = calculate_hit_chance(
                    attacker, defender, calc_attack_type, None,
                    facing_bonus, bounce_bonus, pattern_hit,
                    df_multipliers, haki_obs_eff_attacker, haki_obs_eff_defender,
                    is_defense_phase=False
                )
                print(f"DEBUG HIT: hit_chance={hit_chance:.3f}")
                
                # Calculate damage
                print(f"\n=== CALCULATING BASE DAMAGE ===")
                print(f"Attacker: {attacker.name} | Defender: {defender.name}")
                print(f"Attack type: {attack_type} | Base damage: {base_damage}")
                print(f"Facing bonus: {facing_bonus:.2f} | Bounce bonus: {bounce_bonus:.2f} | Pattern bonus: {pattern_dmg:.2f}")
                print(f"Haki obs attacker: {haki_obs_eff_attacker:.2f} | Haki obs defender: {haki_obs_eff_defender:.2f}")
                print(f"Haki arm attacker: {haki_arm_eff_attacker:.2f} | Haki arm defender: {haki_arm_eff_defender:.2f}")
                print(f"DF multipliers: {df_multipliers}")
                
                dmg = calculate_damage(
                    attacker, defender, base_damage, calc_attack_type, None,
                    facing_bonus, bounce_bonus, pattern_dmg,
                    df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                    is_defense_phase=False
                )
                dmg = max(1, int(dmg))
                print(f"Calculated base damage: {dmg}")
                print(f"=== BASE DAMAGE CALCULATION COMPLETE ===")
                
                # CRITICAL: Check defender position
                defender_tile = (defender.row, defender.col)
                print(f"\n=== DEFENDER POSITION CHECK ===")
                print(f"Defender tile: {defender_tile}")
                print(f"Attack tiles: {attack_tiles}")
                print(f"Breakthrough tiles from damage calc: {list(breakthrough_tiles_damage.keys())}")
                print(f"Breakthrough tile values: {breakthrough_tiles_damage}")
                print(f"Blocked tiles map: {list(self.blocked_tiles_map.keys())}")
                print(f"Is defender in breakthrough? {defender_tile in breakthrough_tiles_damage}")
                print(f"Is defender in attack tiles? {defender_tile in attack_tiles}")
                print(f"Is defender in blocked map? {defender_tile in self.blocked_tiles_map}")
                
                # HIT CHECK: roll once if defender is on an attack or breakthrough tile
                import random
                hit_success = True
                hit_roll = None
                if defender_tile in breakthrough_tiles_damage or defender_tile in attack_tiles:
                    hit_roll = random.random()
                    hit_success = hit_roll <= hit_chance
                    print(f"DEBUG HIT ROLL: chance={hit_chance:.3f}, roll={hit_roll:.3f}, success={hit_success}")
                
                # SIMPLE LOGIC: Defender on breakthrough tile = apply breakthrough damage (only if hit succeeds)
                if defender_tile in breakthrough_tiles_damage:
                    if not hit_success:
                        print(f"\n=== HIT CHANCE MISS ON BREAKTHROUGH TILE ===")
                        print(f"Defender at {defender_tile} on breakthrough tile but hit roll failed")
                        self.battle_log.append("Attack missed due to hit chance roll")
                        dmg = 0
                    else:
                        # Breakthrough: wall destroyed, apply reduced damage
                        passthrough_dmg = breakthrough_tiles_damage[defender_tile]
                        print(f"\n=== BREAKTHROUGH HIT - REDUCED DAMAGE ===")
                        print(f"Defender at {defender_tile} - wall destroyed, applying breakthrough damage")
                        print(f"Original base damage: {base_damage}")
                        print(f"Passthrough damage (attack - wall HP): {passthrough_dmg}")
                        print(f"Recalculating damage with passthrough as new base...")
                        
                        # Use passthrough damage as base, but still apply all combat modifiers
                        dmg_breakthrough = calculate_damage(
                            attacker, defender, passthrough_dmg, "normal", None,
                            facing_bonus, bounce_bonus, pattern_dmg,
                            df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                            is_defense_phase=False
                        )
                        dmg = max(0, int(dmg_breakthrough))
                        
                        print(f"\n=== BREAKTHROUGH DAMAGE FORMULA ===")
                        print(f"Input: passthrough_base={passthrough_dmg}")
                        print(f"Attacker: STR={attacker.strength}, DEF={attacker.defense}, SPD={attacker.speed}")
                        print(f"Defender: STR={defender.strength}, DEF={defender.defense}, SPD={defender.speed}, REA={defender.reaction}, END={defender.endurance}")
                        print(f"Attack type: {attack_type}")
                        print(f"Bonuses: facing={facing_bonus:.2f}, bounce={bounce_bonus:.2f}, pattern={pattern_dmg:.2f}")
                        print(f"DF multipliers: {df_multipliers}")
                        print(f"Haki arm (attacker/defender): {haki_arm_eff_attacker:.2f}/{haki_arm_eff_defender:.2f}")
                        print(f"Final breakthrough damage after all modifiers: {dmg}")
                        print(f"=== BREAKTHROUGH DAMAGE FORMULA END ===")
                        
                        self.battle_log.append(f"Breakthrough! Wall destroyed, reduced damage: {dmg}")
                elif defender_tile in attack_tiles:
                    if not hit_success:
                        print(f"\n=== HIT CHANCE MISS ON ATTACK TILE ===")
                        print(f"Defender at {defender_tile} on attack tile but hit roll failed")
                        self.battle_log.append("Attack missed due to hit chance roll")
                        dmg = 0
                    else:
                        # Normal hit: defender on unblocked attack tile
                        print(f"\n=== NORMAL HIT - FULL DAMAGE ===")
                        print(f"Defender at {defender_tile} on normal attack tile - FULL DAMAGE={dmg}")
                        # dmg already calculated
                elif defender_tile in self.blocked_tiles_map:
                    # Blocked: wall survived
                    print(f"\n=== BLOCKED TILE - NO DAMAGE ===")
                    print(f"Defender at {defender_tile} is protected by wall that survived")
                    print(f"Wall(s) blocking this tile: {self.blocked_tiles_map[defender_tile]}")
                    self.battle_log.append(f"Attack blocked by wall! Defender takes no damage")
                    dmg = 0
                else:
                    # Defender not in pattern at all
                    print(f"\n=== MISS - NO DAMAGE ===")
                    print(f"Defender at {defender_tile} is NOT in attack pattern")
                    self.battle_log.append(f"Attack missed! Defender not in pattern")
                    dmg = 0
                
                print(f"=== FINAL DAMAGE: {dmg} ===")
                print(f"\n=== APPLYING DAMAGE TO DEFENDER ===")
                print(f"Defender {defender.name} health BEFORE: {defender.health}")
                print(f"Damage to apply: {dmg}")
                
                defender.health = max(0, defender.health - dmg)
                
                print(f"Defender {defender.name} health AFTER: {defender.health}")
                print(f"=== DAMAGE APPLICATION COMPLETE ===")
                
                # Check if Tank defense was used - grant +30 stamina
                defense_type = None
                for action in self.planned_actions:
                    if action[0] == "defense":
                        defense_type = action[1]
                        break
                
                if defense_type == "tank":
                    defender.stamina = min(defender.stamina + 30, 100)
                    self.battle_log.append(f"Combat resolved: {dmg} damage → {defender.name} health={defender.health}, gained 30 stamina (Tank)")
                    print(f"DEBUG: Tank defense - granted 30 stamina, defender stamina now: {defender.stamina}")
                else:
                    self.battle_log.append(f"Combat resolved: {dmg} damage → {defender.name} health={defender.health}")
                
                print(f"DEBUG: Damage applied: {dmg}, defender health now: {defender.health}")
                
                # Check for KO
                if defender.health == 0:
                    self.game_active = False
                    self.winner = attacker.name
                    self.battle_log.append(f"KO! Winner: {self.winner}")
                else:
                    # Apply push
                    # Calculate attack quality to determine push distance
                    quality = get_attack_quality(dmg, base_damage)
                    print(f"DEBUG PUSH: Attack quality calculation - damage={dmg}, base_damage={base_damage}, quality={quality}")
                    
                    push_dist = get_push_distance(quality)
                    print(f"DEBUG PUSH: Push distance for quality '{quality}': {push_dist} tiles")
                    
                    if push_dist > 0:
                        # Temporarily set attacker_is_p1 for push calculation
                        old_attacker_flag = self.attacker_is_p1
                        self.attacker_is_p1 = attack_info['attacker_is_p1']
                        print(f"DEBUG PUSH: Applying push - attacker facing: {attacker.facing}, defender at ({defender.row},{defender.col})")
                        pushed = self.apply_push_to_defender(push_dist)
                        print(f"DEBUG PUSH: Pushed {pushed} tiles (attempted {push_dist})")
                        self.attacker_is_p1 = old_attacker_flag
                        if pushed > 0:
                            self.battle_log.append(f"Push: {defender.name} pushed {pushed} tile(s)")
                    else:
                        print(f"DEBUG PUSH: No push applied - attack quality too low ({quality})")
                
                # Clear pending attack
                self.pending_attack = None
                
                # Store special attack effect for turn-end processing (after combat, before next turn)
                if attack_type.startswith("special:"):
                    special_name = attack_type.split(":", 1)[1]
                    self.battle_log.append(f"EFFECT_DEBUG: Special attack detected: {special_name}")
                    
                    if attacker.devil_fruit_data:
                        phase_key = "special_attacks"
                        special_actions = attacker.devil_fruit_data.get(phase_key, {})
                        special_data = special_actions.get(special_name)
                        self.battle_log.append(f"EFFECT_DEBUG: Phase={phase_key}, special_data={'found' if special_data else 'NOT FOUND'}")
                        
                        if special_data and "effect" in special_data:
                            effect_config = special_data["effect"]
                            effect_type = effect_config.get("type")
                            effect_category = effect_config.get("category")
                            self.battle_log.append(f"EFFECT_DEBUG: effect_type={effect_type}, category={effect_category}")
                            
                            if effect_type and effect_category:
                                # Get defender's resistance
                                resistance = 1.0
                                if defender.devil_fruit_data and "effect_resistance" in defender.devil_fruit_data:
                                    resistance = defender.devil_fruit_data["effect_resistance"].get(effect_type, 1.0)
                                    resistance = resistance * (defender.devil_fruit_mastery / 100.0)
                                self.battle_log.append(f"EFFECT_DEBUG: resistance={resistance}, attacker_mastery={attacker.devil_fruit_mastery}")
                                
                                # Calculate effect
                                effect = self.effects_engine.calculate_effect(
                                    effect_type, effect_category, attacker.devil_fruit_mastery, resistance
                                )
                                self.battle_log.append(f"EFFECT_DEBUG: Calculated effect={'SUCCESS' if effect else 'FAILED'}")
                                
                                if effect:
                                    self.battle_log.append(f"EFFECT_DEBUG: Effect magnitude={effect.magnitude}, duration={effect.duration}")
                                    # Store for turn-end processing
                                    if not hasattr(self, 'pending_effects'):
                                        self.pending_effects = []
                                    self.pending_effects.append({'effect': effect, 'target': defender.name})
                                    self.battle_log.append(f"EFFECT_DEBUG: Effect queued for turn-end processing")
                            else:
                                self.battle_log.append(f"EFFECT_DEBUG: Missing effect_type or category in config")
                        else:
                            self.battle_log.append(f"EFFECT_DEBUG: No 'effect' key in special_data")
                    else:
                        self.battle_log.append(f"EFFECT_DEBUG: Attacker has no devil_fruit_data")
            else:
                print("DEBUG DEFENSE PHASE: No pending attack found!")
                print(f"DEBUG DEFENSE PHASE: hasattr={hasattr(self, 'pending_attack')}, value={getattr(self, 'pending_attack', 'NO ATTR')}")
            print(f"{'='*60}\n")
            
            # Defense resolved; next attacker is prior defender
            self.phase = "attack"
            self.attacker_is_p1 = not self.attacker_is_p1
        
        # Reset Haki activation flags after turn ends
        self.attacker_obs_active = False
        self.attacker_arm_active = False
        self.defender_obs_active = False
        self.defender_arm_active = False
        
        # Apply pending effects from special attacks (after combat, before next turn)
        if hasattr(self, 'pending_effects') and self.pending_effects:
            self.battle_log.append(f"EFFECT_DEBUG: Processing {len(self.pending_effects)} pending effects")
            for pending in self.pending_effects:
                effect = pending['effect']
                target_name = pending['target']
                target_player = self.player1 if target_name == self.player1.name else self.player2
                
                self.battle_log.append(f"EFFECT_DEBUG: Applying {effect.effect_type} to {target_name}")
                
                # Apply instant damage if applicable
                if effect.category == "instant_damage":
                    instant_dmg = self.effects_engine.apply_instant_effect(effect, target_player)
                    self.battle_log.append(f"EFFECT_DEBUG: Instant damage applied: {instant_dmg}")
                    self.battle_log.append(f"{effect.effect_type.capitalize()} instant damage: {instant_dmg} → {target_name}")
                    
                    if target_player.health == 0:
                        self.game_active = False
                        self.winner = self.player1.name if target_name == self.player2.name else self.player2.name
                        self.battle_log.append(f"KO from {effect.effect_type} instant damage! Winner: {self.winner}")
                        return
                else:
                    # Add to active effects (DoT, debuffs, stamina drain)
                    if self.effects_engine.should_stack_effect(self.active_effects[target_name], effect):
                        self.active_effects[target_name].append(effect)
                        self.battle_log.append(f"EFFECT_DEBUG: Effect added to active_effects list")
                        self.battle_log.append(f"Effect applied: {effect.effect_type} → {target_name}")
                    else:
                        self.battle_log.append(f"EFFECT_DEBUG: Effect BLOCKED by stacking rules")
            
            # Clear pending effects
            self.pending_effects = []
            self.battle_log.append(f"EFFECT_DEBUG: Pending effects cleared")
        
        # Process effects at turn end (after combat, before next turn)
        # 1. Process DoT effects
        for player_name in [self.player1.name, self.player2.name]:
            player = self.player1 if player_name == self.player1.name else self.player2
            effects_to_process = list(self.active_effects[player_name])
            
            for effect in effects_to_process:
                self.battle_log.append(f"EFFECT_DEBUG: Processing {effect.effect_type} on {player_name}, duration={effect.duration}")
                
                # Apply DoT damage
                if effect.category == "damage_over_time":
                    old_health = player.health
                    player.health = max(0, player.health - effect.magnitude)
                    self.battle_log.append(f"EFFECT_DEBUG: DoT damage {effect.magnitude} → {player_name} health {old_health}→{player.health}")
                    self.battle_log.append(f"{effect.effect_type.capitalize()} effect: {effect.magnitude} damage → {player_name}")
                    
                    if player.health == 0:
                        self.game_active = False
                        self.winner = self.player1.name if player_name == self.player2.name else self.player2.name
                        self.battle_log.append(f"KO from {effect.effect_type} effect! Winner: {self.winner}")
                        return
                
                # Apply stamina drain
                elif effect.category == "stamina_drain":
                    drain_amount = int(player.stamina * (effect.magnitude / 100.0))
                    old_stamina = player.stamina
                    player.stamina = max(0, player.stamina - drain_amount)
                    self.battle_log.append(f"EFFECT_DEBUG: Stamina drain {drain_amount} → {player_name} stamina {old_stamina}→{player.stamina}")
                    self.battle_log.append(f"{effect.effect_type.capitalize()} effect: {drain_amount} stamina drained → {player_name}")
                
                # Decrement duration
                effect.duration -= 1
                self.battle_log.append(f"EFFECT_DEBUG: {effect.effect_type} duration decremented to {effect.duration}")
            
            # Remove expired effects (duration == 0)
            before_count = len(self.active_effects[player_name])
            self.active_effects[player_name] = [e for e in self.active_effects[player_name] if e.duration > 0]
            after_count = len(self.active_effects[player_name])
            if before_count > after_count:
                self.battle_log.append(f"EFFECT_DEBUG: Removed {before_count - after_count} expired effects from {player_name}")
        
        # Recover Haki stamina at turn end
        p1_haki_recovery = self.player1.recover_haki_stamina()
        p2_haki_recovery = self.player2.recover_haki_stamina()
        self.battle_log.append(f"Haki recovery: {self.player1.name} +{int(p1_haki_recovery)}, {self.player2.name} +{int(p2_haki_recovery)}")
        
        # Recover DF stamina at turn end (only during attack phase per spec 3.5)
        if self.phase == 'attack':
            p1_df_recovery = self.player1.recover_df_stamina()
            p2_df_recovery = self.player2.recover_df_stamina()
            if p1_df_recovery > 0 or p2_df_recovery > 0:
                self.battle_log.append(f"DF recovery: {self.player1.name} +{p1_df_recovery:.1f}, {self.player2.name} +{p2_df_recovery:.1f}")
        
        # Apply tile effects after turn confirmation (before planning cancels)
        p = self.get_current_player()
        
        # Create planned tile if exists
        if self.planned_tile_creation:
            tile_data = self.planned_tile_creation
            row, col = tile_data["row"], tile_data["col"]
            tile_config = tile_data["tile_config"]
            
            # Calculate tile HP using same formula as normal tiles
            base_hp = int(100 + self.avg_primary_sum * 0.5)
            
            # Create tile in tile_system
            tile_type_map = tile_config.get("tile_type", "trap_continuous")
            duration = None  # Continuous tiles have no duration
            if "momentary" in tile_type_map:
                duration = random.randint(1, 3)
            
            # Remove existing tile at position if any
            self.tile_system.remove_tile(row, col)
            
            # Create new tile
            from engine.tiles import Tile
            new_tile = Tile(row, col, tile_type_map, base_hp, duration)
            self.tile_system._tiles[(row, col)] = new_tile
            
            # Deduct DF stamina
            df_cost_pts = tile_data["df_cost"]
            max_df = p._calculate_max_df_stamina()
            actual_cost = (df_cost_pts / 100.0) * max_df
            p.devil_fruit_stamina = max(0, p.devil_fruit_stamina - actual_cost)
            
            self.battle_log.append(f"Tile created at ({row},{col}): {tile_config['label']}")
            
            # Increment wall_operations counter for defense phase (3-action limit)
            if self.phase == "defense":
                self.wall_operations_this_phase += 1
            
            # Clear planned tile
            self.planned_tile_creation = None
        
        if self.current_path:
            final_row, final_col = self.current_path[-1]
            effect = self.tile_system.apply_tile_effect(p, final_row, final_col, self.effects_engine)
            if effect:
                if isinstance(effect, dict) and 'effect_obj' in effect:
                    # Trap tile - queue effect for turn-end processing
                    if not hasattr(self, 'pending_effects'):
                        self.pending_effects = []
                    self.pending_effects.append({'effect': effect['effect_obj'], 'target': p.name})
                    self.battle_log.append(f"Tile effect: {effect['effect_type']} → {p.name}")
                    
                    # Apply immediately if needed
                    effect_obj = effect['effect_obj']
                    if effect_obj.category == "instant_damage":
                        instant_dmg = self.effects_engine.apply_instant_effect(effect_obj, p)
                        self.battle_log.append(f"{effect_obj.effect_type.capitalize()} instant damage: {instant_dmg} → {p.name}")
                        if p.health == 0:
                            self.game_active = False
                            self.winner = self.player1.name if p.name == self.player2.name else self.player2.name
                            self.battle_log.append(f"KO from tile effect! Winner: {self.winner}")
                            return
                    else:
                        # Add to active effects
                        if self.effects_engine.should_stack_effect(self.active_effects[p.name], effect_obj):
                            self.active_effects[p.name].append(effect_obj)
                            self.battle_log.append(f"Effect applied from tile: {effect_obj.effect_type} → {p.name}")
                else:
                    # Drop tile - immediate restore (already applied in tile_system)
                    self.battle_log.append(f"Tile effect: {effect}")
        
        self.cancel_planning()
        # Per-turn tile maintenance
        self.tile_system.tick_durations()
        if self.phase == 'attack':
            self.tile_system.spawn_per_turn_tiles(self.avg_primary_sum)
        # Status effects maintenance
        self.tick_status_effects()
        self.battle_log.append(f"Turn confirmed → next phase: {self.phase}, attacker_is_p1={self.attacker_is_p1}")

    def cancel_planning(self) -> None:
        # Refund ALL Haki stamina if any alloys were applied
        if self.applied_haki_alloys:
            player = self.get_current_player()
            total_refund = sum(self.haki_alloy_costs.values())
            player.haki_stamina += total_refund
            self.battle_log.append(f"Planning cancelled - Haki refund: +{total_refund}")
        
        # Refund ALL DF stamina if any alloys were applied
        if self.applied_df_alloys:
            player = self.get_current_player()
            total_refund = sum(self.df_alloy_costs.values())
            player.devil_fruit_stamina += total_refund
            self.battle_log.append(f"Planning cancelled - DF refund: +{total_refund:.1f}")
        
        # Remove all created walls and refund DF stamina
        player = self.get_current_player()
        for action in self.planned_actions:
            if action[0] == "wall_create":
                wall_row, wall_col, orientation, cost = action[1]
                # Remove wall from wall system
                wall = self.wall_system.get_wall_at(wall_row, wall_col, orientation)
                if wall:
                    self.wall_system._walls.remove(wall)
                # Remove from player created walls
                wall_tuple = (wall_row, wall_col, orientation)
                if wall_tuple in self.player_created_walls:
                    self.player_created_walls.remove(wall_tuple)
                # Refund DF stamina
                player.devil_fruit_stamina += cost
                self.battle_log.append(f"Wall creation cancelled at ({wall_row},{wall_col},{orientation}) (+{cost:.1f} DF stamina)")
            elif action[0] == "wall_reinforce":
                wall_row, wall_col, orientation, count, total_cost = action[1]
                # Reduce wall HP by total reinforcement amount
                wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation") if player.devil_fruit_data else {}
                hp_per_click = wall_config.get("hp_per_click", 10)
                total_hp = hp_per_click * count
                wall = self.wall_system.get_wall_at(wall_row, wall_col, orientation)
                if wall:
                    wall.hp = max(0, wall.hp - total_hp)
                # Refund DF stamina
                player.devil_fruit_stamina += total_cost
                self.battle_log.append(f"Wall reinforcement cancelled at ({wall_row},{wall_col},{orientation}) (+{total_cost:.1f} DF stamina)")
        
        # Clear wall mode state
        self.wall_mode = None
        self.wall_first_tile = None
        self.wall_selected_for_reinforce = None
        self.wall_reinforce_count = 0
        self.wall_operations_this_phase = 0
        self.wall_placement_tiles = []
        self.wall_first_tile_highlight = None
        
        # Clear tile creation state
        self.tile_mode = False
        self.selected_tile_type = None
        self.planned_tile_creation = None
        
        self.planning_mode = False
        self.movement_mode = False
        self.planning_terminal = False
        self.current_path = []
        self.highlighted_squares = []
        self.attack_highlighted_squares = []
        self.breakthrough_squares = []
        self.ghost_row = None
        self.ghost_col = None
        self.ghost_facing = None
        # Reset alloy system state
        self.selected_alloy_tab = "attack"
        self.applied_haki_alloys.clear()
        self.haki_alloy_costs.clear()
        self.applied_df_alloys.clear()
        self.df_alloy_costs.clear()
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
        self.bounce_segments = []
        # Pattern tracking
        self.pattern_start_move_idx = None
        self.pattern_end_move_idx = None
        self.pattern_name = None

    # --- Wheel controller ---
    def get_wheel_rotation(self) -> float:
        return self.wheel_rotation

    def start_wheel_drag(self, initial_mouse_angle: float) -> None:
        if not self.planning_mode:
            return
        self.wheel_dragging = True
        self.wheel_drag_initial_mouse_angle = initial_mouse_angle
        if self.ghost_facing is None:
            self.ghost_facing = self.get_current_player().facing
        self.wheel_drag_start_facing = float(self.ghost_facing)

    def update_wheel_drag(self, new_wheel_angle: float) -> None:
        """Update wheel rotation freely during drag."""
        # Update rotation and facing freely without snapping
        normalized_angle = new_wheel_angle % 360
        self.wheel_rotation = normalized_angle
        self.ghost_facing = normalized_angle
        # DON'T recompute highlights during drag - only update facing
        # This prevents flickering and maintains terminal state
    
    def end_wheel_drag(self) -> None:
        """End wheel drag, snap to 45°, and record final rotation."""
        if not self.wheel_dragging:
            return
        self.wheel_dragging = False
        
        # Safety check for ghost_facing
        if self.ghost_facing is None:
            return
        
        print(f"DEBUG WHEEL: Before snap: ghost_facing={self.ghost_facing}")
        # Snap to nearest 45° increment
        snapped_angle = round(self.ghost_facing / 45) * 45
        print(f"DEBUG WHEEL: Snapped angle (before mod): {snapped_angle}")
        self.wheel_rotation = snapped_angle % 360
        self.ghost_facing = snapped_angle % 360
        print(f"DEBUG WHEEL: After snap: wheel_rotation={self.wheel_rotation}, ghost_facing={self.ghost_facing}")
        # Calculate total rotation delta from start to end
        if self.wheel_drag_start_facing is not None and self.ghost_facing is not None:
            delta = (self.ghost_facing - self.wheel_drag_start_facing + 360) % 360
            if delta > 180:
                delta -= 360
            print(f"DEBUG WHEEL: start_facing={self.wheel_drag_start_facing}, final_facing={self.ghost_facing}, delta={delta}")
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
            last_idx = self.bounce_end_move_idx if self.bounce_end_move_idx is not None else (len(self.current_path) - 2)
            bounce_steps = max(0, last_idx - self.bounce_start_move_idx + 1)
        if bounce_steps > 0:
            per_step_after_chain = int(base * (1.0 - chain_bonus_rate))
            # Apply scaling per step: 10%,12.5%,15%,17.5%,20%
            rates = [0.10, 0.125, 0.15, 0.175, 0.20]
            for k in range(bounce_steps):
                rate = rates[min(k, 4)]
                total -= int(per_step_after_chain * rate)
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
                        # Include one preceding rotation immediately before chain start
                        if first_act > 0 and self.planned_actions[first_act - 1][0] == "rotate":
                            action_indices = [first_act - 1] + action_indices
                    
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
                # Include one preceding rotation immediately before chain start
                if first_act > 0 and self.planned_actions[first_act - 1][0] == "rotate":
                    action_indices = [first_act - 1] + action_indices
            
            groups.append({
                "start_idx": current_chain_start,
                "end_idx": len(self.current_path) - 2,
                "chain_len": len(self.current_path) - 1 - current_chain_start,
                "color": chain_colors[color_idx % len(chain_colors)],
                "action_indices": action_indices
            })
        
        return groups

    def get_planned_actions_display(self) -> List[dict]:
        entries: List[dict] = []
        if not self.planned_actions:
            return entries
        base_cost = 15 if self.phase == "attack" else 30
        # Chain groups and mappings
        chain_groups = self.get_move_chain_groups()
        action_to_move_map: List[int] = []
        move_idx = 0
        for action in self.planned_actions:
            if action[0] == "move":
                action_to_move_map.append(move_idx)
                move_idx += 1
            else:
                action_to_move_map.append(-1)
        move_to_chain: Dict[int, dict] = {}
        for g in chain_groups:
            for i in range(g["start_idx"], g["end_idx"] + 1):
                move_to_chain[i] = g
        # Bounce scaling
        bounce_rates = [0.10, 0.125, 0.15, 0.175, 0.20]
        last_idx = self.bounce_end_move_idx if self.bounce_end_move_idx is not None else (len(self.current_path) - 2)
        # Build bounce segments (persisted + current active)
        bounce_segments = list(self.bounce_segments)
        if self.bounce_active and self.bounce_start_move_idx is not None:
            idx_rate = min(max(1, self.bounce_chain_length), 5) - 1
            bounce_segments.append({
                "start": self.bounce_start_move_idx,
                "end": last_idx,
                "rate": bounce_rates[idx_rate],
                "type": self.bounce_type,
                "label": ('Bd' if self.bounce_type == 'diagonal' else ('Bc' if self.bounce_type == 'cardinal' else ''))
            })
        # Map bounce segments to action index ranges
        bounce_action_ranges: List[Tuple[int,int,dict]] = []
        for seg in bounce_segments:
            start_move = seg["start"]
            end_move = seg["end"]
            first_act = None
            for idx, mv in enumerate(action_to_move_map):
                if mv == start_move:
                    first_act = idx
                    break
            last_act = None
            for idx in range(len(action_to_move_map)-1, -1, -1):
                if action_to_move_map[idx] == end_move:
                    last_act = idx
                    break
            if first_act is not None and last_act is not None:
                bounce_action_ranges.append((first_act, last_act, seg))
        # Determine which chain started first (for color shading logic)
        face_first_act = None
        for g in chain_groups:
            if g.get("action_indices"):
                first = min(g["action_indices"])
                face_first_act = first if face_first_act is None else min(face_first_act, first)
        bounce_first_act = None
        for rng in bounce_action_ranges:
            bfirst = rng[0]
            bounce_first_act = bfirst if bounce_first_act is None else min(bounce_first_act, bfirst)
        # Pattern first act (if pattern active)
        pattern_first_act = None
        if self.pattern_start_move_idx is not None:
            # Find first action corresponding to pattern start
            for idx, mv in enumerate(action_to_move_map):
                if mv == self.pattern_start_move_idx:
                    pattern_first_act = idx
                    break
        # Determine first chain type
        chain_starts = []
        if face_first_act is not None:
            chain_starts.append(('face', face_first_act))
        if bounce_first_act is not None:
            chain_starts.append(('bounce', bounce_first_act))
        if pattern_first_act is not None:
            chain_starts.append(('pattern', pattern_first_act))
        if not chain_starts:
            first_chain_type = None
        else:
            chain_starts.sort(key=lambda x: x[1])
            first_chain_type = chain_starts[0][0]
        # Define 3-way colors: green for pattern, red for face, blue for bounce
        # Combinations: orange (face+pattern), teal (bounce+pattern), white (all three)
        generic_color = "#FFFF00"
        pattern_only_color = "#00FF00"  # Green
        face_only_color = "#FF0000"     # Red
        bounce_only_color = "#0000FF"   # Blue
        face_pattern_color = "#FFA500"  # Orange
        bounce_pattern_color = "#00FFFF"  # Teal/Aqua
        face_bounce_color = "#800080"   # Violet (legacy)
        all_three_color = "#FFFFFF"     # White
        # Build entries
        move_index = 0
        for act_idx, action in enumerate(self.planned_actions):
            # Skip haki actions - they're tracked separately and not displayed
            if action[0] == "haki":
                continue
            if action[0] == "move":
                tile = action[1].get("tile", "")
                group = move_to_chain.get(move_index)
                group_for_act = None
                for g in chain_groups:
                    if act_idx in g.get("action_indices", []):
                        group_for_act = g
                        break
                chain_bonus = 0.0
                if group:
                    chain_bonus = min(0.10 * group["chain_len"], 0.50)
                # Color membership
                in_face = group is not None
                in_bounce_act = False
                seg_for_act = None
                # Determine bounce membership by move index (not action range)
                for seg in bounce_segments:
                    if move_index >= seg["start"] and move_index <= seg["end"]:
                        in_bounce_act = True
                        seg_for_act = seg
                        break
                # Pattern membership
                in_pattern = False
                pattern_stamina_bonus = 0.0
                ptt_hit_bonus = 0.0
                ptt_dmg_bonus = 0.0
                if self.pattern_start_move_idx is not None and self.pattern_end_move_idx is not None:
                    if move_index >= self.pattern_start_move_idx and move_index <= self.pattern_end_move_idx:
                        in_pattern = True
                        # Get all pattern bonuses
                        if self.pattern_active_bonus:
                            pattern_stamina_bonus = self.pattern_active_bonus.get('stamina_reduction', 0.0)
                            ptt_hit_bonus = self.pattern_active_bonus.get('hit_bonus', 0.0)
                            ptt_dmg_bonus = self.pattern_active_bonus.get('damage_bonus', 0.0)
                # 3-way color blending
                if in_face and in_bounce_act and in_pattern:
                    chain_color = all_three_color
                elif in_face and in_pattern:
                    chain_color = face_pattern_color
                elif in_bounce_act and in_pattern:
                    chain_color = bounce_pattern_color
                elif in_face and in_bounce_act:
                    chain_color = face_bounce_color
                elif in_pattern:
                    chain_color = pattern_only_color
                elif in_face:
                    chain_color = face_only_color
                elif in_bounce_act:
                    chain_color = bounce_only_color
                else:
                    chain_color = generic_color
                # Calculate total stamina cost with stacked bonuses
                # Base cost after facing chain discount
                move_cost = int(base_cost * (1.0 - chain_bonus))
                # Apply bounce discount
                b_label = ""
                b_pct = 0
                if seg_for_act:
                    rate = seg_for_act["rate"]
                    move_cost = int(move_cost * (1.0 - rate))
                    b_pct = int(rate * 100)
                    b_label = seg_for_act.get("label", "")
                # Apply pattern stamina reduction (additive to total discount)
                ptt_pct = int(pattern_stamina_bonus * 100)
                if pattern_stamina_bonus > 0:
                    move_cost = int(move_cost * (1.0 - pattern_stamina_bonus))
                 # Calculate individual bonus percentages
                dir_pct = int(chain_bonus * 100)
                ptt_st_pct = int(pattern_stamina_bonus * 100)
                ptt_hit_pct = int(ptt_hit_bonus * 100)
                ptt_dmg_pct = int(ptt_dmg_bonus * 100)
                # Build bonus labels
                bonus_parts = []
                if dir_pct > 0:
                    # Dir provides stamina + hit + damage on moves
                    bonus_parts.append(f"Dir -{dir_pct}% St +{dir_pct}% Hit +{dir_pct}% Dmg")
                if b_pct > 0 and b_label:
                    # Bounce provides stamina + hit on moves
                    bonus_parts.append(f"{b_label} -{b_pct}% St +{b_pct}% Hit")
                if in_pattern:
                    # Show pattern bonuses if any exist
                    ptt_parts = []
                    if ptt_st_pct > 0:
                        ptt_parts.append(f"-{ptt_st_pct}% St")
                    if ptt_hit_pct > 0:
                        ptt_parts.append(f"+{ptt_hit_pct}% Hit")
                    if ptt_dmg_pct > 0:
                        ptt_parts.append(f"+{ptt_dmg_pct}% Dmg")
                    if ptt_parts:
                        bonus_parts.append(f"Ptt {' '.join(ptt_parts)}")
                    else:
                        # Pattern active but no bonuses apply to moves (circle/spearhead)
                        bonus_parts.append("Ptt")
                # Format: "5D - 13 Stamina (Dir -10% St)(Bd -10% St)"
                bonus_text = "".join([f"({part})" for part in bonus_parts])
                text = f"  {tile} - {move_cost} Stamina {bonus_text}"
                entries.append({"type": "move", "text": text, "color": chain_color})
                move_index += 1
            elif action[0] == "rotate":
                # Color membership for rotation
                in_face = False
                for g in chain_groups:
                    if act_idx in g.get("action_indices", []):
                        in_face = True
                        break
                in_bounce_act = any(act_idx >= r[0] and act_idx <= r[1] for r in [(fa,la) for fa,la,_ in bounce_action_ranges])
                # Pattern membership for rotations: if between pattern moves, include them
                in_pattern = False
                if pattern_first_act is not None:
                    # Rotations are part of pattern chain if they're between or after pattern start
                    # For simplicity: if any pattern active and rotation is after pattern start
                    if act_idx >= pattern_first_act:
                        in_pattern = True
                # 3-way color blending
                if in_face and in_bounce_act and in_pattern:
                    chain_color = all_three_color
                elif in_face and in_pattern:
                    chain_color = face_pattern_color
                elif in_bounce_act and in_pattern:
                    chain_color = bounce_pattern_color
                elif in_face and in_bounce_act:
                    chain_color = face_bounce_color
                elif in_pattern:
                    chain_color = pattern_only_color
                elif in_face:
                    chain_color = face_only_color
                elif in_bounce_act:
                    chain_color = bounce_only_color
                else:
                    chain_color = generic_color
                deg = action[1]
                # Rotation costs 5 stamina per 45°
                rotation_cost = int((abs(deg) / 45) * 5)
                entries.append({"type": "rotate", "text": f"  Rotate {deg} deg - {rotation_cost} Stamina", "color": chain_color})
            elif action[0] == "attack":
                # Color membership and labels for attack
                in_face = None
                group_for_act = move_to_chain.get(len(self.current_path) - 2)
                dir_pct = 0
                if group_for_act:
                    dir_pct = int(min(0.10 * group_for_act["chain_len"], 0.50) * 100)
                in_bounce_act = False
                seg_for_act = None
                terminal_move_idx = len(self.current_path) - 2
                for seg in bounce_segments:
                    if terminal_move_idx >= seg["start"] and terminal_move_idx <= seg["end"]:
                        in_bounce_act = True
                        seg_for_act = seg
                        break
                # Pattern membership for terminal attack
                in_pattern = False
                ptt_hit_pct = 0
                ptt_dmg_pct = 0
                if self.pattern_start_move_idx is not None and self.pattern_end_move_idx is not None:
                    if terminal_move_idx >= self.pattern_start_move_idx and terminal_move_idx <= self.pattern_end_move_idx:
                        in_pattern = True
                        # Get pattern hit/damage bonuses
                        if self.pattern_active_bonus:
                            ptt_hit_pct = int(self.pattern_active_bonus.get('hit_bonus', 0.0) * 100)
                            ptt_dmg_pct = int(self.pattern_active_bonus.get('damage_bonus', 0.0) * 100)
                # 3-way color blending
                if group_for_act and in_bounce_act and in_pattern:
                    chain_color = all_three_color
                elif group_for_act and in_pattern:
                    chain_color = face_pattern_color
                elif in_bounce_act and in_pattern:
                    chain_color = bounce_pattern_color
                elif group_for_act and in_bounce_act:
                    chain_color = face_bounce_color
                elif in_pattern:
                    chain_color = pattern_only_color
                elif group_for_act:
                    chain_color = face_only_color
                elif in_bounce_act:
                    chain_color = bounce_only_color
                else:
                    chain_color = generic_color
                b_label = ""
                b_pct = 0
                if seg_for_act:
                    b_pct = int(seg_for_act["rate"] * 100)
                    b_label = seg_for_act.get("label", "")
                # Build bonus labels for attack
                bonus_parts = []
                if dir_pct > 0:
                    # Dir provides stamina + hit + damage
                    bonus_parts.append(f"Dir -{dir_pct}% St +{dir_pct}% Hit +{dir_pct}% Dmg")
                if b_pct > 0 and b_label:
                    # Bounce provides stamina + hit (scaled)
                    b_hit_pct = b_pct  # Bounce hit bonus matches stamina rate
                    bonus_parts.append(f"{b_label} -{b_pct}% St +{b_hit_pct}% Hit")
                if ptt_hit_pct > 0 or ptt_dmg_pct > 0:
                    # Pattern provides hit and/or damage
                    ptt_parts = []
                    if ptt_hit_pct > 0:
                        ptt_parts.append(f"+{ptt_hit_pct}% Hit")
                    if ptt_dmg_pct > 0:
                        ptt_parts.append(f"+{ptt_dmg_pct}% Dmg")
                    bonus_parts.append(f"Ptt {' '.join(ptt_parts)}")
                
                # Add Haki alloy bonuses (all applied types)
                haki_labels = {"armament": "Ha", "observation": "Ho", "conqueror": "Hc"}
                for haki_type in self.applied_haki_alloys:
                    haki_label = haki_labels.get(haki_type, "")
                    # Haki effects per spec 12.1
                    if haki_type == "armament":
                        bonus_parts.append(f"{haki_label} +30% Dmg")
                    elif haki_type == "observation":
                        bonus_parts.append(f"{haki_label} +30% Hit")
                    elif haki_type == "conqueror":
                        bonus_parts.append(f"{haki_label} -30% Opp")
                
                # Add DF alloy bonuses (get labels from JSON)
                player = self.get_current_player()
                if player.devil_fruit_data:
                    alloys_available = player.devil_fruit_data.get("alloys_available", {})
                    for alloy_key in self.applied_df_alloys:
                        # Parse alloy_key (might be "alloy_type:level" or just "alloy_type")
                        if ":" in alloy_key:
                            alloy_type, level = alloy_key.split(":", 1)
                            alloy_data = alloys_available.get(alloy_type, {})
                            label = alloy_data.get("label", "")
                            bonus = alloy_data.get("bonus", "")
                            bonus_parts.append(f"{label}L{level} {bonus}")
                        else:
                            alloy_data = alloys_available.get(alloy_key, {})
                            label = alloy_data.get("label", "")
                            bonus = alloy_data.get("bonus", "")
                            bonus_parts.append(f"{label} {bonus}")
                
                kind = action[1]
                bonus_text = "".join([f"({part})" for part in bonus_parts])
                
                # Format display name
                if kind.startswith("special:"):
                    special_name = kind.split(":", 1)[1]
                    display_name = special_name.replace("_", " ").title()
                elif kind == "skip":
                    display_name = "Skip"
                else:
                    display_name = kind.title()
                
                # Skip action grants +30 stamina
                if kind == "skip":
                    entries.append({"type": "attack", "text": f"  {display_name} Attack (+30 Stamina)", "color": chain_color})
                else:
                    entries.append({"type": "attack", "text": f"  {display_name} Attack {bonus_text}", "color": chain_color})
            elif action[0] == "defense":
                # Color membership and labels for defense
                in_face = None
                group_for_act = move_to_chain.get(len(self.current_path) - 2)
                dir_pct = 0
                if group_for_act:
                    dir_pct = int(min(0.10 * group_for_act["chain_len"], 0.50) * 100)
                in_bounce_act = False
                seg_for_act = None
                terminal_move_idx = len(self.current_path) - 2
                for seg in bounce_segments:
                    if terminal_move_idx >= seg["start"] and terminal_move_idx <= seg["end"]:
                        in_bounce_act = True
                        seg_for_act = seg
                        break
                # Pattern membership for terminal defense
                in_pattern = False
                ptt_hit_pct = 0
                ptt_dmg_pct = 0
                if self.pattern_start_move_idx is not None and self.pattern_end_move_idx is not None:
                    if terminal_move_idx >= self.pattern_start_move_idx and terminal_move_idx <= self.pattern_end_move_idx:
                        in_pattern = True
                        # Get pattern hit/damage bonuses
                        if self.pattern_active_bonus:
                            ptt_hit_pct = int(self.pattern_active_bonus.get('hit_bonus', 0.0) * 100)
                            ptt_dmg_pct = int(self.pattern_active_bonus.get('damage_bonus', 0.0) * 100)
                # 3-way color blending
                if group_for_act and in_bounce_act and in_pattern:
                    chain_color = all_three_color
                elif group_for_act and in_pattern:
                    chain_color = face_pattern_color
                elif in_bounce_act and in_pattern:
                    chain_color = bounce_pattern_color
                elif group_for_act and in_bounce_act:
                    chain_color = face_bounce_color
                elif in_pattern:
                    chain_color = pattern_only_color
                elif group_for_act:
                    chain_color = face_only_color
                elif in_bounce_act:
                    chain_color = bounce_only_color
                else:
                    chain_color = generic_color
                b_label = ""
                b_pct = 0
                if seg_for_act:
                    b_pct = int(seg_for_act["rate"] * 100)
                    b_label = seg_for_act.get("label", "")
                # Build bonus labels for defense
                bonus_parts = []
                if dir_pct > 0:
                    # Dir provides stamina + dodge + damage reduction
                    bonus_parts.append(f"Dir -{dir_pct}% St +{dir_pct}% Dodge +{dir_pct}% DmgRed")
                if b_pct > 0 and b_label:
                    # Bounce provides stamina + dodge
                    b_dodge_pct = b_pct
                    bonus_parts.append(f"{b_label} -{b_pct}% St +{b_dodge_pct}% Dodge")
                if ptt_hit_pct > 0 or ptt_dmg_pct > 0:
                    # Pattern provides dodge and/or damage reduction (converted from hit/dmg)
                    ptt_parts = []
                    if ptt_hit_pct > 0:
                        ptt_parts.append(f"+{ptt_hit_pct}% Dodge")
                    if ptt_dmg_pct > 0:
                        ptt_parts.append(f"+{ptt_dmg_pct}% DmgRed")
                    bonus_parts.append(f"Ptt {' '.join(ptt_parts)}")
                
                # Add Haki alloy bonuses (all applied types)
                kind = action[1]
                haki_labels = {"armament": "Ha", "observation": "Ho", "conqueror": "Hc"}
                for haki_type in self.applied_haki_alloys:
                    haki_label = haki_labels.get(haki_type, "")
                    # Haki effects per spec 12.1 (defense)
                    if haki_type == "armament" and kind in ("evade", "defend"):
                        bonus_parts.append(f"{haki_label} +30% DmgRed")
                    elif haki_type == "armament" and kind == "counter":
                        bonus_parts.append(f"{haki_label} +30% CntDmg")
                    elif haki_type == "observation" and kind in ("evade", "defend"):
                        bonus_parts.append(f"{haki_label} +30% Dodge")
                    elif haki_type == "observation" and kind == "counter":
                        bonus_parts.append(f"{haki_label} +30% CntHit")
                    elif haki_type == "conqueror":
                        bonus_parts.append(f"{haki_label} -30% Opp")
                
                # Add DF alloy bonuses (get labels from JSON)
                player = self.get_current_player()
                if player.devil_fruit_data:
                    alloys_available = player.devil_fruit_data.get("alloys_available", {})
                    for alloy_key in self.applied_df_alloys:
                        # Parse alloy_key (might be "alloy_type:level" or just "alloy_type")
                        if ":" in alloy_key:
                            alloy_type, level = alloy_key.split(":", 1)
                            alloy_data = alloys_available.get(alloy_type, {})
                            label = alloy_data.get("label", "")
                            bonus = alloy_data.get("bonus", "")
                            bonus_parts.append(f"{label}L{level} {bonus}")
                        else:
                            alloy_data = alloys_available.get(alloy_key, {})
                            label = alloy_data.get("label", "")
                            bonus = alloy_data.get("bonus", "")
                            bonus_parts.append(f"{label} {bonus}")
                
                kind = action[1]
                bonus_text = "".join([f"({part})" for part in bonus_parts])
                
                # Format display name
                if kind.startswith("special:"):
                    special_name = kind.split(":", 1)[1]
                    display_name = special_name.replace("_", " ").title()
                elif kind == "tank":
                    display_name = "Tank"
                else:
                    display_name = kind.title()
                
                # Tank action grants +30 stamina
                if kind == "tank":
                    entries.append({"type": "defense", "text": f"  {display_name} Defense (+30 Stamina)", "color": chain_color})
                else:
                    entries.append({"type": "defense", "text": f"  {display_name} Defense {bonus_text}", "color": chain_color})
            elif action[0] == "wall_create":
                # Wall creation display
                wall_row, wall_col, orientation, cost = action[1]
                # Determine tiles between which wall is placed
                if orientation == 'v':
                    # Vertical wall between (wall_row, wall_col) and (wall_row, wall_col+1)
                    tile1 = f"{wall_row}{chr(65+wall_col)}"
                    tile2 = f"{wall_row}{chr(65+wall_col+1)}"
                elif orientation == 'h':
                    # Horizontal wall between (wall_row, wall_col) and (wall_row+1, wall_col)
                    tile1 = f"{wall_row}{chr(65+wall_col)}"
                    tile2 = f"{wall_row+1}{chr(65+wall_col)}"
                else:
                    tile1 = tile2 = "?"
                
                # Wall actions are colored like rotations (no chain bonuses)
                # Determine chain color for wall (treated like rotation)
                wall_color = generic_color
                # If any chain is active at this point, color the wall accordingly
                # For now, use generic color (walls don't participate in chains)
                
                text = f"  Wall ({tile1}-{tile2}) ({cost:.0f} DF St)"
                entries.append({"type": "wall_create", "text": text, "color": wall_color})
            elif action[0] == "wall_reinforce":
                # Wall reinforcement display
                wall_row, wall_col, orientation, count, total_cost = action[1]
                
                # Get label from JSON
                player = self.get_current_player()
                wall_label = "Wall Reinforce"
                if player.devil_fruit_data:
                    wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
                    if wall_config:
                        wall_label = wall_config.get("label", "Wall") + " Reinforce"
                
                # Wall actions are colored like rotations (no chain bonuses)
                wall_color = generic_color
                
                text = f"  {wall_label} x{count} ({total_cost:.0f} DF St)"
                entries.append({"type": "wall_reinforce", "text": text, "color": wall_color})
            elif action[0] == "tile_creation":
                # Tile creation display
                tile_type_key, tile_row, tile_col = action[1], action[2], action[3]
                
                # Get tile config for label and cost
                player = self.get_current_player()
                tile_label = tile_type_key.replace("_", " ").title()
                df_cost = 0
                if player.devil_fruit_data:
                    tiles_available = player.devil_fruit_data.get("map_abilities", {}).get("tiles_available", {})
                    if tile_type_key in tiles_available:
                        tile_config = tiles_available[tile_type_key]
                        tile_label = tile_config.get("label", tile_label)
                        df_cost = tile_config.get("df_cost", 0)
                
                # Tile position
                tile_pos = f"{tile_row+1}{chr(65+tile_col)}"
                
                # Tile actions are colored like walls/rotations (no chain bonuses)
                tile_color = generic_color
                
                text = f"  {tile_label} at {tile_pos} ({df_cost} DF St)"
                entries.append({"type": "tile_creation", "text": text, "color": tile_color})
        return entries

    def debug_planned_actions_display(self) -> None:
        entries = self.get_planned_actions_display()
        lines = []
        try:
            header = f"DEBUG PLANNED ACTIONS LIST (count={len(entries)})"
            print(header)
            lines.append(header)
            for i, e in enumerate(entries):
                line = f"DEBUG LIST [{i}] {e.get('color','#FFFF00')}: {e.get('text','')}"
                print(line)
                lines.append(line)
        except Exception as ex:
            err = f"DEBUG PLANNED ACTIONS LIST ERROR: {ex}"
            print(err)
            lines.append(err)
        self.debug_last_display = "\n".join(lines)

    def get_debug_display_text(self) -> str:
        return self.debug_last_display

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
        
        # Bounce bonus uses scaled hit/dodge values (10%→20%)
        bounce_bonus = 0.0
        if self.bounce_active:
            hits = [0.10, 0.125, 0.15, 0.175, 0.20]
            idx = min(max(1, self.bounce_chain_length), 5) - 1
            bounce_bonus = hits[idx]
        
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

    def _compute_counter_attack_pattern(self, defender, defense_type: str) -> List[Tuple[int, int]]:
        """Compute counter attack pattern from defender's position and facing.
        Counter uses normal attack pattern (3x2 base).
        """
        facing_vec = self._facing_to_vector(defender.facing)
        is_diagonal = facing_vec[0] != 0 and facing_vec[1] != 0
        
        if is_diagonal:
            return self._compute_diagonal_attack_pattern(defender.row, defender.col, facing_vec, "normal")
        else:
            return self._compute_cardinal_attack_pattern(defender.row, defender.col, facing_vec, "normal")
    
    def _compute_attack_pattern_from_stored(self, attack_info: Dict[str, Any]) -> List[Tuple[int, int]]:
        """Compute attack pattern from stored attack info."""
        attack_type = attack_info['type']
        attacker_row = attack_info['attacker_row']
        attacker_col = attack_info['attacker_col']
        attacker_facing = attack_info['attacker_facing']  # This is an angle integer
        
        print(f"  >> _compute_attack_pattern_from_stored: type={attack_type}, pos=({attacker_row},{attacker_col}), facing={attacker_facing}")
        
        # Convert attack type string to range integer
        attack_range_map = {'quick': 1, 'normal': 2, 'heavy': 3}
        attack_range = attack_range_map.get(attack_type, 2)  # Default to normal
        print(f"  >> Converted '{attack_type}' -> range={attack_range}")
        
        # Determine if facing is diagonal or cardinal
        ang = int(attacker_facing) % 360
        is_cardinal = ang in [0, 90, 180, 270]
        
        print(f"  >> Angle={ang}, is_cardinal={is_cardinal}")
        
        if is_cardinal:
            # Cardinal: Pass angle integer and attack_range integer
            pattern = self._compute_cardinal_attack_pattern(attacker_row, attacker_col, ang, attack_range)
        else:
            # Diagonal: Pass angle integer and attack_range integer
            pattern = self._compute_diagonal_attack_pattern(attacker_row, attacker_col, ang, attack_range)
        
        print(f"  >> Computed pattern: {len(pattern)} tiles = {pattern}")
        return pattern
    
    def _apply_wall_damage_to_pattern(self, attack_tiles: List[Tuple[int, int]], damage: int) -> Dict[Tuple[int, int], int]:
        """Apply damage to all walls within the attack pattern. Damage already includes all bonuses.
        
        Returns: Dictionary mapping breakthrough tiles to passthrough damage amount.
                 {(row, col): passthrough_damage}
        """
        all_walls = self.wall_system._walls + self.wall_system._border_walls
        walls_damaged = []
        breakthrough_tiles_damage = {}  # Maps tile -> passthrough damage
        
        print(f"  >> _apply_wall_damage called: damage={damage}, tiles={len(attack_tiles)}")
        print(f"  >> Total walls in system: {len(all_walls)} (internal={len(self.wall_system._walls)}, border={len(self.wall_system._border_walls)})")
        
        if len(self.wall_system._walls) > 0:
            print(f"  >> Internal walls list:")
            for w in self.wall_system._walls:
                print(f"     - Wall at ({w.row},{w.col},{w.orientation}), tier={w.tier}, HP={w.hp}/{w.max_hp}")
        else:
            print(f"  >> WARNING: No internal walls in system!")
        
        for wall in all_walls:
            if wall.tier == 'border':
                continue
            
            # Check if this wall blocks any tiles in the attack pattern
            # Use blocked_tiles_map which was populated during filtering
            wall_blocks_pattern = False
            for blocked_tile, blocking_walls in self.blocked_tiles_map.items():
                for wall_row, wall_col, wall_orient in blocking_walls:
                    if wall_row == wall.row and wall_col == wall.col and wall_orient == wall.orientation:
                        wall_blocks_pattern = True
                        break
                if wall_blocks_pattern:
                    break
            
            # Also check if wall's affected tiles are in the attack pattern (for walls that don't block but border pattern)
            affected_tiles = []
            if wall.orientation == 'h':
                affected_tiles = [(wall.row, wall.col), (wall.row + 1, wall.col)]
            elif wall.orientation == 'v':
                affected_tiles = [(wall.row, wall.col), (wall.row, wall.col + 1)]
            
            wall_borders_pattern = any(tile in attack_tiles for tile in affected_tiles)
            
            print(f"  >> Checking wall ({wall.row},{wall.col},{wall.orientation}): affects tiles {affected_tiles}, blocks={wall_blocks_pattern}, borders={wall_borders_pattern}")
            
            # Wall takes damage if it blocks OR borders the attack pattern
            if wall_blocks_pattern or wall_borders_pattern:
                print(f"  >> HIT! Wall ({wall.row},{wall.col},{wall.orientation}) {'blocks' if wall_blocks_pattern else 'borders'} pattern")
                walls_damaged.append((wall.row, wall.col, wall.orientation, wall.hp, affected_tiles))
            else:
                print(f"  >> MISS: No interaction with attack pattern")
        
        print(f"  >> Total walls to damage: {len(walls_damaged)}")
        
        # Apply damage and track breakthrough
        for wr, wc, wo, hp_before, affected_tiles in walls_damaged:
            wall_before = self.wall_system.get_wall_at(wr, wc, wo)
            if wall_before:
                wall_destroyed = self.wall_system.damage_wall(wr, wc, wo, damage)
                wall_after = self.wall_system.get_wall_at(wr, wc, wo)
                hp_after = wall_after.hp if wall_after else 0
                print(f"  >> Damaged wall ({wr},{wc},{wo}): {hp_before} HP -> {hp_after} HP (destroyed={wall_destroyed})")
                
                if wall_destroyed:
                    # Wall destroyed - calculate passthrough damage
                    passthrough_damage = damage - hp_before
                    print(f"  >> BREAKTHROUGH! Passthrough damage: {passthrough_damage} (attack={damage} - wall_hp={hp_before})")
                    
                    # Find ALL tiles this wall was blocking (not just affected tiles)
                    tiles_to_check = set()
                    for blocked_tile, blocking_wall_list in self.blocked_tiles_map.items():
                        for wall_row, wall_col, wall_orient in blocking_wall_list:
                            if wall_row == wr and wall_col == wc and wall_orient == wo:
                                # This wall was blocking this tile - add it to check list
                                tiles_to_check.add(blocked_tile)
                                break
                    
                    print(f"  >> Wall ({wr},{wc},{wo}) was blocking tiles: {tiles_to_check}")
                    
                    # CRITICAL: Only add breakthrough if ALL walls blocking that tile are destroyed
                    for tile in tiles_to_check:
                        # Check if this tile is blocked by OTHER walls (not this one)
                        if tile in self.blocked_tiles_map:
                            blocking_walls = self.blocked_tiles_map[tile]
                            print(f"  >>   Tile {tile} blocked by {len(blocking_walls)} wall(s): {blocking_walls}")
                            
                            # Check if ALL OTHER blocking walls are destroyed (exclude current wall)
                            all_destroyed = True
                            for bw_row, bw_col, bw_orient in blocking_walls:
                                # Skip the wall we just destroyed
                                if bw_row == wr and bw_col == wc and bw_orient == wo:
                                    continue
                                
                                # Check if this OTHER wall is still alive
                                check_wall = self.wall_system.get_wall_at(bw_row, bw_col, bw_orient)
                                if check_wall and check_wall.tier != 'border':
                                    # Another wall still exists and has HP - NOT all destroyed
                                    all_destroyed = False
                                    print(f"  >>   Wall ({bw_row},{bw_col},{bw_orient}) still alive: HP={check_wall.hp}")
                                    break
                            
                            if all_destroyed:
                                # All walls destroyed - this is breakthrough
                                breakthrough_tiles_damage[tile] = passthrough_damage
                                print(f"  >>   CONFIRMED BREAKTHROUGH: Tile {tile} receives {passthrough_damage} damage (all walls destroyed)")
                            else:
                                # Some walls still alive - tile remains blocked
                                print(f"  >>   NOT breakthrough: Tile {tile} still blocked by surviving walls")
                        else:
                            # Tile not in blocked_tiles_map - shouldn't happen but handle it
                            breakthrough_tiles_damage[tile] = passthrough_damage
                            print(f"  >>   Tile {tile} receives {passthrough_damage} breakthrough damage")
                    
                    self.battle_log.append(f"Wall at ({wr},{wc},{wo}) destroyed ({damage} dmg) - {passthrough_damage} breakthrough!")
                    
                    # CRITICAL: Remove breakthrough tiles from blocked_tiles_map
                    for tile in list(breakthrough_tiles_damage.keys()):
                        if tile in self.blocked_tiles_map:
                            print(f"  >> REMOVING tile {tile} from blocked_tiles_map (breakthrough confirmed)")
                            del self.blocked_tiles_map[tile]
                else:
                    if wall_after:
                        self.battle_log.append(f"Wall ({wr},{wc},{wo}): {wall_after.hp}/{wall_after.max_hp} HP")
            else:
                print(f"  >> ERROR: Wall ({wr},{wc},{wo}) not found in system!")
        
        return breakthrough_tiles_damage

    def _filter_cardinal_attack_pattern_by_walls(self, tiles: List[Tuple[int, int]], attacker_row: int, attacker_col: int, ang: int) -> List[Tuple[int, int]]:
        """Filter cardinal attack pattern tiles based on wall blocking.
        
        For each tile in the pattern, determine its directional relationship to the attacker:
        - Tiles in front: use attacker's facing direction
        - Tiles to the left (same row, west): treat as West attack (270° relative)
        - Tiles to the right (same row, east): treat as East attack (90° relative)
        - Tiles behind: use opposite of attacker's facing
        
        Then check if walls block the direct path from attacker to that tile.
        
        Wall blocking rules:
        - Horizontal wall 'h' at (a,b): blocks vertical (N/S) paths through column b between rows a and a+1
        - Vertical wall 'v' at (a,b): blocks horizontal (E/W) paths through row a between columns b and b+1
        
        Also populates self.blocked_tiles_map: {tile: [list of walls blocking it]}
        """
        internal_walls = self.wall_system._walls
        self.blocked_tiles_map = {}
        
        if len(internal_walls) == 0:
            return tiles
        
        filtered_tiles = []
        
        for tile_row, tile_col in tiles:
            # Determine directional relationship between attacker and tile
            row_diff = tile_row - attacker_row
            col_diff = tile_col - attacker_col
            
            # Classify tile direction relative to attacker
            if row_diff == 0 and col_diff == 0:
                # Same position (shouldn't happen)
                filtered_tiles.append((tile_row, tile_col))
                continue
            
            # Determine which direction this tile is from attacker
            if row_diff == 0:  # Same row - horizontal relationship
                if col_diff > 0:
                    tile_direction = 0  # East
                else:
                    tile_direction = 180  # West
            elif col_diff == 0:  # Same column - vertical relationship
                if row_diff > 0:
                    tile_direction = 90  # South
                else:
                    tile_direction = 270  # North
            else:
                # Diagonal - use primary direction based on larger offset
                if abs(row_diff) > abs(col_diff):
                    tile_direction = 90 if row_diff > 0 else 270
                else:
                    tile_direction = 0 if col_diff > 0 else 180
            
            # Check if any wall blocks the path from attacker to tile
            blocked = False
            blocking_wall = None
            
            for wall in internal_walls:
                wall_row, wall_col = wall.row, wall.col
                
                if wall.orientation == 'h':  # Horizontal wall blocks N/S paths
                    # Only relevant for vertical movement (N/S directions)
                    if tile_direction in [90, 270]:  # South or North
                        # Wall must be in the same column and between attacker and tile
                        if wall_col == attacker_col == tile_col:
                            # Check if wall is between attacker and tile vertically
                            if tile_direction == 90:  # South - tile is below attacker
                                if attacker_row <= wall_row < tile_row:
                                    blocked = True
                                    blocking_wall = (wall.row, wall.col, wall.orientation)
                                    break
                            else:  # North - tile is above attacker
                                if tile_row <= wall_row < attacker_row:
                                    blocked = True
                                    blocking_wall = (wall.row, wall.col, wall.orientation)
                                    break
                
                elif wall.orientation == 'v':  # Vertical wall blocks E/W paths
                    # Only relevant for horizontal movement (E/W directions)
                    if tile_direction in [0, 180]:  # East or West
                        # Wall must be in the same row and between attacker and tile
                        if wall_row == attacker_row == tile_row:
                            # Check if wall is between attacker and tile horizontally
                            if tile_direction == 0:  # East - tile is right of attacker
                                if attacker_col <= wall_col < tile_col:
                                    blocked = True
                                    blocking_wall = (wall.row, wall.col, wall.orientation)
                                    break
                            else:  # West - tile is left of attacker
                                if tile_col <= wall_col < attacker_col:
                                    blocked = True
                                    blocking_wall = (wall.row, wall.col, wall.orientation)
                                    break
            
            if blocked and blocking_wall:
                if (tile_row, tile_col) not in self.blocked_tiles_map:
                    self.blocked_tiles_map[(tile_row, tile_col)] = []
                self.blocked_tiles_map[(tile_row, tile_col)].append(blocking_wall)
            elif not blocked:
                filtered_tiles.append((tile_row, tile_col))
        
        return filtered_tiles
    
    def _filter_diagonal_attack_pattern_by_walls(self, tiles: List[Tuple[int, int]], attacker_row: int, attacker_col: int, attack_range: int, facing_angle: int) -> List[Tuple[int, int]]:
        """Filter diagonal attack pattern tiles based on wall blocking.
        Uses index-based lookup from Correct Diagonal Attack Pattern Wall Blocking Examples.md.
        
        Also populates self.blocked_tiles_map for breakthrough detection.
        """
        internal_walls = self.wall_system._walls
        self.blocked_tiles_map = {}  # Initialize for diagonal
        
        print(f"\n[DIAGONAL FILTER] Called: tiles={len(tiles)}, attacker=({attacker_row},{attacker_col}), range={attack_range}, facing={facing_angle}")
        print(f"[DIAGONAL FILTER] Internal walls: {len(internal_walls)}")
        for wall in internal_walls:
            print(f"[DIAGONAL FILTER]   Wall in list: row={wall.row}, col={wall.col}, orient={wall.orientation}, tier={getattr(wall, 'tier', 'none')}")
        
        if not internal_walls or not tiles:
            print(f"[DIAGONAL FILTER] Early return: no walls or no tiles")
            return tiles
        
        # Map angle to facing label
        ang = int(facing_angle) % 360
        if ang == 315:
            facing_label = "NE"
        elif ang == 225:
            facing_label = "NW"
        elif ang == 45:
            facing_label = "SE"
        elif ang == 135:
            facing_label = "SW"
        else:
            print(f"[DIAGONAL FILTER] Non-diagonal facing {ang}")
            return tiles
        
        print(f"[DIAGONAL FILTER] Facing: {facing_label}")
        
        print(f"[DIAGONAL FILTER] Facing: {facing_label}")
        
        # Build heavy pattern with indices for current player position
        Pr, Pc = attacker_row, attacker_col
        
        print(f"[DIAGONAL FILTER] Player position: ({Pr},{Pc})")
        
        # Heavy pattern index layout (NE/NW specific, SE/SW mirrored)
        if facing_label == "NE":
            heavy_tiles_indexed = [
                (Pr, Pc+1),    # 0
                (Pr, Pc+2),    # 1
                (Pr-1, Pc),    # 2
                (Pr-1, Pc+1),  # 3
                (Pr-1, Pc+2),  # 4
                (Pr-2, Pc),    # 5
                (Pr-2, Pc+1),  # 6
                (Pr-2, Pc+2),  # 7
            ]
        elif facing_label == "NW":
            heavy_tiles_indexed = [
                (Pr, Pc-2),    # 0
                (Pr, Pc-1),    # 1
                (Pr-1, Pc-2),  # 2
                (Pr-1, Pc-1),  # 3
                (Pr-1, Pc),    # 4
                (Pr-2, Pc-2),  # 5
                (Pr-2, Pc-1),  # 6
                (Pr-2, Pc),    # 7
            ]
        elif facing_label == "SE":
            heavy_tiles_indexed = [
                (Pr, Pc+1),    # 0
                (Pr, Pc+2),    # 1
                (Pr+1, Pc),    # 2
                (Pr+1, Pc+1),  # 3
                (Pr+1, Pc+2),  # 4
                (Pr+2, Pc),    # 5
                (Pr+2, Pc+1),  # 6
                (Pr+2, Pc+2),  # 7
            ]
        else:  # SW
            heavy_tiles_indexed = [
                (Pr, Pc-2),    # 0
                (Pr, Pc-1),    # 1
                (Pr+1, Pc-2),  # 2
                (Pr+1, Pc-1),  # 3
                (Pr+1, Pc),    # 4
                (Pr+2, Pc-2),  # 5
                (Pr+2, Pc-1),  # 6
                (Pr+2, Pc),    # 7
            ]
        
        # Build reverse map: tile -> index in heavy pattern
        tile_to_index = {tile: idx for idx, tile in enumerate(heavy_tiles_indexed) if 0 <= tile[0] < 7 and 0 <= tile[1] < 7}
        
        print(f"[DIAGONAL FILTER] Heavy pattern indices built: {len(tile_to_index)} tiles")
        
        # Lookup table: (facing, wall_type, dx, dy) -> blocked_indices_set
        # Populated from Examples.md
        blocking_rules = self._build_blocking_lookup_table()
        
        blocked_indices = set()
        pattern_tiles_set = set(tiles)
        
        print(f"[DIAGONAL FILTER] Processing {len(internal_walls)} walls...")
        
        for wall in internal_walls:
            if getattr(wall, "tier", None) == "border":
                continue
            
            wall_row, wall_col = wall.row, wall.col
            wall_type = "v" if wall.orientation == "v" else "h"
            
            print(f"[DIAGONAL FILTER] Wall at ({wall_row},{wall_col}) type={wall_type}")
            
            # Check if wall borders pattern
            if wall_type == "v":
                wall_tiles = {(wall_row, wall_col), (wall_row, wall_col + 1)}
            else:
                wall_tiles = {(wall_row, wall_col), (wall_row + 1, wall_col)}
            
            print(f"[DIAGONAL FILTER]   Wall tiles: {wall_tiles}")
            print(f"[DIAGONAL FILTER]   Pattern tiles overlap: {wall_tiles & pattern_tiles_set}")
            
            if not wall_tiles & pattern_tiles_set:
                print(f"[DIAGONAL FILTER]   -> No overlap, skipping")
                continue
            
            # Compute local vector
            dx, dy = self._get_local_vector_for_blocking(Pr, Pc, wall_row, wall_col, wall_type, facing_label)
            
            print(f"[DIAGONAL FILTER]   -> Player: row={Pr}, col={Pc}")
            print(f"[DIAGONAL FILTER]   -> Wall: row={wall_row}, col={wall_col}, type={wall_type}")
            print(f"[DIAGONAL FILTER]   -> Local vector: dx={dx}, dy={dy}")
            
            # Lookup blocked indices
            key = (facing_label, wall_type, dx, dy)
            
            # Find matching example by wall_type + dx/dy
            example_name = "UNKNOWN"
            example_num = 0
            
            if facing_label == "NE":
                if wall_type == "v":  # Vertical walls: Examples 1-6
                    if (dx, dy) == (-2, 2): example_num = 1
                    elif (dx, dy) == (-1, 2): example_num = 2
                    elif (dx, dy) == (0, 2): example_num = 3
                    elif (dx, dy) == (-2, 1): example_num = 4
                    elif (dx, dy) == (-1, 1): example_num = 5
                    elif (dx, dy) == (0, 1): example_num = 6
                elif wall_type == "h":  # Horizontal walls: Examples 7-12
                    if (dx, dy) == (-2, 2): example_num = 7
                    elif (dx, dy) == (-1, 2): example_num = 8
                    elif (dx, dy) == (-2, 0): example_num = 9
                    elif (dx, dy) == (-2, 1): example_num = 10
                    elif (dx, dy) == (-1, 1): example_num = 11
                    elif (dx, dy) == (-1, 0): example_num = 12
            elif facing_label == "NW":
                if wall_type == "v":  # Vertical walls: Examples 13-18
                    if (dx, dy) == (2, 1): example_num = 13
                    elif (dx, dy) == (1, 1): example_num = 14
                    elif (dx, dy) == (0, 1): example_num = 15
                    elif (dx, dy) == (2, 2): example_num = 16
                    elif (dx, dy) == (1, 2): example_num = 17
                    elif (dx, dy) == (0, 2): example_num = 18
                elif wall_type == "h":  # Horizontal walls: Examples 19-24
                    if (dx, dy) == (2, 2): example_num = 19
                    elif (dx, dy) == (1, 2): example_num = 20
                    elif (dx, dy) == (2, 0): example_num = 21
                    elif (dx, dy) == (2, 1): example_num = 22
                    elif (dx, dy) == (1, 1): example_num = 23
                    elif (dx, dy) == (1, 0): example_num = 24
            elif facing_label == "SE":
                # SE uses same dx/dy as NE, map to NE examples
                if wall_type == "v":  # Vertical walls: Examples 1-6
                    if (dx, dy) == (-2, 2): example_num = 1
                    elif (dx, dy) == (-1, 2): example_num = 2
                    elif (dx, dy) == (0, 2): example_num = 3
                    elif (dx, dy) == (-2, 1): example_num = 4
                    elif (dx, dy) == (-1, 1): example_num = 5
                    elif (dx, dy) == (0, 1): example_num = 6
                elif wall_type == "h":  # Horizontal walls: Examples 7-12
                    if (dx, dy) == (-2, 2): example_num = 7
                    elif (dx, dy) == (-1, 2): example_num = 8
                    elif (dx, dy) == (-2, 0): example_num = 9
                    elif (dx, dy) == (-2, 1): example_num = 10
                    elif (dx, dy) == (-1, 1): example_num = 11
                    elif (dx, dy) == (-1, 0): example_num = 12
            elif facing_label == "SW":
                # SW uses same dx/dy as NW, map to NW examples
                if wall_type == "v":  # Vertical walls: Examples 13-18
                    if (dx, dy) == (2, 1): example_num = 13
                    elif (dx, dy) == (1, 1): example_num = 14
                    elif (dx, dy) == (0, 1): example_num = 15
                    elif (dx, dy) == (2, 2): example_num = 16
                    elif (dx, dy) == (1, 2): example_num = 17
                    elif (dx, dy) == (0, 2): example_num = 18
                elif wall_type == "h":  # Horizontal walls: Examples 19-24
                    if (dx, dy) == (2, 2): example_num = 19
                    elif (dx, dy) == (1, 2): example_num = 20
                    elif (dx, dy) == (2, 0): example_num = 21
                    elif (dx, dy) == (2, 1): example_num = 22
                    elif (dx, dy) == (1, 1): example_num = 23
                    elif (dx, dy) == (1, 0): example_num = 24
            
            if example_num > 0:
                example_name = f"{facing_label}_{wall_type}_{dx}_{dy}"
            
            if key in blocking_rules:
                indices = blocking_rules[key]
                print(f"[DIAGONAL FILTER]   -> Example #{example_num} ({example_name})")
                print(f"[DIAGONAL FILTER]   -> Blocked indices: {indices}")
                blocked_indices.update(indices)
                
                # Track which tiles this wall blocks
                for idx in indices:
                    if idx < len(heavy_tiles_indexed):
                        blocked_tile = heavy_tiles_indexed[idx]
                        if blocked_tile not in self.blocked_tiles_map:
                            self.blocked_tiles_map[blocked_tile] = []
                        self.blocked_tiles_map[blocked_tile].append((wall_row, wall_col, wall.orientation))
            else:
                print(f"[DIAGONAL FILTER]   -> No rule for key {key} (would be example #{example_num} {example_name})")
        
        print(f"[DIAGONAL FILTER] Total blocked indices: {blocked_indices}")
        
        print(f"[DIAGONAL FILTER] Total blocked indices: {blocked_indices}")
        
        # Map blocked indices to actual tiles and filter
        blocked_tiles = {heavy_tiles_indexed[i] for i in blocked_indices if i < len(heavy_tiles_indexed)}
        
        print(f"[DIAGONAL FILTER] Blocked tiles: {blocked_tiles}")
        
        print(f"[DIAGONAL FILTER] Blocked tiles: {blocked_tiles}")
        
        # Hierarchical filtering: only block tiles present in current attack pattern
        blocked_in_pattern = blocked_tiles & set(tiles)
        
        # Filter blocked_tiles_map to only include tiles in current pattern
        self.blocked_tiles_map = {tile: walls for tile, walls in self.blocked_tiles_map.items() if tile in blocked_in_pattern}
        
        print(f"[DIAGONAL FILTER] Blocked in current pattern: {blocked_in_pattern}")
        
        filtered = [t for t in tiles if t not in blocked_in_pattern]
        print(f"[DIAGONAL FILTER] Filtered result: {len(filtered)} tiles (removed {len(tiles)-len(filtered)})")
        return filtered
    
    def _get_local_vector_for_blocking(self, Pr: int, Pc: int, wall_row: int, wall_col: int, wall_type: str, facing: str) -> Tuple[int, int]:
        """Compute (dx, dy) local vector from player to wall for blocking lookup.
        
        Coordinate system:
        - dx = left/right offset (row delta)
        - dy = forward/backward offset (column delta)
        
        Player anchoring (to match minimal index system):
        - For vertical walls: player acts as horizontal wall → use lower column index (Pc)
        - For horizontal walls: player acts as vertical wall → use lower row index (Pr)
        
        Wall encoding:
        - Vertical wall at (row, col) blocks between col and col+1
        - Horizontal wall at (row, col) blocks between row and row+1
        
        Examples use the blocking boundary as reference:
        - For vertical walls: measure to col+1 (the forward column boundary)
        - For horizontal walls: measure to row+1 (the forward row boundary)
        """
        # Compute deltas in grid space
        col_eff = wall_col
        row_eff = wall_row
        
        if wall_type == "v" and facing in ("NE", "SE"):
            # For vertical walls when facing NE/SE, shift wall one column forward
            col_eff = wall_col + 1
        
        if wall_type == "h" and facing in ("SE", "SW"):
            # For horizontal walls when facing SE/SW, shift wall one row forward
            row_eff = wall_row + 1
        
        if wall_type == "v":
            # Vertical wall: player anchor at lower column (Pc)
            row_delta = row_eff - Pr
            col_delta = col_eff - Pc
        else:
            # Horizontal wall: player anchor at lower row (Pr)
            row_delta = row_eff - Pr
            col_delta = wall_col - Pc
        
        # Transform to local (dx, dy) based on facing
        # dx = row delta (left/right), dy = col delta (forward/back)
        if facing == "NE":
            # NE: forward = increasing col (positive dy), wall on left => negative dx when forward/up
            dx = row_delta  # wall at smaller row (up) gives negative dx
            dy = col_delta
        elif facing == "NW":
            # NW: forward = decreasing col (negative dy), wall on right => positive dx when forward/up
            dx = -row_delta  # wall at smaller row (up) gives positive dx
            dy = -col_delta
        elif facing == "SE":
            # SE: flip dx sign to match NE pattern (south-facing reverses left/right)
            dx = -row_delta
            dy = col_delta
        else:  # SW
            # SW: flip dx sign to match NW pattern (south-facing reverses left/right)
            dx = row_delta
            dy = -col_delta
        
        return dx, dy
    
    def _build_blocking_lookup_table(self) -> Dict[Tuple[str, str, int, int], set]:
        """Build lookup table from Examples.md: (facing, wall_type, dx, dy) -> {blocked_indices}."""
        # Hard-coded from Correct Diagonal Attack Pattern Wall Blocking Examples.md
        # Format: (facing, wall_type, dx, dy): {blocked indices}
        
        rules = {}
        
        # NE facing, vertical walls (wall type 'v')
        # Example 1: dx=-2, dy=2 -> block {7}
        rules[("NE", "v", -2, 2)] = {7}
        # Example 2: dx=-1, dy=2 -> block {4,7}
        rules[("NE", "v", -1, 2)] = {4, 7}
        # Example 3: dx=0, dy=2 -> block {1}
        rules[("NE", "v", 0, 2)] = {1}
        
        # Example 4: dx=-2, dy=1 -> block {6}
        rules[("NE", "v", -2, 1)] = {6}
        # Example 5: dx=-1, dy=1 -> block {3,6,7}
        rules[("NE", "v", -1, 1)] = {3, 6, 7}
        # Example 6: dx=0, dy=1 -> block {0,1,3,4,7}
        rules[("NE", "v", 0, 1)] = {0, 1, 3, 4, 7}
        
        # NE facing, horizontal walls (wall type 'h')
        # Example 7: dx=-2, dy=2 -> block {7}
        rules[("NE", "h", -2, 2)] = {7}
        # Example 8: dx=-1, dy=2 -> block {4}
        rules[("NE", "h", -1, 2)] = {4}
        # Example 9: dx=-2, dy=0 -> block {5}
        rules[("NE", "h", -2, 0)] = {5}
        
        # Example 10: dx=-2, dy=1 -> block {6,7}
        rules[("NE", "h", -2, 1)] = {6, 7}
        # Example 11: dx=-1, dy=1 -> block {3,4,7}
        rules[("NE", "h", -1, 1)] = {3, 4, 7}
        # Example 12: dx=-1, dy=0 -> block {2,5}
        rules[("NE", "h", -1, 0)] = {2, 5}
        
        # NW facing, vertical walls
        # Example 13: dx=2, dy=1 -> block {7}
        rules[("NW", "v", 2, 1)] = {7}
        # Example 14: dx=1, dy=1 -> block {3,5,6}
        rules[("NW", "v", 1, 1)] = {3, 5, 6}
        # Example 15: dx=0, dy=1 -> block {0,1}
        rules[("NW", "v", 0, 1)] = {0, 1}
        
        # Example 16: dx=2, dy=2 -> block {5}
        rules[("NW", "v", 2, 2)] = {5}
        # Example 17: dx=1, dy=2 -> block {2,5}
        rules[("NW", "v", 1, 2)] = {2, 5}
        # Example 18: dx=0, dy=2 -> block {0}
        rules[("NW", "v", 0, 2)] = {0}
        
        # NW facing, horizontal walls
        # Example 19: dx=2, dy=2 -> block {5}
        rules[("NW", "h", 2, 2)] = {5}
        # Example 20: dx=1, dy=2 -> block {2}
        rules[("NW", "h", 1, 2)] = {2}
        # Example 21: dx=2, dy=0 -> block {7}
        rules[("NW", "h", 2, 0)] = {7}
        
        # Example 22: dx=2, dy=1 -> block {5,6}
        rules[("NW", "h", 2, 1)] = {5, 6}
        # Example 23: dx=1, dy=1 -> block {2,3,5}
        rules[("NW", "h", 1, 1)] = {2, 3, 5}
        # Example 24: dx=1, dy=0 -> block {4,7}
        rules[("NW", "h", 1, 0)] = {4, 7}
        
        # SE/SW: Reuse NE/NW rules (same dx/dy transform)
        for (facing, wall_type, dx, dy), indices in list(rules.items()):
            if facing == "NE":
                rules[("SE", wall_type, dx, dy)] = indices
            elif facing == "NW":
                rules[("SW", wall_type, dx, dy)] = indices
        
        return rules
    
    def _get_wall_between(self, from_row: int, from_col: int, to_row: int, to_col: int) -> Optional[Tuple[int, int, str]]:
        """Identify the wall blocking movement between two tiles.
        Returns (row, col, orientation) of the blocking wall, or None if no wall found.
        """
        row_diff = to_row - from_row
        col_diff = to_col - from_col
        
        # Check all walls (internal + border)
        all_walls = self.wall_system._walls + self.wall_system._border_walls
        
        # For orthogonal movement
        if abs(row_diff) == 1 and col_diff == 0:
            # Vertical movement
            for wall in all_walls:
                if wall.orientation == 'h':
                    # Moving down: wall at (from_row, from_col)
                    if row_diff == 1 and wall.row == from_row and wall.col == from_col:
                        return (wall.row, wall.col, wall.orientation)
                    # Moving up: wall at (to_row, to_col)
                    if row_diff == -1 and wall.row == to_row and wall.col == to_col:
                        return (wall.row, wall.col, wall.orientation)
        
        elif row_diff == 0 and abs(col_diff) == 1:
            # Horizontal movement
            for wall in all_walls:
                if wall.orientation == 'v':
                    # Moving right: wall at (from_row, from_col)
                    if col_diff == 1 and wall.row == from_row and wall.col == from_col:
                        return (wall.row, wall.col, wall.orientation)
                    # Moving left: wall at (to_row, to_col)
                    if col_diff == -1 and wall.row == to_row and wall.col == to_col:
                        return (wall.row, wall.col, wall.orientation)
        
        return None

    def apply_push_to_defender(self, distance: int) -> int:
        """Attempt to push defender up to 'distance' tiles along attacker facing.
        Per spec 9.2 & 11.3: Wall collision causes damage to both wall and player, stun, and potential breakthrough.
        Returns actual pushed distance. Applies tile effects on landing.
        """
        print(f"\n[PUSH] === Starting push_to_defender ===")
        print(f"[PUSH] Distance requested: {distance}")
        
        if distance <= 0:
            print(f"[PUSH] Distance <= 0, returning 0")
            return 0
            
        # Get attacker and defender based on attacker_is_p1 flag (set by caller)
        # Do NOT use get_current_player() as it depends on phase which is wrong in defense phase
        if self.attacker_is_p1:
            attacker = self.player1
            defender = self.player2
        else:
            attacker = self.player2
            defender = self.player1
            
        facing_vec = self._facing_to_vector(attacker.facing)
        
        print(f"[PUSH] Attacker: {attacker.name} at ({attacker.row},{attacker.col}) facing {attacker.facing}°")
        print(f"[PUSH] Defender: {defender.name} at ({defender.row},{defender.col})")
        print(f"[PUSH] Facing vector: {facing_vec}")
        
        # Calculate push damage per spec 9.2: Push 1 = +10 flat, Push 2 = +20 flat
        push_damage = 10 if distance == 1 else 20
        
        # Calculate wall damage per spec 11.2 & 27.1: Tile_Damage = Base × (1 + bonuses) × (1 + strength/400)
        facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
        bounce_bonus = 0.0
        if self.bounce_active:
            hits = [0.10, 0.125, 0.15, 0.175, 0.20]
            idx = min(max(1, self.bounce_chain_length), 5) - 1
            bounce_bonus = hits[idx]
        pattern_bonus = 0.0
        if self.pattern_active_bonus and not self.pattern_applied_this_phase:
            pattern_bonus = self.pattern_active_bonus.get('damage_bonus', 0.0)
        elif self.pattern_memory:
            pattern_bonus = self.pattern_memory.get('damage_bonus', 0.0)
        
        strength_mult = 1.0 + (attacker.strength / 400.0)  # Up to +25% at 100 STR
        wall_damage = int(push_damage * (1.0 + facing_bonus + bounce_bonus + pattern_bonus) * strength_mult)
        
        pushed = 0
        print(f"[PUSH] Starting push loop for {distance} steps...")
        
        for step in range(distance):
            print(f"\n[PUSH] --- Step {step+1}/{distance} ---")
            print(f"[PUSH] Current defender position: ({defender.row},{defender.col})")
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
            
            print(f"[PUSH] Target position: ({to_row},{to_col})")
            
            # Check bounds
            if not (0 <= to_row < 7 and 0 <= to_col < 7):
                print(f"[PUSH] BLOCKED: Out of bounds! Breaking.")
                break
            
            # Check wall collision per spec 9.2 & 11.3
            wall_blocking = self.wall_system.is_wall_blocking(defender.row, defender.col, to_row, to_col)
            print(f"[PUSH] Wall blocking check: {wall_blocking}")
            
            if wall_blocking:
                # Identify the wall
                wall_info = self._get_wall_between(defender.row, defender.col, to_row, to_col)
                print(f"[PUSH] Wall info: {wall_info}")
                
                if wall_info:
                    wr, wc, wo = wall_info
                    wall = self.wall_system.get_wall_at(wr, wc, wo)
                    print(f"[PUSH] Wall object: tier={wall.tier if wall else 'None'}, hp={wall.hp if wall else 'N/A'}")
                    
                    if wall and wall.tier != 'border':
                        # Apply damage to wall
                        wall_destroyed = self.wall_system.damage_wall(wr, wc, wo, wall_damage)
                        print(f"[PUSH] Wall damaged: {wall_damage} damage, destroyed={wall_destroyed}")
                        self.battle_log.append(f"Wall collision! Wall at ({wr},{wc},{wo}) takes {wall_damage} damage")
                        
                        # Per spec 9.2: Defender takes push damage and gains Stunned status
                        defender.health = max(0, defender.health - push_damage)
                        self.battle_log.append(f"Defender takes {push_damage} collision damage → health={defender.health}")
                        
                        # Apply Stunned status: +50% stamina cost on next defensive action
                        if not hasattr(defender, 'stunned'):
                            defender.stunned = False
                        defender.stunned = True
                        self.battle_log.append(f"{defender.name} is Stunned (+50% stamina cost next defense)")
                        
                        # Check for breakthrough per spec 11.3
                        if wall_destroyed:
                            print(f"[PUSH] BREAKTHROUGH! Wall destroyed, continuing push.")
                            self.battle_log.append(f"Breakthrough! Wall destroyed, defender continues")
                            # Wall is gone, continue push
                            defender.row, defender.col = to_row, to_col
                            pushed += 1
                        else:
                            print(f"[PUSH] BLOCKED: Wall survived, stopping push.")
                            # Wall blocks, defender stops here
                            break
                    else:
                        print(f"[PUSH] BLOCKED: Border wall or no wall object, stopping.")
                        # Border wall - indestructible, defender stops
                        break
                else:
                    print(f"[PUSH] BLOCKED: Wall blocking=True but no wall found, stopping.")
                    # No wall found but blocking reported - treat as blocked
                    break
            elif is_blocked(defender.row, defender.col, to_row, to_col, attacker, self.wall_system, self.tile_system):
                print(f"[PUSH] BLOCKED: is_blocked() returned True (tile/obstacle), stopping.")
                # Blocked by tile or other obstacle (not wall)
                break
            else:
                print(f"[PUSH] FREE MOVEMENT: Moving defender to ({to_row},{to_col})")
                # Free movement
                defender.row, defender.col = to_row, to_col
                pushed += 1
            
            # Apply tile effects after each step
            eff = self.tile_system.apply_tile_effect(defender, defender.row, defender.col, self.effects_engine)
            if eff:
                if isinstance(eff, dict) and 'effect_obj' in eff:
                    # Trap tile - queue effect for turn-end processing
                    if not hasattr(self, 'pending_effects'):
                        self.pending_effects = []
                    self.pending_effects.append({'effect': eff['effect_obj'], 'target': defender.name})
                    self.battle_log.append(f"Defender tile effect: {eff['effect_type']} → {defender.name}")
                else:
                    # Drop tile - immediate restore
                    self.battle_log.append(f"Defender tile effect: {eff}")
        
        print(f"\n[PUSH] === Push complete: {pushed}/{distance} tiles pushed ===")
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
        
        # Get bonuses (scaled bounce)
        facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
        hits = [0.10, 0.125, 0.15, 0.175, 0.20]
        bounce_bonus = hits[min(max(1, self.bounce_chain_length), 5) - 1] if self.bounce_active else 0.0
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
        
        # Apply special attack effect if applicable (per spec 17.3: after damage)
        if attack_type.startswith("special:"):
            special_name = attack_type.split(":", 1)[1]
            self.battle_log.append(f"EFFECT_DEBUG: Special attack detected: {special_name}")
            
            if attacker.devil_fruit_data:
                phase_key = "special_attacks" if self.phase == "attack" else "special_defenses"
                special_actions = attacker.devil_fruit_data.get(phase_key, {})
                special_data = special_actions.get(special_name)
                self.battle_log.append(f"EFFECT_DEBUG: Phase={phase_key}, special_data={'found' if special_data else 'NOT FOUND'}")
                
                if special_data and "effect" in special_data:
                    effect_config = special_data["effect"]
                    effect_type = effect_config.get("type")
                    effect_category = effect_config.get("category")
                    self.battle_log.append(f"EFFECT_DEBUG: effect_type={effect_type}, category={effect_category}")
                    
                    if effect_type and effect_category:
                        # Get defender's resistance
                        resistance = 1.0
                        if defender.devil_fruit_data and "effect_resistance" in defender.devil_fruit_data:
                            resistance = defender.devil_fruit_data["effect_resistance"].get(effect_type, 1.0)
                            # Apply mastery scaling to resistance per spec 17.4
                            resistance = resistance * (defender.devil_fruit_mastery / 100.0)
                        self.battle_log.append(f"EFFECT_DEBUG: resistance={resistance}, attacker_mastery={attacker.devil_fruit_mastery}")
                        
                        # Calculate and apply effect
                        effect = self.effects_engine.calculate_effect(
                            effect_type, effect_category, attacker.devil_fruit_mastery, resistance
                        )
                        self.battle_log.append(f"EFFECT_DEBUG: Calculated effect={'SUCCESS' if effect else 'FAILED'}")
                        
                        if effect:
                            self.battle_log.append(f"EFFECT_DEBUG: Effect magnitude={effect.magnitude}, duration={effect.duration}")
                            # Apply instant damage if applicable
                            if effect.category == "instant_damage":
                                instant_dmg = self.effects_engine.apply_instant_effect(effect, defender)
                                self.battle_log.append(f"EFFECT_DEBUG: Instant damage applied: {instant_dmg}")
                                if defender.health == 0:
                                    self.game_active = False
                                    self.winner = attacker.name
                                    self.battle_log.append(f"KO! Winner: {self.winner}")
                                    return {"result": "ko", "winner": self.winner, **outcome}
                            else:
                                # Add to active effects (DoT, debuffs, etc.)
                                if self.effects_engine.should_stack_effect(self.active_effects[defender.name], effect):
                                    self.active_effects[defender.name].append(effect)
                                    self.battle_log.append(f"EFFECT_DEBUG: Effect added to active_effects list")
                                    self.battle_log.append(f"Effect applied: {effect.effect_type} → {defender.name}")
                                else:
                                    self.battle_log.append(f"EFFECT_DEBUG: Effect BLOCKED by stacking rules")
                    else:
                        self.battle_log.append(f"EFFECT_DEBUG: Missing effect_type or category in config")
                else:
                    self.battle_log.append(f"EFFECT_DEBUG: No 'effect' key in special_data")
            else:
                self.battle_log.append(f"EFFECT_DEBUG: Attacker has no devil_fruit_data")
        
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
        hits = [0.10, 0.125, 0.15, 0.175, 0.20]
        bounce_bonus = hits[min(max(1, self.bounce_chain_length), 5) - 1] if self.bounce_active else 0.0
        
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
        defender_stunned = getattr(defender, 'stunned', False)
        stamina_cost = calculate_defense_stamina_cost(base_cost, hit_chance, def_obs_active, defender_stunned)
        
        # Clear stunned status after applying it once per spec 9.2
        if defender_stunned:
            defender.stunned = False
            self.battle_log.append(f"{defender.name} Stunned status removed (applied to this defense)")
        
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
                # Trigger counter-attack per spec 14.3: counter has attack pattern and damages walls
                # Counter uses Normal pattern (3×2 base) regardless of counter type
                counter_tiles = self._compute_counter_attack_pattern(defender, defense_type)
                counter_base_damage = 10  # Wall damage base for counter (spec 11.2)
                
                # Counter wall damage uses defender's bonuses as attacker
                counter_facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
                counter_bounce_bonus = 0.0
                if self.bounce_active:
                    hits = [0.10, 0.125, 0.15, 0.175, 0.20]
                    idx = min(max(1, self.bounce_chain_length), 5) - 1
                    counter_bounce_bonus = hits[idx]
                counter_pattern_dmg = 0.0
                if self.pattern_active_bonus and not self.pattern_applied_this_phase:
                    counter_pattern_dmg = self.pattern_active_bonus.get('damage_bonus', 0.0)
                elif self.pattern_memory:
                    counter_pattern_dmg = self.pattern_memory.get('damage_bonus', 0.0)
                
                # Apply wall damage from counter (same formula as attack)
                strength_mult = 1.0 + (defender.strength / 400.0)
                counter_wall_damage = int(counter_base_damage * (1.0 + counter_facing_bonus + counter_bounce_bonus + counter_pattern_dmg) * strength_mult)
                print(f"DEBUG COUNTER WALL: base={counter_base_damage}, bonuses: face={counter_facing_bonus}, bounce={counter_bounce_bonus}, ptt={counter_pattern_dmg}, str_mult={strength_mult}, final={counter_wall_damage}")
                # Temporarily swap context for wall damage
                temp_attacker_flag = self.attacker_is_p1
                self.attacker_is_p1 = not self.attacker_is_p1
                counter_breakthrough_tiles_damage = self._apply_wall_damage_to_pattern(counter_tiles, counter_wall_damage)
                self.attacker_is_p1 = temp_attacker_flag
                
                # Counter player damage calculation
                counter_damage = calculate_damage(
                    defender, attacker, 10, "normal", "counter",
                    0.0, 0.0, 0.0,
                    None, haki_arm_eff_defender, haki_arm_eff_attacker,
                    is_defense_phase=True
                )
                
                # Check for breakthrough damage on counter
                attacker_tile = (attacker.row, attacker.col)
                if attacker_tile in counter_breakthrough_tiles_damage:
                    passthrough_dmg = counter_breakthrough_tiles_damage[attacker_tile]
                    print(f"DEBUG COUNTER BREAKTHROUGH: Attacker at {attacker_tile} - applying breakthrough damage")
                    print(f"DEBUG COUNTER BREAKTHROUGH: Original counter_damage={counter_damage}, passthrough={passthrough_dmg}")
                    # Recalculate with breakthrough base damage
                    counter_damage_breakthrough = calculate_damage(
                        defender, attacker, passthrough_dmg, "normal", "counter",
                        0.0, 0.0, 0.0,
                        None, haki_arm_eff_defender, haki_arm_eff_attacker,
                        is_defense_phase=True
                    )
                    counter_damage = max(0, int(counter_damage_breakthrough))
                    print(f"DEBUG COUNTER BREAKTHROUGH: Final breakthrough counter_damage={counter_damage}")
                    self.battle_log.append(f"Counter Breakthrough! Wall destroyed, reduced damage: {counter_damage}")
                
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
        # Apply bounce scaling per eligible steps
        last_idx = self.bounce_end_move_idx if self.bounce_end_move_idx is not None else (len(self.current_path) - 2)
        bounce_steps = 0
        if self.bounce_start_move_idx is not None and last_idx >= (self.bounce_start_move_idx or 0):
            bounce_steps = last_idx - (self.bounce_start_move_idx or 0) + 1
        rates = [0.10, 0.125, 0.15, 0.175, 0.20]
        per_step_after_chain = int(base * (1.0 - chain_bonus))
        total = subtotal
        for k in range(max(0, bounce_steps)):
            total -= int(per_step_after_chain * rates[min(k, 4)])
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
        # Get reinforceable walls if in reinforce mode
        reinforceable_walls = []
        if self.wall_mode == "reinforce":
            reinforceable_walls = self.get_player_walls_in_range()
        
        # Recalculate wall placement tiles in real-time if in conjure mode
        wall_placement_tiles = []
        if self.wall_mode == "conjure":
            player = self.get_current_player()
            wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation")
            if wall_config:
                placement_range = wall_config.get("range", 5)
                # Use ghost position if available (planning mode), otherwise use actual position
                if self.ghost_row is not None and self.ghost_col is not None:
                    player_pos = (self.ghost_row, self.ghost_col)
                else:
                    player_pos = (player.row, player.col)
                for row in range(7):
                    for col in range(7):
                        distance = abs(row - player_pos[0]) + abs(col - player_pos[1])
                        if distance <= placement_range:
                            wall_placement_tiles.append((row, col))
        
        # Recalculate tile placement tiles in real-time if in tile mode
        tile_placement_tiles = []
        tile_planned_position = None
        if self.tile_mode:
            player = self.get_current_player()
            opponent = self.player2 if player == self.player1 else self.player1
            tiles_available = player.devil_fruit_data.get("map_abilities", {}).get("tiles_available", {})
            if self.selected_tile_type and self.selected_tile_type in tiles_available:
                tile_config = tiles_available[self.selected_tile_type]
                placement_range = tile_config.get("range", 5)
                # Use ghost position if available (planning mode), otherwise use actual position
                if self.ghost_row is not None and self.ghost_col is not None:
                    player_pos = (self.ghost_row, self.ghost_col)
                else:
                    player_pos = (player.row, player.col)
                
                # Get existing tiles to exclude
                existing_tiles = {(t[0], t[1]) for t in self.tile_system.get_all_tiles()}
                
                for row in range(7):
                    for col in range(7):
                        # Skip if occupied by player or opponent
                        if (row, col) == (player.row, player.col):
                            continue
                        if (row, col) == (opponent.row, opponent.col):
                            continue
                        # Skip if tile already exists at this position
                        if (row, col) in existing_tiles:
                            continue
                        # Check range
                        distance = abs(row - player_pos[0]) + abs(col - player_pos[1])
                        if distance <= placement_range:
                            tile_placement_tiles.append((row, col))
        
        # Get planned tile position (even when tile_mode is off)
        if self.planned_tile_creation:
            tile_planned_position = (self.planned_tile_creation["row"], self.planned_tile_creation["col"])
        
        return {
            'phase': self.phase,
            'attacker_is_p1': self.attacker_is_p1,
            'ghost': {'row': self.ghost_row, 'col': self.ghost_col, 'facing': self.ghost_facing},
            'highlights': list(self.highlighted_squares),
            'attack_tiles': list(self.attack_highlighted_squares),
            'wall_placement_tiles': wall_placement_tiles,
            'wall_first_tile': self.wall_first_tile_highlight,
            'tile_placement_tiles': tile_placement_tiles,
            'tile_planned_position': tile_planned_position,
            'reinforceable_walls': reinforceable_walls,
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
        self.breakthrough_squares = []
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

    def get_game_state(self) -> dict:
        """Return complete game state for UI."""
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
    def validate_devils_file(self, path: str) -> None:
        """Load and validate devils file if it exists. Fails only when file exists and invalid."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)
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

    def validate_devils_file(self, path: str) -> None:
        """Load and validate devils file if it exists. Fails only when file exists and invalid."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)

    def validate_devils_file(self, path: str) -> None:
        """Load and validate devils file if it exists. Fails only when file exists and invalid."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)
    def validate_devils_file(self, path: str) -> None:
        """Load and validate devils file if it exists. Fails only when file exists and invalid."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)

    def validate_devils_file(self, path: str) -> None:
        """Load and validate devils file if it exists. Fails only when file exists and invalid."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)

    def validate_devils_file(self, path: str) -> None:
        """Load and validate devils file if it exists. Fails only when file exists and invalid."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)

    def validate_devils_file(self, path: str) -> None:
        """Load and validate devils file if it exists. Fails only when file exists and invalid."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)

    def validate_devils_file(self, path: str) -> None:
        """Load and validate devils file if it exists. Fails only when file exists and invalid."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)

    def validate_devils_file(self, path: str) -> None:
        """Load and validate devils file if it exists. Fails only when file exists and invalid."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)

    def validate_devils_file(self, path: str) -> None:
        """Load and validate devils file if it exists. Fails only when file exists and invalid."""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)
