"""Turn/Phase controller skeleton.
Phase 1: alternation helpers (to be used by controller).
"""
class TurnController:
    def next_phase(self, current: str, skip_defense: bool) -> str:
        if current == "attack":
            return "attack" if skip_defense else "defense"
        return "attack"
