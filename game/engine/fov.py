"""Field of View (FOV) System - Layer Calculation Module

Determines which FOV layer (FOV/Periphery/Behind) a target occupies relative to a player's facing direction.
Implements the specification from Rule Update9.md.
"""

from typing import Tuple
import math


# Facing degree to primary direction mapping
# Player.facing uses degrees: North=270, East=0, South=90, West=180
FACING_TO_DIRECTION = {
    270: "North",     # N
    315: "NorthEast", # NE
    0: "East",        # E
    45: "SouthEast",  # SE
    90: "South",      # S
    135: "SouthWest", # SW
    180: "West",      # W
    225: "NorthWest"  # NW
}

# FOV layer mapping by facing direction
# Structure: {facing: {layer: [compass_directions]}}
# FOV = direct front vision (3 directions)
# Periphery = sides and diagonal sides (4 directions total)
# Behind = only direct rear (1 direction - opposite of facing)
FOV_LAYER_MAP = {
    "North": {
        "FOV": ["N", "NE", "NW"],
        "Periphery": ["E", "W", "SE", "SW"],
        "Behind": ["S"]
    },
    "South": {
        "FOV": ["S", "SE", "SW"],
        "Periphery": ["E", "W", "NE", "NW"],
        "Behind": ["N"]
    },
    "East": {
        "FOV": ["E", "NE", "SE"],
        "Periphery": ["N", "S", "NW", "SW"],
        "Behind": ["W"]
    },
    "West": {
        "FOV": ["W", "NW", "SW"],
        "Periphery": ["N", "S", "NE", "SE"],
        "Behind": ["E"]
    },
    "NorthEast": {
        "FOV": ["NE", "N", "E"],
        "Periphery": ["NW", "SE", "W", "S"],
        "Behind": ["SW"]
    },
    "NorthWest": {
        "FOV": ["NW", "N", "W"],
        "Periphery": ["NE", "SW", "E", "S"],
        "Behind": ["SE"]
    },
    "SouthEast": {
        "FOV": ["SE", "S", "E"],
        "Periphery": ["NE", "SW", "N", "W"],
        "Behind": ["NW"]
    },
    "SouthWest": {
        "FOV": ["SW", "S", "W"],
        "Periphery": ["NW", "SE", "N", "E"],
        "Behind": ["NE"]
    }
}


def normalize_facing(facing_degrees: float) -> str:
    """Convert facing degrees to primary direction string.
    
    Args:
        facing_degrees: Player facing in degrees (0-359)
    
    Returns:
        Primary direction string (e.g., "North", "NorthEast")
    """
    # Normalize to 0-359 range
    facing = facing_degrees % 360
    
    # Round to nearest 45-degree increment
    normalized = round(facing / 45.0) * 45
    if normalized == 360:
        normalized = 0
    
    # Look up direction
    return FACING_TO_DIRECTION.get(int(normalized), "North")


def get_compass_direction(dx: int, dy: int) -> str:
    """Convert position delta to compass direction.
    
    Args:
        dx: Column delta (target_col - player_col)
        dy: Row delta (target_row - player_row)
    
    Returns:
        Compass direction string (N, NE, E, SE, S, SW, W, NW)
    """
    # Handle exact cardinal directions first
    if dx == 0 and dy < 0:
        return "N"
    if dx == 0 and dy > 0:
        return "S"
    if dx > 0 and dy == 0:
        return "E"
    if dx < 0 and dy == 0:
        return "W"
    
    # Calculate angle from player to target
    # atan2 gives angle in radians, convert to degrees
    # In grid coordinates: positive dy = south, positive dx = east
    angle_rad = math.atan2(dy, dx)
    angle_deg = math.degrees(angle_rad)
    
    # Normalize to 0-360 range
    if angle_deg < 0:
        angle_deg += 360
    
    # Map angle to 8 compass directions (45-degree sectors)
    # E=0°, SE=45°, S=90°, SW=135°, W=180°, NW=225°, N=270°, NE=315°
    if 337.5 <= angle_deg or angle_deg < 22.5:
        return "E"
    elif 22.5 <= angle_deg < 67.5:
        return "SE"
    elif 67.5 <= angle_deg < 112.5:
        return "S"
    elif 112.5 <= angle_deg < 157.5:
        return "SW"
    elif 157.5 <= angle_deg < 202.5:
        return "W"
    elif 202.5 <= angle_deg < 247.5:
        return "NW"
    elif 247.5 <= angle_deg < 292.5:
        return "N"
    else:  # 292.5 <= angle_deg < 337.5
        return "NE"


def get_fov_layer(player_facing: float, player_pos: Tuple[int, int], target_pos: Tuple[int, int]) -> str:
    """Determine which FOV layer the target occupies relative to the player.
    
    Rules:
    - "Behind" is a special case based on position depth:
      * Any tile strictly behind the player relative to their facing is "Behind".
      * This is computed using a half-plane test, not compass sectors.
    - For tiles in front/side of the player, we use compass sectors + FOV_LAYER_MAP
      to distinguish between "FOV" and "Periphery".
    
    Args:
        player_facing: Player's facing direction in degrees (0-359)
        player_pos: Player position as (row, col)
        target_pos: Target position as (row, col)
    
    Returns:
        FOV layer string: "FOV", "Periphery", or "Behind"
    """
    # Calculate position delta
    dx = target_pos[1] - player_pos[1]  # Column delta (east/west)
    dy = target_pos[0] - player_pos[0]  # Row delta (south/north)
    
    # Same tile as player: treat as frontal
    if dx == 0 and dy == 0:
        return "FOV"
    
    # Normalize facing and get continuous facing vector
    facing = player_facing % 360.0
    facing_rad = math.radians(facing)
    facing_dx = math.cos(facing_rad)
    facing_dy = math.sin(facing_rad)
    
    # Forward depth via dot product:
    # > 0 → in front/side; < 0 → strictly behind
    forward_depth = dx * facing_dx + dy * facing_dy
    
    # Tolerance to avoid floating point noise around 0
    EPS = 1e-6
    
    # Special rule: ANY tile strictly behind the player is "Behind"
    if forward_depth < -EPS:
        return "Behind"
    
    # Tiles in front/side: decide between FOV wedge vs Periphery
    # Angle between facing vector and target vector
    v_len_sq = dx * dx + dy * dy
    if v_len_sq == 0:
        return "FOV"
    v_len = math.sqrt(v_len_sq)
    cos_theta = forward_depth / v_len  # since |facing| ≈ 1

    # Half-angle of FOV wedge: 45° (between forward and diagonal)
    cos_half = math.cos(math.radians(45.0))

    # Inside wedge (between front-left and front-right diagonals)
    # Allow a small tolerance so exact diagonal tiles (like 3E / 3C) count as FOV
    if cos_theta + EPS >= cos_half:
        return "FOV"

    # Not behind and not in FOV wedge → Periphery
    return "Periphery"


def get_fov_hit_bonus(player_facing: float, player_pos: Tuple[int, int], target_pos: Tuple[int, int]) -> float:
    """Calculate FOV hit chance bonus for attacker.
    
    Args:
        player_facing: Attacker's facing direction in degrees
        player_pos: Attacker position as (row, col)
        target_pos: Defender position as (row, col)
    
    Returns:
        Hit chance bonus: 0.0 (FOV), 0.10 (Periphery), or 0.30 (Behind)
    """
    layer = get_fov_layer(player_facing, player_pos, target_pos)
    
    if layer == "FOV":
        return 0.0  # No bonus for frontal attack
    elif layer == "Periphery":
        return 0.10  # +10% flanking bonus
    elif layer == "Behind":
        return 0.30  # +30% rear attack bonus
    else:
        return 0.0  # Fallback
