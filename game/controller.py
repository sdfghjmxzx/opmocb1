# Controller (UI Adapter) – Phase 1 Vertical Slice
# Theme-agnostic core orchestrated via adapter; no UI animation state in core Player.

from typing import List, Tuple, Optional, Dict, Any, Set
from engine.movement import get_neighbors, is_blocked
from engine.push_bounce import detect_bounce, apply_bounce_discount
from engine.combat import calculate_hit_chance, calculate_damage, get_attack_quality, get_push_distance, calculate_defense_stamina_cost
from engine.devil_fruit import calculate_type_advantage
from engine.haki import calculate_haki_effectiveness, calculate_haki_cost, set_config
from engine.walls import WallSystem
from engine.tiles import TileSystem
from engine.pattern import PatternEvaluator
from engine.effects import EffectsEngine, StatusEffect
from engine.animation import AnimationSystem, AnimationEntry
from engine.fov import get_fov_layer, get_compass_direction, normalize_facing, FOV_LAYER_MAP
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
        # Health & Stamina Pools (per spec 2.2)
        self.max_health = self._calculate_max_health()
        self.max_stamina = self._calculate_max_stamina()
        self.health = self.max_health
        self.stamina = self.max_stamina
    
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
    
    def _calculate_max_health(self) -> float:
        """Calculate max Health per spec 2.2 using strength+defense with END/WIL scaling."""
        primary_sum = self.strength + self.defense
        base = primary_sum
        end_term = primary_sum * (self.endurance / 100.0) * 0.667
        wil_term = primary_sum * (self.willpower / 150.0) * 0.5
        return base + end_term + wil_term
    
    def _calculate_max_stamina(self) -> float:
        """Calculate max Stamina per spec 2.2 using speed+reaction with END/WIL scaling."""
        primary_sum = self.speed + self.reaction
        base = primary_sum
        end_term = primary_sum * (self.endurance / 100.0) * 0.667
        wil_term = primary_sum * (self.willpower / 150.0) * 0.5
        return base + end_term + wil_term
    
    def recover_df_stamina(self) -> float:
        """Recover DF stamina per spec 2.3: MaxDFStamina × (mastery × 0.002)"""
        max_df = self._calculate_max_df_stamina()
        recovery = max_df * (self.devil_fruit_mastery * 0.002)
        self.devil_fruit_stamina = min(self.devil_fruit_stamina + recovery, max_df)
        return recovery
    
    def recover_stamina_and_health(self) -> Tuple[float, float]:
        """Recover Stamina and Health per spec 2.3 using MaxStamina as base."""
        primary_sum = self.speed + self.reaction
        if primary_sum <= 0:
            return 0.0, 0.0
        if primary_sum <= 100:
            exponent = 1.1 + 0.002 * (primary_sum - 50)
        else:
            exponent = 1.2 + 0.004 * (primary_sum - 100)
        base_k = 0.000304 * (50.0 / float(primary_sum)) ** exponent
        recovery_rate = 0.02 + (base_k * self.endurance * 0.667) + (base_k * self.willpower * 0.333)
        max_stamina = self._calculate_max_stamina()
        max_health = self._calculate_max_health()
        stamina_recovery = max_stamina * recovery_rate
        health_recovery = max_stamina * recovery_rate * 0.5
        # Update cached maxima
        self.max_stamina = max_stamina
        self.max_health = max_health
        self.stamina = min(self.stamina + stamina_recovery, self.max_stamina)
        self.health = min(self.health + health_recovery, self.max_health)
        return stamina_recovery, health_recovery

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

    def _classify_tile_field(self, attacker_row: int, attacker_col: int, attacker_facing: float, tile_row: int, tile_col: int) -> str:
        """Classify a tile into Front/Back/Left/Right field using FOV-style dividers.

        Rules:
        - Front  = FOV wedge for current facing (from FOV_LAYER_MAP).
        - Back   = FOV wedge for opposite facing ("inverted FOV"), not the generic Behind half-plane.
        - Left/Right = remaining tiles, split by lateral side of facing vector.
        """
        dx = tile_col - attacker_col
        dy = tile_row - attacker_row

        # Same tile as attacker: treat as Front
        if dx == 0 and dy == 0:
            return "Front"

        # Diagonal facings: align fields to cardinal dividers via quadrants
        facing_dir_diag = normalize_facing(attacker_facing)
        if facing_dir_diag in ("NorthEast", "SouthEast", "SouthWest", "NorthWest") and dx != 0 and dy != 0:
            # Use relative quadrant of tile around attacker to decide field so that
            # Front/Back/Left/Right regions follow the horizontal/vertical dividers.
            if facing_dir_diag == "NorthEast":
                if dy < 0 and dx > 0:
                    return "Front"   # NE quadrant
                elif dy > 0 and dx < 0:
                    return "Back"    # SW quadrant
                elif dy < 0 and dx < 0:
                    return "Left"    # NW quadrant
                else:
                    return "Right"   # SE quadrant
            elif facing_dir_diag == "SouthEast":
                if dy > 0 and dx > 0:
                    return "Front"   # SE quadrant
                elif dy < 0 and dx < 0:
                    return "Back"    # NW quadrant
                elif dy < 0 and dx > 0:
                    return "Left"    # NE quadrant
                else:
                    return "Right"   # SW quadrant
            elif facing_dir_diag == "SouthWest":
                if dy > 0 and dx < 0:
                    return "Front"   # SW quadrant
                elif dy < 0 and dx > 0:
                    return "Back"    # NE quadrant
                elif dy > 0 and dx > 0:
                    return "Left"    # SE quadrant
                else:
                    return "Right"   # NW quadrant
            else:  # "NorthWest"
                if dy < 0 and dx < 0:
                    return "Front"   # NW quadrant
                elif dy > 0 and dx > 0:
                    return "Back"    # SE quadrant
                elif dy > 0 and dx < 0:
                    return "Left"    # SW quadrant
                else:
                    return "Right"   # NE quadrant

        # Determine compass direction of tile relative to attacker
        compass_dir = get_compass_direction(dx, dy)

        # Normalize facing and compute opposite facing
        facing_dir = normalize_facing(attacker_facing)
        opposite_map = {
            "North": "South",
            "South": "North",
            "East": "West",
            "West": "East",
            "NorthEast": "SouthWest",
            "SouthWest": "NorthEast",
            "NorthWest": "SouthEast",
            "SouthEast": "NorthWest",
        }
        opposite_dir = opposite_map.get(facing_dir, "South")

        # Front = FOV directions for current facing
        front_dirs = set(FOV_LAYER_MAP.get(facing_dir, {}).get("FOV", []))
        # Back = FOV directions for opposite facing (inverted FOV)
        back_dirs = set(FOV_LAYER_MAP.get(opposite_dir, {}).get("FOV", []))

        if compass_dir in front_dirs:
            return "Front"
        if compass_dir in back_dirs:
            return "Back"

        # Remaining tiles: resolve Left vs Right via cross product against facing vector
        ang_rad = math.radians(attacker_facing % 360.0)
        fx = math.cos(ang_rad)
        fy = math.sin(ang_rad)
        vx = float(dx)
        vy = float(dy)
        cross = fx * vy - fy * vx

        # Sign convention was reversed; treat cross>0 as Right and cross<0 as Left
        if cross > 0:
            return "Right"
        elif cross < 0:
            return "Left"
        return "Front"

    def __init__(self):
        # Starting positions per spec (zero-index): P1 6D → (5,3), facing 270; P2 2D → (1,3), facing 90
        self.player1 = Player("Player 1", 5, 3, 270)
        self.player2 = Player("Player 2", 1, 3, 90)
        
        # Devil fruits will be assigned by sp_game_start label from character presets
        # Defaults set to None - preset system will override
        self.player1.devil_fruit_type = None
        self.player2.devil_fruit_type = None
        
        self.ui_p1 = UIPlayerState()
        self.ui_p2 = UIPlayerState()
        self.attacker_is_p1 = True

        # Animation system
        self.animation_system = AnimationSystem()

        # Sea doom visualization flags (set when a player is pushed into a Sea Tile and the game ends)
        self.p1_sea_doom = False
        self.p2_sea_doom = False

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
        self.debug_rays: List[Tuple[int, int, int, int]] = []  # Debug rays (src_row, src_col, tile_row, tile_col)
        
        # Defender counter pattern storage (for defensive phase with counter)
        self.defender_counter_attack_tiles: List[Tuple[int, int]] = []
        self.defender_counter_breakthrough_tiles: List[Tuple[int, int]] = []
        self.defender_counter_blocked_map: Dict[Tuple[int, int], List[Tuple[int, int, str]]] = {}
        
        self.current_path: List[Tuple[int, int]] = []
        self.planned_actions: List[Tuple[str, object]] = []
        self.battle_log: List[str] = []  # Deprecated - kept for compatibility
        self.debug_last_display: str = ""
        
        # Battle History - structured log for console display
        self.battle_history: List[Dict[str, Any]] = []  # List of turn records
        self.current_turn_record: Optional[Dict[str, Any]] = None  # Active turn being built
        self.system_turn_counter: int = 1  # Actual turn counter (increments after defense phase)
        
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
        # Pass player positions to avoid spawning tiles on them
        player_positions = [(self.player1.row, self.player1.col), (self.player2.row, self.player2.col)]
        self.tile_system.spawn_initial_tiles(avg_primary_sum, player_positions)
        # Multiplayer: by default, allow local tile spawns (single-player / offline).
        # MP setup can disable this flag to rely on server-driven map RNG.
        self.use_local_tile_spawns = True
        # Multiplayer mode flag - set to True when in MP battles to skip local RNG
        self.is_multiplayer = False
        # Pending server resolution (used in MP to apply server hit/damage after headless replay)
        self.pending_server_resolution = None
        # Object tracking for MP manifest (PHASE 1)
        self.objects_created_this_turn = []  # [{"type": "wall"/"tile", "row": int, "col": int, "orientation"/"tile_type": str, "hp": int}]
        self.objects_destroyed_this_turn = []  # [{"type": "wall"/"tile", "row": int, "col": int, "orientation"/"tile_type": str}]
        
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
                            # Recalculate pools based on loaded stats
                            player.max_health = player._calculate_max_health()
                            player.max_stamina = player._calculate_max_stamina()
                            player.health = player.max_health
                            player.stamina = player.max_stamina
                            player.haki_stamina = player._calculate_max_haki_stamina()
                            player.devil_fruit_stamina = player._calculate_max_df_stamina()
            
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
        # Save starting facing for animation builder
        self.planning_start_facing = p.facing
        self.ghost_facing = p.facing
        self.current_path = [(p.row, p.col)]
        self.planned_actions = []
        self.planning_terminal = False
        self.move_facing_history = []  # Reset facing history
        self.pattern_active_bonus = None
        self.pattern_applied_this_phase = False
        self._recompute_highlights()
        self._update_pattern_bonus()
        # Clear battle_log to prevent dict interpolation issues
        self.battle_log = []
        self.battle_log.append(f"Start planning: {p.name} at {p.get_position_str()} facing {p.facing}°")
        
        # Initialize FOV cache when planning starts
        self._update_fov_cache()
        
        # Force clear hover states when entering planning mode
        # This prevents stuck zoom when button becomes insensitive
        import renpy
        renpy.store.hovered_p1 = False
        renpy.store.hovered_p2 = False

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
            # Set origin for cascading breakthrough preview
            self._breakthrough_origin = (self.ghost_row, self.ghost_col)
            all_pattern_tiles = self._compute_attack_pattern_preview()
            # Separate normal attack tiles from breakthrough tiles
            self.attack_highlighted_squares, self.breakthrough_squares = self._separate_breakthrough_tiles(
                all_pattern_tiles,
                attacker_override=self.get_current_player()
            )
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
                        
                        # Apply DF range boosters to special cardinal pattern
                        tiles = self._apply_df_range_boost_to_tiles(tiles, r, c, ang)
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
                        
                        # Apply DF range boosters to special diagonal pattern
                        tiles = self._apply_df_range_boost_to_tiles(tiles, r, c, ang)
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
    
    def _compute_attack_pattern_preview_for_player(self, player, override_row=None, override_col=None) -> List[Tuple[int, int]]:
        """Compute quick attack pattern for a specific player (used for counter flash).
        
        Args:
            player: The player to compute pattern for
            override_row: Optional row to use instead of player.row
            override_col: Optional col to use instead of player.col
        """
        tiles: List[Tuple[int, int]] = []
        r = override_row if override_row is not None else player.row
        c = override_col if override_col is not None else player.col
        ang = int(player.facing) % 360
        
        # Counter always uses quick attack (range 1)
        attack_range = 1
        
        # Check if facing is cardinal or diagonal
        is_cardinal = ang in [0, 90, 180, 270]
        
        if is_cardinal:
            # Cardinal attack: 3 tiles wide × 1 tile deep
            tiles = self._compute_cardinal_attack_pattern(r, c, ang, attack_range)
        else:
            # Diagonal attack: Use tier algorithm
            tiles = self._compute_diagonal_attack_pattern(r, c, ang, attack_range)
        
        return tiles
    
    def _compute_cardinal_attack_pattern(self, r: int, c: int, ang: int, attack_range: int) -> List[Tuple[int, int]]:
        """Compute cardinal attack pattern (3 wide × range deep rectangle).
        Width and length are modified by DF range booster alloys (width_boost, length_boost).
        """
        tiles = []

        # Apply DF range boosters (cardinal only)
        extra_width, extra_length = self._get_df_range_boosts()
        # Effective depth: base range + length boost, clamped to board size
        eff_range = max(1, min(7, attack_range + extra_length))
        # Effective width: base 3 tiles (half_width=1) plus width boost (2 or 4) → widths 5 or 7
        half_width = 1 + (extra_width // 2)
        width_offsets = range(-half_width, half_width + 1)
        
        if ang == 0:  # East
            # 3+ tiles wide (rows), eff_range tiles deep (cols)
            for depth in range(1, eff_range + 1):
                nc = c + depth
                if nc >= 7:
                    break
                for width_offset in width_offsets:
                    nr = r + width_offset
                    if 0 <= nr < 7:
                        tiles.append((nr, nc))
        elif ang == 90:  # South
            # 3+ tiles wide (cols), eff_range tiles deep (rows)
            for depth in range(1, eff_range + 1):
                nr = r + depth
                if nr >= 7:
                    break
                for width_offset in width_offsets:
                    nc = c + width_offset
                    if 0 <= nc < 7:
                        tiles.append((nr, nc))
        elif ang == 180:  # West
            # 3+ tiles wide (rows), eff_range tiles deep (cols)
            for depth in range(1, eff_range + 1):
                nc = c - depth
                if nc < 0:
                    break
                for width_offset in width_offsets:
                    nr = r + width_offset
                    if 0 <= nr < 7:
                        tiles.append((nr, nc))
        elif ang == 270:  # North
            # 3+ tiles wide (cols), eff_range tiles deep (rows)
            for depth in range(1, eff_range + 1):
                nr = r - depth
                if nr < 0:
                    break
                for width_offset in width_offsets:
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
        
        # Apply DF range boosters (diagonal patterns)
        tiles = self._apply_df_range_boost_to_tiles(tiles, r, c, ang)
        
        # Apply wall blocking per Section 7.6 (internal walls only)
        tiles = self._filter_diagonal_attack_pattern_by_walls(tiles, r, c, attack_range, ang)
        return tiles
    
    def _compute_wall_attack_base_damage(self, attack_type: str, attacker) -> int:
        """DEPRECATED: Use _calculate_wall_damage() instead.
        Kept for backward compatibility but should not be used for new code.
        """
        # Universal base damage before special modifiers
        base = 20
        calc_attack_type = attack_type
        
        # Special Devil Fruit attacks: apply JSON-driven damage modifiers
        if isinstance(attack_type, str) and attack_type.startswith("special:"):
            special_name = attack_type.split(":", 1)[1]
            special_data = None
            if attacker.devil_fruit_data:
                special_actions = attacker.devil_fruit_data.get("special_attacks", {})
                special_data = special_actions.get(special_name)
            if special_data:
                df_dmg_mod = special_data.get('damage_modifier', 0)
                base = max(1, int(round(base * (1.0 + df_dmg_mod / 100.0))))
            # Specials use neutral quick/normal/heavy modifier
            calc_attack_type = "normal"
        
        damage_mod = 0.0
        if calc_attack_type == "quick":
            damage_mod -= 0.50
        elif calc_attack_type == "heavy":
            damage_mod += 0.50
        
        effective_base = max(1, int(round(base * (1.0 + damage_mod))))
        return effective_base
    
    def _calculate_wall_damage(self, attack_type: str, attacker) -> int:
        """Calculate damage against walls/objects using full combat formula.
        
        Walls are treated as defenders with 0 defense stats.
        Hit chance is always 100% (no roll needed).
        
        Returns: Integer damage value
        """
        from engine.combat import calculate_damage
        from engine.devil_fruit import calculate_type_advantage
        from engine.haki import calculate_haki_effectiveness
        
        # Base damage
        base_damage = 20
        calc_attack_type = attack_type
        
        # Special DF attacks modify base damage
        if isinstance(attack_type, str) and attack_type.startswith("special:"):
            special_name = attack_type.split(":", 1)[1]
            if attacker.devil_fruit_data:
                special_actions = attacker.devil_fruit_data.get("special_attacks", {})
                special_data = special_actions.get(special_name)
                if special_data:
                    df_dmg_mod = special_data.get('damage_modifier', 0)
                    base_damage = max(1, int(round(base_damage * (1.0 + df_dmg_mod / 100.0))))
            calc_attack_type = "normal"  # Specials use neutral type
        
        # Get movement bonuses
        facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
        bounce_bonus = 0.0
        if self.bounce_active:
            hits = [0.10, 0.125, 0.15, 0.175, 0.20]
            idx = min(max(1, self.bounce_chain_length), 5) - 1
            bounce_bonus = hits[idx]
        # Wall damage calculation - use current pattern bonus only
        pattern_dmg = 0.0
        if self.pattern_active_bonus and not self.pattern_applied_this_phase:
            pattern_dmg = self.pattern_active_bonus.get('damage_bonus', 0.0)
        
        # DF type advantage (walls have no DF type, so no defender multiplier)
        df_multipliers = None
        
        # Haki effectiveness (walls have no haki, so 0 for defender)
        att_arm_active = getattr(self, 'attacker_arm_active', False)
        haki_arm_eff_attacker = calculate_haki_effectiveness(attacker.haki_armament, 0, att_arm_active) if att_arm_active else 0.0
        haki_arm_eff_defender = 0.0  # Walls have no haki
        
        # Get DF alloys
        attacker_df_alloys = self.applied_df_alloys if hasattr(self, 'applied_df_alloys') else set()
        defender_df_alloys = set()  # Walls have no DF alloys
        
        # Apply status effect stat modifications to attacker
        effective_attacker = self._get_effective_player(attacker)
        
        # Create dummy wall "defender" with 0 stats
        class WallDefender:
            def __init__(self):
                self.name = "Wall"
                self.strength = 0
                self.defense = 0  # Key: 0 defense
                self.speed = 0
                self.reaction = 0
                self.endurance = 0
                self.aura = 0
                self.willpower = 0
                self.combat_instinct = 0
                self.haki_armament = 0
                self.haki_observation = 0
                self.devil_fruit_type = None
                self.devil_fruit_mastery = 0
        
        wall_defender = WallDefender()
        
        # Call damage formula (attack phase, no defense type)
        damage = calculate_damage(
            effective_attacker, wall_defender, base_damage, calc_attack_type, None,
            facing_bonus, bounce_bonus, pattern_dmg,
            df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
            is_defense_phase=False,
            attacker_df_alloys=attacker_df_alloys,
            defender_df_alloys=defender_df_alloys
        )
        
        return damage
    
    def _separate_breakthrough_tiles(self, unblocked_tiles: List[Tuple[int, int]], attack_type_override: Optional[str] = None, attacker_override: Optional[Any] = None, wall_damage_override: Optional[int] = None) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        """Find blocked tiles that will breakthrough using tracked blocking data.
        
        Uses self.blocked_tiles_map populated during wall filtering.
        For multi-wall blocks, ALL walls must break for breakthrough.
        
        Args:
            attack_type_override: If provided, use this attack type instead of getting from planned actions.
                                  Used during defense phase to calculate enemy attack breakthrough.
        
        Returns: (normal_attack_tiles, breakthrough_tiles)
        """
        if not self.blocked_tiles_map:
            return unblocked_tiles, []
        
        attack_type = attack_type_override if attack_type_override else self._get_selected_attack_type()
        if not attack_type:
            return unblocked_tiles, []
        
        attacker = attacker_override if attacker_override is not None else self.get_current_player()
        
        if wall_damage_override is not None:
            wall_damage = wall_damage_override
        else:
            # Calculate wall damage using FULL combat damage formula
            wall_damage = self._calculate_wall_damage(attack_type, attacker)
        
        print(f"[BREAKTHROUGH] Blocked tiles to check: {len(self.blocked_tiles_map)}")
        print(f"[BREAKTHROUGH] Attack damage: {wall_damage}")
        
        breakthrough_tiles_set: Set[Tuple[int, int]] = set()
        
        # Determine attack origin for preview (set by callers before invoking this function)
        origin = getattr(self, "_breakthrough_origin", None)
        if origin is not None:
            origin_row, origin_col = origin
            breakthrough_tiles_set = self._compute_cascading_breakthrough_preview(wall_damage, origin_row, origin_col)
        else:
            # Fallback: simple per-tile check (all blocking walls must break)
            for blocked_tile, blocking_wall_list in self.blocked_tiles_map.items():
                print(f"[BREAKTHROUGH] Tile {blocked_tile}: blocked by {len(blocking_wall_list)} wall(s)")
                walls = []
                for wall_row, wall_col, wall_orient in blocking_wall_list:
                    wall = self.wall_system.get_wall_at(wall_row, wall_col, wall_orient)
                    if wall and wall.tier != 'border':
                        walls.append(wall)
                        print(f"[BREAKTHROUGH]   Wall ({wall_row},{wall_col},{wall_orient}): HP={wall.hp}")
                if not walls:
                    continue
                all_break = all(wall.hp < wall_damage for wall in walls)
                if all_break:
                    breakthrough_tiles_set.add(blocked_tile)
        
        breakthrough_tiles = list(breakthrough_tiles_set)
        print(f"[BREAKTHROUGH] Result: {len(unblocked_tiles)} normal, {len(breakthrough_tiles)} breakthrough")
        return unblocked_tiles, breakthrough_tiles

    def _compute_cascading_breakthrough_preview(self, wall_damage: int, origin_row: int, origin_col: int) -> Set[Tuple[int, int]]:
        """Non-mutating cascading breakthrough preview per Rule Update8.
        
        Uses current wall HP values and blocked_tiles_map to determine which tiles
        would become breakthrough tiles and with what stored damage, without
        modifying any wall state.
        """
        breakthrough: Set[Tuple[int, int]] = set()
        if wall_damage <= 0 or not self.blocked_tiles_map:
            return breakthrough
        
        # Track tiles that were processed (breakthrough OR exact absorption)
        processed_tiles: Set[Tuple[int, int]] = set()
        
        # Group blocked tiles into cardinal lines (same row or column as origin).
        # Key: (axis, index, sign) where axis is 'row' or 'col', sign is +1 or -1 from origin.
        lines: Dict[Tuple[str, int, int], List[Tuple[int, int]]] = {}
        other_blocked: List[Tuple[int, int]] = []
        
        for (tr, tc) in self.blocked_tiles_map.keys():
            if tr == origin_row and tc == origin_col:
                continue
            if tc == origin_col and tr != origin_row:
                sign = 1 if tr > origin_row else -1
                key = ("col", origin_col, sign)
                lines.setdefault(key, []).append((tr, tc))
            elif tr == origin_row and tc != origin_col:
                sign = 1 if tc > origin_col else -1
                key = ("row", origin_row, sign)
                lines.setdefault(key, []).append((tr, tc))
            else:
                other_blocked.append((tr, tc))
        
        internal_walls = [w for w in self.wall_system._walls if w.tier != 'border']
        
        # Process vertical and horizontal lines with sequential propagation
        for (axis, index, sign), tiles in lines.items():
            if not tiles:
                continue
            
            if axis == "col":
                # Vertical line: same column, varying rows
                tile_positions = sorted(tiles, key=lambda t: (t[0] - origin_row) * sign)
                furthest_row = tile_positions[-1][0]
                # Collect horizontal walls on this column between origin and furthest tile
                line_walls = []
                for w in internal_walls:
                    if w.orientation != 'h' or w.col != index:
                        continue
                    if sign == 1:
                        if origin_row <= w.row < furthest_row:
                            line_walls.append(w)
                    else:
                        if furthest_row < w.row <= origin_row:
                            line_walls.append(w)
                if not line_walls:
                    continue
                line_walls.sort(key=lambda w: (w.row - origin_row) * sign)
                remaining = wall_damage
                tile_rows_sorted = sorted({r for (r, c) in tile_positions}, key=lambda r: (r - origin_row) * sign)
                for i, wall in enumerate(line_walls):
                    if remaining <= 0:
                        break
                    hp_before = max(0, wall.hp)
                    if remaining >= hp_before and hp_before > 0:
                        remaining_after = remaining - hp_before
                        this_row = wall.row
                        if i + 1 < len(line_walls):
                            next_row = line_walls[i + 1].row
                        else:
                            next_row = furthest_row
                        if sign == 1:
                            seg_min = this_row + 1
                            seg_max = next_row
                        else:
                            seg_min = next_row
                            seg_max = this_row - 1
                        
                        print(f"[PREVIEW] Wall {i} at row {this_row}: remaining={remaining}, hp={hp_before}, after={remaining_after}")
                        print(f"[PREVIEW] Segment: rows {seg_min} to {seg_max}, furthest={furthest_row}")
                        
                        if remaining_after > 0:
                            for r in tile_rows_sorted:
                                if seg_min <= r <= seg_max:
                                    breakthrough.add((r, index))
                                    processed_tiles.add((r, index))
                                    print(f"[PREVIEW] Added ({r},{index}) to BREAKTHROUGH")
                        else:
                            # Exact absorption: mark tiles as processed but don't add to breakthrough
                            for r in tile_rows_sorted:
                                if seg_min <= r <= seg_max:
                                    processed_tiles.add((r, index))
                                    print(f"[PREVIEW] Marked ({r},{index}) as PROCESSED (exact absorption)")
                        remaining = remaining_after
                    else:
                        # Wall survives and absorbs remaining damage; cascade stops on this line
                        remaining = 0
                        break
            elif axis == "row":
                # Horizontal line: same row, varying columns
                tile_positions = sorted(tiles, key=lambda t: (t[1] - origin_col) * sign)
                furthest_col = tile_positions[-1][1]
                # Collect vertical walls on this row between origin and furthest tile
                line_walls = []
                for w in internal_walls:
                    if w.orientation != 'v' or w.row != index:
                        continue
                    if sign == 1:
                        if origin_col <= w.col < furthest_col:
                            line_walls.append(w)
                    else:
                        if furthest_col < w.col <= origin_col:
                            line_walls.append(w)
                if not line_walls:
                    continue
                line_walls.sort(key=lambda w: (w.col - origin_col) * sign)
                remaining = wall_damage
                tile_cols_sorted = sorted({c for (r, c) in tile_positions}, key=lambda c: (c - origin_col) * sign)
                for i, wall in enumerate(line_walls):
                    if remaining <= 0:
                        break
                    hp_before = max(0, wall.hp)
                    if remaining >= hp_before and hp_before > 0:
                        remaining_after = remaining - hp_before
                        this_col = wall.col
                        if i + 1 < len(line_walls):
                            next_col = line_walls[i + 1].col
                        else:
                            next_col = furthest_col
                        if sign == 1:
                            seg_min = this_col + 1
                            seg_max = next_col
                        else:
                            seg_min = next_col
                            seg_max = this_col - 1
                        if remaining_after > 0:
                            for c in tile_cols_sorted:
                                if seg_min <= c <= seg_max:
                                    breakthrough.add((index, c))
                                    processed_tiles.add((index, c))
                        else:
                            # Exact absorption: mark tiles as processed but don't add to breakthrough
                            for c in tile_cols_sorted:
                                if seg_min <= c <= seg_max:
                                    processed_tiles.add((index, c))
                        remaining = remaining_after
                    else:
                        remaining = 0
                        break
        
        # Fallback: for any blocked tiles not handled by cardinal-line cascade (e.g., diagonal cases),
        # use simple "all blocking walls break" rule for preview.
        for blocked_tile, blocking_wall_list in self.blocked_tiles_map.items():
            if blocked_tile in processed_tiles:
                continue
            walls = []
            total_hp = 0
            for wall_row, wall_col, wall_orient in blocking_wall_list:
                wall = self.wall_system.get_wall_at(wall_row, wall_col, wall_orient)
                if wall and wall.tier != 'border':
                    walls.append(wall)
                    total_hp += max(0, wall.hp)
            # Breakthrough only if all walls destroyed AND damage exceeds total HP
            if walls and all(wall.hp < wall_damage for wall in walls):
                remaining_damage_fallback = wall_damage - total_hp
                if remaining_damage_fallback > 0:
                    breakthrough.add(blocked_tile)
        
        return breakthrough
    
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
            
            # Update FOV cache after position change
            # Always update: attacker moving affects FOV, defender moving affects FOV
            self._update_fov_cache()
            
            # Bounce detection FIRST, then continuity check
            continuing_chain = False
            
            # Phase 1: Detect NEW bounce
            if len(self.current_path) >= 3:
                bounce_result = detect_bounce(self.current_path[-3:], self.wall_system, self.tile_system)
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
                pattern_name = self.pattern_active_bonus.get('name', 'Unknown')
                self.battle_log.append(f"Pattern active: {pattern_name}")
            tile_str = action_data.get('tile', 'Unknown')
            self.battle_log.append(f"Move → {tile_str}")
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
            bounce_result = detect_bounce(triplet, self.wall_system, self.tile_system)
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
        
        # Update FOV cache after rotation
        # Only matters if defender rotates (changes their FOV)
        # Attacker rotation doesn't affect their position in defender's FOV
        if self.phase == "defense":
            # Defense phase: current player is defender, rotation matters
            self._update_fov_cache()
        # Attack phase: current player is attacker, rotation doesn't affect FOV position

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
            # Reset Haki activation flags
            self.attacker_obs_active = False
            self.attacker_arm_active = False
            self.defender_obs_active = False
            self.defender_arm_active = False
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
        
        # Set Haki activation flags for current phase
        if self.phase == "attack":
            self.attacker_arm_active = (haki_type == "armament")
            self.attacker_obs_active = (haki_type == "observation")
        elif self.phase == "defense":
            self.defender_arm_active = (haki_type == "armament")
            self.defender_obs_active = (haki_type == "observation")
        
        # Add haki action to planned_actions for undo tracking
        self.planned_actions.append(("haki", haki_type))
        
        self.battle_log.append(f"Haki alloy applied: {haki_type} (-{cost} Haki stamina)")
        self.debug_planned_actions_display()
        
        # Recalculate attack pattern if attack is selected (bonuses may affect breakthrough)
        if self.phase == "attack" and any(a[0] == "attack" for a in self.planned_actions):
            self._recalculate_attack_pattern_on_change()
        # Recalculate enemy patterns in defense phase (Haki may affect counter/preview)
        elif self.phase == "defense":
            self.recalculate_enemy_patterns()

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
        
        # Recalculate attack pattern if attack is selected (damage alloy affects breakthrough)
        if self.phase == "attack" and any(a[0] == "attack" for a in self.planned_actions):
            self._recalculate_attack_pattern_on_change()
        # Recalculate enemy patterns in defense phase (DF alloys may affect counter/preview)
        elif self.phase == "defense":
            self.recalculate_enemy_patterns()
    
    def select_df_alloy_for_level(self, alloy_type: str) -> None:
        """Enter level selection mode for width/length boost alloys."""
        self.df_alloy_level_select = alloy_type
    
    def cancel_df_alloy_level_select(self) -> None:
        """Exit level selection mode."""
        self.df_alloy_level_select = None
        
    def _get_df_range_boosts(self) -> Tuple[int, int]:
        """Return (extra_width, extra_length) from applied DF range booster alloys.
        Width boost uses Rule Update widths (L1=+2, L2=+4); length boost uses level as +depth.
        """
        extra_width = 0
        extra_length = 0
        if not self.applied_df_alloys:
            return 0, 0
        for alloy_key in self.applied_df_alloys:
            if ":" in alloy_key:
                alloy_type, level_str = alloy_key.split(":", 1)
                try:
                    level = int(level_str)
                except ValueError:
                    continue
            else:
                alloy_type = alloy_key
                level = 1
            if alloy_type == "width_boost":
                # Width Boost L1/L2: expand width 3→5 or 5→7 (Rule Update table)
                width_map = {1: 2, 2: 4}
                extra_width = max(extra_width, width_map.get(level, 0))
            elif alloy_type == "length_boost":
                # Length boost: +1 to +6 depth based on level
                extra_length = max(extra_length, level)
        return extra_width, extra_length
        
    def _apply_df_range_boost_to_tiles(self, tiles: List[Tuple[int, int]], origin_row: int, origin_col: int, ang: int) -> List[Tuple[int, int]]:
        """Apply DF width/length boosters to an arbitrary attack pattern.
        - Length boost extends tiles forward along facing.
        - Width boost extends tiles sideways (left/right) relative to facing.
        """
        if not tiles:
            return tiles
        extra_width, extra_length = self._get_df_range_boosts()
        if extra_width <= 0 and extra_length <= 0:
            return tiles
        # Get facing vector (col_delta, row_delta)
        facing_vec = self._facing_to_vector(float(ang))
        if facing_vec == (999, 999):
            return tiles
        fx, fy = facing_vec  # fx = col direction, fy = row direction
        
        # Use a set to avoid duplicates
        original_tiles = list(tiles)
        existing = set(tiles)
        extended = list(tiles)
        # Length: push tiles forward along facing
        if extra_length > 0:
            base_positions = list(original_tiles)
            for row, col in base_positions:
                for step in range(1, extra_length + 1):
                    nr = row + step * fy
                    nc = col + step * fx
                    if 0 <= nr < 7 and 0 <= nc < 7 and (nr, nc) not in existing:
                        existing.add((nr, nc))
                        extended.append((nr, nc))
        # Width: extend sideways relative to facing
        if extra_width > 0:
            side_steps = extra_width // 2
            if side_steps > 0:
                left_vec = (-fy, fx)
                right_vec = (fy, -fx)
                base_positions = list(original_tiles)
                for row, col in base_positions:
                    for step in range(1, side_steps + 1):
                        # Left side
                        nr = row + step * left_vec[1]
                        nc = col + step * left_vec[0]
                        if 0 <= nr < 7 and 0 <= nc < 7 and (nr, nc) not in existing:
                            existing.add((nr, nc))
                            extended.append((nr, nc))
                        # Right side
                        nr = row + step * right_vec[1]
                        nc = col + step * right_vec[0]
                        if 0 <= nr < 7 and 0 <= nc < 7 and (nr, nc) not in existing:
                            existing.add((nr, nc))
                            extended.append((nr, nc))
        return extended
        
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
        
        # Check if tile is in range from player position (use ghost position if available)
        if self.ghost_row is not None and self.ghost_col is not None:
            player_pos = (self.ghost_row, self.ghost_col)
        else:
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
            # If clicking the same tile again, deselect it
            if self.wall_first_tile == (row, col):
                self.wall_first_tile = None
                self.wall_first_tile_highlight = None
                self.battle_log.append(f"First tile deselected: ({row},{col})")
                return
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
        
        # Track wall creation for MP manifest (PHASE 1)
        if self.is_multiplayer:
            self.objects_created_this_turn.append({
                "type": "wall",
                "row": wall_row,
                "col": wall_col,
                "orientation": orientation,
                "tier": "player",  # Player-created walls always have 'player' tier
                "hp": hp_per_click
            })
        
        # Track wall creation
        self.player_created_walls.append((wall_row, wall_col, orientation))
        
        # Add to planned actions
        self.planned_actions.append(("wall_create", (wall_row, wall_col, orientation, total_cost)))
        
        # Increment operation counter for defense phase
        if self.phase == "defense":
            self.wall_operations_this_phase += 1
        
        self.battle_log.append(f"Wall created at ({wall_row},{wall_col},{orientation}) - {hp_per_click} HP, -{total_cost:.1f} DF stamina")
        self.debug_planned_actions_display()
        
        # Recalculate available movement tiles (wall blocks movement)
        self._recompute_highlights()
        
        # Recalculate attack pattern (wall blocks tiles, affects breakthrough)
        if self.phase == "attack" and any(a[0] == "attack" for a in self.planned_actions):
            self._recalculate_attack_pattern_on_change()
        # Recalculate blocked tiles if in defense phase
        elif self.phase == "defense":
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
        
        # Add to planned actions; replacement should be treated as a NEW action at the end
        # Capture previous tile action (if any) AND its original index so undo can restore order
        prev_tile_action = None
        prev_tile_index = None
        for idx, a in enumerate(self.planned_actions):
            if a[0] == "tile_creation":
                prev_tile_action = a
                prev_tile_index = idx
                break
        # Remove any existing tile_creation action first to keep other actions' order intact
        self.planned_actions = [a for a in self.planned_actions if a[0] != "tile_creation"]
        # Append new tile action, linking to previous one and its index for undo chaining
        self.planned_actions.append(("tile_creation", self.selected_tile_type, row, col, prev_tile_action, prev_tile_index))
        
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
        # Only stack reinforcements into the SAME last action; otherwise create a new one
        existing_action = None
        if self.planned_actions:
            last_idx = len(self.planned_actions) - 1
            last = self.planned_actions[last_idx]
            if last[0] == "wall_reinforce" and last[1][:3] == (row, col, orientation):
                existing_action = last_idx
        
        if existing_action is not None:
            # Update existing last action (stack reinforcement clicks)
            old_row, old_col, old_orient, old_count, old_cost = self.planned_actions[existing_action][1]
            new_count = old_count + 1
            new_cost = old_cost + click_cost
            self.planned_actions[existing_action] = ("wall_reinforce", (row, col, orientation, new_count, new_cost))
            self.wall_reinforce_count = new_count
            self.battle_log.append(f"Wall reinforced: +{hp_per_click} HP (total: {new_count} clicks, -{new_cost:.1f} DF stamina)")
        else:
            # Create new action (separate from any earlier reinforcements)
            self.planned_actions.append(("wall_reinforce", (row, col, orientation, 1, click_cost)))
            self.wall_reinforce_count = 1
            self.battle_log.append(f"Wall reinforced: +{hp_per_click} HP (1 click, -{click_cost:.1f} DF stamina)")
        
        self.debug_planned_actions_display()
        
        # Recalculate attack pattern (wall HP affects breakthrough)
        if self.phase == "attack" and any(a[0] == "attack" for a in self.planned_actions):
            self._recalculate_attack_pattern_on_change()
        # Recalculate blocked tiles if in defense phase
        elif self.phase == "defense":
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
        Stores results separately for hover display only - does NOT populate attack_highlighted_squares.
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
            
            # Save previous counts for logging
            before_count = len(getattr(self, 'enemy_attack_tiles', []))
            before_blocked = len(self.blocked_tiles_map)
            before_breakthrough = len(getattr(self, 'enemy_breakthrough_tiles', []))
            
            # Compute the full enemy attack pattern from stored attack
            all_pattern_tiles = self._compute_attack_pattern_from_stored(self.pending_attack)
            print(f"Enemy attack pattern: {len(all_pattern_tiles)} tiles = {all_pattern_tiles}")
            # Set origin for cascading breakthrough preview (enemy attacker position)
            self._breakthrough_origin = (self.pending_attack['attacker_row'], self.pending_attack['attacker_col'])
            
            # Separate normal attack tiles from breakthrough tiles
            # This will re-filter walls and populate blocked_tiles_map
            # Pass enemy attack type explicitly to override defender's planned action type
            # Store in separate variables for hover-only display
            # Use stored attacker from pending_attack
            pending_attacker = self.player1 if self.pending_attack['attacker_is_p1'] else self.player2
            stored_wall_damage = self.pending_attack.get('wall_damage')
            self.enemy_attack_tiles, self.enemy_breakthrough_tiles = self._separate_breakthrough_tiles(
                all_pattern_tiles, 
                attack_type_override=self.pending_attack['type'],
                attacker_override=pending_attacker,
                wall_damage_override=stored_wall_damage
            )
            
            after_count = len(self.enemy_attack_tiles)
            after_blocked = len(self.blocked_tiles_map)
            after_breakthrough = len(self.enemy_breakthrough_tiles)
            
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
                self._breakthrough_origin = (self.ghost_row, self.ghost_col)
                counter_pattern = self._compute_attack_pattern_preview()
                print(f"Defender counter pattern (raw): {len(counter_pattern)} tiles = {counter_pattern}")
                
                # Separate counter attack tiles with wall filtering
                counter_attack_tiles, counter_breakthrough_tiles = self._separate_breakthrough_tiles(
                    counter_pattern,
                    attacker_override=self.get_opponent()
                )
                
                print(f"Defender counter after separation: {len(counter_attack_tiles)} attack, {len(counter_breakthrough_tiles)} breakthrough")
                self.battle_log.append(f"WALL_DEBUG: Defender counter: {len(counter_attack_tiles)} attack, {len(self.blocked_tiles_map)} blocked, {len(counter_breakthrough_tiles)} breakthrough")
                
                # Store defender's counter pattern separately for UI display
                # When hovering over enemy, we show enemy pattern
                # When not hovering, we show defender's counter pattern
                self.defender_counter_attack_tiles = counter_attack_tiles
                self.defender_counter_breakthrough_tiles = counter_breakthrough_tiles
                self.defender_counter_blocked_map = dict(self.blocked_tiles_map)
                
                # Restore enemy blocked map (don't populate attack_highlighted_squares)
                self.blocked_tiles_map = enemy_blocked_map
                
                print(f"Stored defender counter separately, restored enemy blocked map")
            else:
                print(f"No ghost position for counter pattern calculation")
        
        print(f"=== RECALCULATION COMPLETE ===\n")
    
    def _recalculate_attack_pattern_on_change(self) -> None:
        """Recalculate attack pattern and breakthrough tiles when damage/wall HP changes during attack phase planning.
        
        Triggers:
        - DF alloy applied (damage_alloy changes damage)
        - Haki alloy applied (armament changes damage)
        - Wall reinforced (wall HP changes breakthrough threshold)
        """
        if self.phase != "attack":
            return
        
        # Get the selected attack type
        attack_type = self._get_selected_attack_type()
        if not attack_type:
            return
        
        print(f"\n=== RECALCULATING ATTACK PATTERN (alloy/wall change) ===")
        
        # Store previous counts for logging
        before_attack = len(getattr(self, 'attack_highlighted_squares', []))
        before_breakthrough = len(getattr(self, 'breakthrough_squares', []))
        
        # Recompute the attack pattern with current bonuses
        self._breakthrough_origin = (self.ghost_row if self.ghost_row is not None else self.get_current_player().row,
                                      self.ghost_col if self.ghost_col is not None else self.get_current_player().col)
        
        all_pattern_tiles = self._compute_attack_pattern_preview()
        
        # Separate normal attack tiles from breakthrough tiles (re-evaluates wall damage)
        attack_tiles, breakthrough_tiles = self._separate_breakthrough_tiles(all_pattern_tiles)
        
        # Update display squares
        self.attack_highlighted_squares = attack_tiles
        self.breakthrough_squares = breakthrough_tiles
        
        after_attack = len(attack_tiles)
        after_breakthrough = len(breakthrough_tiles)
        
        print(f"Pattern updated: {after_attack} attack ({after_attack - before_attack:+d}), {after_breakthrough} breakthrough ({after_breakthrough - before_breakthrough:+d})")
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
            
            # Reduce wall HP and max HP symmetrically for player walls
            wall = self.wall_system.get_wall_at(wall_row, wall_col, orientation)
            if wall:
                wall.hp = max(0, wall.hp - hp_per_click)
                if getattr(wall, "creator", None) is not None:
                    wall.max_hp = max(0, wall.max_hp - hp_per_click)
            
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
            # Undo tile creation or replacement
            prev_action = last[4] if len(last) > 4 else None
            prev_index = last[5] if len(last) > 5 else None
            if prev_action is not None and prev_index is not None:
                # Restore previous tile placement at its original position in the list
                tile_type_key, tile_row, tile_col = prev_action[1], prev_action[2], prev_action[3]
                player = self.get_current_player()
                tiles_available = player.devil_fruit_data.get("map_abilities", {}).get("tiles_available", {})
                tile_config = tiles_available.get(tile_type_key)
                if tile_config:
                    df_cost = tile_config.get("df_cost", 0)
                    self.planned_tile_creation = {
                        "tile_type": tile_type_key,
                        "row": tile_row,
                        "col": tile_col,
                        "df_cost": df_cost,
                        "tile_config": tile_config,
                    }
                else:
                    self.planned_tile_creation = None
                # Reinsert previous tile action at its original index
                insert_index = min(max(prev_index, 0), len(self.planned_actions))
                self.planned_actions.insert(insert_index, prev_action)
                self.battle_log.append("Undo tile replacement → previous tile restored and order restored")
            else:
                # No previous tile state: fully undo creation
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
    
    def _build_turn_record(self) -> Dict[str, Any]:
        """Build structured turn record from current planned actions.
        
        Returns:
            Dictionary with:
            - player: str ("Player 1" or "Player 2")
            - player_color: str (hex color)
            - phase: str ("attack" or "defense")
            - moves: List[str] (position tiles only: ["5D", "4D", "3D"])
            - action: Optional[str] (attack/defense with bonuses from debug display)
            - results: List[str] (combat results, effects - added later)
        """
        p = self.get_current_player()
        player_name = p.name
        player_color = "#ff4444" if p == self.player1 else "#4444FF"
        
        # Get formatted actions from display system
        display_entries = self.get_planned_actions_display()
        
        # Extract movement positions (tile names only)
        moves = []
        action_text = None
        
        for entry in display_entries:
            entry_type = entry.get("type", "")
            text = entry.get("text", "")
            
            if entry_type == "move":
                # Extract tile position from "  5D - 13 Stamina (Dir -10% St +10% Hit +10% Dmg)"
                # Format: "  {tile} - {cost} Stamina {bonuses}"
                parts = text.strip().split(" - ")
                if parts:
                    tile = parts[0].strip()
                    moves.append(tile)
            
            elif entry_type == "attack":
                # Full attack text with bonuses: "  Heavy Attack (Dir -10% St +10% Hit +10% Dmg)"
                # Skip if it's just "Skip Attack"
                if "Skip" not in text:
                    action_text = text.strip()
            
            elif entry_type == "defense":
                # Full defense text with bonuses
                # Skip if it's just "Tank Defense"
                if "Tank" not in text or "(" in text:
                    action_text = text.strip()
        
        return {
            "turn": self.system_turn_counter,
            "player": player_name,
            "player_color": player_color,
            "phase": self.phase,
            "moves": moves,
            "action": action_text,
            "results": []  # Will be populated with combat/effect results
        }
    
    def _add_turn_result(self, result_text: str) -> None:
        """Add a result line to the current turn record."""
        if self.current_turn_record:
            self.current_turn_record["results"].append(result_text)
    
    def _finalize_turn_record(self) -> None:
        """Finalize and append current turn record to battle history."""
        if self.current_turn_record:
            self.battle_history.append(self.current_turn_record)
            self.current_turn_record = None

    def _calculate_attack_combat_only(self) -> None:
        """Calculate attack phase combat (miss check, wall damage, attack pattern) WITHOUT executing.
        Used in MP mode to get values for attack payload before sending to server.
        Stores results in last_attack_calc for payload extraction.
        """
        print(f"[MP] _calculate_attack_combat_only() CALLED - starting attack calculations")
        
        if self.phase != "attack":
            print(f"[MP] ERROR: Not in attack phase, current phase={self.phase}")
            return
        
        # Get attack type from planned actions
        attack_type = None
        for action in self.planned_actions:
            if action[0] == "attack" and action[1] != "skip":
                attack_type = action[1]
                break
        
        if not attack_type:
            print(f"[MP] ERROR: No attack action found in planned_actions")
            return
        
        attacker = self.get_current_player()
        defender = self.get_opponent()
        
        # Calculate attack pattern
        attack_tiles = self.attack_highlighted_squares if self.attack_highlighted_squares else self._compute_attack_pattern_preview()
        
        # Calculate wall damage
        wall_damage = self._calculate_wall_damage(attack_type, attacker)
        
        # Calculate breakthrough tiles
        breakthrough_tiles_damage = self._apply_wall_damage_to_pattern(attack_tiles, wall_damage, attacker.row, attacker.col)
        breakthrough_tiles = list(breakthrough_tiles_damage.keys())
        
        # Miss check: defender's CURRENT position (before defense movement)
        defender_pos = (defender.row, defender.col)
        is_miss = defender_pos not in attack_tiles and defender_pos not in breakthrough_tiles
        
        # Calculate bonuses
        attacker_facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
        attacker_bounce_bonus = 0.0
        if self.bounce_active:
            hits = [0.10, 0.125, 0.15, 0.175, 0.20]
            idx = min(max(1, self.bounce_chain_length), 5) - 1
            attacker_bounce_bonus = hits[idx]
        attacker_pattern_hit = 0.0
        attacker_pattern_dmg = 0.0
        if self.pattern_active_bonus:
            attacker_pattern_hit = self.pattern_active_bonus.get('hit_bonus', 0.0)
            attacker_pattern_dmg = self.pattern_active_bonus.get('damage_bonus', 0.0)
        
        # Store calculations for payload
        self.last_attack_calc = {
            'turn': self.system_turn_counter,
            'attacker_is_p1': self.attacker_is_p1,
            'attack_type': attack_type,
            'is_miss': is_miss,
            'defender_start_pos': defender_pos,
            'attack_tiles': attack_tiles,
            'breakthrough_tiles': breakthrough_tiles,
            'wall_damage': wall_damage,
            'attacker_facing_bonus': attacker_facing_bonus,
            'attacker_bounce_bonus': attacker_bounce_bonus,
            'attacker_pattern_hit': attacker_pattern_hit,
            'attacker_pattern_dmg': attacker_pattern_dmg,
        }
        print(f"[MP] Attack calculations complete: is_miss={is_miss}, wall_damage={wall_damage}, defender_pos={defender_pos}")
    
    def _calculate_defense_combat_only(self) -> None:
        """Calculate defense combat (hit/damage/counter) and populate last_defense_calc WITHOUT applying damage.
        Used in MP mode to get values for payload before sending to server.
        """
        print(f"[MP] _calculate_defense_combat_only() CALLED - starting calculations")
        
        if self.phase != "defense":
            print(f"[MP] ERROR: Not in defense phase, current phase={self.phase}")
            return
        
        if not self.pending_attack:
            print("[MP] ERROR: No pending attack - cannot calculate defense combat")
            return
        
        attack_info = self.pending_attack
        attack_type = attack_info['type']
        
        # Get attacker and defender
        if attack_info['attacker_is_p1']:
            attacker = self.player1
            defender = self.player2
        else:
            attacker = self.player2
            defender = self.player1
        
        # Set defender Haki flags
        if "armament" in self.applied_haki_alloys:
            self.defender_arm_active = True
        if "observation" in self.applied_haki_alloys:
            self.defender_obs_active = True
        
        # Store defender's DF alloys
        attack_info['defender_df_alloys'] = set(self.applied_df_alloys)
        
        base_damage = 20
        
        # Extract defense type
        defense_type = None
        for action in self.planned_actions:
            if action[0] == "defense":
                defense_type = action[1]
                break
        
        # Get bonuses
        attacker_facing_bonus = attack_info.get('attacker_facing_bonus', 0.0)
        attacker_bounce_bonus = attack_info.get('attacker_bounce_bonus', 0.0)
        attacker_pattern_hit = attack_info.get('attacker_pattern_hit', 0.0)
        attacker_pattern_dmg = attack_info.get('attacker_pattern_dmg', 0.0)
        
        defender_facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
        defender_bounce_bonus = 0.0
        if self.bounce_active:
            hits = [0.10, 0.125, 0.15, 0.175, 0.20]
            idx = min(max(1, self.bounce_chain_length), 5) - 1
            defender_bounce_bonus = hits[idx]
        
        # Use pattern_active_bonus from CURRENT planning session
        # This ensures we only use the defender's current movement pattern
        defender_pattern_hit = 0.0
        defender_pattern_dmg = 0.0
        if self.pattern_active_bonus:
            defender_pattern_hit = self.pattern_active_bonus.get('hit_bonus', 0.0)
            defender_pattern_dmg = self.pattern_active_bonus.get('damage_bonus', 0.0)
        
        print(f"[MP DEFENSE CALC] Defender bonuses: facing={defender_facing_bonus:.2f}, bounce={defender_bounce_bonus:.2f}, pattern_hit={defender_pattern_hit:.2f} (from pattern_active_bonus={self.pattern_active_bonus})")
        print(f"[MP DEFENSE CALC] Attacker bonuses from pending_attack: facing={attacker_facing_bonus:.2f}, bounce={attacker_bounce_bonus:.2f}, pattern_hit={attacker_pattern_hit:.2f}")
        
        net_facing_bonus = attacker_facing_bonus - defender_facing_bonus
        net_bounce_bonus = attacker_bounce_bonus - defender_bounce_bonus
        net_pattern_hit = attacker_pattern_hit - defender_pattern_hit
        net_pattern_dmg = attacker_pattern_dmg - defender_pattern_dmg
        
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
                base_damage = max(1, int(round(base_damage * (1.0 + df_dmg_mod / 100.0))))
                net_pattern_hit += df_hit_mod / 100.0
            calc_attack_type = "normal"
        
        # Wall damage and breakthrough
        attack_tiles = self._compute_attack_pattern_from_stored(attack_info)
        wall_damage = self._calculate_wall_damage(attack_type, attacker)
        breakthrough_tiles_damage = self._apply_wall_damage_to_pattern(attack_tiles, wall_damage, attacker.row, attacker.col)
        
        # Defender position
        if self.ghost_row is not None and self.ghost_col is not None:
            defender_tile = (self.ghost_row, self.ghost_col)
        elif hasattr(defender, 'current_path') and defender.current_path:
            defender_tile = defender.current_path[-1]
        elif attack_info.get('defender_row') is not None:
            defender_tile = (attack_info['defender_row'], attack_info['defender_col'])
        else:
            defender_tile = (defender.row, defender.col)
        
        # Check MISS
        is_miss = (defender_tile not in attack_tiles and 
                  defender_tile not in breakthrough_tiles_damage and 
                  defender_tile not in self.blocked_tiles_map)
        
        import random
        effective_attacker = self._get_effective_player(attacker)
        effective_defender = self._get_effective_player(defender)
        df_multipliers = None
        if attacker.devil_fruit_type or defender.devil_fruit_type:
            df_multipliers = calculate_type_advantage(
                attacker.devil_fruit_type,
                defender.devil_fruit_type,
                attacker.devil_fruit_mastery,
                defender.devil_fruit_mastery,
                self.devils_type_adv.get(attacker.devil_fruit_type) if attacker.devil_fruit_type else None
            )
        
        att_obs_active = getattr(self, 'attacker_obs_active', False)
        def_obs_active = getattr(self, 'defender_obs_active', False)
        att_arm_active = getattr(self, 'attacker_arm_active', False)
        def_arm_active = getattr(self, 'defender_arm_active', False)
        haki_obs_eff_attacker = calculate_haki_effectiveness(attacker.haki_observation, defender.haki_observation, att_obs_active and def_obs_active) if att_obs_active else 0.0
        haki_obs_eff_defender = calculate_haki_effectiveness(defender.haki_observation, attacker.haki_observation, att_obs_active and def_obs_active) if def_obs_active else 0.0
        haki_arm_eff_attacker = calculate_haki_effectiveness(attacker.haki_armament, defender.haki_armament, att_arm_active and def_arm_active) if att_arm_active else 0.0
        haki_arm_eff_defender = calculate_haki_effectiveness(defender.haki_armament, attacker.haki_armament, att_arm_active and def_arm_active) if def_arm_active else 0.0
        attacker_df_alloys = attack_info.get('attacker_df_alloys', set())
        defender_df_alloys = attack_info.get('defender_df_alloys', set())
        
        if is_miss:
            # MISS - store and return
            self.last_defense_calc = {
                'turn': self.system_turn_counter,
                'attacker_is_p1': attack_info.get('attacker_is_p1', True),
                'defense_type': defense_type,
                'is_miss': True,
                'hit_chance': 0.0,
                'base_damage': 0,
                'counter_is_miss': True,
                'counter_hit_chance': 0.0,
                'counter_base_damage': 0,
            }
            print(f"[MP] Calculated MISS - last_defense_calc populated")
            return
        
        # NOT MISS - calculate combat
        from engine.fov import get_fov_hit_bonus
        fov_hit_bonus = get_fov_hit_bonus(
            defender.facing,
            (defender.row, defender.col),
            (attacker.row, attacker.col)
        )
        
        hit_chance = calculate_hit_chance(
            effective_attacker, effective_defender, calc_attack_type, defense_type,
            net_facing_bonus, net_bounce_bonus, net_pattern_hit,
            df_multipliers, haki_obs_eff_attacker, haki_obs_eff_defender,
            is_defense_phase=True,
            attacker_df_alloys=attacker_df_alloys,
            defender_df_alloys=defender_df_alloys,
            fov_hit_bonus=fov_hit_bonus
        )
        
        dmg = calculate_damage(
            effective_attacker, effective_defender, base_damage, calc_attack_type, defense_type,
            net_facing_bonus, net_bounce_bonus, net_pattern_dmg,
            df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
            is_defense_phase=True,
            attacker_df_alloys=attacker_df_alloys,
            defender_df_alloys=defender_df_alloys
        )
        dmg = max(1, int(dmg))
        
        # Counter calculation
        counter_hit_chance = 0.0
        counter_base_damage = 0
        counter_is_miss = True
        
        if defense_type == "counter":
            counter_base_damage = 10
            counter_attack_type = "normal"
            
            counter_fov_bonus = 0.0
            if hasattr(self, '_get_fov_layer'):
                counter_fov_layer = self._get_fov_layer(
                    defender.facing,
                    (defender.row, defender.col),
                    (attacker.row, attacker.col)
                )
                if counter_fov_layer == "Periphery":
                    counter_fov_bonus = 0.10
                elif counter_fov_layer == "Behind":
                    counter_fov_bonus = 0.30
            
            counter_net_facing = defender_facing_bonus - attacker_facing_bonus
            counter_net_bounce = defender_bounce_bonus - attacker_bounce_bonus
            counter_net_pattern_hit = defender_pattern_hit - attacker_pattern_hit
            counter_net_pattern_dmg = defender_pattern_dmg - attacker_pattern_dmg
            
            counter_hit_chance = calculate_hit_chance(
                effective_defender, effective_attacker, counter_attack_type, None,
                counter_net_facing, counter_net_bounce, counter_net_pattern_hit,
                df_multipliers, haki_obs_eff_defender, haki_obs_eff_attacker,
                is_defense_phase=False,
                attacker_df_alloys=defender_df_alloys,
                defender_df_alloys=attacker_df_alloys,
                fov_hit_bonus=counter_fov_bonus
            )
            
            counter_damage_calc = calculate_damage(
                effective_defender, effective_attacker, counter_base_damage, counter_attack_type, None,
                counter_net_facing, counter_net_bounce, counter_net_pattern_dmg,
                df_multipliers, haki_arm_eff_defender, haki_arm_eff_attacker,
                is_defense_phase=False,
                attacker_df_alloys=defender_df_alloys,
                defender_df_alloys=attacker_df_alloys
            )
            counter_base_damage = max(1, int(counter_damage_calc))
            counter_is_miss = False
        
        # Store calculations
        self.last_defense_calc = {
            'turn': self.system_turn_counter,
            'attacker_is_p1': attack_info.get('attacker_is_p1', True),
            'defense_type': defense_type,
            'is_miss': False,
            'hit_chance': float(hit_chance),
            'base_damage': int(dmg),
            'net_facing_bonus': float(net_facing_bonus),
            'net_bounce_bonus': float(net_bounce_bonus),
            'net_pattern_hit': float(net_pattern_hit),
            'net_pattern_dmg': float(net_pattern_dmg),
            'counter_is_miss': bool(counter_is_miss),
            'counter_hit_chance': float(counter_hit_chance),
            'counter_base_damage': int(counter_base_damage),
        }
        print(f"[MP] Calculated HIT - last_defense_calc populated: hit_chance={hit_chance:.3f}, damage={dmg}, counter_hit_chance={counter_hit_chance:.3f}, counter_damage={counter_base_damage}")
    
    def _calculate_attacker_validation(self) -> None:
        """Attacker calculates hit_chance/damage after receiving defender's final position.
        Called headlessly (no planning mode) for server cross-validation.
        Stores results in last_attacker_validation for payload.
        """
        print(f"[MP] _calculate_attacker_validation() CALLED - attacker validating combat")
        
        if self.phase != "defense":
            print(f"[MP] ERROR: Not in defense phase, current phase={self.phase}")
            return
        
        # Use last_attack_calc if available (from attack phase)
        last_atk = getattr(self, 'last_attack_calc', None)
        if not last_atk or not hasattr(last_atk, 'get'):
            print(f"[MP] ERROR: No last_attack_calc available for validation")
            return
        
        attack_type = last_atk.get('attack_type')
        if not attack_type or attack_type == "skip":
            print(f"[MP] Attack was skip, no validation needed")
            return
        
        # Get players
        attacker_is_p1 = last_atk.get('attacker_is_p1', True)
        attacker = self.player1 if attacker_is_p1 else self.player2
        defender = self.player2 if attacker_is_p1 else self.player1
        
        # Get defender's FINAL position (after defense movement)
        defender_final_pos = (defender.row, defender.col)
        
        # Get attack pattern
        attack_tiles = last_atk.get('attack_tiles', [])
        breakthrough_tiles = last_atk.get('breakthrough_tiles', [])
        
        # Calculate miss with defender's FINAL position
        is_miss = defender_final_pos not in attack_tiles and defender_final_pos not in breakthrough_tiles
        
        if is_miss:
            # Miss - no combat calculations needed
            self.last_attacker_validation = {
                'turn': self.system_turn_counter,
                'is_miss': True,
                'hit_chance': 0.0,
                'damage': 0,
                'counter_is_miss': True,
                'counter_hit_chance': 0.0,
                'counter_damage': 0,
            }
            print(f"[MP] Attacker validation: MISS (defender moved out of pattern)")
            return
        
        # NOT MISS - calculate combat
        from engine.combat import calculate_hit_chance, calculate_damage
        from engine.devil_fruit import calculate_type_advantage
        from engine.fov import get_fov_hit_bonus
        
        # Get defense action from defender's planned_actions
        defense_type = None
        for action in self.planned_actions:
            if action[0] == "defense" and action[1] != "skip":
                defense_type = action[1]
                break
        
        # Calculate bonuses (net = attacker - defender)
        attacker_facing_bonus = last_atk.get('attacker_facing_bonus', 0.0)
        attacker_bounce_bonus = last_atk.get('attacker_bounce_bonus', 0.0)
        attacker_pattern_hit = last_atk.get('attacker_pattern_hit', 0.0)
        attacker_pattern_dmg = last_atk.get('attacker_pattern_dmg', 0.0)
        
        print(f"[MP ATTACKER VALIDATION] Attacker bonuses from last_attack_calc: facing={attacker_facing_bonus:.2f}, bounce={attacker_bounce_bonus:.2f}, pattern_hit={attacker_pattern_hit:.2f}")
        
        # Defender bonuses (extract from headless defense replay state)
        # These were calculated during apply_remote_defense_payload
        defender_facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
        defender_bounce_bonus = 0.0
        if self.bounce_active:
            hits = [0.10, 0.125, 0.15, 0.175, 0.20]
            idx = min(max(1, self.bounce_chain_length), 5) - 1
            defender_bounce_bonus = hits[idx]
        defender_pattern_hit = 0.0
        defender_pattern_dmg = 0.0
        if self.pattern_active_bonus:
            defender_pattern_hit = self.pattern_active_bonus.get('hit_bonus', 0.0)
            defender_pattern_dmg = self.pattern_active_bonus.get('damage_bonus', 0.0)
        
        print(f"[MP] Defender bonuses - facing={defender_facing_bonus:.2f}, bounce={defender_bounce_bonus:.2f}, pattern_hit={defender_pattern_hit:.2f}, pattern_dmg={defender_pattern_dmg:.2f}")
        print(f"[MP ATTACKER VALIDATION] pattern_active_bonus={self.pattern_active_bonus}")
        
        net_facing_bonus = attacker_facing_bonus - defender_facing_bonus
        net_bounce_bonus = attacker_bounce_bonus - defender_bounce_bonus
        net_pattern_hit = attacker_pattern_hit - defender_pattern_hit
        net_pattern_dmg = attacker_pattern_dmg - defender_pattern_dmg
        
        # Get base damage
        base_damage = 20
        if attack_type.startswith("special:"):
            special_name = attack_type.replace("special:", "")
            if attacker.devil_fruit_data:
                special_attacks = attacker.devil_fruit_data.get('special_attacks', {})
                if special_name in special_attacks:
                    damage_mod = special_attacks[special_name].get('damage_modifier', 1.0)
                    base_damage = int(20 * damage_mod)
        
        # Get DF alloys from pending_attack (set during attack phase) and applied alloys (set during defense phase)
        if hasattr(self, 'pending_attack') and self.pending_attack:
            attacker_df_alloys = self.pending_attack.get('attacker_df_alloys', set())
            defender_df_alloys = self.pending_attack.get('defender_df_alloys', set())
        else:
            attacker_df_alloys = set()
            defender_df_alloys = set()
        
        print(f"[MP] DF alloys - attacker={attacker_df_alloys}, defender={defender_df_alloys}")
        
        # Calculate DF type advantage
        from engine.devil_fruit import calculate_type_advantage as calc_df_adv
        df_multipliers = None
        if attacker.devil_fruit_type or defender.devil_fruit_type:
            df_multipliers = calc_df_adv(
                attacker.devil_fruit_type,
                defender.devil_fruit_type,
                attacker.devil_fruit_mastery,
                defender.devil_fruit_mastery,
                self.devils_type_adv.get(attacker.devil_fruit_type) if attacker.devil_fruit_type else None
            )
        
        # Calculate haki effectiveness from activation flags
        from engine.haki import calculate_haki_effectiveness
        att_obs_active = getattr(self, 'attacker_obs_active', False)
        def_obs_active = getattr(self, 'defender_obs_active', False)
        att_arm_active = getattr(self, 'attacker_arm_active', False)
        def_arm_active = getattr(self, 'defender_arm_active', False)
        
        haki_obs_eff_attacker = calculate_haki_effectiveness(attacker.haki_observation, defender.haki_observation, att_obs_active and def_obs_active) if att_obs_active else 0.0
        haki_obs_eff_defender = calculate_haki_effectiveness(defender.haki_observation, attacker.haki_observation, att_obs_active and def_obs_active) if def_obs_active else 0.0
        haki_arm_eff_attacker = calculate_haki_effectiveness(attacker.haki_armament, defender.haki_armament, att_arm_active and def_arm_active) if att_arm_active else 0.0
        haki_arm_eff_defender = calculate_haki_effectiveness(defender.haki_armament, attacker.haki_armament, att_arm_active and def_arm_active) if def_arm_active else 0.0
        
        print(f"[MP] Haki effectiveness - obs_att={haki_obs_eff_attacker:.2f}, obs_def={haki_obs_eff_defender:.2f}, arm_att={haki_arm_eff_attacker:.2f}, arm_def={haki_arm_eff_defender:.2f}")
        
        # Get status effects
        effective_attacker = self._get_effective_player(attacker)
        effective_defender = self._get_effective_player(defender)
        
        # Calculate FOV bonus
        fov_hit_bonus = get_fov_hit_bonus(
            defender.facing,
            (defender.row, defender.col),
            (attacker.row, attacker.col)
        )
        
        # Calculate hit_chance and damage
        hit_chance = calculate_hit_chance(
            effective_attacker, effective_defender, attack_type, defense_type,
            net_facing_bonus, net_bounce_bonus, net_pattern_hit,
            df_multipliers, haki_obs_eff_attacker, haki_obs_eff_defender,
            is_defense_phase=True,
            attacker_df_alloys=attacker_df_alloys,
            defender_df_alloys=defender_df_alloys,
            fov_hit_bonus=fov_hit_bonus
        )
        
        damage = calculate_damage(
            effective_attacker, effective_defender, base_damage, attack_type, defense_type,
            net_facing_bonus, net_bounce_bonus, net_pattern_dmg,
            df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
            is_defense_phase=True,
            attacker_df_alloys=attacker_df_alloys,
            defender_df_alloys=defender_df_alloys
        )
        damage = max(1, int(damage))
        
        # Counter calculation (if defender countered)
        counter_hit_chance = 0.0
        counter_damage = 0
        counter_is_miss = True  # Default to miss unless counter is executed
        if defense_type == "counter":
            counter_base_damage = 10
            counter_attack_type = "normal"
            
            counter_fov_bonus = 0.0
            if hasattr(self, '_get_fov_layer'):
                counter_fov_layer = self._get_fov_layer(
                    defender.facing,
                    (defender.row, defender.col),
                    (attacker.row, attacker.col)
                )
                if counter_fov_layer == "Periphery":
                    counter_fov_bonus = 0.10
                elif counter_fov_layer == "Behind":
                    counter_fov_bonus = 0.30
            
            counter_net_facing = defender_facing_bonus - attacker_facing_bonus
            counter_net_bounce = defender_bounce_bonus - attacker_bounce_bonus
            counter_net_pattern_hit = defender_pattern_hit - attacker_pattern_hit
            counter_net_pattern_dmg = defender_pattern_dmg - attacker_pattern_dmg
            
            counter_hit_chance = calculate_hit_chance(
                effective_defender, effective_attacker, counter_attack_type, None,
                counter_net_facing, counter_net_bounce, counter_net_pattern_hit,
                df_multipliers, haki_obs_eff_defender, haki_obs_eff_attacker,
                is_defense_phase=False,
                attacker_df_alloys=defender_df_alloys,
                defender_df_alloys=attacker_df_alloys,
                fov_hit_bonus=counter_fov_bonus
            )
            
            counter_damage_calc = calculate_damage(
                effective_defender, effective_attacker, counter_base_damage, counter_attack_type, None,
                counter_net_facing, counter_net_bounce, counter_net_pattern_dmg,
                df_multipliers, haki_arm_eff_defender, haki_arm_eff_attacker,
                is_defense_phase=False,
                attacker_df_alloys=defender_df_alloys,
                defender_df_alloys=attacker_df_alloys
            )
            counter_damage = max(1, int(counter_damage_calc))
            counter_is_miss = False  # Counter executed, not a miss
        
        # Store validation results
        self.last_attacker_validation = {
            'turn': self.system_turn_counter,
            'is_miss': False,
            'hit_chance': float(hit_chance),
            'damage': int(damage),
            'counter_is_miss': bool(counter_is_miss),
            'counter_hit_chance': float(counter_hit_chance),
            'counter_damage': int(counter_damage),
        }
        print(f"[MP] Attacker validation: hit_chance={hit_chance:.3f}, damage={damage}, counter_is_miss={counter_is_miss}, counter_hit_chance={counter_hit_chance:.3f}, counter_damage={counter_damage}")
    
    def confirm_turn(self) -> None:
        if not self.planning_mode:
            return
        p = self.get_current_player()
        
        # Build turn record at start of turn
        self.current_turn_record = self._build_turn_record()
        
        # Deduct stamina cost FIRST
        stamina_cost = self.total_cost
        if p.stamina < stamina_cost:
            self.battle_log.append(f"Insufficient stamina! Need {stamina_cost}, have {p.stamina}")
            # Finalize turn record even if stamina insufficient
            self._finalize_turn_record()
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
        
        # DON'T apply movement and facing here - let animations update player state
        # Combat calculations use ghost data (current_path, ghost_facing)
        # Animations will update p.row, p.col, p.facing when they complete
        
        # Use planning_start_facing (saved at planning start) for animation builder
        original_facing = self.planning_start_facing
        
        # Build and queue movement/rotation animations for this phase using optimization
        player_id = "player1" if p is self.player1 else "player2"
        phase_anims = self._build_optimized_animations_from_actions(player_id, original_facing)
        
        # Build creation animations with timing based on action sequence
        # Pass phase_anims so we can extract actual animation durations
        creation_anims = self._build_creation_animations_from_actions(player_id, phase_anims)
        
        if phase_anims:
            # Handle mixed list of animations and concurrent groups
            for item in phase_anims:
                if isinstance(item, list):
                    # Concurrent group (e.g., paired movement+rotation)
                    self.battle_log.append(f"ANIM: Queueing concurrent group with {len(item)} animations")
                    self.animation_system.queue_concurrent_group(item)
                else:
                    # Single animation
                    self.battle_log.append(f"ANIM: Queueing single {item.anim_type}")
                    self.animation_system.queue_animations([item])
            
            # Queue ALL creation animations individually with their start_time as delay
            # They will be rendered during the entire animation sequence based on their delays
            if creation_anims:
                self.battle_log.append(f"ANIM: Storing {len(creation_anims)} creation animations for rendering")
                # Store creation animations in animation_system for rendering lookup
                self.animation_system.current_phase_animations.extend(creation_anims)
            
            # Apply tile effects for each position in path
            for path_pos in self.current_path:
                path_row, path_col = path_pos
                # Get tile at position to retrieve its config
                tile_at_pos = self.tile_system.get_tile_at(path_row, path_col)
                tile_cfg = getattr(tile_at_pos, 'tile_config', None) if tile_at_pos else None
                
                tile_effect_result = self.tile_system.apply_tile_effect(path_row, path_col, p, self.effects_engine, tile_cfg)
                
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
                                # Finalize turn record before ending game
                                self._finalize_turn_record()
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
        
        # Apply wall/tile creations from planned_actions (for headless replay)
        # This processes wall_create/wall_reinforce/tile_creation actions added during remote attack/defense
        player_id = "player1" if p is self.player1 else "player2"
        for action in self.planned_actions:
            if action[0] == "wall_create":
                # Extract wall data from action tuple: ("wall_create", (row, col, orientation, total_cost))
                try:
                    wall_row, wall_col, orientation, total_cost = action[1]
                    # Get wall HP from player's devil fruit config
                    wall_config = p.devil_fruit_data.get("map_abilities", {}).get("wall_creation", {})
                    hp_per_click = wall_config.get("hp_per_click", 10)
                    # Add wall to system (deduplication handled by WallSystem)
                    if self.wall_system.add_player_wall(wall_row, wall_col, orientation, hp_per_click, player_id):
                        self.battle_log.append(f"[HEADLESS] Wall created at ({wall_row},{wall_col},{orientation}) - {hp_per_click} HP")
                    else:
                        self.battle_log.append(f"[HEADLESS] Wall creation failed at ({wall_row},{wall_col},{orientation}) - duplicate")
                except Exception as e:
                    print(f"[HEADLESS ERROR] Failed to create wall from planned_actions: {e}")
            
            elif action[0] == "wall_reinforce":
                # Extract reinforcement data: ("wall_reinforce", (row, col, orientation, clicks, total_cost))
                try:
                    wall_row, wall_col, orientation, clicks, total_cost = action[1]
                    # Get HP per click from config
                    wall_config = p.devil_fruit_data.get("map_abilities", {}).get("wall_creation", {})
                    hp_per_click = wall_config.get("hp_per_click", 10)
                    total_hp = hp_per_click * clicks
                    if self.wall_system.reinforce_wall(wall_row, wall_col, orientation, total_hp):
                        self.battle_log.append(f"[HEADLESS] Wall reinforced at ({wall_row},{wall_col},{orientation}) +{total_hp} HP")
                    else:
                        self.battle_log.append(f"[HEADLESS] Wall reinforcement failed - wall not found")
                except Exception as e:
                    print(f"[HEADLESS ERROR] Failed to reinforce wall from planned_actions: {e}")
            
            elif action[0] == "tile_creation":
                # Extract tile data: ("tile_creation", tile_type, row, col, prev_tile_action, prev_tile_index)
                try:
                    tile_type_key = action[1]
                    tile_row, tile_col = action[2], action[3]
                    # Get tile config from player's devil fruit data
                    tiles_available = p.devil_fruit_data.get("map_abilities", {}).get("tiles_available", {})
                    tile_config = tiles_available.get(tile_type_key)
                    if tile_config:
                        # Get HP from config
                        hp_range = tile_config.get("hp_range", [100, 100])
                        tile_hp = hp_range[1] if isinstance(hp_range, list) and len(hp_range) >= 2 else 100
                        tile_type = tile_config.get("tile_type", "trap_continuous")
                        # Create tile in system
                        from engine.tiles import Tile
                        new_tile = Tile(tile_row, tile_col, tile_type, tile_hp, duration=None)
                        new_tile.tile_config = tile_config
                        self.tile_system._tiles[(tile_row, tile_col)] = new_tile
                        self.battle_log.append(f"[HEADLESS] Tile created at ({tile_row},{tile_col}): {tile_type} ({tile_hp} HP)")
                    else:
                        self.battle_log.append(f"[HEADLESS] Tile creation failed - invalid tile type: {tile_type_key}")
                except Exception as e:
                    print(f"[HEADLESS ERROR] Failed to create tile from planned_actions: {e}")
        
        # Execute tile creation if planned (legacy path for local player planning)
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
            
            # Track tile creation for MP manifest (PHASE 1)
            if self.is_multiplayer:
                self.objects_created_this_turn.append({
                    "type": "tile",
                    "row": tile_row,
                    "col": tile_col,
                    "tile_type": tile_type,
                    "hp": tile_hp
                })
            
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
                p.stamina = min(p.stamina + 30, p.max_stamina)
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
                self.pattern_applied_this_phase = True
                self.battle_log.append(f"Pattern detected: {self.pattern_active_bonus['name']}")
            
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
                    
                    # Calculate and store ATTACKER's movement bonuses from attack phase
                    # These must be stored now because defender's movement in defense phase will overwrite the global variables
                    attacker_facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
                    attacker_bounce_bonus = 0.0
                    if self.bounce_active:
                        hits = [0.10, 0.125, 0.15, 0.175, 0.20]
                        idx = min(max(1, self.bounce_chain_length), 5) - 1
                        attacker_bounce_bonus = hits[idx]
                    
                    # Use pattern_active_bonus from current planning session
                    # We only want THIS attacker's pattern from their current movement
                    attacker_pattern_hit = 0.0
                    attacker_pattern_dmg = 0.0
                    if self.pattern_active_bonus:
                        attacker_pattern_hit = self.pattern_active_bonus.get('hit_bonus', 0.0)
                        attacker_pattern_dmg = self.pattern_active_bonus.get('damage_bonus', 0.0)
                    
                    print(f"[ATTACK PHASE PENDING] Storing attacker bonuses: facing={attacker_facing_bonus:.2f}, bounce={attacker_bounce_bonus:.2f}, pattern_hit={attacker_pattern_hit:.2f} (from pattern_active_bonus={self.pattern_active_bonus})")
                    
                    self.pending_attack = {
                        'type': attack_type,
                        'attacker_row': self.ghost_row if self.ghost_row is not None else attacker.row,
                        'attacker_col': self.ghost_col if self.ghost_col is not None else attacker.col,
                        'attacker_facing': self.ghost_facing if self.ghost_facing is not None else attacker.facing,
                        'defender_row': defender.row,
                        'defender_col': defender.col,
                        'attacker_is_p1': self.attacker_is_p1,
                        'wall_damage': None,
                        'attacker_df_alloys': set(self.applied_df_alloys),  # Store attacker's DF alloys
                        'defender_df_alloys': set(),  # Defender alloys applied during defense phase
                        # Store attacker's movement bonuses
                        'attacker_facing_bonus': attacker_facing_bonus,
                        'attacker_bounce_bonus': attacker_bounce_bonus,
                        'attacker_pattern_hit': attacker_pattern_hit,
                        'attacker_pattern_dmg': attacker_pattern_dmg,
                        # Store attack pattern tiles for flash animations
                        'attack_tiles': self.attack_highlighted_squares if self.attack_highlighted_squares else []
                    }
                    
                    # Precompute wall damage only if walls exist
                    h_walls = self.wall_system.get_all_horizontal_walls()
                    v_walls = self.wall_system.get_all_vertical_walls()
                    if h_walls or v_walls:
                        wall_damage = self._calculate_wall_damage(attack_type, attacker)
                        self.pending_attack['wall_damage'] = wall_damage
                    else:
                        self.pending_attack['wall_damage'] = 0
                    
                    self.battle_log.append(f"Attack confirmed: {attack_type} → Awaiting defense phase")
            
            # Queue 3 attack pattern flashes after movement/rotation animations
            if attack_selected and not skip and not miss:
                # Get attack pattern tiles
                attack_tiles = self.attack_highlighted_squares if self.attack_highlighted_squares else self._compute_attack_pattern_preview()
                
                # Calculate flash speed multiplier based on same bonuses as movement/rotation
                # Base: 0.5 + (speed/100) * 0.5
                base_speed_mult = 0.5 + (p.speed / 100.0) * 0.5
                # Apply bonuses (facing + bounce + pattern)
                total_bonus = attacker_facing_bonus + attacker_bounce_bonus + attacker_pattern_dmg
                flash_speed_mult = base_speed_mult * (1.0 + total_bonus)
                
                # Queue 3 flashes with calculated speed multiplier
                for i in range(3):
                    flash_anim = self.animation_system.build_flash_animation(attack_tiles, speed_multiplier=flash_speed_mult)
                    self.animation_system.queue_animations([flash_anim])
            
            # For SKIP or MISS, queue a simple attack-phase animation so turn doesn't feel empty
            attacker_id = "player1" if self.attacker_is_p1 else "player2"
            if skip or miss:
                # Skip uses dip; miss uses hop with zero damage
                if skip:
                    attack_type_for_anim = "skip"
                    is_skip_anim = True
                else:
                    # Use any selected non-skip attack type for animation label
                    attack_type_for_anim = None
                    for action in self.planned_actions:
                        if action[0] == "attack" and action[1] != "skip":
                            attack_type_for_anim = action[1]
                            break
                    if not attack_type_for_anim:
                        attack_type_for_anim = "skip"
                    is_skip_anim = False
                # Compute a basic attack animation speed based on attacker speed stat
                base_speed_mult = 0.5 + (p.speed / 100.0) * 0.5
                attack_anim = self._build_attack_animation(attack_type_for_anim, 0, is_skip_anim, False, attacker_id, base_speed_mult)
                self.animation_system.queue_animations([attack_anim])
            
            if skip:
                # Skip/Rest: gain +30 stamina
                p.stamina = min(p.stamina + 30, p.max_stamina)
                self.battle_log.append(f"Attacker skip/rest → defense phase skipped, gained 30 stamina")
                self._add_turn_result("Skipped (+30 stamina)")
                # Clear any pending attack from previous turn
                self.pending_attack = None
            elif miss:
                self.battle_log.append("Attack miss → defense phase skipped")
                self._add_turn_result("Attack MISS")
                # Clear pending attack on miss
                self.pending_attack = None
            
            if skip or miss:
                # Defense phase skipped; defender becomes next attacker
                # Note: Wall damage is NOT applied on miss - walls are only damaged at end of turn (after defense phase)
                self.phase = "attack"
                self.attacker_is_p1 = not self.attacker_is_p1
                self.system_turn_counter += 1  # Increment turn counter
                print(f"[TURN DEBUG] Counter++ at line 3827 (skip/miss in attack phase) -> {self.system_turn_counter}")
                import sys
                sys.stdout.flush()
            else:
                # Before entering defense phase, check if defender would be threatened
                # Use cascading breakthrough PREVIEW (no wall damage yet)
                attack_type = None
                for action in self.planned_actions:
                    if action[0] == "attack" and action[1] != "skip":
                        attack_type = action[1]
                        break
                
                if attack_type:
                    attacker = self.get_current_player()
                    defender = self.get_opponent()
                    
                    # Only calculate wall damage and check for wall protection if walls exist
                    h_walls = self.wall_system.get_all_horizontal_walls()
                    v_walls = self.wall_system.get_all_vertical_walls()
                    
                    defender_protected_by_walls = False
                    if h_walls or v_walls:
                        # Calculate wall damage for preview
                        wall_damage = self._calculate_wall_damage(attack_type, attacker)
                        
                        # Check defender position against PREVIEW
                        defender_tile = self._get_defender_combat_tile(defender)
                        
                        # Check if breakthrough would occur
                        if defender_tile in self.blocked_tiles_map:
                            # Check if walls would survive
                            blocking_walls = self.blocked_tiles_map[defender_tile]
                            total_hp = 0
                            for wall_row, wall_col, wall_orient in blocking_walls:
                                wall = self.wall_system.get_wall_at(wall_row, wall_col, wall_orient)
                                if wall and wall.tier != 'border':
                                    total_hp += max(0, wall.hp)
                            
                            # If walls would survive or exactly absorb attack, defender is protected
                            if wall_damage < total_hp or (wall_damage == total_hp):
                                defender_protected_by_walls = True
                                print(f"\n=== DEFENDER PROTECTED BY WALLS - SKIP DEFENSE ===")
                                print(f"Defender at {defender_tile} on blocked tile")
                                print(f"Total wall HP={total_hp}, attack damage={wall_damage}")
                                if wall_damage == total_hp:
                                    print(f"Exact absorption: walls destroyed but no breakthrough beyond defender")
                                self.battle_log.append("Attack fully blocked by walls! Defense phase skipped")
                    
                    if defender_protected_by_walls:
                        # Skip defense phase entirely
                        self.pending_attack = None
                        self.phase = "attack"
                        self.attacker_is_p1 = not self.attacker_is_p1
                        self._reset_planning_state(canceled=False)
                        self.system_turn_counter += 1  # Increment turn counter
                        print(f"[TURN DEBUG] Counter++ at line 3879 (wall protection skip) -> {self.system_turn_counter}")
                        import sys
                        sys.stdout.flush()
                        print(f"=== DEFENSE SKIPPED - NEXT ATTACKER ===")
                    else:
                        # Activate defense phase
                        self.phase = "defense"
                        # Calculate enemy attack pattern for display
                        self.recalculate_enemy_patterns()
                else:
                    # No attack selected - should not reach here
                    self.phase = "defense"
                    # Calculate enemy attack pattern for display
                    self.recalculate_enemy_patterns()
        else:
            # Defense phase confirmed - NOW execute the combat resolution
            print(f"\n{'='*60}")
            print(f"DEBUG DEFENSE PHASE: pending_attack={getattr(self, 'pending_attack', None)}")
            print(f"DEBUG DEFENSE PHASE: Current phase={self.phase}, attacker_is_p1={self.attacker_is_p1}")
            
            # Check if defense action selected - if not, treat as Tank
            defense_selected = any(a for a in self.planned_actions if a[0] == "defense")
            if not defense_selected:
                defender = self.get_opponent()
                defender.stamina = min(defender.stamina + 30, defender.max_stamina)
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
                
                # Store defender's DF alloys in pending_attack
                attack_info['defender_df_alloys'] = set(self.applied_df_alloys)
                
                # Base damage for all attacks
                # Base damage before special modifiers
                base_damage = 20
                
                # Extract defense type to use in combat calculations
                defense_type = None
                for action in self.planned_actions:
                    if action[0] == "defense":
                        defense_type = action[1]
                        break
                
                # Get ATTACKER's bonuses from stored attack phase data
                attacker_facing_bonus = attack_info.get('attacker_facing_bonus', 0.0)
                attacker_bounce_bonus = attack_info.get('attacker_bounce_bonus', 0.0)
                attacker_pattern_hit = attack_info.get('attacker_pattern_hit', 0.0)
                attacker_pattern_dmg = attack_info.get('attacker_pattern_dmg', 0.0)
                
                # Calculate DEFENDER's bonuses from defense phase movement (current state)
                print(f"[NET CALC] Reading defender bonuses from current state: facing_chain_length={self.facing_chain_length}, bounce_active={self.bounce_active}, pattern_active_bonus={self.pattern_active_bonus}")
                defender_facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
                defender_bounce_bonus = 0.0
                if self.bounce_active:
                    hits = [0.10, 0.125, 0.15, 0.175, 0.20]
                    idx = min(max(1, self.bounce_chain_length), 5) - 1
                    defender_bounce_bonus = hits[idx]
                defender_pattern_hit = 0.0
                defender_pattern_dmg = 0.0
                if self.pattern_active_bonus:
                    defender_pattern_hit = self.pattern_active_bonus.get('hit_bonus', 0.0)
                    defender_pattern_dmg = self.pattern_active_bonus.get('damage_bonus', 0.0)
                                
                # Compute NET bonuses: attacker contributions minus defender contributions
                net_facing_bonus = attacker_facing_bonus - defender_facing_bonus
                net_bounce_bonus = attacker_bounce_bonus - defender_bounce_bonus
                net_pattern_hit = attacker_pattern_hit - defender_pattern_hit
                net_pattern_dmg = attacker_pattern_dmg - defender_pattern_dmg
                print(f"[NET CALC] Attacker bonuses: facing={attacker_facing_bonus:.2%}, bounce={attacker_bounce_bonus:.2%}, pattern_hit={attacker_pattern_hit:.2%}")
                print(f"[NET CALC] Defender bonuses: facing={defender_facing_bonus:.2%}, bounce={defender_bounce_bonus:.2%}, pattern_hit={defender_pattern_hit:.2%}")
                print(f"[NET CALC] NET bonuses: facing={net_facing_bonus:.2%}, bounce={net_bounce_bonus:.2%}, pattern_hit={net_pattern_hit:.2%}")
                
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
                        net_pattern_hit += df_hit_mod / 100.0
                    # Specials use neutral attack type for quick/normal/heavy modifiers
                    calc_attack_type = "normal"
                
                # Apply wall damage BEFORE player damage calculation
                attack_tiles = self._compute_attack_pattern_from_stored(attack_info)
                print(f"\n--- WALL DAMAGE (DEFENSE PHASE) ---")
                print(f"DEBUG WALL: Attack pattern tiles ({len(attack_tiles)}): {attack_tiles}")
                
                # Calculate wall damage using FULL combat formula
                wall_damage = self._calculate_wall_damage(attack_type, attacker)
                
                print(f"DEBUG WALL: Wall damage from combat formula={wall_damage}")
                print(f"DEBUG WALL: Blocked tiles BEFORE damage: {list(self.blocked_tiles_map.keys())}")
                
                breakthrough_tiles_damage = self._apply_wall_damage_to_pattern(attack_tiles, wall_damage, attacker.row, attacker.col)
                
                print(f"--- WALL DAMAGE END ---\n")
                print(f"\n=== BREAKTHROUGH CALCULATION RESULT ===")
                print(f"Total breakthrough tiles: {len(breakthrough_tiles_damage)}")
                print(f"Breakthrough tiles with passthrough damage: {breakthrough_tiles_damage}")
                print(f"Blocked tiles map AFTER damage (walls survived): {list(self.blocked_tiles_map.keys())}")
                print(f"=== BREAKTHROUGH CALCULATION END ===")
                
                # CRITICAL: Check defender position FIRST - before combat calculations
                # Use ghost position (set during planning or by headless replay) for final position
                if self.ghost_row is not None and self.ghost_col is not None:
                    defender_tile = (self.ghost_row, self.ghost_col)
                elif hasattr(defender, 'current_path') and defender.current_path:
                    defender_tile = defender.current_path[-1]
                elif attack_info.get('defender_row') is not None:
                    defender_tile = (attack_info['defender_row'], attack_info['defender_col'])
                else:
                    defender_tile = (defender.row, defender.col)
                
                print(f"\n=== DEFENDER POSITION CHECK ===")
                print(f"Defender tile (final position after defense): {defender_tile}")
                print(f"Attack tiles: {attack_tiles}")
                print(f"Breakthrough tiles: {list(breakthrough_tiles_damage.keys())}")
                print(f"Blocked tiles: {list(self.blocked_tiles_map.keys())}")
                print(f"Is defender in breakthrough? {defender_tile in breakthrough_tiles_damage}")
                print(f"Is defender in attack tiles? {defender_tile in attack_tiles}")
                print(f"Is defender in blocked map? {defender_tile in self.blocked_tiles_map}")
                
                # Check if MISS (defender not in pattern at all)
                is_miss = (defender_tile not in attack_tiles and 
                          defender_tile not in breakthrough_tiles_damage and 
                          defender_tile not in self.blocked_tiles_map)
                
                # Import random at function scope for both main and counter rolls
                import random
                
                # Initialize variables needed for counter attack (even on miss)
                effective_attacker = self._get_effective_player(attacker)
                effective_defender = self._get_effective_player(defender)
                df_multipliers = None
                if attacker.devil_fruit_type or defender.devil_fruit_type:
                    df_multipliers = calculate_type_advantage(
                        attacker.devil_fruit_type,
                        defender.devil_fruit_type,
                        attacker.devil_fruit_mastery,
                        defender.devil_fruit_mastery,
                        self.devils_type_adv.get(attacker.devil_fruit_type) if attacker.devil_fruit_type else None
                    )
                
                att_obs_active = getattr(self, 'attacker_obs_active', False)
                def_obs_active = getattr(self, 'defender_obs_active', False)
                att_arm_active = getattr(self, 'attacker_arm_active', False)
                def_arm_active = getattr(self, 'defender_arm_active', False)
                haki_obs_eff_attacker = calculate_haki_effectiveness(attacker.haki_observation, defender.haki_observation, att_obs_active and def_obs_active) if att_obs_active else 0.0
                haki_obs_eff_defender = calculate_haki_effectiveness(defender.haki_observation, attacker.haki_observation, att_obs_active and def_obs_active) if def_obs_active else 0.0
                haki_arm_eff_attacker = calculate_haki_effectiveness(attacker.haki_armament, defender.haki_armament, att_arm_active and def_arm_active) if att_arm_active else 0.0
                haki_arm_eff_defender = calculate_haki_effectiveness(defender.haki_armament, attacker.haki_armament, att_arm_active and def_arm_active) if def_arm_active else 0.0
                attacker_df_alloys = attack_info.get('attacker_df_alloys', set())
                defender_df_alloys = attack_info.get('defender_df_alloys', set())
                
                if is_miss:
                    # MISS: Defender not in pattern - skip all combat calculations
                    print(f"\n=== MISS - NO DAMAGE ===")
                    print(f"Defender at {defender_tile} is NOT in attack pattern")
                    self.battle_log.append(f"Attack missed! Defender not in pattern")
                    dmg = 0
                    hit_success = False
                    
                    # Store miss status for MP payload
                    try:
                        self.last_defense_calc = {
                            'turn': self.system_turn_counter,
                            'attacker_is_p1': attack_info.get('attacker_is_p1', True),
                            'defense_type': defense_type,
                            'is_miss': True,
                            'hit_chance': 0.0,
                            'base_damage': 0,
                        }
                    except Exception:
                        self.last_defense_calc = None
                else:
                    # NOT MISS: Defender in pattern - calculate combat
                    print(f"\n=== DEFENDER IN PATTERN - CALCULATING COMBAT ===")
                
                    # FOV hit bonus: where is attacker around defender's body (attack phase)
                    from engine.fov import get_fov_hit_bonus
                    fov_hit_bonus = get_fov_hit_bonus(
                        defender.facing,
                        (defender.row, defender.col),
                        (attacker.row, attacker.col)
                    )
                    
                    # Hit chance (attack vs defender on pattern/breakthrough)
                    # Use NET bonuses (attacker - defender) so defender partially cancels attacker bonuses
                    hit_chance = calculate_hit_chance(
                        effective_attacker, effective_defender, calc_attack_type, defense_type,
                        net_facing_bonus, net_bounce_bonus, net_pattern_hit,
                        df_multipliers, haki_obs_eff_attacker, haki_obs_eff_defender,
                        is_defense_phase=True,
                        attacker_df_alloys=attacker_df_alloys,
                        defender_df_alloys=defender_df_alloys,
                        fov_hit_bonus=fov_hit_bonus
                    )
                    print(f"DEBUG HIT: hit_chance={hit_chance:.3f}")
                    
                    # Calculate damage
                    print(f"\n=== CALCULATING BASE DAMAGE ===")
                    print(f"Attacker: {attacker.name} | Defender: {defender.name}")
                    print(f"Attack type: {attack_type} | Base damage: {base_damage}")
                    print(f"Attacker bonuses - Facing: {attacker_facing_bonus:.2f} | Bounce: {attacker_bounce_bonus:.2f} | Pattern: {attacker_pattern_dmg:.2f}")
                    print(f"Defender bonuses - Facing: {defender_facing_bonus:.2f} | Bounce: {defender_bounce_bonus:.2f} | Pattern: {defender_pattern_dmg:.2f}")
                    print(f"NET bonuses - Facing: {net_facing_bonus:.2f} | Bounce: {net_bounce_bonus:.2f} | Pattern: {net_pattern_dmg:.2f}")
                    print(f"Haki obs attacker: {haki_obs_eff_attacker:.2f} | Haki obs defender: {haki_obs_eff_defender:.2f}")
                    print(f"Haki arm attacker: {haki_arm_eff_attacker:.2f} | Haki arm defender: {haki_arm_eff_defender:.2f}")
                    print(f"DF multipliers: {df_multipliers}")
                    
                    # Pass NET bonuses for damage calculation with is_defense_phase=True
                    dmg = calculate_damage(
                        effective_attacker, effective_defender, base_damage, calc_attack_type, defense_type,
                        net_facing_bonus, net_bounce_bonus, net_pattern_dmg,
                        df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                        is_defense_phase=True,
                        attacker_df_alloys=attacker_df_alloys,
                        defender_df_alloys=defender_df_alloys
                    )
                    dmg = max(1, int(dmg))
                    print(f"Calculated base damage: {dmg}")
                    print(f"=== BASE DAMAGE CALCULATION COMPLETE ===")
                    
                    # COUNTER CALCULATION: If defender chose counter, calculate counter hit/damage for payload
                    counter_hit_chance = 0.0
                    counter_base_damage = 0
                    counter_is_miss = True  # Default to miss unless defense_type is counter
                                        
                    if defense_type == "counter":
                        print(f"\n=== COUNTER ATTACK CALCULATION (for payload) ===")
                        counter_base_damage = 10
                        counter_attack_type = "normal"
                                            
                        # FOV for counter: from defender's perspective looking at attacker
                        counter_fov_bonus = 0.0
                        if hasattr(self, '_get_fov_layer'):
                            counter_fov_layer = self._get_fov_layer(
                                defender.facing,
                                (defender.row, defender.col),
                                (attacker.row, attacker.col)
                            )
                            if counter_fov_layer == "Periphery":
                                counter_fov_bonus = 0.10
                            elif counter_fov_layer == "Behind":
                                counter_fov_bonus = 0.30
                                            
                        # For counter: defender becomes attacker, attacker becomes defender
                        counter_net_facing = defender_facing_bonus - attacker_facing_bonus
                        counter_net_bounce = defender_bounce_bonus - attacker_bounce_bonus
                        counter_net_pattern_hit = defender_pattern_hit - attacker_pattern_hit
                        counter_net_pattern_dmg = defender_pattern_dmg - attacker_pattern_dmg
                                            
                        # Counter hit chance (defender attacking, attacker defending with no defense action)
                        counter_hit_chance = calculate_hit_chance(
                            effective_defender, effective_attacker, counter_attack_type, None,
                            counter_net_facing, counter_net_bounce, counter_net_pattern_hit,
                            df_multipliers, haki_obs_eff_defender, haki_obs_eff_attacker,
                            is_defense_phase=False,
                            attacker_df_alloys=defender_df_alloys,
                            defender_df_alloys=attacker_df_alloys,
                            fov_hit_bonus=counter_fov_bonus
                        )
                                            
                        # Counter damage calculation
                        counter_damage_calc = calculate_damage(
                            effective_defender, effective_attacker, counter_base_damage, counter_attack_type, None,
                            counter_net_facing, counter_net_bounce, counter_net_pattern_dmg,
                            df_multipliers, haki_arm_eff_defender, haki_arm_eff_attacker,
                            is_defense_phase=False,
                            attacker_df_alloys=defender_df_alloys,
                            defender_df_alloys=attacker_df_alloys
                        )
                        counter_base_damage = max(1, int(counter_damage_calc))
                        counter_is_miss = False  # Counter always hits attacker (no pattern miss check)
                                            
                        print(f"Counter hit_chance={counter_hit_chance:.3f}, base_damage={counter_base_damage}")
                        print(f"=== COUNTER CALCULATION COMPLETE ===")
                    
                    # Store deterministic defense calculation snapshot for multiplayer validation payloads
                    try:
                        self.last_defense_calc = {
                            'turn': self.system_turn_counter,
                            'attacker_is_p1': attack_info.get('attacker_is_p1', True),
                            'defense_type': defense_type,
                            'is_miss': False,
                            'hit_chance': float(hit_chance),
                            'base_damage': int(dmg),
                            'net_facing_bonus': float(net_facing_bonus),
                            'net_bounce_bonus': float(net_bounce_bonus),
                            'net_pattern_hit': float(net_pattern_hit),
                            'net_pattern_dmg': float(net_pattern_dmg),
                            # Counter attack data
                            'counter_is_miss': bool(counter_is_miss),
                            'counter_hit_chance': float(counter_hit_chance),
                            'counter_base_damage': int(counter_base_damage),
                        }
                    except Exception:
                        self.last_defense_calc = None
                    
                    # HIT CHECK: In MP mode, skip local RNG and wait for server resolution
                    # In SP mode, roll locally for immediate feedback
                    hit_success = True
                    hit_roll = None
                    
                    # Check if this is multiplayer mode
                    is_multiplayer = getattr(self, 'is_multiplayer', False)
                    
                    if not is_multiplayer:
                        # SP mode: roll locally
                        if defender_tile in breakthrough_tiles_damage or defender_tile in attack_tiles:
                            hit_roll = random.random()
                            hit_success = hit_roll <= hit_chance
                            print(f"DEBUG HIT ROLL: chance={hit_chance:.3f}, roll={hit_roll:.3f}, success={hit_success}")
                    else:
                        # MP mode: Store pending state, wait for server resolution
                        # Assume hit for now, server will override via apply_server_combat_resolution()
                        print(f"[MP] Skipping local hit roll, waiting for server resolution. hit_chance={hit_chance:.3f}")
                        hit_success = True  # Placeholder - server will override
                    
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
                                effective_attacker, effective_defender, passthrough_dmg, "normal", None,
                                facing_bonus, bounce_bonus, pattern_dmg,
                                df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                                is_defense_phase=False,
                                attacker_df_alloys=attacker_df_alloys,
                                defender_df_alloys=defender_df_alloys
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
                
                print(f"=== FINAL DAMAGE: {dmg} ===")
                print(f"\n=== APPLYING DAMAGE TO DEFENDER ===")
                print(f"Defender {defender.name} health BEFORE: {defender.health}")
                print(f"Damage to apply: {dmg}")
                
                # In MP mode, don't apply damage yet - wait for server resolution
                is_multiplayer = getattr(self, 'is_multiplayer', False)
                if not is_multiplayer:
                    # SP mode: Apply damage immediately
                    defender.health = max(0, defender.health - dmg)
                    print(f"Defender {defender.name} health AFTER: {defender.health}")
                else:
                    # MP mode: Store pending damage, wait for server
                    print(f"[MP] NOT applying local damage - waiting for server resolution")
                    self.pending_server_resolution = {'local_dmg': dmg, 'defender': defender}
                
                print(f"=== DAMAGE APPLICATION COMPLETE ===")
                
                # Check if Tank defense was used - grant +30 stamina
                defense_type = None
                for action in self.planned_actions:
                    if action[0] == "defense":
                        defense_type = action[1]
                        break
                
                if defense_type == "tank":
                    defender.stamina = min(defender.stamina + 30, defender.max_stamina)
                    self.battle_log.append(f"Combat resolved: {dmg} damage → {defender.name} health={defender.health}, gained 30 stamina (Tank)")
                    self._add_turn_result(f"Took {dmg} damage (Tank +30 stamina)")
                    print(f"DEBUG: Tank defense - granted 30 stamina, defender stamina now: {defender.stamina}")
                else:
                    self.battle_log.append(f"Combat resolved: {dmg} damage → {defender.name} health={defender.health}")
                    if dmg == 0:
                        self._add_turn_result("Blocked by wall (0 damage)")
                    else:
                        self._add_turn_result(f"Took {dmg} damage")
                
                print(f"DEBUG: Damage applied: {dmg}, defender health now: {defender.health}")
                
                # COUNTER ATTACK: If defender chose counter and survives, trigger counter-attack
                counter_damage = 0
                if defense_type == "counter" and defender.health > 0:
                    print(f"\n=== COUNTER ATTACK TRIGGERED ===")
                    print(f"Defender {defender.name} survived with {defender.health} HP - counter-attacking!")
                    
                    # Counter uses Normal attack type and base damage of 10
                    counter_base_damage = 10
                    counter_attack_type = "normal"
                    
                    # FOV for counter: from defender's perspective looking at attacker
                    counter_fov_bonus = 0.0
                    if hasattr(self, '_get_fov_layer'):
                        counter_fov_layer = self._get_fov_layer(
                            defender.facing,
                            (defender.row, defender.col),
                            (attacker.row, attacker.col)
                        )
                        if counter_fov_layer == "Periphery":
                            counter_fov_bonus = 0.10
                        elif counter_fov_layer == "Behind":
                            counter_fov_bonus = 0.30
                    
                    # For counter: defender becomes attacker, attacker becomes defender
                    # Use defender's bonuses as offensive, attacker's as defensive (reversed NET)
                    counter_net_facing = defender_facing_bonus - attacker_facing_bonus
                    counter_net_bounce = defender_bounce_bonus - attacker_bounce_bonus
                    counter_net_pattern_hit = defender_pattern_hit - attacker_pattern_hit
                    counter_net_pattern_dmg = defender_pattern_dmg - attacker_pattern_dmg
                    
                    print(f"Counter NET bonuses - Facing: {counter_net_facing:.2f} | Bounce: {counter_net_bounce:.2f} | Pattern Hit: {counter_net_pattern_hit:.2f} | Pattern Dmg: {counter_net_pattern_dmg:.2f}")
                    
                    # Counter hit chance (defender attacking, attacker defending with no defense action)
                    counter_hit_chance = calculate_hit_chance(
                        effective_defender, effective_attacker, counter_attack_type, None,
                        counter_net_facing, counter_net_bounce, counter_net_pattern_hit,
                        df_multipliers, haki_obs_eff_defender, haki_obs_eff_attacker,
                        is_defense_phase=False,  # Counter is an attack, not defense
                        attacker_df_alloys=defender_df_alloys,
                        defender_df_alloys=attacker_df_alloys,
                        fov_hit_bonus=counter_fov_bonus
                    )
                    
                    # Counter damage calculation
                    counter_damage = calculate_damage(
                        effective_defender, effective_attacker, counter_base_damage, counter_attack_type, None,
                        counter_net_facing, counter_net_bounce, counter_net_pattern_dmg,
                        df_multipliers, haki_arm_eff_defender, haki_arm_eff_attacker,
                        is_defense_phase=False,  # Counter is an attack, not defense
                        attacker_df_alloys=defender_df_alloys,
                        defender_df_alloys=attacker_df_alloys
                    )
                    counter_damage = max(1, int(counter_damage))
                    
                    # Counter hit roll - skip in MP mode, wait for server
                    is_multiplayer = getattr(self, 'is_multiplayer', False)
                    if not is_multiplayer:
                        counter_hit_roll = random.random()
                        counter_hit_success = counter_hit_roll <= counter_hit_chance
                        print(f"DEBUG COUNTER HIT ROLL: chance={counter_hit_chance:.3f}, roll={counter_hit_roll:.3f}, success={counter_hit_success}")
                    else:
                        # MP: Server will handle counter resolution separately (future implementation)
                        counter_hit_success = False  # Skip counter in MP for now
                        print(f"[MP] Skipping local counter roll and damage application")
                    
                    if counter_hit_success and not is_multiplayer:
                        attacker.health = max(0, attacker.health - counter_damage)
                        self.battle_log.append(f"Counter hit! {attacker.name} took {counter_damage} damage")
                        self._add_turn_result(f"Counter HIT! {counter_damage} damage")
                        print(f"Counter HIT: {attacker.name} health: {attacker.health}")
                    else:
                        counter_damage = 0
                        self.battle_log.append(f"Counter attack missed!")
                        self._add_turn_result("Counter MISS")
                        print(f"Counter MISS")
                    
                    print(f"=== COUNTER ATTACK COMPLETE ===")
                
                # Check for KO (defender or attacker from counter)
                if defender.health == 0:
                    self.game_active = False
                    self.winner = attacker.name
                    self.battle_log.append(f"KO! Winner: {self.winner}")
                elif defense_type == "counter" and attacker.health == 0:
                    self.game_active = False
                    self.winner = defender.name
                    self.battle_log.append(f"Counter KO! Winner: {self.winner}")
                else:
                    # Apply push for INITIAL ATTACK (attacker pushes defender)
                    # In MP mode, use server damage; in SP mode, use local damage
                    is_multiplayer = getattr(self, 'is_multiplayer', False)
                    push_damage = getattr(self, 'server_main_damage', dmg) if is_multiplayer else dmg
                    
                    quality = get_attack_quality(push_damage, base_damage)
                    print(f"DEBUG PUSH (Initial Attack): Attack quality calculation - damage={push_damage}, base_damage={base_damage}, quality={quality}")
                    
                    push_dist = get_push_distance(quality)
                    print(f"DEBUG PUSH (Initial Attack): Push distance for quality '{quality}': {push_dist} tiles")
                    
                    # Store push info for animation queueing AFTER attack/defense animations
                    push_info = None
                    if push_dist > 0:
                        # Save defender's starting position BEFORE push
                        from_row, from_col = defender.row, defender.col
                        
                        # Calculate push by calling apply_push_to_defender()
                        # This WILL apply tile effects and update defender position
                        old_attacker_flag = self.attacker_is_p1
                        self.attacker_is_p1 = attack_info['attacker_is_p1']
                        pushed = self.apply_push_to_defender(push_dist)
                        self.attacker_is_p1 = old_attacker_flag
                        
                        # Save final position for animation
                        to_row, to_col = defender.row, defender.col
                        
                        if pushed > 0:
                            self.battle_log.append(f"Push: {defender.name} pushed {pushed} tile(s)")
                            self._add_turn_result(f"Pushed {pushed} tile(s)")
                            push_info = {
                                'from_row': from_row,
                                'from_col': from_col,
                                'to_row': to_row,
                                'to_col': to_col,
                                'distance': pushed,
                                'defender_id': "player2" if attack_info['attacker_is_p1'] else "player1"
                            }
                            # Revert defender position - animation will update it visually
                            defender.row, defender.col = from_row, from_col
                    else:
                        print(f"DEBUG PUSH (Initial Attack): No push applied - attack quality too low ({quality})")
                    
                    # Apply push for COUNTER ATTACK (defender pushes attacker back)
                    counter_push_info = None
                    if defense_type == "counter" and counter_damage > 0:
                        # In MP mode, use server counter damage; in SP mode, use local counter damage
                        is_multiplayer = getattr(self, 'is_multiplayer', False)
                        push_counter_damage = getattr(self, 'server_counter_damage', counter_damage) if is_multiplayer else counter_damage
                        
                        counter_quality = get_attack_quality(push_counter_damage, counter_base_damage)
                        print(f"DEBUG PUSH (Counter Attack): Attack quality calculation - damage={push_counter_damage}, base_damage={counter_base_damage}, quality={counter_quality}")
                        
                        counter_push_dist = get_push_distance(counter_quality)
                        print(f"DEBUG PUSH (Counter Attack): Push distance for quality '{counter_quality}': {counter_push_dist} tiles")
                        
                        if counter_push_dist > 0:
                            # Save attacker's starting position BEFORE counter push
                            from_row, from_col = attacker.row, attacker.col
                            
                            # For counter push: attacker becomes the one being pushed
                            # Temporarily swap attacker_is_p1 flag to push the attacker
                            old_attacker_flag = self.attacker_is_p1
                            self.attacker_is_p1 = not attack_info['attacker_is_p1']  # Reverse - defender is now attacking
                            counter_pushed = self.apply_push_to_defender(counter_push_dist)
                            self.attacker_is_p1 = old_attacker_flag
                            
                            # Save final position for animation
                            to_row, to_col = attacker.row, attacker.col
                            
                            if counter_pushed > 0:
                                self.battle_log.append(f"Counter Push: {attacker.name} pushed {counter_pushed} tile(s)")
                                self._add_turn_result(f"Counter pushed {counter_pushed} tile(s)")
                                counter_push_info = {
                                    'from_row': from_row,
                                    'from_col': from_col,
                                    'to_row': to_row,
                                    'to_col': to_col,
                                    'distance': counter_pushed,
                                    'defender_id': "player1" if attack_info['attacker_is_p1'] else "player2"  # Attacker gets pushed
                                }
                                # Revert attacker position - animation will update it visually
                                attacker.row, attacker.col = from_row, from_col
                        else:
                            print(f"DEBUG PUSH (Counter Attack): No push applied - counter quality too low ({counter_quality})")
                
                # Queue attack/defense resolution animations (always play, even on miss)
                attacker_id = "player1" if attack_info['attacker_is_p1'] else "player2"
                defender_id = "player2" if attack_info['attacker_is_p1'] else "player1"

                # Calculate animation speed multiplier from bonuses
                # Base: 0.5 + (speed/100) * 0.5, then apply hit bonuses
                attacker_speed_mult = 0.5 + (attacker.speed / 100.0) * 0.5
                defender_speed_mult = 0.5 + (defender.speed / 100.0) * 0.5
                
                # Apply hit bonuses (facing + bounce + pattern) to attacker animation
                total_bonus = attacker_facing_bonus + attacker_bounce_bonus + attacker_pattern_dmg
                final_attacker_speed = attacker_speed_mult * (1.0 + total_bonus)
                
                is_skip = (attack_type == "skip")
                # Pass hit_success (from combat hit chance roll) to animation, not dmg > 0
                attack_anim = self._build_attack_animation(attack_type, dmg, is_skip, hit_success, attacker_id, final_attacker_speed)

                # Determine defense type (Tank if none selected)
                defense_type = None
                for action in self.planned_actions:
                    if action[0] == "defense":
                        defense_type = action[1]
                        break
                if not defense_type:
                    defense_type = "tank"

                # Use defender's original position from pending_attack (before damage/push)
                defender_start_row = attack_info.get('defender_row', defender.row)
                defender_start_col = attack_info.get('defender_col', defender.col)
                defender_start_facing = defender.facing  # Facing doesn't change during combat
                
                defense_anim = self._build_defense_animation(
                    defense_type, defender_id, 
                    defender_start_row, defender_start_col, defender_start_facing,
                    defender_speed_mult
                )
                
                # Build flash animation sequence data for combat (to be included in concurrent group)
                # Get attacker's attack pattern from stored data
                attacker_pattern = attack_info.get('attack_tiles', [])
                
                # Get defender's counter pattern if counter was chosen
                defender_pattern = []
                if defense_type == "counter":
                    # Counter uses quick attack pattern (same as current player's attack pattern)
                    # Calculate from defender's ORIGINAL position (before defense movement)
                    defender_pattern = self._compute_attack_pattern_preview_for_player(
                        defender, 
                        override_row=defender_start_row, 
                        override_col=defender_start_col
                    )
                
                # Build single flash animation that will alternate patterns during combat
                flash_anim = None
                if attacker_pattern:
                    # Calculate flash speeds (same as combat animation speeds)
                    attacker_flash_speed = final_attacker_speed
                    defender_total_bonus = defender_facing_bonus + defender_bounce_bonus + defender_pattern_dmg
                    defender_flash_speed = defender_speed_mult * (1.0 + defender_total_bonus)
                    
                    # Build flash animation with both patterns
                    flash_anim = self.animation_system.build_combat_flash_animation(
                        attacker_pattern, 
                        defender_pattern,
                        attacker_flash_speed,
                        defender_flash_speed
                    )
                
                # Queue combat animations + flash as concurrent group
                if flash_anim:
                    self.animation_system.queue_concurrent_group([attack_anim, defense_anim, flash_anim])
                else:
                    self.animation_system.queue_concurrent_group([attack_anim, defense_anim])
                
                # Queue push animations AFTER attack/defense (sequential, not concurrent)
                # If both initial push and counter push exist, queue them sequentially
                if push_info and counter_push_info:
                    # Both pushes: queue sequentially (initial push, then counter push)
                    push_anim = self._build_push_animation(
                        push_info['from_row'], push_info['from_col'],
                        push_info['to_row'], push_info['to_col'],
                        push_info['distance'], push_info['defender_id']
                    )
                    counter_push_anim = self._build_push_animation(
                        counter_push_info['from_row'], counter_push_info['from_col'],
                        counter_push_info['to_row'], counter_push_info['to_col'],
                        counter_push_info['distance'], counter_push_info['defender_id']
                    )
                    # Queue both in sequence: initial push completes, THEN counter push
                    self.animation_system.queue_animations([push_anim, counter_push_anim])
                elif push_info:
                    # Only initial push
                    push_anim = self._build_push_animation(
                        push_info['from_row'], push_info['from_col'],
                        push_info['to_row'], push_info['to_col'],
                        push_info['distance'], push_info['defender_id']
                    )
                    self.animation_system.queue_animations([push_anim])
                elif counter_push_info:
                    # Only counter push (initial attack didn't push, but counter did)
                    counter_push_anim = self._build_push_animation(
                        counter_push_info['from_row'], counter_push_info['from_col'],
                        counter_push_info['to_row'], counter_push_info['to_col'],
                        counter_push_info['distance'], counter_push_info['defender_id']
                    )
                    self.animation_system.queue_animations([counter_push_anim])
                
                # Clear pending attack (in MP, leave it for resolution handler to use)
                if not self.is_multiplayer:
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
            
            # ONLY increment turn counter when ATTACKER finishes defense phase
            # Before role flip, current attacker_is_p1 indicates who was attacking this turn
            # That player is now finishing their defense phase, so increment counter
            self.system_turn_counter += 1
            print(f"[TURN DEBUG] Attacker (p1={self.attacker_is_p1}) finished defense, turn counter -> {self.system_turn_counter}")
            import sys
            sys.stdout.flush()
            
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
            # Initialize active_effects dict if missing (MP desync safety)
            if player_name not in self.active_effects:
                self.active_effects[player_name] = []
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
        
        # Recover stamina, health, and Haki at turn end (ONLY once per system turn)
        # Check if recovery already applied for current system turn counter
        if not hasattr(self, '_last_recovery_turn'):
            self._last_recovery_turn = 1  # Start at 1 to skip first turn
        
        if self._last_recovery_turn != self.system_turn_counter:
            print(f"[RECOVERY DEBUG] BEFORE recovery: P1 health={self.player1.health:.2f}, stamina={self.player1.stamina:.2f}")
            print(f"[RECOVERY DEBUG] BEFORE recovery: P2 health={self.player2.health:.2f}, stamina={self.player2.stamina:.2f}")
            import sys
            sys.stdout.flush()
            
            p1_stam_rec, p1_hp_rec = self.player1.recover_stamina_and_health()
            p2_stam_rec, p2_hp_rec = self.player2.recover_stamina_and_health()
            
            print(f"[RECOVERY DEBUG] AFTER recovery: P1 health={self.player1.health:.2f} (+{p1_hp_rec:.2f}), stamina={self.player1.stamina:.2f} (+{p1_stam_rec:.2f})")
            print(f"[RECOVERY DEBUG] AFTER recovery: P2 health={self.player2.health:.2f} (+{p2_hp_rec:.2f}), stamina={self.player2.stamina:.2f} (+{p2_stam_rec:.2f})")
            sys.stdout.flush()
            
            self.battle_log.append(f"Stamina/Health recovery: {self.player1.name} +{int(p1_stam_rec)} St / +{int(p1_hp_rec)} HP, {self.player2.name} +{int(p2_stam_rec)} St / +{int(p2_hp_rec)} HP")
            p1_haki_recovery = self.player1.recover_haki_stamina()
            p2_haki_recovery = self.player2.recover_haki_stamina()
            self.battle_log.append(f"Haki recovery: {self.player1.name} +{int(p1_haki_recovery)}, {self.player2.name} +{int(p2_haki_recovery)}")
            
            # DF recovery (only if attack phase - per spec 3.5)
            if self.phase == 'attack':
                p1_df_recovery = self.player1.recover_df_stamina()
                p2_df_recovery = self.player2.recover_df_stamina()
                if p1_df_recovery > 0 or p2_df_recovery > 0:
                    self.battle_log.append(f"DF recovery: {self.player1.name} +{p1_df_recovery:.1f}, {self.player2.name} +{p2_df_recovery:.1f}")
            
            # Mark this system turn as recovered
            self._last_recovery_turn = self.system_turn_counter
            print(f"[RECOVERY DEBUG] Recovery applied for system turn {self.system_turn_counter}")
            sys.stdout.flush()
        else:
            print(f"[RECOVERY DEBUG] Skipping recovery - already applied for system turn {self.system_turn_counter}")
            import sys
            sys.stdout.flush()
        
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
            existing_tile = self.tile_system.get_tile_at(row, col)
            if existing_tile and self.is_multiplayer:
                self.objects_destroyed_this_turn.append({
                    "type": "tile",
                    "row": row,
                    "col": col,
                    "tile_type": existing_tile.tile_type
                })
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
            effect = self.tile_system.apply_tile_effect(final_row, final_col, p, self.effects_engine)
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
        
        # Finalize turn record and add to battle history
        print(f"[CONFIRM_TURN] About to finalize - phase={self.phase}, attacker_is_p1={self.attacker_is_p1}")
        import sys
        sys.stdout.flush()
        self._finalize_turn_record()
            
        self._reset_planning_state(canceled=False)
        # Per-turn tile maintenance
        self.tile_system.tick_durations()
        if self.phase == 'attack' and getattr(self, 'use_local_tile_spawns', True):
            # Pass player positions to avoid spawning tiles on them
            player_positions = [(self.player1.row, self.player1.col), (self.player2.row, self.player2.col)]
            self.tile_system.spawn_per_turn_tiles(self.avg_primary_sum, player_positions)
        # Status effects maintenance
        self.tick_status_effects()
        self.battle_log.append(f"Turn confirmed 2 next phase: {self.phase}, attacker_is_p1={self.attacker_is_p1}")
    
    def apply_remote_attack_payload(self, payload: Dict[str, Any]) -> None:
        """Headless replay of a remote attack phase on this client.
    
        Reconstructs planning state from a combat_attack payload and invokes confirm_turn()
        so that attack-phase logic (bonuses, pending_attack, animations, tiles, turn flow)
        is executed exactly as on the attacker client, but without entering UI planning.
        """
        try:
            if not isinstance(payload, dict):
                return
            if payload.get("type") != "combat_attack":
                return
    
            # Ensure we only apply remote attacks while still in attack phase
            if self.phase != "attack":
                return
    
            # Set attacker flag from payload and identify roles
            attacker_is_p1 = bool(payload.get("attacker_is_p1", True))
            self.attacker_is_p1 = attacker_is_p1
            attacker = self.player1 if attacker_is_p1 else self.player2
    
            # Basic path reconstruction
            raw_path = payload.get("path") or []
            path: List[Tuple[int, int]] = []
            for item in raw_path:
                try:
                    r, c = int(item[0]), int(item[1])
                    path.append((r, c))
                except Exception:
                    continue
    
            if not path:
                return
    
            # Prepare planning state to mirror attacker planning (without UI)
            self.planning_mode = True
            self.movement_mode = True
            self.planning_terminal = False
            self.current_path = path
            self.ghost_row, self.ghost_col = path[-1]
            self.planning_start_facing = getattr(attacker, "facing", 0)
    
            # Rebuild planned_actions from serialized actions list (preserves order)
            # MUST DO THIS BEFORE reconstructing move_facing_history
            self.planned_actions = []
            try:
                actions_list = payload.get("actions") or []
                for action in actions_list:
                    if not isinstance(action, (list, tuple)) or len(action) < 2:
                        continue
                    kind, value = action[0], action[1]
                    # Reconstruct move/rotate/attack actions
                    self.planned_actions.append((kind, value))
            except Exception:
                pass
    
            # Reconstruct move_facing_history by walking through planned_actions in order
            # This captures the facing AT THE TIME OF EACH MOVE (same as add_to_path does)
            print(f"\n[HEADLESS ATTACK] Replaying {len(self.planned_actions)} actions for attacker")
            print(f"[HEADLESS ATTACK] Starting facing: {self.planning_start_facing}°")
            print(f"[HEADLESS ATTACK] Path: {path}")
            self.move_facing_history = []
            current_facing = self.planning_start_facing
            for idx, action in enumerate(self.planned_actions):
                action_type = action[0]
                if action_type == "rotate":
                    # Update facing for next move
                    rotation_delta = float(action[1])
                    current_facing = (current_facing + rotation_delta) % 360
                    print(f"  [HEADLESS ATTACK] Action {idx}: ROTATE {rotation_delta:+.1f}° → facing now {current_facing:.1f}°")
                elif action_type == "move":
                    # Record facing at time of this move
                    self.move_facing_history.append(current_facing)
                    print(f"  [HEADLESS ATTACK] Action {idx}: MOVE → record facing {current_facing:.1f}° in history")
                else:
                    print(f"  [HEADLESS ATTACK] Action {idx}: {action_type} (non-movement)")
                        
            # Set final facing from payload
            try:
                final_facing = int(payload.get("final_facing", attacker.facing))
            except Exception:
                final_facing = int(getattr(attacker, "facing", 0))
            self.ghost_facing = float(final_facing)

            # Apply map actions from payload (player-created walls/tiles)
            try:
                map_actions = payload.get("map_actions") or []
            except Exception:
                map_actions = []
            try:
                for ma in map_actions:
                    try:
                        kind = ma.get("kind")
                    except Exception:
                        continue
                    if kind == "wall_create":
                        try:
                            wr = int(ma.get("row"))
                            wc = int(ma.get("col"))
                            orientation = str(ma.get("orientation") or "h")
                            total_cost = float(ma.get("df_cost", 0.0))
                        except Exception:
                            continue
                        self.planned_actions.append(("wall_create", (wr, wc, orientation, total_cost)))
                    elif kind == "wall_reinforce":
                        try:
                            wr = int(ma.get("row"))
                            wc = int(ma.get("col"))
                            orientation = str(ma.get("orientation") or "h")
                            clicks = int(ma.get("clicks", 1))
                            total_cost = float(ma.get("df_cost", 0.0))
                        except Exception:
                            continue
                        self.planned_actions.append(("wall_reinforce", (wr, wc, orientation, clicks, total_cost)))
                    elif kind == "tile_creation":
                        tile_type = ma.get("tile_type")
                        if tile_type is None:
                            continue
                        try:
                            tr = int(ma.get("row"))
                            tc = int(ma.get("col"))
                        except Exception:
                            continue
                        # prev_tile_action / prev_tile_index are only needed for undo; not required for headless
                        self.planned_actions.append(("tile_creation", tile_type, tr, tc, None, None))
            except Exception:
                pass

            # Apply alloys from payload so bonuses and DF interactions match
            try:
                self.applied_haki_alloys = set(payload.get("haki_alloys") or [])
            except Exception:
                self.applied_haki_alloys = set()
            try:
                self.applied_df_alloys = set(payload.get("df_alloys") or [])
            except Exception:
                self.applied_df_alloys = set()
    
            # Recompute derived movement bonuses and pattern state from reconstructed path
            print(f"[HEADLESS ATTACK] Recomputing bonuses...")
            self._recompute_bounce_state()
            print(f"[HEADLESS ATTACK] After bounce: active={self.bounce_active}, chain_len={self.bounce_chain_length}, type={self.bounce_chain_type}")
            self._update_facing_chain()
            facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
            print(f"[HEADLESS ATTACK] After facing chain: len={self.facing_chain_length}, bonus={facing_bonus:.2%}, move_facing_history={self.move_facing_history}")
            self._update_pattern_bonus()
            print(f"[HEADLESS ATTACK] After pattern: active={self.pattern_active_bonus}")
            self._recompute_highlights()
            self._update_fov_cache()
    
            # Finally, run normal attack-phase confirm logic using reconstructed planning
            print(f"[HEADLESS ATTACK] Before confirm_turn: attacker stamina={attacker.stamina}, total_cost={self.total_cost}, planning_mode={self.planning_mode}")
            self.confirm_turn()
            print(f"[HEADLESS ATTACK] After confirm_turn: attacker stamina={attacker.stamina}")
        except Exception:
            # Never crash the client on malformed or unexpected payloads
            try:
                import renpy
                renpy.log("[MP] apply_remote_attack_payload failed", level="warning")
            except Exception:
                pass

    def apply_remote_defense_payload(self, payload: Dict[str, Any]) -> None:
        """Headless replay of a remote defense phase on the attacker client.
        
        Reconstructs the defender's planning state from a combat_defense payload and invokes confirm_turn()
        so that defense-phase logic (bonuses, HP, animations, tiles, turn flow) is executed exactly as on the defender client.
        """
        try:
            if not isinstance(payload, dict):
                return
            if payload.get("type") != "combat_defense":
                return
            
            # ATTACKER receives this while in attack phase - must transition to defense phase FIRST
            if self.phase == "attack":
                print(f"[MP] Attacker transitioning attack -> defense phase before applying remote defense")
                self.phase = "defense"
                self.planning_mode = False  # Ensure not in planning until remote defense sets it
            
            # Now we should be in defense phase
            if self.phase != "defense":
                print(f"[MP] ERROR: Not in defense phase after transition, current phase={self.phase}")
                return
            
            # Identify defender from payload
            defender_is_p1 = bool(payload.get("defender_is_p1", True))
            defender = self.player1 if defender_is_p1 else self.player2
            
            # Basic path reconstruction
            raw_path = payload.get("path") or []
            path: List[Tuple[int, int]] = []
            for item in raw_path:
                try:
                    r, c = int(item[0]), int(item[1])
                    path.append((r, c))
                except Exception:
                    continue
            
            if not path:
                return
            
            # Prepare planning state to mirror defender planning (headless)
            self.planning_mode = True
            self.movement_mode = True
            self.planning_terminal = False
            self.current_path = path
            self.ghost_row, self.ghost_col = path[-1]
            self.planning_start_facing = getattr(defender, "facing", 0)
            
            # Rebuild planned_actions from serialized actions list (preserves order)
            # MUST DO THIS BEFORE reconstructing move_facing_history
            self.planned_actions = []
            try:
                actions_list = payload.get("actions") or []
                for action in actions_list:
                    if not isinstance(action, (list, tuple)) or len(action) < 2:
                        continue
                    kind, value = action[0], action[1]
                    # Reconstruct move/rotate/attack/defense actions
                    self.planned_actions.append((kind, value))
            except Exception:
                pass
            
            # Reconstruct move_facing_history by walking through planned_actions in order
            # This captures the facing AT THE TIME OF EACH MOVE (same as add_to_path does)
            print(f"\n[HEADLESS DEFENSE] Replaying {len(self.planned_actions)} actions for defender")
            print(f"[HEADLESS DEFENSE] Starting facing: {self.planning_start_facing}°")
            print(f"[HEADLESS DEFENSE] Path: {path}")
            self.move_facing_history = []
            current_facing = self.planning_start_facing
            for idx, action in enumerate(self.planned_actions):
                action_type = action[0]
                if action_type == "rotate":
                    # Update facing for next move
                    rotation_delta = float(action[1])
                    current_facing = (current_facing + rotation_delta) % 360
                    print(f"  [HEADLESS DEFENSE] Action {idx}: ROTATE {rotation_delta:+.1f}° → facing now {current_facing:.1f}°")
                elif action_type == "move":
                    # Record facing at time of this move
                    self.move_facing_history.append(current_facing)
                    print(f"  [HEADLESS DEFENSE] Action {idx}: MOVE → record facing {current_facing:.1f}° in history")
                elif action_type == "defense":
                    print(f"  [HEADLESS DEFENSE] Action {idx}: DEFENSE {action[1]}")
                else:
                    print(f"  [HEADLESS DEFENSE] Action {idx}: {action_type} (non-movement)")
            
            # Set final facing from payload
            try:
                final_facing = int(payload.get("final_facing", defender.facing))
            except Exception:
                final_facing = int(getattr(defender, "facing", 0))
            self.ghost_facing = float(final_facing)
            
            # Apply map actions from payload (player-created walls/tiles)
            try:
                map_actions = payload.get("map_actions") or []
            except Exception:
                map_actions = []
            try:
                for ma in map_actions:
                    try:
                        kind = ma.get("kind")
                    except Exception:
                        continue
                    if kind == "wall_create":
                        try:
                            wr = int(ma.get("row"))
                            wc = int(ma.get("col"))
                            orientation = str(ma.get("orientation") or "h")
                            total_cost = float(ma.get("df_cost", 0.0))
                        except Exception:
                            continue
                        self.planned_actions.append(("wall_create", (wr, wc, orientation, total_cost)))
                    elif kind == "wall_reinforce":
                        try:
                            wr = int(ma.get("row"))
                            wc = int(ma.get("col"))
                            orientation = str(ma.get("orientation") or "h")
                            clicks = int(ma.get("clicks", 1))
                            total_cost = float(ma.get("df_cost", 0.0))
                        except Exception:
                            continue
                        self.planned_actions.append(("wall_reinforce", (wr, wc, orientation, clicks, total_cost)))
                    elif kind == "tile_creation":
                        tile_type = ma.get("tile_type")
                        if tile_type is None:
                            continue
                        try:
                            tr = int(ma.get("row"))
                            tc = int(ma.get("col"))
                        except Exception:
                            continue
                        self.planned_actions.append(("tile_creation", tile_type, tr, tc, None, None))
            except Exception:
                pass
            
            # Apply alloys from payload
            try:
                self.applied_haki_alloys = set(payload.get("haki_alloys") or [])
            except Exception:
                self.applied_haki_alloys = set()
            try:
                self.applied_df_alloys = set(payload.get("df_alloys") or [])
            except Exception:
                self.applied_df_alloys = set()
            
            # Recompute derived movement bonuses and pattern state from reconstructed path
            print(f"[HEADLESS DEFENSE] Recomputing bonuses...")
            self._recompute_bounce_state()
            print(f"[HEADLESS DEFENSE] After bounce: active={self.bounce_active}, chain_len={self.bounce_chain_length}, type={self.bounce_chain_type}")
            self._update_facing_chain()
            facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
            print(f"[HEADLESS DEFENSE] After facing chain: len={self.facing_chain_length}, bonus={facing_bonus:.2%}, move_facing_history={self.move_facing_history}")
            self._update_pattern_bonus()
            print(f"[HEADLESS DEFENSE] After pattern: active={self.pattern_active_bonus}")
            self._recompute_highlights()
            self._update_fov_cache()
            
            print(f"[MP] apply_remote_defense_payload complete - headless defense state prepared")
            # NOTE: Unlike apply_remote_attack_payload, we do NOT call confirm_turn() here
            # The attacker must wait for server combat_resolution before calling confirm_turn
            
        except Exception:
            try:
                import renpy
                renpy.log("[MP] apply_remote_defense_payload failed", level="warning")
            except Exception:
                pass
    
    def apply_server_combat_resolution(self, hit: bool, damage: int, counter_hit: bool = False, counter_damage: int = 0, new_spawns: list = None) -> None:
        """Apply server-authoritative combat resolution for BOTH main attack and counter attack.
        
        Called after both clients finish headless replay. Server sends final hit/damage for both attacks.
        This overrides the placeholder values calculated during confirm_turn.
        
        Args:
            hit: Server's RNG result for main attack hit success
            damage: Server-calculated main attack damage (0 if miss/block)
            counter_hit: Server's RNG result for counter attack hit success
            counter_damage: Server-calculated counter attack damage (0 if miss/no counter)
            new_spawns: List of new tile spawns from server (PHASE 5)
        """
        if not self.is_multiplayer:
            return  # Only apply in MP mode
        
        try:
            # Find attacker/defender from pending attack state
            print(f"[MP DEBUG] pending_attack exists: {self.pending_attack is not None}")
            print(f"[MP DEBUG] pending_attack value: {self.pending_attack}")
            if not self.pending_attack:
                print(f"[MP] No pending attack - cannot apply resolution")
                return
            
            attacker_is_p1 = self.pending_attack.get('attacker_is_p1', True)
            print(f"[MP DEBUG] attacker_is_p1 from pending_attack: {attacker_is_p1}")
            attacker = self.player1 if attacker_is_p1 else self.player2
            defender = self.player2 if attacker_is_p1 else self.player1
            
            print(f"[MP] Applying server resolution: hit={hit}, damage={damage}, counter_hit={counter_hit}, counter_damage={counter_damage}")
            print(f"[MP] Defender {defender.name} health BEFORE: {defender.health}")
            print(f"[MP] Attacker {attacker.name} health BEFORE: {attacker.health}")
            
            # Apply server's authoritative MAIN ATTACK damage to defender
            defender.health = max(0, defender.health - damage)
            
            # Apply server's authoritative COUNTER ATTACK damage to attacker
            if counter_damage > 0:
                attacker.health = max(0, attacker.health - counter_damage)
            
            print(f"[MP] Defender {defender.name} health AFTER: {defender.health}")
            print(f"[MP] Attacker {attacker.name} health AFTER: {attacker.health}")
            
            # Store server damage for push calculation (will be used in confirm_turn)
            self.server_main_damage = damage
            self.server_counter_damage = counter_damage
            
            # Update battle log with server result
            if damage > 0:
                self.battle_log.append(f"[SERVER] Main attack: {damage} damage")
            else:
                self.battle_log.append(f"[SERVER] Main attack missed or blocked")
            
            if counter_damage > 0:
                self.battle_log.append(f"[SERVER] Counter attack: {counter_damage} damage")
            elif counter_hit:  # Hit but 0 damage
                self.battle_log.append(f"[SERVER] Counter attack blocked")
            # Don't log if no counter (counter_hit=False, counter_damage=0)
            
            # === PHASE 5: Apply server-authoritative new spawns ===
            if new_spawns:
                print(f"[MP] Applying {len(new_spawns)} new spawns from server")
                from engine.tiles import Tile
                for spawn in new_spawns:
                    try:
                        row = int(spawn.get("row"))
                        col = int(spawn.get("col"))
                        tile_type = spawn.get("tile_type")
                        duration = spawn.get("duration")  # Can be None for continuous tiles
                        
                        # Calculate HP using same formula as clients
                        base_hp = int(100 + self.avg_primary_sum * 0.5)
                        
                        # Create tile in tile_system
                        new_tile = Tile(row, col, tile_type, base_hp, duration)
                        self.tile_system._tiles[(row, col)] = new_tile
                        
                        print(f"[MP SPAWN] Applied: {tile_type} at ({row},{col}), HP={base_hp}, duration={duration}")
                        self.battle_log.append(f"New tile spawned: {tile_type} at ({row},{col})")
                    except Exception as e:
                        print(f"[MP SPAWN ERROR] Failed to apply spawn {spawn}: {e}")
            
        except Exception as e:
            print(f"[MP] apply_server_combat_resolution error: {e}")
    
    def _build_optimized_animations_from_actions(self, player_id: str, original_facing: float) -> List[AnimationEntry]:
        """Build animations using rotation grouping and movement-rotation pairing.
            
        Args:
            player_id: "player1" or "player2"
            original_facing: Player's facing BEFORE this turn's rotation (for animation from_facing)
        """
        if not self.current_path and self.ghost_facing is None:
            return []
            
        player = self.player1 if player_id == "player1" else self.player2
            
        # Build action list by reconstructing order from planned_actions
        # This preserves the interleaving of movements and rotations
        actions = []
        move_index = 1  # Start at 1 because current_path[0] is starting position
        current_facing = original_facing  # Track facing as we build actions
            
        for action in self.planned_actions:
            action_type = action[0]
            # Only process move and rotate actions for animation building
            # Skip attack, defense, wall, tile, etc.
            if action_type not in ("move", "rotate"):
                continue
                
            action_data = action[1] if len(action) > 1 else None
                
            if action_type == "move":
                # Add movement
                if self.current_path and move_index < len(self.current_path):
                    actions.append(("move", self.current_path[move_index]))
                    move_index += 1
            elif action_type == "rotate":
                # action_data is the delta (degrees rotated)
                rotation_delta = float(action_data)
                actions.append(("rotate", rotation_delta))
                # Update cumulative facing
                current_facing = (current_facing + rotation_delta) % 360
            
        if not actions:
            return []
            
        # Log raw actions
        action_str = ", ".join([f"{a[0]}" for a in actions])
        self.battle_log.append(f"RAW ACTIONS: {action_str}")
            
        # Apply rotation grouping
        grouped = self.animation_system.group_consecutive_rotations(actions)
        grouped_str = ", ".join([f"{a[0]}" for a in grouped])
        self.battle_log.append(f"AFTER GROUPING: {grouped_str}")
            
        # Apply movement-rotation pairing
        paired = self.animation_system.pair_rotations_with_movements(grouped)
        paired_str = ", ".join([p.get("type", "unknown") for p in paired])
        self.battle_log.append(f"AFTER PAIRING: {paired_str}")
            
        # Build animations from paired commands
        animations = []
        current_pos = self.current_path[0] if self.current_path else (player.row, player.col)
        current_facing = player.facing
            
        # Calculate speed multiplier with bonuses
        speed_value = max(0, getattr(player, "speed", 100))
        base_speed_multiplier = 0.5 + (speed_value / 100.0) * 0.5
            
        # Get hit bonuses for this action sequence
        facing_bonus = min(0.10 * self.facing_chain_length, 0.50) if self.facing_chain_length > 0 else 0.0
        bounce_bonus = 0.0
        if self.bounce_active:
            hits = [0.10, 0.125, 0.15, 0.175, 0.20]
            idx = min(max(1, self.bounce_chain_length), 5) - 1
            bounce_bonus = hits[idx]
        pattern_bonus = 0.0
        if self.pattern_active_bonus:
            pattern_bonus = self.pattern_active_bonus.get('hit_bonus', 0.0)
            
        total_bonus = facing_bonus + bounce_bonus + pattern_bonus
        bonus_multiplier = 1.0 + total_bonus
        final_speed = base_speed_multiplier * bonus_multiplier
            
        for cmd in paired:
            cmd_type = cmd["type"]
                
            if cmd_type == "paired_move_rotate":
                # Movement with paired rotation - queue as CONCURRENT group
                to_pos = cmd["move_data"]
                rotation_delta = cmd["rotation"]
                    
                # Create movement animation with paired rotation
                from_row, from_col = current_pos
                to_row, to_col = to_pos
    
                # Movement uses hit bonuses
                move_anim = AnimationEntry(
                    "movement",
                    player_id,
                    {
                        "from_row": from_row,
                        "from_col": from_col,
                        "to_row": to_row,
                        "to_col": to_col,
                        "speed_multiplier": final_speed,
                    }
                )
                
                # Rotation paired with this movement
                to_facing = (current_facing + rotation_delta) % 360
                self.battle_log.append(f"ROTATION ANIM: from={current_facing} to={to_facing} delta={rotation_delta}")
                rot_anim = AnimationEntry(
                    "rotation",
                    player_id,
                    {
                        "from_facing": current_facing,
                        "to_facing": to_facing,
                        "speed_multiplier": final_speed,  # Uses movement's bonus
                    }
                )
                
                # Add as sublist to mark concurrent group
                animations.append([move_anim, rot_anim])
                current_pos = to_pos
                current_facing = to_facing
                
            elif cmd_type == "movement":
                # Unpaired movement
                to_pos = cmd["move_data"]
                from_row, from_col = current_pos
                to_row, to_col = to_pos
                
                move_anim = AnimationEntry(
                    "movement",
                    player_id,
                    {
                        "from_row": from_row,
                        "from_col": from_col,
                        "to_row": to_row,
                        "to_col": to_col,
                        "speed_multiplier": final_speed,
                    }
                )
                animations.append(move_anim)
                current_pos = to_pos
                
            elif cmd_type == "rotation":
                # Standalone rotation (no successor movement)
                rotation_delta = cmd["rotation"]
                to_facing = (current_facing + rotation_delta) % 360
                
                rot_anim = AnimationEntry(
                    "rotation",
                    player_id,
                    {
                        "from_facing": current_facing,
                        "to_facing": to_facing,
                        "speed_multiplier": base_speed_multiplier,  # No hit bonuses for standalone rotation
                    }
                )
                animations.append(rot_anim)
                current_facing = to_facing
        
        return animations

    def _build_creation_animations_from_actions(self, player_id: str, phase_anims: List) -> List[AnimationEntry]:
        """Build wall/tile creation animations with timing offsets based on action sequence.
        
        All creations between two movement actions start simultaneously at the movement transition point.
        Duration: 0.4s fade-in from invisible to visible.
        
        Args:
            player_id: "player1" or "player2"
            phase_anims: List of already-built animations (from _build_optimized_animations_from_actions)
                        to extract actual durations from
        
        Returns:
            List of AnimationEntry for wall/tile creations with start_time offsets
        """
        player = self.player1 if player_id == "player1" else self.player2
        creation_anims = []
        
        # Calculate cumulative time offset by reading durations from actual animations
        current_time_offset = 0.0
        pending_creations = []  # Creations waiting for next movement to determine start time
        
        # Flatten phase_anims to handle both single animations and concurrent groups
        flat_anims = []
        for item in phase_anims:
            if isinstance(item, list):
                # Concurrent group - add all
                flat_anims.extend(item)
            else:
                flat_anims.append(item)
        
        # Track which animation index we're at
        anim_idx = 0
        
        for action in self.planned_actions:
            action_type = action[0]
            
            if action_type == "move":
                # Start all pending creations at current time offset (before this movement)
                if pending_creations:
                    for creation_data in pending_creations:
                        if creation_data["type"] == "wall":
                            anim = self.animation_system.build_wall_creation_animation(
                                creation_data["row"],
                                creation_data["col"],
                                creation_data["orientation"],
                                current_time_offset
                            )
                            creation_anims.append(anim)
                        elif creation_data["type"] == "tile":
                            anim = self.animation_system.build_tile_creation_animation(
                                creation_data["row"],
                                creation_data["col"],
                                creation_data["tile_type"],
                                current_time_offset
                            )
                            creation_anims.append(anim)
                    pending_creations.clear()
                
                # Get duration from actual animation
                if anim_idx < len(flat_anims):
                    move_anim = flat_anims[anim_idx]
                    if move_anim.anim_type == "movement":
                        move_duration = self.animation_system.get_animation_duration(move_anim)
                        current_time_offset += move_duration
                        anim_idx += 1
            
            elif action_type == "rotate":
                # Get duration from actual animation
                if anim_idx < len(flat_anims):
                    rot_anim = flat_anims[anim_idx]
                    if rot_anim.anim_type == "rotation":
                        rotate_duration = self.animation_system.get_animation_duration(rot_anim)
                        current_time_offset += rotate_duration
                        anim_idx += 1
            
            elif action_type == "wall_create":
                # Queue wall creation for next movement transition
                try:
                    wall_row, wall_col, orientation, total_cost = action[1]
                    pending_creations.append({
                        "type": "wall",
                        "row": wall_row,
                        "col": wall_col,
                        "orientation": orientation
                    })
                except Exception:
                    pass
            
            elif action_type == "wall_reinforce":
                # Reinforcements don't have visual animations (instant HP boost)
                pass
            
            elif action_type == "tile_creation":
                # Queue tile creation for next movement transition
                try:
                    tile_type_key = action[1]
                    tile_row, tile_col = action[2], action[3]
                    # Get tile type from config
                    tiles_available = player.devil_fruit_data.get("map_abilities", {}).get("tiles_available", {})
                    tile_config = tiles_available.get(tile_type_key)
                    if tile_config:
                        tile_type = tile_config.get("tile_type", "trap_continuous")
                        pending_creations.append({
                            "type": "tile",
                            "row": tile_row,
                            "col": tile_col,
                            "tile_type": tile_type
                        })
                except Exception:
                    pass
        
        # Handle any remaining pending creations (creations after final movement)
        if pending_creations:
            for creation_data in pending_creations:
                if creation_data["type"] == "wall":
                    anim = self.animation_system.build_wall_creation_animation(
                        creation_data["row"],
                        creation_data["col"],
                        creation_data["orientation"],
                        current_time_offset
                    )
                    creation_anims.append(anim)
                elif creation_data["type"] == "tile":
                    anim = self.animation_system.build_tile_creation_animation(
                        creation_data["row"],
                        creation_data["col"],
                        creation_data["tile_type"],
                        current_time_offset
                    )
                    creation_anims.append(anim)
        
        return creation_anims

    def _build_attack_animation(self, attack_type: str, damage_output: int, is_skip: bool, is_hit: bool, player_id: str, speed_multiplier: float) -> AnimationEntry:
        # is_hit from combat hit chance roll determines double hop; damage_output scales second hop height
        safe_damage = max(0, int(damage_output))
        return self.animation_system.build_attack_animation(attack_type, safe_damage, is_skip, is_hit, player_id, speed_multiplier)

    def _build_defense_animation(self, defense_type: str, player_id: str, from_row: int, from_col: int, from_facing: int, speed_multiplier: float) -> AnimationEntry:
        return self.animation_system.build_defense_animation(defense_type, player_id, from_row, from_col, from_facing, speed_multiplier)

    def _build_push_animation(self, from_row: int, from_col: int, to_row: int, to_col: int, distance: int, player_id: str) -> AnimationEntry:
        return self.animation_system.build_push_animation(from_row, from_col, to_row, to_col, player_id, distance)

    def _build_doom_animation(self, player_id: str) -> AnimationEntry:
        return self.animation_system.build_doom_animation(player_id)

    def apply_map_update(self, map_update: Dict[str, Any]) -> None:
        """Apply a server map_update to tile_system and wall_system.
        
        Used for per-turn server-driven spawns in multiplayer.
        Server sends new coordinates; client creates tiles/walls using engine logic.
        """
        try:
            tiles = map_update.get("tiles") or []
            for t in tiles:
                try:
                    r = int(t.get("row"))
                    c = int(t.get("col"))
                    tile_type = t.get("tile_type") or t.get("type")
                    if tile_type is None:
                        continue
                except Exception:
                    continue
                base_hp = int(100 + self.avg_primary_sum * 0.5)
                if tile_type == 'unpassable':
                    hp = float('inf')
                    duration = None
                else:
                    hp = base_hp
                    duration = None
                try:
                    from engine.tiles import Tile
                    self.tile_system._tiles[(r, c)] = Tile(r, c, tile_type, hp, duration)
                except Exception:
                    continue
        except Exception:
            pass

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
                    if getattr(wall, "creator", None) is not None:
                        wall.max_hp = max(0, wall.max_hp - total_hp)
                # Refund DF stamina
                player.devil_fruit_stamina += total_cost
                self.battle_log.append(f"Wall reinforcement cancelled at ({wall_row},{wall_col},{orientation}) (+{total_cost:.1f} DF stamina)")
        
        self._reset_planning_state(canceled=True)

    def _reset_planning_state(self, canceled: bool = False) -> None:
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
        if canceled:
            self.battle_log.append("Planning canceled/reset")
        else:
            self.battle_log.append("Planning reset")
        self.bounce_segments = []
        # Pattern tracking
        self.pattern_start_move_idx = None
        self.pattern_end_move_idx = None
        self.pattern_name = None
        
        # Clear MP object tracking (PHASE 1)
        if self.is_multiplayer:
            self.objects_created_this_turn.clear()
            self.objects_destroyed_this_turn.clear()

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

        # Update FOV cache after rotation via wheel when defending
        if self.phase == "defense":
            self._update_fov_cache()

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

        # FOV-based stamina modifiers (defense phase only)
        fov_move_mult = 1.0
        fov_def_mult = 1.0
        if self.phase == "defense":
            try:
                from engine.fov import get_fov_layer
                defender = self.get_current_player()
                attacker = self.get_opponent()
                defender_fov_layer = get_fov_layer(defender.facing, (defender.row, defender.col), (attacker.row, attacker.col))
                if defender_fov_layer == "FOV":
                    fov_move_mult = 0.85
                    fov_def_mult = 0.70
                elif defender_fov_layer == "Behind":
                    fov_move_mult = 1.15
            except Exception:
                # Fall back to neutral multipliers if FOV calculation fails
                fov_move_mult = 1.0
                fov_def_mult = 1.0

        if self.phase == "defense":
            movement_cost = int(movement_cost * fov_move_mult)
        
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
            defense_cost = int(defense_cost * fov_def_mult)
        
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
        # FOV-based movement modifier (defense phase only)
        defender_fov_layer = None
        fov_move_mult = 1.0
        if self.phase == "defense":
            try:
                from engine.fov import get_fov_layer
                defender = self.get_current_player()
                attacker = self.get_opponent()
                defender_fov_layer = get_fov_layer(defender.facing, (defender.row, defender.col), (attacker.row, attacker.col))
                if defender_fov_layer == "FOV":
                    fov_move_mult = 0.85
                elif defender_fov_layer == "Behind":
                    fov_move_mult = 1.15
            except Exception:
                defender_fov_layer = None
                fov_move_mult = 1.0
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
                # Apply FOV stamina modifier (defense phase only)
                if self.phase == "defense":
                    move_cost = int(move_cost * fov_move_mult)
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
                if self.phase == "defense" and defender_fov_layer is not None:
                    if defender_fov_layer == "FOV":
                        bonus_parts.append("FOV -15% St")
                    elif defender_fov_layer == "Behind":
                        bonus_parts.append("FOV +15% St")
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
                    tile1 = f"{wall_row+1}{chr(65+wall_col)}"
                    tile2 = f"{wall_row+1}{chr(65+wall_col+1)}"
                elif orientation == 'h':
                    # Horizontal wall between (wall_row, wall_col) and (wall_row+1, wall_col)
                    tile1 = f"{wall_row+1}{chr(65+wall_col)}"
                    tile2 = f"{wall_row+2}{chr(65+wall_col)}"
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
        
        # Apply status effect stat modifications
        effective_attacker = self._get_effective_player(attacker)
        effective_defender = self._get_effective_player(defender)
        
        from engine.fov import get_fov_hit_bonus
        # Use defender's FOV: where is attacker around defender's body
        fov_hit_bonus = get_fov_hit_bonus(
            defender.facing,
            (defender.row, defender.col),
            (attacker.row, attacker.col)
        )
        
        # Calculate hit chance
        hit_chance = calculate_hit_chance(
            effective_attacker, effective_defender, attack_type, None,  # No defense_type in attack phase
            facing_bonus, bounce_bonus, pattern_hit,
            df_multipliers, haki_obs_eff_attacker, haki_obs_eff_defender,
            is_defense_phase=False,
            attacker_df_alloys=self.applied_df_alloys,
            defender_df_alloys=set(),  # No defender alloys in preview
            fov_hit_bonus=fov_hit_bonus
        )
        
        # Calculate damage
        damage = calculate_damage(
            effective_attacker, effective_defender, base_damage, attack_type, None,  # No defense_type in attack phase
            facing_bonus, bounce_bonus, pattern_dmg,
            df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
            is_defense_phase=False,
            attacker_df_alloys=self.applied_df_alloys,
            defender_df_alloys=set()  # No defender alloys in preview
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
    
    def _apply_wall_damage_to_pattern(self, attack_tiles: List[Tuple[int, int]], damage: int, origin_row: int, origin_col: int) -> Dict[Tuple[int, int], int]:
        """Apply damage to walls within the attack pattern using cascading breakthrough.
        
        Damage already includes all bonuses. Returns a dict mapping breakthrough
        tiles to passthrough damage amount: {(row, col): passthrough_damage}.
        
        Also stores breakthrough tiles in self.breakthrough_squares for UI display.
        """
        all_walls = self.wall_system._walls + self.wall_system._border_walls
        breakthrough_tiles_damage: Dict[Tuple[int, int], int] = {}
        
        print(f"  >> _apply_wall_damage called: damage={damage}, tiles={len(attack_tiles)}")
        print(f"  >> Total walls in system: {len(all_walls)} (internal={len(self.wall_system._walls)}, border={len(self.wall_system._border_walls)})")
        
        internal_walls = [w for w in self.wall_system._walls if w.tier != 'border']
        if internal_walls:
            print(f"  >> Internal walls list:")
            for w in internal_walls:
                print(f"     - Wall at ({w.row},{w.col},{w.orientation}), tier={w.tier}, HP={w.hp}/{w.max_hp}")
        else:
            print(f"  >> WARNING: No internal walls in system!")
        
        # === PART 1: Cascading breakthrough along cardinal lines from origin ===
        # Group blocked tiles into cardinal lines (same row or column as origin).
        lines: Dict[Tuple[str, int, int], List[Tuple[int, int]]] = {}
        other_blocked: List[Tuple[int, int]] = []
        
        for (tr, tc) in self.blocked_tiles_map.keys():
            if tr == origin_row and tc == origin_col:
                continue
            if tc == origin_col and tr != origin_row:
                sign = 1 if tr > origin_row else -1
                key = ("col", origin_col, sign)
                lines.setdefault(key, []).append((tr, tc))
            elif tr == origin_row and tc != origin_col:
                sign = 1 if tc > origin_col else -1
                key = ("row", origin_row, sign)
                lines.setdefault(key, []).append((tr, tc))
            else:
                other_blocked.append((tr, tc))
        
        processed_walls: Set[Tuple[int, int, str]] = set()
        processed_tiles: Set[Tuple[int, int]] = set()
        
        # Process vertical and horizontal lines with sequential propagation
        for (axis, index, sign), tiles in lines.items():
            if not tiles:
                continue
            
            if axis == "col":
                # Vertical line: same column, varying rows
                tile_positions = sorted(tiles, key=lambda t: (t[0] - origin_row) * sign)
                furthest_row = tile_positions[-1][0]
                # Collect horizontal walls on this column between origin and furthest tile
                line_walls = []
                for w in internal_walls:
                    if w.orientation != 'h' or w.col != index:
                        continue
                    if sign == 1:
                        if origin_row <= w.row < furthest_row:
                            line_walls.append(w)
                    else:
                        if furthest_row < w.row <= origin_row:
                            line_walls.append(w)
                if not line_walls:
                    continue
                line_walls.sort(key=lambda w: (w.row - origin_row) * sign)
                remaining = damage
                tile_rows_sorted = sorted({r for (r, c) in tile_positions}, key=lambda r: (r - origin_row) * sign)
                for i, wall in enumerate(line_walls):
                    if remaining <= 0:
                        break
                    hp_before = max(0, wall.hp)
                    if hp_before <= 0:
                        continue
                    processed_walls.add((wall.row, wall.col, wall.orientation))
                    # Apply only the remaining damage to this wall
                    wall_destroyed = self.wall_system.damage_wall(wall.row, wall.col, wall.orientation, remaining)
                    
                    # Track wall destruction for MP manifest (PHASE 1)
                    if self.is_multiplayer and wall_destroyed:
                        self.objects_destroyed_this_turn.append({
                            "type": "wall",
                            "row": wall.row,
                            "col": wall.col,
                            "orientation": wall.orientation
                        })
                    wall_after = self.wall_system.get_wall_at(wall.row, wall.col, wall.orientation)
                    hp_after = wall_after.hp if wall_after else 0
                    print(f"  >> Damaged wall ({wall.row},{wall.col},{wall.orientation}): {hp_before} HP -> {hp_after} HP (destroyed={wall_destroyed})")
                    absorbed = min(remaining, hp_before)
                    remaining_after = max(0, remaining - absorbed)
                    
                    this_row = wall.row
                    if i + 1 < len(line_walls):
                        next_row = line_walls[i + 1].row
                    else:
                        next_row = furthest_row
                    if sign == 1:
                        seg_min = this_row + 1
                        seg_max = next_row
                    else:
                        seg_min = next_row
                        seg_max = this_row - 1
                    
                    if wall_destroyed and remaining_after > 0:
                        # Tiles between this wall and the next boundary become breakthrough tiles
                        for r in tile_rows_sorted:
                            if seg_min <= r <= seg_max:
                                tile = (r, index)
                                if tile not in breakthrough_tiles_damage:
                                    breakthrough_tiles_damage[tile] = remaining_after
                                    processed_tiles.add(tile)
                                    if tile in self.blocked_tiles_map:
                                        print(f"  >> REMOVING tile {tile} from blocked_tiles_map (breakthrough confirmed)")
                                        del self.blocked_tiles_map[tile]
                        self.battle_log.append(
                            f"Wall at ({wall.row},{wall.col},{wall.orientation}) destroyed ({absorbed} dmg) - {remaining_after} breakthrough!"
                        )
                    elif wall_destroyed and remaining_after == 0:
                        # Wall destroyed but absorbed exactly the remaining damage - no breakthrough beyond
                        # Remove tiles from blocked_tiles_map but don't create breakthrough
                        for r in tile_rows_sorted:
                            if seg_min <= r <= seg_max:
                                tile = (r, index)
                                if tile in self.blocked_tiles_map:
                                    print(f"  >> REMOVING tile {tile} from blocked_tiles_map (wall destroyed, exact absorption)")
                                    del self.blocked_tiles_map[tile]
                        self.battle_log.append(
                            f"Wall at ({wall.row},{wall.col},{wall.orientation}) destroyed ({absorbed} dmg) - exact absorption!"
                        )
                        remaining_after = 0
                    elif not wall_destroyed and wall_after:
                        # Wall survives and stops cascade on this line
                        self.battle_log.append(
                            f"Wall ({wall.row},{wall.col},{wall.orientation}): {wall_after.hp}/{wall_after.max_hp} HP"
                        )
                        remaining_after = 0
                    remaining = remaining_after
            elif axis == "row":
                # Horizontal line: same row, varying columns
                tile_positions = sorted(tiles, key=lambda t: (t[1] - origin_col) * sign)
                furthest_col = tile_positions[-1][1]
                # Collect vertical walls on this row between origin and furthest tile
                line_walls = []
                for w in internal_walls:
                    if w.orientation != 'v' or w.row != index:
                        continue
                    if sign == 1:
                        if origin_col <= w.col < furthest_col:
                            line_walls.append(w)
                    else:
                        if furthest_col < w.col <= origin_col:
                            line_walls.append(w)
                if not line_walls:
                    continue
                line_walls.sort(key=lambda w: (w.col - origin_col) * sign)
                remaining = damage
                tile_cols_sorted = sorted({c for (r, c) in tile_positions}, key=lambda c: (c - origin_col) * sign)
                for i, wall in enumerate(line_walls):
                    if remaining <= 0:
                        break
                    hp_before = max(0, wall.hp)
                    if hp_before <= 0:
                        continue
                    processed_walls.add((wall.row, wall.col, wall.orientation))
                    wall_destroyed = self.wall_system.damage_wall(wall.row, wall.col, wall.orientation, remaining)
                    
                    # Track wall destruction for MP manifest (PHASE 1)
                    if self.is_multiplayer and wall_destroyed:
                        self.objects_destroyed_this_turn.append({
                            "type": "wall",
                            "row": wall.row,
                            "col": wall.col,
                            "orientation": wall.orientation
                        })
                    wall_after = self.wall_system.get_wall_at(wall.row, wall.col, wall.orientation)
                    hp_after = wall_after.hp if wall_after else 0
                    print(f"  >> Damaged wall ({wall.row},{wall.col},{wall.orientation}): {hp_before} HP -> {hp_after} HP (destroyed={wall_destroyed})")
                    absorbed = min(remaining, hp_before)
                    remaining_after = max(0, remaining - absorbed)
                    
                    this_col = wall.col
                    if i + 1 < len(line_walls):
                        next_col = line_walls[i + 1].col
                    else:
                        next_col = furthest_col
                    if sign == 1:
                        seg_min = this_col + 1
                        seg_max = next_col
                    else:
                        seg_min = next_col
                        seg_max = this_col - 1
                    
                    if wall_destroyed and remaining_after > 0:
                        for c in tile_cols_sorted:
                            if seg_min <= c <= seg_max:
                                tile = (index, c)
                                if tile not in breakthrough_tiles_damage:
                                    breakthrough_tiles_damage[tile] = remaining_after
                                    processed_tiles.add(tile)
                                    if tile in self.blocked_tiles_map:
                                        print(f"  >> REMOVING tile {tile} from blocked_tiles_map (breakthrough confirmed)")
                                        del self.blocked_tiles_map[tile]
                        self.battle_log.append(
                            f"Wall at ({wall.row},{wall.col},{wall.orientation}) destroyed ({absorbed} dmg) - {remaining_after} breakthrough!"
                        )
                    elif wall_destroyed and remaining_after == 0:
                        # Wall destroyed but absorbed exactly the remaining damage - no breakthrough beyond
                        # Remove tiles from blocked_tiles_map but don't create breakthrough
                        for c in tile_cols_sorted:
                            if seg_min <= c <= seg_max:
                                tile = (index, c)
                                if tile in self.blocked_tiles_map:
                                    print(f"  >> REMOVING tile {tile} from blocked_tiles_map (wall destroyed, exact absorption)")
                                    del self.blocked_tiles_map[tile]
                        self.battle_log.append(
                            f"Wall at ({wall.row},{wall.col},{wall.orientation}) destroyed ({absorbed} dmg) - exact absorption!"
                        )
                        remaining_after = 0
                    elif not wall_destroyed and wall_after:
                        self.battle_log.append(
                            f"Wall ({wall.row},{wall.col},{wall.orientation}): {wall_after.hp}/{wall_after.max_hp} HP"
                        )
                        remaining_after = 0
                    remaining = remaining_after
        
        # === PART 2: Handle remaining blocked tiles (e.g., diagonal cases) with simple rule ===
        for blocked_tile, blocking_wall_list in list(self.blocked_tiles_map.items()):
            if blocked_tile in processed_tiles:
                continue
            walls = []
            total_hp_destroyed = 0
            all_destroyed = True
            for wall_row, wall_col, wall_orient in blocking_wall_list:
                wall = self.wall_system.get_wall_at(wall_row, wall_col, wall_orient)
                if wall and wall.tier != 'border':
                    walls.append(wall)
                    if (wall_row, wall_col, wall_orient) not in processed_walls:
                        # Apply full damage once to walls not yet processed (non-cascading)
                        hp_before = max(0, wall.hp)
                        if hp_before > 0:
                            destroyed = self.wall_system.damage_wall(wall_row, wall_col, wall_orient, damage)
                            
                            # Track wall destruction for MP manifest (PHASE 1)
                            if self.is_multiplayer and destroyed:
                                self.objects_destroyed_this_turn.append({
                                    "type": "wall",
                                    "row": wall_row,
                                    "col": wall_col,
                                    "orientation": wall_orient
                                })
                            wall_after = self.wall_system.get_wall_at(wall_row, wall_col, wall_orient)
                            hp_after = wall_after.hp if wall_after else 0
                            print(f"  >> Damaged wall (fallback {wall_row},{wall_col},{wall_orient}): {hp_before} HP -> {hp_after} HP (destroyed={destroyed})")
                            processed_walls.add((wall_row, wall_col, wall_orient))
                            total_hp_destroyed += hp_before
                            if not destroyed:
                                all_destroyed = False
                        else:
                            # Already at 0 HP
                            continue
            if walls and all_destroyed:
                # All blocking walls destroyed -> breakthrough only if damage exceeds total wall HP
                remaining_fallback = max(0, damage - total_hp_destroyed)
                if remaining_fallback > 0 and blocked_tile not in breakthrough_tiles_damage:
                    breakthrough_tiles_damage[blocked_tile] = remaining_fallback
                    print(f"  >> Fallback breakthrough: Tile {blocked_tile} receives {remaining_fallback} damage (all walls destroyed, total HP={total_hp_destroyed})")
                    if blocked_tile in self.blocked_tiles_map:
                        print(f"  >> REMOVING tile {blocked_tile} from blocked_tiles_map (fallback breakthrough)")
                        del self.blocked_tiles_map[blocked_tile]
                else:
                    print(f"  >> Fallback: Tile {blocked_tile} protected (all walls destroyed but no remaining damage: {damage} - {total_hp_destroyed} = {remaining_fallback})")
        
        # === PART 3: Side/bordering walls that do not participate in cascade ===
        for wall in all_walls:
            if wall.tier == 'border':
                continue
            key = (wall.row, wall.col, wall.orientation)
            if key in processed_walls:
                continue
            
            # Determine if wall blocks any tiles (already covered by blocked_tiles_map)
            wall_blocks_pattern = any(
                any(w_row == wall.row and w_col == wall.col and w_orient == wall.orientation
                    for (w_row, w_col, w_orient) in blocking_walls)
                for blocking_walls in self.blocked_tiles_map.values()
            )
            
            # Or if it borders the attack pattern (side hit)
            affected_tiles = []
            if wall.orientation == 'h':
                affected_tiles = [(wall.row, wall.col), (wall.row + 1, wall.col)]
            elif wall.orientation == 'v':
                affected_tiles = [(wall.row, wall.col), (wall.row, wall.col + 1)]
            wall_borders_pattern = any(tile in attack_tiles for tile in affected_tiles)
            
            print(f"  >> Checking side wall ({wall.row},{wall.col},{wall.orientation}): affects tiles {affected_tiles}, blocks={wall_blocks_pattern}, borders={wall_borders_pattern}")
            
            if wall_blocks_pattern or wall_borders_pattern:
                hp_before = max(0, wall.hp)
                if hp_before <= 0:
                    continue
                destroyed = self.wall_system.damage_wall(wall.row, wall.col, wall.orientation, damage)
                
                # Track wall destruction for MP manifest (PHASE 1)
                if self.is_multiplayer and destroyed:
                    self.objects_destroyed_this_turn.append({
                        "type": "wall",
                        "row": wall.row,
                        "col": wall.col,
                        "orientation": wall.orientation
                    })
                wall_after = self.wall_system.get_wall_at(wall.row, wall.col, wall.orientation)
                hp_after = wall_after.hp if wall_after else 0
                print(f"  >> Damaged side wall ({wall.row},{wall.col},{wall.orientation}): {hp_before} HP -> {hp_after} HP (destroyed={destroyed})")
                if destroyed:
                    self.battle_log.append(
                        f"Wall at ({wall.row},{wall.col},{wall.orientation}) destroyed ({damage} dmg)"
                    )
                elif wall_after:
                    self.battle_log.append(
                        f"Wall ({wall.row},{wall.col},{wall.orientation}): {wall_after.hp}/{wall_after.max_hp} HP"
                    )
        
        # Store breakthrough tiles for UI display during defense phase
        self.breakthrough_squares = list(breakthrough_tiles_damage.keys())
        
        # === PART 4: Damage special tiles in attack pattern ===
        # According to rules: tiles take same damage as walls (0 defense, 100% hit chance)
        # Tiles that can be damaged: trap_continuous, trap_momentary, drop_continuous, drop_momentary
        print(f"\n  >> Checking special tiles in attack pattern for damage...")
        for tile_pos in attack_tiles:
            special_tile = self.tile_system.get_tile_at(tile_pos[0], tile_pos[1])
            if special_tile and special_tile.tile_type in ['trap_continuous', 'trap_momentary', 'drop_continuous', 'drop_momentary']:
                tile_destroyed = self.tile_system.damage_tile(tile_pos[0], tile_pos[1], damage)
                
                # Track tile destruction for MP manifest (PHASE 1)
                if self.is_multiplayer and tile_destroyed:
                    self.objects_destroyed_this_turn.append({
                        "type": "tile",
                        "row": tile_pos[0],
                        "col": tile_pos[1],
                        "tile_type": special_tile.tile_type
                    })
                
                if tile_destroyed:
                    print(f"  >> Special tile at {tile_pos} destroyed by attack ({damage} damage)")
                    self.battle_log.append(f"Special tile at {tile_pos} destroyed!")
                else:
                    tile_after = self.tile_system.get_tile_at(tile_pos[0], tile_pos[1])
                    if tile_after:
                        print(f"  >> Special tile at {tile_pos}: {tile_after.hp}/{tile_after.max_hp} HP remaining")
                        self.battle_log.append(f"Tile at {tile_pos}: {int(tile_after.hp)}/{int(tile_after.max_hp)} HP")
        
        return breakthrough_tiles_damage

    def _filter_cardinal_attack_pattern_by_walls(self, tiles: List[Tuple[int, int]], attacker_row: int, attacker_col: int, ang: int) -> List[Tuple[int, int]]:
        """Filter cardinal attack pattern tiles based on wall blocking.

        Cardinal ray-based version (cardinal paths only):
        - Rays always travel along rows/columns (no diagonal grid steps).
        - For each tile, we trace a Manhattan path from the attacker to the tile
          using cardinal steps only.
        - For East/West facings: sideways moves along rows, then forward/back
          along columns.
        - For North/South facings: sideways moves along columns, then forward/back
          along rows.
        - At each step, we query _get_wall_between; any non-border wall blocks
          the tile and is recorded in blocked_tiles_map.
        """
        # TEMP SWITCH: disable cardinal ray-based wall filtering while redesigning
        # divider shapes for cardinal. Set this to False to bypass the new system.
        ENABLE_CARDINAL_RAY_FILTER = True
        if not ENABLE_CARDINAL_RAY_FILTER:
            return tiles

        internal_walls = self.wall_system._walls
        self.blocked_tiles_map = {}
        self.debug_rays = []
        filtered_tiles: List[Tuple[int, int]] = []

        for tile_row, tile_col in tiles:
            # Classify tile field (Front/Back/Left/Right)
            field = self._classify_tile_field(attacker_row, attacker_col, float(ang), tile_row, tile_col)
            
            # Compute source on axis-aligned field boundary divider based on facing, field, and tile position
            norm_facing = int(ang % 360)

            # Decide whether this ray is vertical or horizontal (same rule as before)
            if norm_facing in (270, 90):  # North/South
                use_vertical = field in ("Front", "Back")
            else:  # East/West
                use_vertical = field in ("Left", "Right")

            # Allowed boundary field pairs for this tile's field
            if field == "Front":
                allowed_pairs = ({"Front", "Left"}, {"Front", "Right"})
            elif field == "Back":
                allowed_pairs = ({"Back", "Left"}, {"Back", "Right"})
            elif field == "Left":
                allowed_pairs = ({"Front", "Left"}, {"Back", "Left"})
            else:  # "Right"
                allowed_pairs = ({"Front", "Right"}, {"Back", "Right"})

            src_row = float(attacker_row)
            src_col = float(attacker_col)
            found_src = False

            if use_vertical:
                # Vertical ray: search horizontal boundaries along this column from tile toward attacker
                c = tile_col
                if attacker_row > tile_row:
                    step = 1
                elif attacker_row < tile_row:
                    step = -1
                else:
                    # Same row as attacker: choose direction based on facing (South=down, North=up)
                    step = 1 if norm_facing == 90 else -1

                r = tile_row
                while 0 <= r < 7 and r != attacker_row:
                    next_r = r + step
                    if not (0 <= next_r < 7):
                        break
                    f1 = self._classify_tile_field(attacker_row, attacker_col, float(ang), r, c)
                    f2 = self._classify_tile_field(attacker_row, attacker_col, float(ang), next_r, c)
                    fields_pair = {f1, f2}
                    if fields_pair in allowed_pairs:
                        # Horizontal boundary between rows r and next_r at y = min(r, next_r) + 1
                        boundary_row = min(r, next_r) + 0.5
                        src_row = boundary_row
                        src_col = float(c)
                        found_src = True
                        break
                    r = next_r
            else:
                # Horizontal ray: search vertical boundaries along this row from tile toward attacker
                r = tile_row
                if attacker_col > tile_col:
                    step = 1
                elif attacker_col < tile_col:
                    step = -1
                else:
                    # Same column as attacker: choose direction based on facing (East=right, West=left)
                    step = 1 if norm_facing == 0 else -1

                c = tile_col
                while 0 <= c < 7 and c != attacker_col:
                    next_c = c + step
                    if not (0 <= next_c < 7):
                        break
                    f1 = self._classify_tile_field(attacker_row, attacker_col, float(ang), r, c)
                    f2 = self._classify_tile_field(attacker_row, attacker_col, float(ang), r, next_c)
                    fields_pair = {f1, f2}
                    if fields_pair in allowed_pairs:
                        # Vertical boundary between cols c and next_c at x = min(c, next_c) + 1
                        boundary_col = min(c, next_c) + 0.5
                        src_col = boundary_col
                        src_row = float(r)
                        found_src = True
                        break
                    c = next_c

            if not found_src:
                src_row = float(attacker_row)
                src_col = float(attacker_col)
            
            # Record ray for visualization
            self.debug_rays.append((src_row, src_col, tile_row, tile_col))
            
            # SPECIAL CASE: Parallel wall blocking for cardinal directions
            # If a parallel wall exists one step in front of the player in the same column/row,
            # block the entire column/row of tiles in that field
            blocked_by_parallel_wall = False
            parallel_wall: Optional[Tuple[int, int, str]] = None
            
            if norm_facing == 270:  # North (moving up, decreasing rows)
                # Horizontal walls are parallel (perpendicular to movement)
                # Check for horizontal wall at (attacker_row - 1, tile_col)
                check_row = attacker_row - 1
                if check_row >= 0:
                    for wall in internal_walls:
                        if (wall.row == check_row and wall.col == tile_col and 
                            wall.orientation == 'h' and getattr(wall, "tier", "") != "border"):
                            blocked_by_parallel_wall = True
                            parallel_wall = (wall.row, wall.col, wall.orientation)
                            break
            
            elif norm_facing == 90:  # South (moving down, increasing rows)
                # Horizontal walls are parallel
                # Check for horizontal wall at (attacker_row, tile_col) - wall between attacker and next row
                check_row = attacker_row
                if check_row < 6:
                    for wall in internal_walls:
                        if (wall.row == check_row and wall.col == tile_col and 
                            wall.orientation == 'h' and getattr(wall, "tier", "") != "border"):
                            blocked_by_parallel_wall = True
                            parallel_wall = (wall.row, wall.col, wall.orientation)
                            break
            
            elif norm_facing == 0:  # East (moving right, increasing cols)
                # Vertical walls are parallel
                # Check for vertical wall at (tile_row, attacker_col)
                check_col = attacker_col
                if check_col < 6:
                    for wall in internal_walls:
                        if (wall.row == tile_row and wall.col == check_col and 
                            wall.orientation == 'v' and getattr(wall, "tier", "") != "border"):
                            blocked_by_parallel_wall = True
                            parallel_wall = (wall.row, wall.col, wall.orientation)
                            break
            
            elif norm_facing == 180:  # West (moving left, decreasing cols)
                # Vertical walls are parallel
                # Check for vertical wall at (tile_row, attacker_col - 1)
                check_col = attacker_col - 1
                if check_col >= 0:
                    for wall in internal_walls:
                        if (wall.row == tile_row and wall.col == check_col and 
                            wall.orientation == 'v' and getattr(wall, "tier", "") != "border"):
                            blocked_by_parallel_wall = True
                            parallel_wall = (wall.row, wall.col, wall.orientation)
                            break
            
            if blocked_by_parallel_wall and parallel_wall is not None:
                if (tile_row, tile_col) not in self.blocked_tiles_map:
                    self.blocked_tiles_map[(tile_row, tile_col)] = []
                self.blocked_tiles_map[(tile_row, tile_col)].append(parallel_wall)
                continue
            
            # CONNECTED WALLS SOURCE BLOCKING:
            # If 2+ walls of same orientation share a coordinate on the source divider,
            # activate source blocking for tiles traced from that divider coordinate
            blocked_by_connected_walls = False
            connected_wall: Optional[Tuple[int, int, str]] = None
            
            if ray_is_vertical := (abs(src_col - tile_col) < 0.01):
                # Vertical ray: check for vertical walls sharing this column coordinate
                shared_coord = src_col
                v_walls_at_col = [w for w in internal_walls 
                                  if w.col == int(shared_coord) and w.orientation == 'v' 
                                  and getattr(w, "tier", "") != "border"]
                if len(v_walls_at_col) >= 2:
                    blocked_by_connected_walls = True
                    connected_wall = (v_walls_at_col[0].row, v_walls_at_col[0].col, 'v')
            
            elif ray_is_horizontal := (abs(src_row - tile_row) < 0.01):
                # Horizontal ray: check for horizontal walls sharing this row coordinate
                shared_coord = src_row
                h_walls_at_row = [w for w in internal_walls 
                                  if w.row == int(shared_coord) and w.orientation == 'h' 
                                  and getattr(w, "tier", "") != "border"]
                if len(h_walls_at_row) >= 2:
                    blocked_by_connected_walls = True
                    connected_wall = (h_walls_at_row[0].row, h_walls_at_row[0].col, 'h')
            
            if blocked_by_connected_walls and connected_wall is not None:
                if (tile_row, tile_col) not in self.blocked_tiles_map:
                    self.blocked_tiles_map[(tile_row, tile_col)] = []
                self.blocked_tiles_map[(tile_row, tile_col)].append(connected_wall)
                continue
            
            # Cardinal ray-based blocking: cast ray from source to tile, check perpendicular walls
            sx = src_col + 0.5
            sy = src_row + 0.5
            tx = tile_col + 0.5
            ty = tile_row + 0.5

            dx = tx - sx
            dy = ty - sy

            blocked = False
            blocking_wall: Optional[Tuple[int, int, str]] = None

            if dx == 0 and dy == 0:
                filtered_tiles.append((tile_row, tile_col))
                continue

            # Determine if ray is vertical or horizontal
            ray_is_vertical = abs(dx) < 0.01
            ray_is_horizontal = abs(dy) < 0.01

            for wall in internal_walls:
                if getattr(wall, "tier", "") == "border":
                    continue

                w_row = wall.row
                w_col = wall.col

                # Perpendicular blocking: vertical rays blocked by horizontal walls, horizontal rays by vertical walls
                if ray_is_vertical and wall.orientation == 'h':
                    yw = w_row + 1.0
                    if dy == 0:
                        continue
                    t = (yw - sy) / dy
                    if 0.0 < t <= 1.0:
                        x_hit = sx + t * dx
                        if w_col <= x_hit <= w_col + 1.0:
                            blocked = True
                            blocking_wall = (w_row, w_col, wall.orientation)
                            break
                elif ray_is_horizontal and wall.orientation == 'v':
                    xw = w_col + 1.0
                    if dx == 0:
                        continue
                    t = (xw - sx) / dx
                    if 0.0 < t <= 1.0:
                        y_hit = sy + t * dy
                        if w_row <= y_hit <= w_row + 1.0:
                            blocked = True
                            blocking_wall = (w_row, w_col, wall.orientation)
                            break

            if blocked and blocking_wall is not None:
                if (tile_row, tile_col) not in self.blocked_tiles_map:
                    self.blocked_tiles_map[(tile_row, tile_col)] = []
                self.blocked_tiles_map[(tile_row, tile_col)].append(blocking_wall)
            else:
                filtered_tiles.append((tile_row, tile_col))

        return filtered_tiles
    
    def _filter_diagonal_attack_pattern_by_walls(self, tiles: List[Tuple[int, int]], attacker_row: int, attacker_col: int, attack_range: int, facing_angle: int) -> List[Tuple[int, int]]:
        """Filter diagonal attack pattern tiles based on wall blocking.

        Ray-based, divider-as-source system per Rule Update10:
        - For diagonal facings (NE/NW/SE/SW), dividers at the attacker's row/col
          act as wave sources.
        - Each tile is assigned a source on either the horizontal (row) or
          vertical (col) divider based on its front/back/left/right field.
        - A ray is cast from the source center to the tile center, and any
          intersection with an internal wall segment (vertical or horizontal)
          blocks that tile.
        - Border walls are ignored here (board edges are handled elsewhere).
        """
        internal_walls = self.wall_system._walls
        self.blocked_tiles_map = {}
        self.debug_rays = []

        if not internal_walls or not tiles:
            return tiles

        # Map facing angle to diagonal direction label using existing facing vector
        fx, fy = self._facing_to_vector(float(facing_angle))
        facing_name: Optional[str] = None
        if (fx, fy) == (1, -1):
            facing_name = "NE"
        elif (fx, fy) == (-1, -1):
            facing_name = "NW"
        elif (fx, fy) == (1, 1):
            facing_name = "SE"
        elif (fx, fy) == (-1, 1):
            facing_name = "SW"

        filtered: List[Tuple[int, int]] = []

        # Determine diagonal family usage based on facing
        if facing_name in ("NE", "SW"):
            fb_family = "NE_SW"   # Front/Back use NE-SW diagonals
            lr_family = "NW_SE"   # Left/Right use NW-SE diagonals
        elif facing_name in ("NW", "SE"):
            fb_family = "NW_SE"
            lr_family = "NE_SW"
        else:
            fb_family = "NE_SW"
            lr_family = "NW_SE"

        norm_facing = int(facing_angle % 360)
        is_cardinal = norm_facing in (0, 90, 180, 270)

        for tile_row, tile_col in tiles:
            field = self._classify_tile_field(attacker_row, attacker_col, facing_angle, tile_row, tile_col)

            # Determine tracing direction and compute source intersection
            if is_cardinal:
                # CARDINAL: trace along row or column
                if norm_facing in (270, 90):  # North or South
                    if field in ("Front", "Back"):
                        # Trace along column (vertical) to horizontal divider
                        src_row = attacker_row
                        src_col = tile_col
                    else:  # Left/Right
                        # Trace along row (horizontal) to vertical divider
                        src_row = tile_row
                        src_col = attacker_col
                else:  # East (0) or West (180)
                    if field in ("Front", "Back"):
                        # Trace along row (horizontal) to vertical divider
                        src_row = attacker_row
                        src_col = tile_col
                    else:  # Left/Right
                        # Trace along column (vertical) to horizontal divider
                        src_row = tile_row
                        src_col = attacker_col
            else:
                # DIAGONAL: trace along diagonal line to find intersection with one of the two field dividers
                # For NE facing: FL=vertical up (col=attacker_col, row<=attacker_row), FR=horizontal right (row=attacker_row, col>=attacker_col)
                #               BL=horizontal left (row=attacker_row, col<=attacker_col), BR=vertical down (col=attacker_col, row>=attacker_row)
                
                if norm_facing == 315:  # NE
                    if field == "Front":
                        # Front bounded by FL (vertical up) and FR (horizontal right)
                        # Trace NE-SW diagonal: check intersection with both
                        s = tile_row + tile_col
                        # Try FR (horizontal right): row=attacker_row, col>=attacker_col
                        fr_col = s - attacker_row
                        if attacker_col <= fr_col < 7:
                            src_row = attacker_row
                            src_col = fr_col
                        else:
                            # Try FL (vertical up): col=attacker_col, row<=attacker_row
                            fl_row = s - attacker_col
                            if 0 <= fl_row <= attacker_row:
                                src_row = fl_row
                                src_col = attacker_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    elif field == "Back":
                        # Back bounded by BL (horizontal left) and BR (vertical down)
                        s = tile_row + tile_col
                        # Try BL (horizontal left): row=attacker_row, col<=attacker_col
                        bl_col = s - attacker_row
                        if 0 <= bl_col <= attacker_col:
                            src_row = attacker_row
                            src_col = bl_col
                        else:
                            # Try BR (vertical down): col=attacker_col, row>=attacker_row
                            br_row = s - attacker_col
                            if attacker_row <= br_row < 7:
                                src_row = br_row
                                src_col = attacker_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    elif field == "Left":
                        # Left bounded by FL (vertical up) and BL (horizontal left)
                        d = tile_row - tile_col
                        # Try FL (vertical up): col=attacker_col, row<=attacker_row
                        fl_row = d + attacker_col
                        if 0 <= fl_row <= attacker_row:
                            src_row = fl_row
                            src_col = attacker_col
                        else:
                            # Try BL (horizontal left): row=attacker_row, col<=attacker_col
                            bl_col = attacker_row - d
                            if 0 <= bl_col <= attacker_col:
                                src_row = attacker_row
                                src_col = bl_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    else:  # Right
                        # Right bounded by FR (horizontal right) and BR (vertical down)
                        d = tile_row - tile_col
                        # Try FR (horizontal right): row=attacker_row, col>=attacker_col
                        fr_col = attacker_row - d
                        if attacker_col <= fr_col < 7:
                            src_row = attacker_row
                            src_col = fr_col
                        else:
                            # Try BR (vertical down): col=attacker_col, row>=attacker_row
                            br_row = d + attacker_col
                            if attacker_row <= br_row < 7:
                                src_row = br_row
                                src_col = attacker_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                # Similar logic for SE/SW/NW
                elif norm_facing == 45:  # SE
                    # For SE: FL=horizontal right (E), FR=vertical down (S), BR=horizontal left (W), BL=vertical up (N)
                    if field == "Front":
                        # Front bounded by FL (horizontal right) and FR (vertical down)
                        d = tile_row - tile_col
                        # Try FR (vertical down): col=attacker_col, row>=attacker_row
                        fr_row = d + attacker_col
                        if attacker_row <= fr_row < 7:
                            src_row = fr_row
                            src_col = attacker_col
                        else:
                            # Try FL (horizontal right): row=attacker_row, col>=attacker_col
                            fl_col = attacker_row - d
                            if attacker_col <= fl_col < 7:
                                src_row = attacker_row
                                src_col = fl_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    elif field == "Back":
                        # Back bounded by BL (vertical up) and BR (horizontal left)
                        d = tile_row - tile_col
                        # Try BL (vertical up): col=attacker_col, row<=attacker_row
                        bl_row = d + attacker_col
                        if 0 <= bl_row <= attacker_row:
                            src_row = bl_row
                            src_col = attacker_col
                        else:
                            # Try BR (horizontal left): row=attacker_row, col<=attacker_col
                            br_col = attacker_row - d
                            if 0 <= br_col <= attacker_col:
                                src_row = attacker_row
                                src_col = br_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    elif field == "Left":
                        # Left bounded by FL (horizontal right) and BL (vertical up)
                        s = tile_row + tile_col
                        # Try FL (horizontal right): row=attacker_row, col>=attacker_col
                        fl_col = s - attacker_row
                        if attacker_col <= fl_col < 7:
                            src_row = attacker_row
                            src_col = fl_col
                        else:
                            # Try BL (vertical up): col=attacker_col, row<=attacker_row
                            bl_row = s - attacker_col
                            if 0 <= bl_row <= attacker_row:
                                src_row = bl_row
                                src_col = attacker_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    else:  # Right
                        # Right bounded by FR (vertical down) and BR (horizontal left)
                        s = tile_row + tile_col
                        # Try FR (vertical down): col=attacker_col, row>=attacker_row
                        fr_row = s - attacker_col
                        if attacker_row <= fr_row < 7:
                            src_row = fr_row
                            src_col = attacker_col
                        else:
                            # Try BR (horizontal left): row=attacker_row, col<=attacker_col
                            br_col = s - attacker_row
                            if 0 <= br_col <= attacker_col:
                                src_row = attacker_row
                                src_col = br_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                elif norm_facing == 135:  # SW
                    # For SW: FL=vertical down, FR=horizontal left, BR=vertical up, BL=horizontal right
                    if field == "Front":
                        # Front bounded by FL (vertical down) and FR (horizontal left)
                        s = tile_row + tile_col
                        # Try FR (horizontal left): row=attacker_row, col<=attacker_col
                        fr_col = s - attacker_row
                        if 0 <= fr_col <= attacker_col:
                            src_row = attacker_row
                            src_col = fr_col
                        else:
                            # Try FL (vertical down): col=attacker_col, row>=attacker_row
                            fl_row = s - attacker_col
                            if attacker_row <= fl_row < 7:
                                src_row = fl_row
                                src_col = attacker_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    elif field == "Back":
                        # Back bounded by BL (horizontal right) and BR (vertical up)
                        s = tile_row + tile_col
                        # Try BL (horizontal right): row=attacker_row, col>=attacker_col
                        bl_col = s - attacker_row
                        if attacker_col <= bl_col < 7:
                            src_row = attacker_row
                            src_col = bl_col
                        else:
                            # Try BR (vertical up): col=attacker_col, row<=attacker_row
                            br_row = s - attacker_col
                            if 0 <= br_row <= attacker_row:
                                src_row = br_row
                                src_col = attacker_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    elif field == "Left":
                        # Left bounded by FL (vertical down) and BL (horizontal right)
                        d = tile_row - tile_col
                        # Try FL (vertical down): col=attacker_col, row>=attacker_row
                        fl_row = d + attacker_col
                        if attacker_row <= fl_row < 7:
                            src_row = fl_row
                            src_col = attacker_col
                        else:
                            # Try BL (horizontal right): row=attacker_row, col>=attacker_col
                            bl_col = attacker_row - d
                            if attacker_col <= bl_col < 7:
                                src_row = attacker_row
                                src_col = bl_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    else:  # Right
                        # Right bounded by FR (horizontal left) and BR (vertical up)
                        d = tile_row - tile_col
                        # Try FR (horizontal left): row=attacker_row, col<=attacker_col
                        fr_col = attacker_row - d
                        if 0 <= fr_col <= attacker_col:
                            src_row = attacker_row
                            src_col = fr_col
                        else:
                            # Try BR (vertical up): col=attacker_col, row<=attacker_row
                            br_row = d + attacker_col
                            if 0 <= br_row <= attacker_row:
                                src_row = br_row
                                src_col = attacker_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                elif norm_facing == 225:  # NW
                    # For NW: FL=horizontal left (W), FR=vertical up (N), BR=horizontal right (E), BL=vertical down (S)
                    if field == "Front":
                        # Front bounded by FL (horizontal left) and FR (vertical up)
                        d = tile_row - tile_col
                        # Try FR (vertical up): col=attacker_col, row<=attacker_row
                        fr_row = d + attacker_col
                        if 0 <= fr_row <= attacker_row:
                            src_row = fr_row
                            src_col = attacker_col
                        else:
                            # Try FL (horizontal left): row=attacker_row, col<=attacker_col
                            fl_col = attacker_row - d
                            if 0 <= fl_col <= attacker_col:
                                src_row = attacker_row
                                src_col = fl_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    elif field == "Back":
                        # Back bounded by BL (vertical down) and BR (horizontal right)
                        d = tile_row - tile_col
                        # Try BL (vertical down): col=attacker_col, row>=attacker_row
                        bl_row = d + attacker_col
                        if attacker_row <= bl_row < 7:
                            src_row = bl_row
                            src_col = attacker_col
                        else:
                            # Try BR (horizontal right): row=attacker_row, col>=attacker_col
                            br_col = attacker_row - d
                            if attacker_col <= br_col < 7:
                                src_row = attacker_row
                                src_col = br_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    elif field == "Left":
                        # Left bounded by FL (horizontal left) and BL (vertical down)
                        s = tile_row + tile_col
                        # Try FL (horizontal left): row=attacker_row, col<=attacker_col
                        fl_col = s - attacker_row
                        if 0 <= fl_col <= attacker_col:
                            src_row = attacker_row
                            src_col = fl_col
                        else:
                            # Try BL (vertical down): col=attacker_col, row>=attacker_row
                            bl_row = s - attacker_col
                            if attacker_row <= bl_row < 7:
                                src_row = bl_row
                                src_col = attacker_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                    else:  # Right
                        # Right bounded by FR (vertical up) and BR (horizontal right)
                        s = tile_row + tile_col
                        # Try FR (vertical up): col=attacker_col, row<=attacker_row
                        fr_row = s - attacker_col
                        if 0 <= fr_row <= attacker_row:
                            src_row = fr_row
                            src_col = attacker_col
                        else:
                            # Try BR (horizontal right): row=attacker_row, col>=attacker_col
                            br_col = s - attacker_row
                            if attacker_col <= br_col < 7:
                                src_row = attacker_row
                                src_col = br_col
                            else:
                                src_row = attacker_row
                                src_col = attacker_col
                else:
                    src_row = attacker_row
                    src_col = attacker_col

            source_block_wall = self._is_divider_source_blocked(attacker_row, attacker_col, src_row, src_col, field, facing_angle)
            if source_block_wall is not None:
                if (tile_row, tile_col) not in self.blocked_tiles_map:
                    self.blocked_tiles_map[(tile_row, tile_col)] = []
                self.blocked_tiles_map[(tile_row, tile_col)].append(source_block_wall)
                continue

            # Record ray for visualization (may be off-board; still useful for debugging)
            self.debug_rays.append((src_row, src_col, tile_row, tile_col))

            # Continuous coordinates: centers of source and tile cells
            sx = src_col + 0.5
            sy = src_row + 0.5
            tx = tile_col + 0.5
            ty = tile_row + 0.5

            dx = tx - sx
            dy = ty - sy

            blocked = False
            blocking_wall: Optional[Tuple[int, int, str]] = None

            if dx == 0 and dy == 0:
                filtered.append((tile_row, tile_col))
                continue

            for wall in internal_walls:
                if getattr(wall, "tier", "") == "border":
                    continue

                w_row = wall.row
                w_col = wall.col

                if wall.orientation == 'v':
                    # Vertical wall between columns (w_col, w_col+1) for rows (w_row, w_row+1)
                    xw = w_col + 1.0
                    if dx == 0:
                        continue
                    t = (xw - sx) / dx
                    if 0.0 < t <= 1.0:
                        y_hit = sy + t * dy
                        y_min = w_row
                        y_max = w_row + 1.0
                        if y_min <= y_hit <= y_max:
                            blocked = True
                            blocking_wall = (w_row, w_col, wall.orientation)
                            break
                elif wall.orientation == 'h':
                    # Horizontal wall between rows (w_row, w_row+1) for columns (w_col, w_col+1)
                    yw = w_row + 1.0
                    if dy == 0:
                        continue
                    t = (yw - sy) / dy
                    if 0.0 < t <= 1.0:
                        x_hit = sx + t * dx
                        x_min = w_col
                        x_max = w_col + 1.0
                        if x_min <= x_hit <= x_max:
                            blocked = True
                            blocking_wall = (w_row, w_col, wall.orientation)
                            break

            if blocked and blocking_wall is not None:
                if (tile_row, tile_col) not in self.blocked_tiles_map:
                    self.blocked_tiles_map[(tile_row, tile_col)] = []
                self.blocked_tiles_map[(tile_row, tile_col)].append(blocking_wall)
            else:
                filtered.append((tile_row, tile_col))

        return filtered

    def _is_divider_source_blocked(self, attacker_row: int, attacker_col: int, src_row: int, src_col: int, field: str, facing_angle: int) -> Optional[Tuple[int, int, str]]:
        """Check if a divider source is shadowed by a wall inside the same field.

        If a perpendicular wall intersects the divider segment between the attacker and
        the source, and both tiles adjacent to that wall are inside the same field,
        then all sources behind that wall are considered blocked.
        """
        internal_walls = getattr(self.wall_system, "_walls", [])
        if not internal_walls:
            return None

        if attacker_row == src_row and attacker_col == src_col:
            return None

        sx = attacker_col + 0.5
        sy = attacker_row + 0.5
        tx = src_col + 0.5
        ty = src_row + 0.5

        dx = tx - sx
        dy = ty - sy

        if dx == 0 and dy == 0:
            return None

        path_is_horizontal = attacker_row == src_row
        path_is_vertical = attacker_col == src_col

        if path_is_horizontal:
            allowed_orients = ("v",)
        elif path_is_vertical:
            allowed_orients = ("h",)
        else:
            allowed_orients = ("h", "v")

        for wall in internal_walls:
            if getattr(wall, "tier", "") == "border":
                continue

            if wall.orientation not in allowed_orients:
                continue

            w_row = wall.row
            w_col = wall.col
            intersects = False

            if wall.orientation == "v":
                if dx == 0:
                    continue
                xw = w_col + 1.0
                t = (xw - sx) / dx
                if 0.0 < t <= 1.0:
                    y_hit = sy + t * dy
                    if w_row <= y_hit <= w_row + 1.0:
                        intersects = True
            else:  # 'h'
                if dy == 0:
                    continue
                yw = w_row + 1.0
                t = (yw - sy) / dy
                if 0.0 < t <= 1.0:
                    x_hit = sx + t * dx
                    if w_col <= x_hit <= w_col + 1.0:
                        intersects = True

            if not intersects:
                continue

            if wall.orientation == "v":
                tiles = [(w_row, w_col), (w_row, w_col + 1)]
            else:
                tiles = [(w_row, w_col), (w_row + 1, w_col)]

            inside_field = True
            for tr, tc in tiles:
                if not (0 <= tr < 7 and 0 <= tc < 7):
                    inside_field = False
                    break
                f = self._classify_tile_field(attacker_row, attacker_col, float(facing_angle), tr, tc)
                if f != field:
                    inside_field = False
                    break

            if not inside_field:
                # Special case: wall adjacent to the attacker along the divider direction
                # still blocks sources even if it lies exactly on a field boundary.
                if path_is_vertical:
                    if dy > 0 and wall.orientation == "h" and w_row == attacker_row and w_col == attacker_col:
                        return (w_row, w_col, wall.orientation)
                    if dy < 0 and wall.orientation == "h" and w_row == attacker_row - 1 and w_col == attacker_col:
                        return (w_row, w_col, wall.orientation)
                elif path_is_horizontal:
                    if dx > 0 and wall.orientation == "v" and w_row == attacker_row and w_col == attacker_col:
                        return (w_row, w_col, wall.orientation)
                    if dx < 0 and wall.orientation == "v" and w_row == attacker_row and w_col == attacker_col - 1:
                        return (w_row, w_col, wall.orientation)
                continue

            return (w_row, w_col, wall.orientation)

        return None

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
        
        strength_mult = 1.0 + (attacker.strength / 400.0)  # Up to +25% at 100 STR
        wall_damage = int(push_damage * (1.0 + facing_bonus + bounce_bonus + pattern_bonus) * strength_mult)
        
        # Apply Haki armament bonuses vs walls/tiles
        att_arm_active_obj = getattr(self, 'attacker_arm_active', False)
        if att_arm_active_obj:
            haki_eff_obj = calculate_haki_effectiveness(attacker.haki_armament, 0, att_arm_active_obj)
            wall_damage = int(wall_damage * (1.0 + haki_eff_obj * 0.30))
        
        pushed = 0
        sea_doom_triggered = False  # Track sea tile doom
        print(f"[PUSH] Starting push loop for {distance} steps...")

        # Remember starting defender position for push animation
        start_pos = (defender.row, defender.col)
        for step in range(distance):
            print(f"\n[PUSH] --- Step {step+1}/{distance} ---")
            print(f"[PUSH] Current defender position: ({defender.row},{defender.col})")
            
            to_row = defender.row + facing_vec[1]
            to_col = defender.col + facing_vec[0]
            
            print(f"[PUSH] Target position: ({to_row},{to_col})")
            
            # Check bounds
            if not (0 <= to_row < 7 and 0 <= to_col < 7):
                print(f"[PUSH] BLOCKED: Out of bounds! Breaking.")
                break
            
            # Check sea tile at target position (corners + edges)
            sea_tile_doom = self.tile_system.is_sea_tile_at_position(to_row, to_col)
            if sea_tile_doom:
                # Move player onto sea tile first for visual feedback
                defender.row, defender.col = to_row, to_col
                pushed += 1
                self.battle_log.append(f"Sea doom! {defender.name} pushed into sea tile at ({to_row},{to_col})")
                # Store doom state, trigger game over after push loop completes
                sea_doom_triggered = True
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
                        self._add_turn_result(f"Push into wall: {push_damage} collision damage")
                        
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
            eff = self.tile_system.apply_tile_effect(defender.row, defender.col, defender, self.effects_engine)
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
            # Push animation is queued by caller, not here
        
        # Trigger game over after position update if sea doom occurred
        if sea_doom_triggered:
            # Mark which player fell into the sea for UI visualization
            if defender == self.player1:
                self.p1_sea_doom = True
            else:
                self.p2_sea_doom = True
            # Queue doom animation at final sea position
            player_id = "player1" if defender is self.player1 else "player2"
            doom_anim = self._build_doom_animation(player_id)
            self.animation_system.queue_animations([doom_anim])
            # Defer setting game over until after doom animation completes
            self.pending_game_over = attacker.name
        
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
        
        # Apply status effect stat modifications
        effective_attacker = self._get_effective_player(attacker)
        effective_defender = self._get_effective_player(defender)
        
        # Calculate damage using new signature
        dmg = calculate_damage(
            effective_attacker, effective_defender, base_damage, attack_type, None,
            facing_bonus, bounce_bonus, pattern_dmg,
            df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
            is_defense_phase=False,
            attacker_df_alloys=self.applied_df_alloys,
            defender_df_alloys=set()  # No defender alloys in attack phase direct hit
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
        # Push is now handled via animation queue, not here
        return {"result": "hit", **outcome}

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
    
    def get_fov_position_in_enemy_view(self) -> str:
        """Get where attacker is positioned in defender's FOV (cached).
        Returns: 'FOV', 'Periphery', 'Behind', or 'N/A' if not in planning mode.
        """
        if not self.planning_mode:
            return "N/A"
        
        # Return cached value (updated by _update_fov_cache)
        return getattr(self, '_fov_cache', 'FOV')
    
    def _update_fov_cache(self):
        """Recalculate FOV cache when positions or facing change.
        Only recalculates if current player is attacker OR if defender's position/facing changed.
        """
        if not self.planning_mode:
            self._fov_cache = "N/A"
            return
        
        # Determine who is attacker and defender
        if self.phase == "attack":
            # Attack phase: current player is attacker, opponent is defender
            attacker = self.get_current_player()
            defender = self.get_opponent()
            # Use ghost position for attacker (planning position)
            attacker_pos = (self.ghost_row, self.ghost_col)
            defender_pos = (defender.row, defender.col)
            defender_facing = defender.facing
        else:  # defense phase
            # Defense phase: opponent is attacker, current player is defender
            attacker = self.get_opponent()
            defender = self.get_current_player()
            # Use ghost position for defender (planning position)
            attacker_pos = (attacker.row, attacker.col)
            defender_pos = (self.ghost_row, self.ghost_col)
            defender_facing = self.ghost_facing
        
        from engine.fov import get_fov_layer
        
        # Calculate where attacker is in defender's FOV
        print(f"\n[FOV RECALC] Attacker: {attacker.name} {attacker_pos} | Defender: {defender.name} {defender_pos} facing {defender_facing}°")
        
        layer = get_fov_layer(
            defender_facing,
            defender_pos,
            attacker_pos
        )
        
        print(f"[FOV RECALC] Attacker is in defender's {layer}")
        
        self._fov_cache = layer
    
    def _get_defender_combat_tile(self, defender: Player) -> Tuple[int, int]:
        """Return defender tile used for combat resolution.
        
        Currently uses live row/col; later can be switched to ghost/snapshot data
        without touching combat math in multiple places.
        """
        return (defender.row, defender.col)
    
    def _get_effective_player(self, player: Player) -> Player:
        """Create a shallow copy of player with status effect stat debuffs applied.
        
        Maps effect types to target stats per spec:
        - 'slow': reduces speed and reaction (movement/reaction speed reduction)
        - 'freeze': reduces defense (ice-based stat reduction)
        
        Returns a new Player instance with modified stats; original is unchanged.
        """
        # Get active effects for this player
        effects = self.active_effects.get(player.name, [])
        if not effects:
            return player  # No effects, return original
        
        # Get aggregated debuffs by effect type (already handles stacking)
        debuffs = self.effects_engine.get_stat_debuffs(effects)
        if not debuffs:
            return player  # No stat debuffs, return original
        
        # Create shallow copy to avoid mutating original player
        import copy
        effective_player = copy.copy(player)
        
        # Map effect types to target stats and apply debuffs
        # Per spec: stat_debuff category uses "flat additive" reduction on 0-100 scale
        for effect_type, total_magnitude in debuffs.items():
            if effect_type == 'slow':
                # Slow: reduce speed and reaction
                effective_player.speed = max(0, effective_player.speed - total_magnitude)
                effective_player.reaction = max(0, effective_player.reaction - total_magnitude)
                print(f"[EFFECTIVE STATS] {player.name}: slow debuff -{total_magnitude} → speed {player.speed}→{effective_player.speed}, reaction {player.reaction}→{effective_player.reaction}")
            elif effect_type == 'freeze':
                # Freeze: reduce defense
                effective_player.defense = max(0, effective_player.defense - total_magnitude)
                print(f"[EFFECTIVE STATS] {player.name}: freeze debuff -{total_magnitude} → defense {player.defense}→{effective_player.defense}")
            # Unknown effect types with stat_debuff category are ignored (no assumptions)
        
        return effective_player

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
        # Get DF alloys from pending_attack (if available)
        attacker_df_alloys = set()
        defender_df_alloys = set()
        if hasattr(self, 'pending_attack') and self.pending_attack:
            attacker_df_alloys = self.pending_attack.get('attacker_df_alloys', set())
            defender_df_alloys = self.pending_attack.get('defender_df_alloys', set())
        
        # FOV Hit Bonus for Attacker (Rule Update9.md Part II)
        # Calculate after defender rotations have been applied
        from engine.fov import get_fov_hit_bonus
        fov_hit_bonus = get_fov_hit_bonus(
            defender.facing,
            (defender.row, defender.col),
            (attacker.row, attacker.col)
        )
        
        hit_chance = calculate_hit_chance(
            attacker, defender, attack_type, defense_type,
            facing_bonus, bounce_bonus, pattern_hit,
            df_multipliers, haki_obs_eff_attacker, haki_obs_eff_defender,
            is_defense_phase=True,
            attacker_df_alloys=attacker_df_alloys,
            defender_df_alloys=defender_df_alloys,
            fov_hit_bonus=fov_hit_bonus
        )
        
        # Calculate stamina cost
        base_cost = self.get_movement_cost(max(0, len(self.current_path) - 1))
        defender_stunned = getattr(defender, 'stunned', False)
        
        # FOV Defense Stamina Modifier (Rule Update9.md Part II)
        from engine.fov import get_fov_layer
        defender_fov_layer = get_fov_layer(defender.facing, (defender.row, defender.col), (attacker.row, attacker.col))
        is_movement = len(self.current_path) > 1  # Movement if path has more than just starting position
        
        stamina_cost = calculate_defense_stamina_cost(
            base_cost, hit_chance, def_obs_active, defender_stunned,
            defender_fov_layer=defender_fov_layer,
            is_movement=is_movement
        )
        
        # Clear stunned status after applying it once per spec 9.2
        if defender_stunned:
            defender.stunned = False
            self.battle_log.append(f"{defender.name} Stunned status removed (applied to this defense)")
        
        if defender.stamina < stamina_cost:
            self.battle_log.append(f"Defense failed: insufficient stamina (need {stamina_cost})")
            return {"error": "insufficient stamina", "cost": stamina_cost}
        
        defender.stamina -= stamina_cost
        self.battle_log.append(f"Defense {defense_type}: stamina cost {stamina_cost}")
        
        # Apply status effect stat modifications
        effective_attacker = self._get_effective_player(attacker)
        effective_defender = self._get_effective_player(defender)
        
        # Resolve defense type
        result = {"defense": defense_type, "stamina_cost": stamina_cost, "hit_chance": hit_chance}
        
        if defense_type == "tank":
            # Tank: take full damage, gain +30 stamina
            damage = calculate_damage(
                effective_attacker, effective_defender, base_damage, attack_type, None,
                facing_bonus, bounce_bonus, pattern_dmg,
                df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                is_defense_phase=False,
                attacker_df_alloys=attacker_df_alloys,
                defender_df_alloys=defender_df_alloys
            )
            defender.health = max(0, defender.health - damage)
            defender.stamina = min(defender.stamina + 30, defender.max_stamina)
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
                    effective_attacker, effective_defender, base_damage, attack_type, defense_type,
                    facing_bonus, bounce_bonus, pattern_dmg,
                    df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                    is_defense_phase=True,
                    attacker_df_alloys=attacker_df_alloys,
                    defender_df_alloys=defender_df_alloys
                )
                defender.health = max(0, defender.health - damage)
                self.battle_log.append(f"Evade: dodge failed, took {damage} damage")
                result["dodged"] = False
                result["damage"] = damage
        
        elif defense_type == "defend":
            # Defend: always take reduced damage
            damage = calculate_damage(
                effective_attacker, effective_defender, base_damage, attack_type, defense_type,
                facing_bonus, bounce_bonus, pattern_dmg,
                df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                is_defense_phase=True,
                attacker_df_alloys=attacker_df_alloys,
                defender_df_alloys=defender_df_alloys
            )
            defender.health = max(0, defender.health - damage)
            self.battle_log.append(f"Defend: took {damage} reduced damage")
            result["damage"] = damage
        
        elif defense_type == "counter":
            # Counter: take damage first, then trigger counter-attack if alive
            damage = calculate_damage(
                effective_attacker, effective_defender, base_damage, attack_type, defense_type,
                facing_bonus, bounce_bonus, pattern_dmg,
                df_multipliers, haki_arm_eff_attacker, haki_arm_eff_defender,
                is_defense_phase=True,
                attacker_df_alloys=attacker_df_alloys,
                defender_df_alloys=defender_df_alloys
            )
            defender.health = max(0, defender.health - damage)
            self.battle_log.append(f"Counter: took {damage} damage")
            result["damage"] = damage
            
            if defender.health > 0:
                # Trigger counter-attack per spec 14.3: counter has attack pattern and damages walls
                # Counter uses Normal pattern (3×2 base) regardless of counter type
                counter_tiles = self._compute_counter_attack_pattern(defender, defense_type)
                counter_base_damage = 10  # Wall damage base for counter (spec 11.2)
                
                # FOV Counter Success Modifier (Rule Update9.md Part II)
                from engine.fov import get_fov_layer
                defender_fov_layer = get_fov_layer(defender.facing, (defender.row, defender.col), (attacker.row, attacker.col))
                counter_success_multiplier = 1.0
                if defender_fov_layer == "Behind":
                    # Attacker behind defender: -20% counter success
                    counter_success_multiplier = 0.80
                    print(f"[FOV COUNTER PENALTY] Attacker behind defender: counter success × 0.80")
                
                # Observation Haki Counter Bonus (Rule Update9.md Part IV)
                if defender_haki_obs_effectiveness > 0.0:
                    # Defender Observation Haki active: +20% counter success
                    counter_success_multiplier += 0.20
                    print(f"[OBSERVATION HAKI COUNTER BONUS] Defender Obs Haki: counter success +0.20 (total: {counter_success_multiplier})")
                
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
                
                # Apply wall damage from counter (same formula as attack)
                strength_mult = 1.0 + (defender.strength / 400.0)
                counter_wall_damage = int(counter_base_damage * (1.0 + counter_facing_bonus + counter_bounce_bonus + counter_pattern_dmg) * strength_mult)
                print(f"DEBUG COUNTER WALL: base={counter_base_damage}, bonuses: face={counter_facing_bonus}, bounce={counter_bounce_bonus}, ptt={counter_pattern_dmg}, str_mult={strength_mult}, final={counter_wall_damage}")
                # Temporarily swap context for wall damage
                temp_attacker_flag = self.attacker_is_p1
                self.attacker_is_p1 = not self.attacker_is_p1
                counter_breakthrough_tiles_damage = self._apply_wall_damage_to_pattern(counter_tiles, counter_wall_damage, defender.row, defender.col)
                self.attacker_is_p1 = temp_attacker_flag
                
                # Counter player hit & damage calculation (defender counter-attacks attacker)
                import random
                counter_hit_chance = calculate_hit_chance(
                    effective_defender, effective_attacker, "normal", None,
                    counter_facing_bonus, counter_bounce_bonus, 0.0,
                    None, 0.0, 0.0,
                    is_defense_phase=False,
                    attacker_df_alloys=defender_df_alloys,  # Defender is counter-attacker
                    defender_df_alloys=attacker_df_alloys  # Attacker becomes defender
                )
                hit_roll = random.random()
                hit_success = hit_roll <= counter_hit_chance
                print(f"DEBUG COUNTER HIT: chance={counter_hit_chance:.3f}, roll={hit_roll:.3f}, success={hit_success}")

                counter_damage = 0
                if hit_success:
                    # Apply FOV counter success multiplier to base damage
                    counter_base_dmg_modified = int(10 * counter_success_multiplier)
                    counter_damage = calculate_damage(
                        effective_defender, effective_attacker, counter_base_dmg_modified, "normal", "counter",
                        0.0, 0.0, 0.0,
                        None, haki_arm_eff_defender, haki_arm_eff_attacker,
                        is_defense_phase=True,
                        attacker_df_alloys=defender_df_alloys,  # Defender is counter-attacker
                        defender_df_alloys=attacker_df_alloys  # Attacker becomes defender
                    )
                    
                    # Check for breakthrough damage on counter
                    attacker_tile = (attacker.row, attacker.col)
                    if attacker_tile in counter_breakthrough_tiles_damage:
                        passthrough_dmg = counter_breakthrough_tiles_damage[attacker_tile]
                        print(f"DEBUG COUNTER BREAKTHROUGH: Attacker at {attacker_tile} - applying breakthrough damage")
                        print(f"DEBUG COUNTER BREAKTHROUGH: Original counter_damage={counter_damage}, passthrough={passthrough_dmg}")
                        # Recalculate with breakthrough base damage (also apply counter success multiplier)
                        breakthrough_base_modified = int(passthrough_dmg * counter_success_multiplier)
                        counter_damage_breakthrough = calculate_damage(
                            effective_defender, effective_attacker, breakthrough_base_modified, "normal", "counter",
                            0.0, 0.0, 0.0,
                            None, haki_arm_eff_defender, haki_arm_eff_attacker,
                            is_defense_phase=True,
                            attacker_df_alloys=defender_df_alloys,  # Defender is counter-attacker
                            defender_df_alloys=attacker_df_alloys  # Attacker becomes defender
                        )
                        counter_damage = max(0, int(counter_damage_breakthrough))
                        print(f"DEBUG COUNTER BREAKTHROUGH: Final breakthrough counter_damage={counter_damage}")
                        self.battle_log.append(f"Counter Breakthrough! Wall destroyed, reduced damage: {counter_damage}")
                else:
                    self.battle_log.append("Counter-attack missed due to hit chance roll")
                
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
        """Returns current pattern detection status."""
        return {
            "active": self.pattern_active_bonus or None,
            "applied_this_phase": self.pattern_applied_this_phase
        }

    def clear_pattern_memory(self) -> None:
        """Legacy method - now clears pattern_active_bonus instead."""
        self.pattern_active_bonus = None
        self.battle_log.append("Pattern cleared")

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

                # If no first tile selected yet, show only tiles that have at least one valid adjacent endpoint
                if self.wall_first_tile is None:
                    for row in range(7):
                        for col in range(7):
                            distance = abs(row - player_pos[0]) + abs(col - player_pos[1])
                            if distance > placement_range:
                                continue

                            # Check if this tile has at least one orthogonally adjacent neighbor that can form a wall
                            has_valid_neighbor = False
                            for d_row, d_col in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                                nr = row + d_row
                                nc = col + d_col
                                # Skip out-of-bounds
                                if nr < 0 or nr >= 7 or nc < 0 or nc >= 7:
                                    continue

                                # Neighbor also must be within placement range
                                neighbor_distance = abs(nr - player_pos[0]) + abs(nc - player_pos[1])
                                if neighbor_distance > placement_range:
                                    continue

                                # Determine wall coordinates between this tile and neighbor
                                if nr == row:
                                    # Vertical wall between columns
                                    orientation = 'v'
                                    wall_row = row
                                    wall_col = min(col, nc)
                                else:
                                    # Horizontal wall between rows
                                    orientation = 'h'
                                    wall_row = min(row, nr)
                                    wall_col = col

                                # Valid neighbor if there is no wall (internal or border) between tiles
                                if not self.wall_system.has_wall_at(wall_row, wall_col, orientation):
                                    has_valid_neighbor = True
                                    break

                            if has_valid_neighbor:
                                wall_placement_tiles.append((row, col))
                else:
                    # After first tile is selected, only show orthogonally adjacent, buildable neighbors
                    base_row, base_col = self.wall_first_tile
                    for d_row, d_col in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr = base_row + d_row
                        nc = base_col + d_col
                        # Skip out-of-bounds
                        if nr < 0 or nr >= 7 or nc < 0 or nc >= 7:
                            continue

                        # Respect wall placement range from player/ghost position
                        distance = abs(nr - player_pos[0]) + abs(nc - player_pos[1])
                        if distance > placement_range:
                            continue

                        # Determine wall coordinates between base tile and neighbor
                        if nr == base_row:
                            # Vertical wall between columns
                            orientation = 'v'
                            wall_row = base_row
                            wall_col = min(base_col, nc)
                        else:
                            # Horizontal wall between rows
                            orientation = 'h'
                            wall_row = min(base_row, nr)
                            wall_col = base_col

                        # Only mark neighbor as available if no wall (internal or border) exists between them
                        if not self.wall_system.has_wall_at(wall_row, wall_col, orientation):
                            wall_placement_tiles.append((nr, nc))
        
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
        self.pattern_applied_this_phase = False
        self.active_effects[self.player1.name] = []
        self.active_effects[self.player2.name] = []
        # Recreate walls/tiles and apply configs
        self.wall_system = WallSystem()
        self.wall_system.spawn_initial_walls(self.avg_primary_sum)
        self.tile_system = TileSystem()
        # Pass player positions to avoid spawning tiles on them
        player_positions = [(self.player1.row, self.player1.col), (self.player2.row, self.player2.col)]
        self.tile_system.spawn_initial_tiles(self.avg_primary_sum, player_positions)
        self.reload_configs()
        self.battle_log.clear()
        self.battle_log.append('Battle restarted')

    def reset_map_for_multiplayer(self, map_init: Optional[Dict[str, Any]] = None) -> None:
        """Reset wall/tile systems for multiplayer and apply server-authoritative map.

        - Recomputes avg_primary_sum from current player stats (after MP presets applied).
        - Recreates WallSystem/TileSystem without local random spawns.
        - Applies server-provided walls, tiles, and sea tiles.
        - In MP, local per-turn tile spawns should be disabled via use_local_tile_spawns.
        """
        print("[MP MAP INIT] reset_map_for_multiplayer called")
        
        # Recompute average primary sum from current stats
        self.avg_primary_sum = (
            self.player1.strength + self.player1.defense +
            self.player2.strength + self.player2.defense
        ) / 2.0

        # Recreate walls/tiles (border walls only; no internal random spawns)
        self.wall_system = WallSystem()
        self.tile_system = TileSystem()
        print(f"[MP MAP INIT] WallSystem and TileSystem recreated (empty except borders)")

        # Apply server-provided map layout when available
        if not map_init:
            print("[MP MAP INIT] No map_init provided, skipping spawn application")
            return

        # Apply WALLS from server
        walls = map_init.get("walls") or []
        print(f"[MP MAP INIT] Applying {len(walls)} walls from server")
        for wall_entry in walls:
            try:
                row = int(wall_entry.get("row"))
                col = int(wall_entry.get("col"))
                orientation = wall_entry.get("orientation")
                tier = wall_entry.get("tier")
                if orientation not in ['h', 'v'] or tier not in ['fragile', 'standard', 'reinforced']:
                    continue
                # Calculate HP using same formula as server would
                base_hps = {'fragile': 100, 'standard': 150, 'reinforced': 200}
                base_hp = base_hps.get(tier, 100)
                hp = int(base_hp * (1 + self.avg_primary_sum / 400))
                # Add wall directly to system
                from engine.walls import Wall
                self.wall_system._walls.append(Wall(row, col, orientation, tier, hp, creator=None))
                print(f"[MP MAP INIT]   Wall added: ({row},{col},{orientation}) tier={tier} hp={hp}")
            except Exception as e:
                print(f"[MP MAP INIT]   Failed to add wall {wall_entry}: {e}")
                continue

        # Apply TILES from server
        tiles = map_init.get("tiles") or []
        print(f"[MP MAP INIT] Applying {len(tiles)} tiles from server")
        for entry in tiles:
            try:
                r = int(entry.get("row"))
                c = int(entry.get("col"))
                tile_type = entry.get("tile_type") or entry.get("type")
                if tile_type is None:
                    continue
            except Exception as e:
                print(f"[MP MAP INIT]   Failed to parse tile {entry}: {e}")
                continue
            base_hp = int(100 + self.avg_primary_sum * 0.5)
            if tile_type == 'unpassable':
                hp = float('inf')
                duration = None
            else:
                hp = base_hp
                duration = entry.get("duration")  # Use server-provided duration
            try:
                from engine.tiles import Tile
                self.tile_system._tiles[(r, c)] = Tile(r, c, tile_type, hp, duration)
                print(f"[MP MAP INIT]   Tile added: ({r},{c}) type={tile_type} hp={hp} dur={duration}")
            except Exception as e:
                print(f"[MP MAP INIT]   Failed to add tile {entry}: {e}")
                continue

        # Apply SEA TILES from server
        sea_tiles = map_init.get("sea_tiles") or []
        print(f"[MP MAP INIT] Applying {len(sea_tiles)} sea tiles from server")
        for st in sea_tiles:
            try:
                edge = st.get("edge")
                pos = int(st.get("position"))
            except Exception as e:
                print(f"[MP MAP INIT]   Failed to parse sea tile {st}: {e}")
                continue
            try:
                from engine.tiles import SeaTile
                self.tile_system._sea_tiles.append(SeaTile(edge, pos))
                print(f"[MP MAP INIT]   Sea tile added: edge={edge} pos={pos}")
            except Exception as e:
                print(f"[MP MAP INIT]   Failed to add sea tile {st}: {e}")
                continue
        
        print(f"[MP MAP INIT] Map initialization complete: {len(self.wall_system._walls)} walls, {len(self.tile_system._tiles)} tiles, {len(self.tile_system._sea_tiles)} sea tiles")

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
    def apply_completed_animations(self, completed_anims: List) -> None:
        """Apply state changes from completed animations to player objects."""
        if not completed_anims:
            return
        
        for anim in completed_anims:
            player_id = anim.player_id
            player = self.player1 if player_id == "player1" else self.player2
            
            if anim.anim_type == "movement":
                # Update position to animation's destination
                to_row = anim.params.get("to_row")
                to_col = anim.params.get("to_col")
                if to_row is not None and to_col is not None:
                    player.row = int(to_row)
                    player.col = int(to_col)
                    
            elif anim.anim_type == "push":
                # Update position to animation's destination (tile effects already applied during combat)
                to_row = anim.params.get("to_row")
                to_col = anim.params.get("to_col")
                if to_row is not None and to_col is not None:
                    player.row = int(to_row)
                    player.col = int(to_col)
                    
            elif anim.anim_type == "rotation":
                # Update facing to animation's destination
                to_facing = anim.params.get("to_facing")
                if to_facing is not None:
                    player.facing = int(to_facing) % 360
    
    def check_animation_completion(self) -> None:
        """Finalize any pending game-over state after animations complete."""
        # If there is a pending doom-based game over and no animations are playing, apply it
        if getattr(self, "pending_game_over", None) and not self.animation_system.is_playing():
            if self.game_active:
                self.game_active = False
                self.winner = self.pending_game_over
                self.battle_log.append(f"Winner: {self.winner}")
            self.pending_game_over = None

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
    def apply_completed_animations(self, completed_anims: List) -> None:
        """Apply state changes from completed animations to player objects."""
        if not completed_anims:
            return
        
        for anim in completed_anims:
            player_id = anim.player_id
            player = self.player1 if player_id == "player1" else self.player2
            
            if anim.anim_type == "movement":
                # Update position to animation's destination
                to_row = anim.params.get("to_row")
                to_col = anim.params.get("to_col")
                if to_row is not None and to_col is not None:
                    player.row = int(to_row)
                    player.col = int(to_col)
                    
            elif anim.anim_type == "push":
                # Update position to animation's destination (tile effects already applied during combat)
                to_row = anim.params.get("to_row")
                to_col = anim.params.get("to_col")
                if to_row is not None and to_col is not None:
                    player.row = int(to_row)
                    player.col = int(to_col)
                    
            elif anim.anim_type == "rotation":
                # Update facing to animation's destination
                to_facing = anim.params.get("to_facing")
                if to_facing is not None:
                    player.facing = int(to_facing) % 360
    
    def check_animation_completion(self) -> None:
        """Finalize any pending game-over state after animations complete."""
        # If there is a pending doom-based game over and no animations are playing, apply it
        if getattr(self, "pending_game_over", None) and not self.animation_system.is_playing():
            if self.game_active:
                self.game_active = False
                self.winner = self.pending_game_over
                self.battle_log.append(f"Winner: {self.winner}")
            self.pending_game_over = None

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
        with open(path, 'r', encoding='utf-8') as f:
            devils = json.load(f)
        self.validate_devils(devils)
