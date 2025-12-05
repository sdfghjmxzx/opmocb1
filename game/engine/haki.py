"""Haki system - Phase 3/6: Alloys, nullification, and JSON-driven costs."""

# Runtime-configurable cost parameters (defaults)
CONFIG = {
    'armament_base': 40,
    'observation_base': 100,
    'conqueror_base': 200,
    'divisor': 150,
    'min_add': 1,
}

def set_config(cfg: dict) -> None:
    """Set Haki cost config from JSON at runtime."""
    if not isinstance(cfg, dict):
        return
    for k in ('armament_base', 'observation_base', 'conqueror_base', 'divisor', 'min_add'):
        if k in cfg:
            try:
                if k == 'min_add':
                    CONFIG[k] = int(cfg[k])
                else:
                    CONFIG[k] = float(cfg[k])
            except Exception:
                pass

def calculate_haki_effectiveness(
    attacker_haki: int,
    defender_haki: int,
    both_activated: bool
) -> float:
    """
    Calculate Haki effectiveness per spec v5.1 section 12.2.
    Nullification occurs only when BOTH players activate Haki on same action.
    Returns effectiveness in range [0.0, 1.0].
    """
    if not both_activated:
        # If only attacker uses Haki: 100% effectiveness based on their stat
        return attacker_haki / 100.0
    
    # Both activated: nullification applies
    return max(0.0, (attacker_haki - defender_haki) / 100.0)

def calculate_haki_cost(haki_type: str, haki_stat: int) -> int:
    """
    Calculate Haki stamina cost per spec v5.1 section 12.3.
    Cost decreases with higher stat. Uses runtime CONFIG when provided.
    """
    base_map = {
        'armament': CONFIG.get('armament_base', 40.0),
        'observation': CONFIG.get('observation_base', 100.0),
        'conqueror': CONFIG.get('conqueror_base', 200.0),
    }
    base = base_map.get(haki_type)
    if base is None:
        return 0
    divisor = CONFIG.get('divisor', 150.0)
    min_add = CONFIG.get('min_add', 1)
    return int((base * (1 - (haki_stat / float(divisor)))) + int(min_add))

class HakiSystem:
    def cost(self, haki_type: str, haki_stat: int) -> int:
        return calculate_haki_cost(haki_type, haki_stat)
