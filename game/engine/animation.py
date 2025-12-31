# Animation system for battle actions
# Handles queuing and playback of movement, rotation, attack, and defense animations

from typing import List, Dict, Any, Optional, Tuple

class AnimationEntry:
    """Single animation action entry."""
    def __init__(self, anim_type: str, player_id: str, params: dict):
        self.anim_type = anim_type  # "movement", "rotation", "attack", "defense"
        self.player_id = player_id  # "player1" or "player2"
        self.params = params  # Animation-specific parameters
        self.completed = False


class AnimationSystem:
    """Manages animation queue and playback for battle actions."""
    
    def __init__(self):
        self.animation_queue: List[AnimationEntry] = []
        self.animations_playing = False
        self.current_phase_animations: List[AnimationEntry] = []  # Stored between phases
        # Pattern flash system - simple on/off state
        self.current_flash_pattern = []  # List of (row, col) tuples currently being flashed
        self.flash_visible = False  # Whether flash is currently visible
        # Track when animation playback started for timing calculations
        self.playback_start_time = 0.0
    
    def build_movement_animations(self, path: List[Tuple[int, int]], player_id: str, speed_multiplier: float = 1.0) -> List[AnimationEntry]:
        """Build movement animations from path."""
        animations = []
        if len(path) > 1:
            from_pos = path[0]
            for i in range(1, len(path)):
                to_pos = path[i]
                animations.append(AnimationEntry(
                    "movement",
                    player_id,
                    {
                        "from_row": from_pos[0],
                        "from_col": from_pos[1],
                        "to_row": to_pos[0],
                        "to_col": to_pos[1],
                        "speed_multiplier": speed_multiplier,
                    }
                ))
                from_pos = to_pos
        return animations
    
    def build_rotation_animation(self, from_facing: float, to_facing: float, player_id: str, speed_multiplier: float = 1.0) -> AnimationEntry:
        """Build rotation animation."""
        return AnimationEntry(
            "rotation",
            player_id,
            {
                "from_facing": from_facing,
                "to_facing": to_facing,
                "speed_multiplier": speed_multiplier,
            }
        )
    
    def build_attack_animation(self, attack_type: str, damage_output: int, is_skip: bool, is_hit: bool, player_id: str, speed_multiplier: float) -> AnimationEntry:
        """Build attack animation with jump height based on damage."""
        return AnimationEntry(
            "attack",
            player_id,
            {
                "attack_type": attack_type,
                "damage_output": damage_output,
                "is_skip": is_skip,
                "is_hit": is_hit,
                "speed_multiplier": speed_multiplier
            }
        )
    
    def build_defense_animation(self, defense_type: str, player_id: str, from_row: int, from_col: int, from_facing: int, speed_multiplier: float) -> AnimationEntry:
        """Build defense animation."""
        return AnimationEntry(
            "defense",
            player_id,
            {
                "defense_type": defense_type,
                "from_row": from_row,
                "from_col": from_col,
                "from_facing": from_facing,
                "speed_multiplier": speed_multiplier
            }
        )
    
    def build_push_animation(self, from_row: int, from_col: int, to_row: int, to_col: int, player_id: str, distance: int) -> AnimationEntry:
        """Build push animation (slide without hop).
        
        Args:
            from_row: Starting row
            from_col: Starting column
            to_row: Ending row
            to_col: Ending column
            player_id: "player1" or "player2"
            distance: Number of tiles pushed
        
        Returns:
            AnimationEntry for push
        """
        return AnimationEntry(
            "push",
            player_id,
            {
                "from_row": from_row,
                "from_col": from_col,
                "to_row": to_row,
                "to_col": to_col,
                "distance": distance
            }
        )
    
    def build_flash_animation(self, pattern_tiles: List[Tuple[int, int]], speed_multiplier: float = 1.0) -> AnimationEntry:
        """Build a flash animation that displays attack pattern.
        
        Args:
            pattern_tiles: List of (row, col) tuples to flash
            speed_multiplier: Speed multiplier from bonuses (same as movement/rotation)
        
        Returns:
            AnimationEntry for flash
        """
        return AnimationEntry(
            "flash",
            "pattern",  # Not player-specific
            {
                "pattern": pattern_tiles,
                "speed_multiplier": speed_multiplier
            }
        )
    
    def build_combat_flash_animation(self, attacker_pattern: List[Tuple[int, int]], defender_pattern: List[Tuple[int, int]], attacker_speed: float, defender_speed: float) -> AnimationEntry:
        """Build a combat flash animation that alternates between attacker and defender patterns.
        
        This animation spans the entire duration of the combat attack/defense animations.
        Flashes alternate: attacker, defender, attacker, defender, attacker, defender (6 total if counter, 3 if no counter).
        
        Args:
            attacker_pattern: List of (row, col) tuples for attacker's attack pattern
            defender_pattern: List of (row, col) tuples for defender's counter pattern (empty list if no counter)
            attacker_speed: Speed multiplier for attacker (affects flash timing)
            defender_speed: Speed multiplier for defender (affects flash timing)
        
        Returns:
            AnimationEntry for combat flash sequence
        """
        return AnimationEntry(
            "combat_flash",
            "pattern",  # Not player-specific
            {
                "attacker_pattern": attacker_pattern,
                "defender_pattern": defender_pattern,
                "attacker_speed": attacker_speed,
                "defender_speed": defender_speed
            }
        )
    
    def build_doom_animation(self, player_id: str) -> AnimationEntry:
        """Build doom animation (sink/fade on sea tile).
        
        Args:
            player_id: "player1" or "player2"
        
        Returns:
            AnimationEntry for doom
        """
        return AnimationEntry(
            "doom",
            player_id,
            {}
        )
    
    def build_wall_creation_animation(self, row: int, col: int, orientation: str, start_time: float = 0.0) -> AnimationEntry:
        """Build wall creation animation (fade-in from invisible to visible).
        
        Args:
            row: Wall row position
            col: Wall column position
            orientation: 'h' or 'v'
            start_time: Offset in seconds before animation starts (for synchronization with movement)
        
        Returns:
            AnimationEntry for wall creation
        """
        return AnimationEntry(
            "wall_creation",
            "map_object",
            {
                "row": row,
                "col": col,
                "orientation": orientation,
                "start_time": start_time,
                "duration": 0.4  # 0.4 seconds fade-in
            }
        )
    
    def build_tile_creation_animation(self, row: int, col: int, tile_type: str, start_time: float = 0.0) -> AnimationEntry:
        """Build tile creation animation (fade-in from invisible to visible).
        
        Args:
            row: Tile row position
            col: Tile column position
            tile_type: Type of tile being created
            start_time: Offset in seconds before animation starts (for synchronization with movement)
        
        Returns:
            AnimationEntry for tile creation
        """
        return AnimationEntry(
            "tile_creation",
            "map_object",
            {
                "row": row,
                "col": col,
                "tile_type": tile_type,
                "start_time": start_time,
                "duration": 0.4  # 0.4 seconds fade-in
            }
        )
    
    def queue_animations(self, animations: List[AnimationEntry]) -> None:
        """Add animations to the queue as sequential single-animation groups."""
        for anim in animations:
            self.animation_queue.append([anim])
        # Auto-start playback if not already playing
        if self.animation_queue and not self.animations_playing:
            self.animations_playing = True

    def queue_concurrent_group(self, animations: List[AnimationEntry]) -> None:
        """Add a group of animations that should play concurrently."""
        if animations:
            self.animation_queue.append(animations)
            # Auto-start playback if not already playing
            if not self.animations_playing:
                self.animations_playing = True
    
    def store_for_next_phase(self, animations: List[AnimationEntry]) -> None:
        """Store animations to be played in next phase (attack -> defense transition)."""
        self.current_phase_animations = animations
    
    def get_stored_animations(self) -> List[AnimationEntry]:
        """Get and clear stored animations."""
        anims = self.current_phase_animations
        self.current_phase_animations = []
        return anims
    
    def group_consecutive_rotations(self, actions: List[Tuple[str, Any]]) -> List[Tuple[str, Any]]:
        """Group consecutive rotation actions into single rotations.
        
        Example:
            Input: [("move", pos1), ("rotate", 45), ("rotate", 45), ("rotate", -90), ("move", pos2)]
            Output: [("move", pos1), ("rotate", 0), ("move", pos2)]
        
        Args:
            actions: List of planned actions
        
        Returns:
            List with consecutive rotations grouped
        """
        if not actions:
            return []
        
        grouped = []
        i = 0
        
        while i < len(actions):
            action_type, action_data = actions[i]
            
            if action_type == "rotate":
                # Start accumulating rotations
                total_rotation = action_data
                j = i + 1
                
                # Find consecutive rotations
                while j < len(actions) and actions[j][0] == "rotate":
                    total_rotation += actions[j][1]
                    j += 1
                
                # Normalize to 0-360 range
                total_rotation = total_rotation % 360
                
                # Add grouped rotation
                grouped.append(("rotate", total_rotation))
                i = j
            else:
                # Not a rotation, add as-is
                grouped.append((action_type, action_data))
                i += 1
        
        return grouped
    
    def pair_rotations_with_movements(self, actions: List[Tuple[str, Any]]) -> List[Dict[str, Any]]:
        """Pair rotations with their successor movements for concurrent animation.
        
        Rules:
        - A rotation pairs with the NEXT movement (never previous)
        - If rotation has no successor movement, it's standalone
        - Multiple rotations should be grouped first (use group_consecutive_rotations)
        
        Args:
            actions: List of actions (should be pre-grouped)
        
        Returns:
            List of animation commands with pairing info
        """
        if not actions:
            return []
        
        paired = []
        i = 0
        
        while i < len(actions):
            action_type, action_data = actions[i]
            
            if action_type == "rotate":
                # Check if next action is a movement
                if i + 1 < len(actions) and actions[i + 1][0] == "move":
                    # Pair rotation with next movement
                    next_move = actions[i + 1]
                    paired.append({
                        "type": "paired_move_rotate",
                        "move_data": next_move[1],
                        "rotation": action_data
                    })
                    i += 2  # Skip both rotation and movement
                else:
                    # Standalone rotation
                    paired.append({
                        "type": "rotation",
                        "rotation": action_data
                    })
                    i += 1
            elif action_type == "move":
                # Unpaired movement
                paired.append({
                    "type": "movement",
                    "move_data": action_data
                })
                i += 1
            else:
                # Other action types (attack, defense)
                paired.append({
                    "type": action_type,
                    "data": action_data
                })
                i += 1
        
        return paired
    
    def start_playback(self) -> bool:
        """Start animation playback. Returns True if animations started."""
        if not self.animation_queue:
            return False
        self.animations_playing = True
        # Record start time for timing calculations
        import time
        self.playback_start_time = time.time()
        return True
    
    def is_playing(self) -> bool:
        """Check if animations are currently playing."""
        return self.animations_playing
    
    def get_current_animation(self) -> Optional[AnimationEntry]:
        """Get the first animation in the current group (for backwards compatibility)."""
        if self.animation_queue and self.animation_queue[0]:
            return self.animation_queue[0][0]
        return None
    
    def get_current_group(self) -> List[AnimationEntry]:
        """Get the list of animations in the current group."""
        if self.animation_queue:
            return self.animation_queue[0]
        return []
    
    def mark_current_complete(self) -> List[AnimationEntry]:
        """Mark current animation as complete and advance queue. Returns completed animation group."""
        if not self.animation_queue:
            self.animations_playing = False
            return []
        
        # Get completed animation group before removing
        completed_group = self.animation_queue[0]
        
        # Remove completed animation
        self.animation_queue.pop(0)
        
        # Check if more animations remain
        if not self.animation_queue:
            self.animations_playing = False
        
        return completed_group
    
    def clear_all(self) -> None:
        """Clear all queued and stored animations."""
        self.animation_queue = []
        self.current_phase_animations = []
        self.animations_playing = False
        # Clear flash state
        self.current_flash_pattern = []
        self.flash_visible = False
    
    def get_animation_duration(self, anim: AnimationEntry) -> float:
        """Get duration in seconds for an animation type."""
        if anim.anim_type == "movement":
            base_duration = 0.4  # 400ms per tile hop
            speed_multiplier = anim.params.get("speed_multiplier", 1.0) or 1.0
            return base_duration / speed_multiplier
        elif anim.anim_type == "rotation":
            # Fixed duration for all rotations (for pairing with movements)
            base_duration = 0.4  # Same as movement
            speed_multiplier = anim.params.get("speed_multiplier", 1.0) or 1.0
            return base_duration / speed_multiplier
        elif anim.anim_type == "attack":
            speed_multiplier = anim.params.get("speed_multiplier", 1.0) or 1.0
            if anim.params.get("is_skip"):
                base_duration = 0.3  # Quick reverse jump
            else:
                # Scale with damage output
                damage = anim.params.get("damage_output", 20)
                base_duration = 0.4
                # Higher damage = longer jump
                damage_factor = damage / 20.0  # Normalize to base
                base_duration = base_duration * (0.8 + 0.4 * damage_factor)  # 0.8x to 1.2x duration
            return base_duration / speed_multiplier
        elif anim.anim_type == "defense":
            speed_multiplier = anim.params.get("speed_multiplier", 1.0) or 1.0
            defense_type = anim.params.get("defense_type")
            if defense_type == "defend":
                base_duration = 1.2  # 6 rotations * 0.2s each
            elif defense_type == "evade":
                base_duration = 1.2  # 6 shakes * 0.2s each
            elif defense_type == "tank":
                base_duration = 0.3  # Quick reverse jump like skip
            elif defense_type == "counter":
                base_duration = 0.5  # Attack-style jump
            else:
                base_duration = 0.5
            return base_duration / speed_multiplier
        elif anim.anim_type == "push":
            # 0.3s per tile pushed
            distance = anim.params.get("distance", 1)
            return 0.3 * distance
        elif anim.anim_type == "doom":
            return 1.0  # 1 second sink/fade
        elif anim.anim_type == "flash":
            # Flash uses same base duration as movement/rotation: 0.4s / speed_multiplier
            base_duration = 0.4
            speed_multiplier = anim.params.get("speed_multiplier", 1.0) or 1.0
            return base_duration / speed_multiplier
        elif anim.anim_type == "combat_flash":
            # Combat flash: runs concurrently with attack/defense animations
            # Return 0.0 so it doesn't affect the group's max duration
            # The flashes will cycle during whatever time the combat animations take
            return 0.0
        
        return 0.5  # Default duration
