"""Effects application engine for status effects, DoT, debuffs per spec sections 17."""
import random
import math
import json
import os
from typing import Dict, List, Tuple, Optional, Any

class StatusEffect:
    """Represents an active status effect on a player."""
    def __init__(self, effect_type: str, category: str, magnitude: int, duration: int, source: str = "attack"):
        self.effect_type = effect_type  # 'burn', 'poison', 'freeze', 'slow'
        self.category = category  # 'damage_over_time', 'instant_damage', 'stat_debuff', 'stamina_drain'
        self.magnitude = magnitude  # Damage/debuff amount
        self.duration = duration  # Turns remaining
        self.source = source  # 'attack', 'tile', 'special'
    
    def __repr__(self):
        return f"StatusEffect({self.effect_type}, {self.category}, mag={self.magnitude}, dur={self.duration})"

class EffectsEngine:
    """Manages effect types, categories, and application logic."""
    
    def __init__(self):
        self.effect_types: Dict[str, Any] = {}
        self.effect_categories: Dict[str, Any] = {}
        self.loaded = False
    
    def load_from_files(self, data_dir: str) -> None:
        """Load effect_types.json and effect_categories.json."""
        types_path = os.path.join(data_dir, 'effect_types.json')
        categories_path = os.path.join(data_dir, 'effect_categories.json')
        
        if os.path.exists(types_path):
            with open(types_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.effect_types = data.get('effect_types', {})
        
        if os.path.exists(categories_path):
            with open(categories_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.effect_categories = data.get('effect_categories', {})
        
        self.loaded = True
        print(f"[EFFECTS] Loaded {len(self.effect_types)} effect types, {len(self.effect_categories)} categories")
    
    def calculate_effect(self, effect_type: str, category: str, df_mastery: int, 
                        resistance: float = 1.0) -> Optional[StatusEffect]:
        """Calculate effect magnitude and duration based on spec 17.3 formulas.
        
        Args:
            effect_type: 'burn', 'poison', 'freeze', 'slow'
            category: 'damage_over_time', 'instant_damage', 'stat_debuff', 'stamina_drain'
            df_mastery: Attacker's DF mastery (0-100)
            resistance: Defender's resistance multiplier (0.0-1.5+)
        
        Returns:
            StatusEffect object or None if effect is resisted completely
        """
        if effect_type not in self.effect_types:
            print(f"[EFFECTS] Unknown effect type: {effect_type}")
            return None
        
        type_data = self.effect_types[effect_type]
        if category not in type_data.get('allowed_categories', []):
            print(f"[EFFECTS] Category {category} not allowed for {effect_type}")
            return None
        
        # Magnitude formula: floor(base_min + (random(0, base_max - base_min) × (df_mastery / 100)))
        base_min, base_max = type_data['base_magnitude_range']
        magnitude = math.floor(base_min + (random.randint(0, base_max - base_min) * (df_mastery / 100.0)))
        
        # Apply resistance: FinalMagnitude = CalculatedMagnitude × resistance
        magnitude = max(0, int(magnitude * resistance))
        
        if magnitude == 0:
            print(f"[EFFECTS] Effect {effect_type} completely resisted (mag=0)")
            return None
        
        # Duration formula: ceil(1 + (random(0, base_max - 1) × (df_mastery / 100)))
        # Only for non-instant effects
        duration = 0
        if category != 'instant_damage':
            dur_max = type_data['base_duration_range'][1]
            duration = math.ceil(1 + (random.randint(0, dur_max - 1) * (df_mastery / 100.0)))
        
        effect = StatusEffect(effect_type, category, magnitude, duration)
        print(f"[EFFECTS] Created {effect}")
        return effect
    
    def apply_instant_effect(self, effect: StatusEffect, player: Any) -> int:
        """Apply instant_damage effect immediately. Returns damage dealt."""
        if effect.category != 'instant_damage':
            return 0
        
        damage = effect.magnitude
        player.health = max(0, player.health - damage)
        print(f"[EFFECTS] Instant {effect.effect_type} damage: {damage} → {player.name} health={player.health}")
        return damage
    
    def should_stack_effect(self, existing: List[StatusEffect], new_effect: StatusEffect) -> bool:
        """Check if new effect should stack with existing effects per spec 17.1."""
        category_rules = self.effect_categories.get(new_effect.category, {})
        
        # If category is not stackable, refresh duration to longest
        if not category_rules.get('stackable', False):
            # Find existing effect of same type
            for existing_effect in existing:
                if existing_effect.effect_type == new_effect.effect_type:
                    # Refresh to longest duration
                    if new_effect.duration > existing_effect.duration:
                        existing_effect.duration = new_effect.duration
                        existing_effect.magnitude = max(existing_effect.magnitude, new_effect.magnitude)
                    return False  # Don't add new effect, refreshed existing
        
        # Check max stacks for stackable categories
        max_stacks = category_rules.get('max_stacks', 999)
        same_type_count = sum(1 for e in existing if e.effect_type == new_effect.effect_type)
        if same_type_count >= max_stacks:
            return False
        
        return True
    
    def tick_effects(self, effects: List[StatusEffect]) -> List[StatusEffect]:
        """Process effects at turn start per spec 17.3 Resolution Order.
        Returns updated list of effects.
        """
        # Step 1: Remove effects where duration == 0
        active_effects = [e for e in effects if e.duration > 0 or e.category == 'instant_damage']
        
        # Step 5: Decrement all effect durations by 1
        for effect in active_effects:
            if effect.duration > 0:
                effect.duration -= 1
        
        return active_effects
    
    def apply_dot_effects(self, effects: List[StatusEffect], player: Any) -> int:
        """Apply damage_over_time effects. Returns total damage dealt."""
        total_damage = 0
        for effect in effects:
            if effect.category == 'damage_over_time':
                player.health = max(0, player.health - effect.magnitude)
                total_damage += effect.magnitude
                print(f"[EFFECTS] DoT {effect.effect_type}: {effect.magnitude} dmg → {player.name} health={player.health}")
        return total_damage
    
    def apply_stamina_drain_effects(self, effects: List[StatusEffect], player: Any) -> int:
        """Apply stamina_drain effects. Returns total stamina drained."""
        total_drain = 0
        for effect in effects:
            if effect.category == 'stamina_drain':
                drain = int(player.stamina * (effect.magnitude / 100.0))
                player.stamina = max(0, player.stamina - drain)
                total_drain += drain
                print(f"[EFFECTS] Stamina drain {effect.effect_type}: {drain} → {player.name} stamina={player.stamina}")
        return total_drain
    
    def get_stat_debuffs(self, effects: List[StatusEffect]) -> Dict[str, int]:
        """Get total stat debuffs from active effects."""
        debuffs = {}
        for effect in effects:
            if effect.category == 'stat_debuff':
                # Additive stacking
                debuffs[effect.effect_type] = debuffs.get(effect.effect_type, 0) + effect.magnitude
        return debuffs

# Legacy bridge for backward compatibility
class EffectsBridge:
    def apply(self, effect_block: dict, context: dict):
        # Placeholder; real application in later phases.
        return context
