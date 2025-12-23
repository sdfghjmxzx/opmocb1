"""Tile system - Phase 4: Spawn mechanics, interaction matrix, Sea Tiles."""

from typing import List, Tuple, Optional, Dict, Any
import random

# Runtime-configurable tile parameters (defaults)
CONFIG: Dict[str, Any] = {
    'initial_spawn_chance': {
        'unpassable': 0.02,
        'trap_continuous': 0.02,
        'trap_momentary': 0.02,
        'drop_continuous': 0.02,
        'drop_momentary': 0.02,
    },
    'sea_initial_chance': 0.2,
    'per_turn_spawn': {
        'trap_continuous': {'chance': 0.01, 'cap': 1},
        'trap_momentary': {'chance': 0.01, 'cap': 1},
        'drop_continuous': {'chance': 0.01, 'cap': None},
        'drop_momentary': {'chance': 0.01, 'cap': 1},
    },
    'base_hp_formula': {'base': 100, 'scale': 0.5},
}

def set_config(cfg: Dict[str, Any]) -> None:
    """Set tile CONFIG from JSON at runtime (safe overrides)."""
    if not isinstance(cfg, dict):
        return
    if 'initial_spawn_chance' in cfg and isinstance(cfg['initial_spawn_chance'], dict):
        CONFIG['initial_spawn_chance'].update({k: float(v) for k, v in cfg['initial_spawn_chance'].items() if isinstance(v, (int, float))})
    if 'sea_initial_chance' in cfg and isinstance(cfg['sea_initial_chance'], (int, float)):
        CONFIG['sea_initial_chance'] = float(cfg['sea_initial_chance'])
    if 'per_turn_spawn' in cfg and isinstance(cfg['per_turn_spawn'], dict):
        for k, v in cfg['per_turn_spawn'].items():
            if isinstance(v, dict):
                dest = CONFIG['per_turn_spawn'].setdefault(k, {})
                if 'chance' in v and isinstance(v['chance'], (int, float)):
                    dest['chance'] = float(v['chance'])
                if 'cap' in v and (isinstance(v['cap'], int) or v['cap'] is None):
                    dest['cap'] = v['cap']
    if 'base_hp_formula' in cfg and isinstance(cfg['base_hp_formula'], dict):
        base = cfg['base_hp_formula'].get('base')
        scale = cfg['base_hp_formula'].get('scale')
        if isinstance(base, (int, float)):
            CONFIG['base_hp_formula']['base'] = float(base)
        if isinstance(scale, (int, float)):
            CONFIG['base_hp_formula']['scale'] = float(scale)

class Tile:
    """Represents a special tile on the battlefield."""
    def __init__(self, row: int, col: int, tile_type: str, hp: float, duration: Optional[int] = None):
        self.row = row
        self.col = col
        self.tile_type = tile_type  # 'unpassable', 'trap_continuous', 'trap_momentary', 'drop_continuous', 'drop_momentary'
        # Handle infinity HP for unpassable tiles
        if hp == float('inf'):
            self.max_hp = float('inf')
            self.hp = float('inf')
        else:
            self.max_hp = int(hp)
            self.hp = int(hp)
        self.duration = duration  # For momentary tiles (turns remaining)
        self.destructible = tile_type != 'unpassable'
    
    def take_damage(self, damage: int) -> bool:
        """Apply damage to tile. Returns True if tile is destroyed."""
        if not self.destructible:
            return False
        self.hp -= damage
        return self.hp <= 0
    
    def tick_duration(self) -> bool:
        """Decrement duration. Returns True if tile expired."""
        if self.duration is not None:
            self.duration -= 1
            return self.duration <= 0
        return False

class SeaTile:
    """Represents a Sea Tile (edge-based doom mechanic)."""
    def __init__(self, edge: str, position: int):
        self.edge = edge  # 'north', 'south', 'east', 'west'
        self.position = position  # Column (for N/S) or row (for E/W)

class TileSystem:
    """Manages special tiles, spawn mechanics, and Sea Tiles per spec sections 19-23."""
    
    def __init__(self):
        self._tiles: Dict[Tuple[int, int], Tile] = {}  # (row, col) -> Tile
        self._sea_tiles: List[SeaTile] = []
    
    def set_config(self, cfg: Dict[str, Any]) -> None:
        """Apply runtime tile config."""
        try:
            set_config(cfg)
        except Exception:
            pass

    def spawn_initial_tiles(self, avg_primary_sum: float) -> None:
        """Spawn tiles at battle start per spec 19.2."""
        # Tile HP: base + (AvgPlayerPrimarySum × scale)
        base_hp = int(CONFIG.get('base_hp_formula', {}).get('base', 100) + avg_primary_sum * CONFIG.get('base_hp_formula', {}).get('scale', 0.5))
        
        # For testing: guarantee at least 1-2 tiles spawn
        # 2% chance for each type (except Sea Tiles which are 20%)
        tile_types = [
            ('unpassable', CONFIG['initial_spawn_chance'].get('unpassable', 0.02), float('inf'), None),
            ('trap_continuous', CONFIG['initial_spawn_chance'].get('trap_continuous', 0.02), base_hp, None),
            ('trap_momentary', CONFIG['initial_spawn_chance'].get('trap_momentary', 0.02), base_hp, random.randint(1, 3)),
            ('drop_continuous', CONFIG['initial_spawn_chance'].get('drop_continuous', 0.02), base_hp, None),
            ('drop_momentary', CONFIG['initial_spawn_chance'].get('drop_momentary', 0.02), base_hp, random.randint(1, 3))
        ]
        
        spawned_count = 0
        for tile_type, spawn_chance, hp, duration in tile_types:
            # Increase spawn chance for testing OR force spawn if nothing spawned yet
            if random.random() < spawn_chance or (spawned_count == 0 and tile_type == 'unpassable'):
                # Find empty square
                attempts = 0
                while attempts < 20:
                    row = random.randint(0, 6)
                    col = random.randint(0, 6)
                    # Avoid player starting positions
                    if (row, col) == (5, 3) or (row, col) == (1, 3):
                        attempts += 1
                        continue
                    if (row, col) not in self._tiles:
                        # Pass hp as-is (can be float('inf') for unpassable)
                        self._tiles[(row, col)] = Tile(row, col, tile_type, hp, duration)
                        spawned_count += 1
                        break
                    attempts += 1
        
        # Sea Tiles: 20% chance at battle start
        if random.random() < CONFIG.get('sea_initial_chance', 0.20):
            self._spawn_sea_tiles()
    
    def _spawn_sea_tiles(self) -> None:
        """Spawn Sea Tiles at edges per spec 21.1."""
        edges = ['north', 'south', 'east', 'west']
        for edge in edges:
            # 1-4 groups per edge
            group_count = random.randint(1, 4)
            for _ in range(group_count):
                # Each group: 4-7 contiguous tiles
                group_size = random.randint(4, 7)
                if edge in ['north', 'south']:
                    start_col = random.randint(0, max(0, 7 - group_size))
                    for i in range(group_size):
                        self._sea_tiles.append(SeaTile(edge, start_col + i))
                else:  # east, west
                    start_row = random.randint(0, max(0, 7 - group_size))
                    for i in range(group_size):
                        self._sea_tiles.append(SeaTile(edge, start_row + i))
        
        # Corner rule: if corner has both edges, add third corner tile
        self._create_corner_sea_tiles()
    
    def _create_corner_sea_tiles(self) -> None:
        """Create corner sea tiles where both adjacent edges have sea tiles."""
        # Check all 4 corners: (north,west), (north,east), (south,west), (south,east)
        corners = [
            (0, 0, 'north', 'west'),   # NW corner
            (0, 6, 'north', 'east'),   # NE corner
            (6, 0, 'south', 'west'),   # SW corner
            (6, 6, 'south', 'east')    # SE corner
        ]
        
        for row, col, edge1, edge2 in corners:
            has_edge1 = False
            has_edge2 = False
            
            for st in self._sea_tiles:
                # Check if edge1 has tile at corner
                if st.edge == edge1:
                    if edge1 in ['north', 'south'] and st.position == col:
                        has_edge1 = True
                    elif edge1 in ['east', 'west'] and st.position == row:
                        has_edge1 = True
                
                # Check if edge2 has tile at corner
                if st.edge == edge2:
                    if edge2 in ['north', 'south'] and st.position == col:
                        has_edge2 = True
                    elif edge2 in ['east', 'west'] and st.position == row:
                        has_edge2 = True
            
            # If both edges present, create corner tile
            if has_edge1 and has_edge2:
                # Add corner marker (use special edge name)
                corner_name = f"corner_{edge1}_{edge2}"
                self._sea_tiles.append(SeaTile(corner_name, row * 10 + col))  # Encode row,col in position
    
    def spawn_per_turn_tiles(self, avg_primary_sum: float) -> None:
        """Spawn tiles at turn start per spec 19.2 (1% per type with caps)."""
        base_hp = int(100 + avg_primary_sum * 0.5)
        
        # Per-turn spawnable types with caps
        spawnable = [
            ('trap_continuous', CONFIG['per_turn_spawn'].get('trap_continuous', {}).get('chance', 0.01), base_hp, None, CONFIG['per_turn_spawn'].get('trap_continuous', {}).get('cap', 1)),
            ('trap_momentary', CONFIG['per_turn_spawn'].get('trap_momentary', {}).get('chance', 0.01), base_hp, random.randint(1, 3), CONFIG['per_turn_spawn'].get('trap_momentary', {}).get('cap', 1)),
            ('drop_continuous', CONFIG['per_turn_spawn'].get('drop_continuous', {}).get('chance', 0.01), base_hp, None, CONFIG['per_turn_spawn'].get('drop_continuous', {}).get('cap', None)),
            ('drop_momentary', CONFIG['per_turn_spawn'].get('drop_momentary', {}).get('chance', 0.01), base_hp, random.randint(1, 3), CONFIG['per_turn_spawn'].get('drop_momentary', {}).get('cap', 1))
        ]
        
        for tile_type, spawn_chance, hp, duration, cap in spawnable:
            # Check cap
            if cap is not None:
                count = sum(1 for t in self._tiles.values() if t.tile_type == tile_type)
                if count >= cap:
                    continue
            
            if random.random() < spawn_chance:
                # Find empty square
                attempts = 0
                while attempts < 20:
                    row = random.randint(0, 6)
                    col = random.randint(0, 6)
                    if (row, col) not in self._tiles:
                        # Pass hp as-is (already int from base_hp calculation)
                        self._tiles[(row, col)] = Tile(row, col, tile_type, hp, duration)
                        break
                    attempts += 1
    
    def get_tile_at(self, row: int, col: int) -> Optional[Tile]:
        """Get tile at position."""
        return self._tiles.get((row, col))
    
    def remove_tile(self, row: int, col: int) -> None:
        """Remove tile from battlefield."""
        if (row, col) in self._tiles:
            del self._tiles[(row, col)]
    
    def damage_tile(self, row: int, col: int, damage: int) -> bool:
        """Apply damage to tile. Returns True if tile was destroyed."""
        tile = self.get_tile_at(row, col)
        if tile and tile.take_damage(damage):
            self.remove_tile(row, col)
            return True
        return False
    
    def tick_durations(self) -> None:
        """Advance durations for all momentary tiles."""
        expired = []
        for pos, tile in self._tiles.items():
            if tile.tick_duration():
                expired.append(pos)
        for pos in expired:
            del self._tiles[pos]
    
    def is_tile_blocking_movement(self, row: int, col: int) -> bool:
        """Check if tile blocks movement."""
        tile = self.get_tile_at(row, col)
        return tile is not None and tile.tile_type == 'unpassable'
    
    def is_sea_tile_at_edge(self, row: int, col: int, direction: str) -> bool:
        """Check if moving in direction would hit a Sea Tile."""
        # Check if position is at edge and Sea Tile exists there
        for sea_tile in self._sea_tiles:
            if sea_tile.edge == 'north' and row == 0 and sea_tile.position == col:
                return direction == 'north'
            if sea_tile.edge == 'south' and row == 6 and sea_tile.position == col:
                return direction == 'south'
            if sea_tile.edge == 'east' and col == 6 and sea_tile.position == row:
                return direction == 'east'
            if sea_tile.edge == 'west' and col == 0 and sea_tile.position == row:
                return direction == 'west'
        return False
    
    def is_sea_tile_at_position(self, row: int, col: int) -> bool:
        """Check if position (corner or edge) has a sea tile. For push doom detection."""
        # Check corners first
        if (row, col) in [(0, 0), (0, 6), (6, 0), (6, 6)]:
            for sea_tile in self._sea_tiles:
                if sea_tile.edge.startswith('corner_'):
                    # Decode position: row*10 + col
                    encoded = sea_tile.position
                    corner_row = encoded // 10
                    corner_col = encoded % 10
                    if corner_row == row and corner_col == col:
                        return True
        
        # Check edges
        if row == 0:  # North edge
            for st in self._sea_tiles:
                if st.edge == 'north' and st.position == col:
                    return True
        if row == 6:  # South edge
            for st in self._sea_tiles:
                if st.edge == 'south' and st.position == col:
                    return True
        if col == 0:  # West edge
            for st in self._sea_tiles:
                if st.edge == 'west' and st.position == row:
                    return True
        if col == 6:  # East edge
            for st in self._sea_tiles:
                if st.edge == 'east' and st.position == row:
                    return True
        
        return False
    
    def apply_tile_effect(self, row: int, col: int, player, effects_engine, tile_config: Optional[Dict[str, Any]] = None):
        """Apply the effect of the tile at (row, col) to the given player.
        Returns a dict describing the effect, or None.
        """
        key = (row, col)
        tile = self._tiles.get(key)
        if not tile:
            return None

        effect_type = None

        # Apply effects per spec 20, 23
        if tile.tile_type in ['drop_continuous', 'drop_momentary']:
            # Restore health/stamina (simplified: +20 health or +30 stamina)
            if random.random() < 0.5:
                max_health = getattr(player, "max_health", 100)
                player.health = min(player.health + 20, max_health)
                effect_type = 'health_restore'
            else:
                max_stamina = getattr(player, "max_stamina", 100)
                player.stamina = min(player.stamina + 30, max_stamina)
                effect_type = 'stamina_restore'
            # Tile vanishes
            self.remove_tile(row, col)

        elif tile.tile_type == 'trap_continuous':
            # Check if tile has predefined effect from config
            if tile_config and 'effect' in tile_config:
                chosen_type = tile_config['effect'].get('type', 'burn')
                category = tile_config['effect'].get('category', 'damage_over_time')
            else:
                # Fallback to random selection
                effect_types = ['burn', 'poison', 'freeze', 'slow']
                chosen_type = random.choice(effect_types)

                # Determine category based on effect type
                if chosen_type == 'burn':
                    category = random.choice(['damage_over_time', 'instant_damage'])
                elif chosen_type == 'poison':
                    category = random.choice(['damage_over_time', 'stamina_drain'])
                elif chosen_type == 'freeze':
                    category = random.choice(['stat_debuff', 'instant_damage'])
                else:  # slow
                    category = 'stat_debuff'

            # Calculate effect with tile mastery (50% base for tiles)
            tile_mastery = 50
            resistance = 1.0  # No resistance from tiles
            if player.devil_fruit_data and 'effect_resistance' in player.devil_fruit_data:
                resistance = player.devil_fruit_data['effect_resistance'].get(chosen_type, 1.0)
                resistance = resistance * (player.devil_fruit_mastery / 100.0)

            effect = effects_engine.calculate_effect(chosen_type, category, tile_mastery, resistance)
            if effect:
                effect_type = f'trap_{chosen_type}_{category}'
                return {'effect_obj': effect, 'effect_type': effect_type}
            # Tile stays

        elif tile.tile_type == 'trap_momentary':
            # Check if tile has predefined effect from config
            if tile_config and 'effect' in tile_config:
                chosen_type = tile_config['effect'].get('type', 'burn')
                category = tile_config['effect'].get('category', 'damage_over_time')
            else:
                # Fallback to random selection
                effect_types = ['burn', 'poison', 'freeze', 'slow']
                chosen_type = random.choice(effect_types)

                # Determine category based on effect type
                if chosen_type == 'burn':
                    category = random.choice(['damage_over_time', 'instant_damage'])
                elif chosen_type == 'poison':
                    category = random.choice(['damage_over_time', 'stamina_drain'])
                elif chosen_type == 'freeze':
                    category = random.choice(['stat_debuff', 'instant_damage'])
                else:  # slow
                    category = 'stat_debuff'

            # Calculate effect with tile mastery (50% base for tiles)
            tile_mastery = 50
            resistance = 1.0  # No resistance from tiles
            if player.devil_fruit_data and 'effect_resistance' in player.devil_fruit_data:
                resistance = player.devil_fruit_data['effect_resistance'].get(chosen_type, 1.0)
                resistance = resistance * (player.devil_fruit_mastery / 100.0)

            effect = effects_engine.calculate_effect(chosen_type, category, tile_mastery, resistance)
            if effect:
                effect_type = f'trap_{chosen_type}_{category}'
                # Tile vanishes
                self.remove_tile(row, col)
                return {'effect_obj': effect, 'effect_type': effect_type}

        return effect_type
    
    def get_all_tiles(self) -> List[Tuple[int, int, str]]:
        """Return list of (row, col, tile_type) for rendering."""
        return [(t.row, t.col, t.tile_type) for t in self._tiles.values()]
    
    def get_all_tiles_with_hp(self) -> List[Tuple[int, int, str, int, int]]:
        """Return list of (row, col, tile_type, hp, max_hp) for rendering with HP bars."""
        result = []
        for t in self._tiles.values():
            if t.hp == float('inf'):
                result.append((t.row, t.col, t.tile_type, -1, -1))  # -1 indicates infinite HP
            else:
                result.append((t.row, t.col, t.tile_type, int(t.hp), int(t.max_hp)))
        return result
    
    def get_sea_tiles(self) -> List[Tuple[str, int]]:
        """Return list of (edge, position) for Sea Tiles."""
        return [(st.edge, st.position) for st in self._sea_tiles]
    def get_sea_tiles(self) -> List[Tuple[str, int]]:
        """Return list of (edge, position) for Sea Tiles."""
        return [(st.edge, st.position) for st in self._sea_tiles]
    def get_sea_tiles(self) -> List[Tuple[str, int]]:
        """Return list of (edge, position) for Sea Tiles."""
        return [(st.edge, st.position) for st in self._sea_tiles]
