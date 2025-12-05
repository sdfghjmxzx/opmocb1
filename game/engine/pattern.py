"""Pattern detection - Phase 5: circle, half-circle, zig-zag tiers, spearhead, knight's tour.
Detectors ignore rotations; operate on move directions and positions from current_path.
First-match-wins priority list. Magnitudes and priority can be configured via JSON (movement_bonuses.json).
"""

from typing import List, Tuple, Optional, Dict, Any

Dir = Tuple[int, int]
Pos = Tuple[int, int]

class PatternEvaluator:
    def __init__(self):
        # Default priority
        self.priority = [
            'circle_360', 'half_circle', 'zig_zag_l1', 'zig_zag_l2', 'zig_zag_l3', 'spearhead_l1', 'spearhead_l2', 'knights_tour'
        ]
        # Default magnitudes
        self.magnitudes: Dict[str, Dict[str, float]] = {
            'circle_360': {'hit_bonus': 0.40, 'damage_bonus': 0.00},
            'half_circle': {'hit_bonus': 0.20, 'damage_bonus': 0.00},
            'zig_zag_l1': {'hit_bonus': 0.15, 'damage_bonus': 0.0},
            'zig_zag_l2': {'hit_bonus': 0.10, 'damage_bonus': 0.0},
            'zig_zag_l3': {'hit_bonus': 0.05, 'damage_bonus': 0.0},
            'spearhead_l1': {'hit_bonus': 0.10, 'damage_bonus': 0.10},
            'spearhead_l2': {'hit_bonus': 0.20, 'damage_bonus': 0.20},
            'knights_tour': {'hit_bonus': 0.0, 'damage_bonus': 0.15},
        }
    
    def set_config(self, config: Dict[str, Any]) -> None:
        """Apply config: priority list and per-pattern magnitudes if provided."""
        if isinstance(config, dict):
            pr = config.get('priority')
            if isinstance(pr, list) and pr:
                self.priority = pr
            mags = config.get('magnitudes')
            src = mags if isinstance(mags, dict) else config
            for name, vals in src.items():
                if isinstance(vals, dict) and name in self.magnitudes:
                    hit = vals.get('hit_bonus')
                    dmg = vals.get('damage_bonus')
                    if isinstance(hit, (int, float)):
                        self.magnitudes[name]['hit_bonus'] = float(hit)
                    if isinstance(dmg, (int, float)):
                        self.magnitudes[name]['damage_bonus'] = float(dmg)
    
    def _move_dirs(self, path: List[Pos]) -> List[Dir]:
        dirs: List[Dir] = []
        for i in range(1, len(path)):
            r1, c1 = path[i-1]
            r2, c2 = path[i]
            dirs.append((c2 - c1, r2 - r1))  # (dc, dr)
        return dirs
    
    def _ring_positions(self, op_row: int, op_col: int) -> List[Pos]:
        """8 Chebyshev-1 neighbors around opponent within 7x7 bounds."""
        ring: List[Pos] = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                r = op_row + dr
                c = op_col + dc
                if 0 <= r < 7 and 0 <= c < 7:
                    ring.append((r, c))
        return ring
    
    def _tail_ring_sequence(self, path: List[Pos], op_row: int, op_col: int, max_len: int) -> List[Pos]:
        """Collect ordered unique ring positions from path tail (up to max_len)."""
        ring_set = set(self._ring_positions(op_row, op_col))
        seq: List[Pos] = []
        seen = set()
        # traverse tail backwards, then reverse to preserve order of first occurrence in tail
        for i in range(len(path) - 1, -1, -1):
            pos = path[i]
            if pos in ring_set and pos not in seen:
                seq.append(pos)
                seen.add(pos)
                if len(seq) >= max_len:
                    break
        seq.reverse()
        return seq
    
    def _facing_to_vector(self, facing: float) -> Dir:
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
        return (999, 999)
    
    def _angle_to_vector(self, ang: int) -> Dir:
        return self._facing_to_vector(ang)
    
    def evaluate(self, path: List[Pos], facing: Optional[float], opponent: Optional[Pos]) -> Optional[Dict[str, Any]]:
        """Evaluate path with optional facing/opponent context and return a pattern result dict or None."""
        if not path or len(path) < 2:
            return None
        dirs = self._move_dirs(path)
        op_row, op_col = opponent if opponent else (-1, -1)
        
        # Check in configured priority order
        for name in self.priority:
            if name == 'circle_360' and opponent and self._detect_circle(path, op_row, op_col):
                return {'name': name, **self.magnitudes[name]}
            if name == 'half_circle' and opponent and self._detect_half_circle(path, op_row, op_col):
                return {'name': name, **self.magnitudes[name]}
            if name == 'zig_zag_l1' and self._detect_zig_zag_l1(dirs):
                return {'name': name, **self.magnitudes[name]}
            if name == 'zig_zag_l2' and self._detect_zig_zag_l2(dirs):
                return {'name': name, **self.magnitudes[name]}
            if name == 'zig_zag_l3' and self._detect_zig_zag_l3(dirs):
                return {'name': name, **self.magnitudes[name]}
            if name == 'spearhead_l1' and facing is not None and self._detect_spearhead(dirs, facing, level=1):
                return {'name': name, **self.magnitudes[name]}
            if name == 'spearhead_l2' and facing is not None and self._detect_spearhead(dirs, facing, level=2):
                return {'name': name, **self.magnitudes[name]}
            if name == 'knights_tour' and self._detect_knights_tour(dirs):
                return {'name': name, **self.magnitudes[name]}
        
        return None
    
    # --- Specific detectors ---
    def _detect_circle(self, path: List[Pos], op_row: int, op_col: int) -> bool:
        ring = set(self._ring_positions(op_row, op_col))
        seq = self._tail_ring_sequence(path, op_row, op_col, 8)
        return len(seq) == 8 and set(seq) == ring
    
    def _detect_half_circle(self, path: List[Pos], op_row: int, op_col: int) -> bool:
        seq = self._tail_ring_sequence(path, op_row, op_col, 5)
        return len(seq) == 5
    
    def _detect_zig_zag_l1(self, dirs: List[Dir]) -> bool:
        """Level 1 (Tight): NE → NW → NE in the tail sequence."""
        seq = [(1, -1), (-1, -1), (1, -1)]
        return self._tail_has_sequence(dirs, seq)
    
    def _detect_zig_zag_l2(self, dirs: List[Dir]) -> bool:
        """Level 2 (Wide): NE,NE → NW,NW in the tail sequence."""
        seq = [(1, -1), (1, -1), (-1, -1), (-1, -1)]
        return self._tail_has_sequence(dirs, seq)
    
    def _detect_zig_zag_l3(self, dirs: List[Dir]) -> bool:
        """Level 3 (Triple): NE×3 → NW×3 in the tail sequence."""
        seq = [(1, -1), (1, -1), (1, -1), (-1, -1), (-1, -1), (-1, -1)]
        return self._tail_has_sequence(dirs, seq)
    
    def _detect_knights_tour(self, dirs: List[Dir]) -> bool:
        """Two knight L-moves in sequence anywhere in tail."""
        def is_knight(d: Dir) -> bool:
            return (abs(d[0]) == 1 and abs(d[1]) == 2) or (abs(d[0]) == 2 and abs(d[1]) == 1)
        if len(dirs) < 2:
            return False
        return is_knight(dirs[-1]) and is_knight(dirs[-2])
    
    def _detect_spearhead(self, dirs: List[Dir], facing: float, level: int) -> bool:
        """Spearhead: diag-left → forward → diag-right.
        Level 1: one sequence (3 moves) at tail.
        Level 2: two sequences (6 moves) at tail.
        """
        forward = self._facing_to_vector(facing)
        left = self._angle_to_vector((int(facing) - 45) % 360)
        right = self._angle_to_vector((int(facing) + 45) % 360)
        base_seq = [left, forward, right]
        if level == 1:
            return self._tail_has_sequence(dirs, base_seq)
        elif level == 2:
            return self._tail_has_sequence(dirs, base_seq + base_seq)
        return False
    
    def _tail_has_sequence(self, dirs: List[Dir], seq: List[Dir]) -> bool:
        if len(dirs) < len(seq):
            return False
        tail = dirs[-len(seq):]
        return tail == seq