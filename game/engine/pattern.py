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
        """8 neighbors around opponent in fixed clockwise ring order (starting north, then NE, E, SE, S, SW, W, NW)."""
        r = op_row
        c = op_col
        ring: List[Pos] = []
        # N, NE, E, SE, S, SW, W, NW
        candidates = [
            (r - 1, c),     # 0: North
            (r - 1, c + 1), # 1: NE
            (r, c + 1),     # 2: East
            (r + 1, c + 1), # 3: SE
            (r + 1, c),     # 4: South
            (r + 1, c - 1), # 5: SW
            (r, c - 1),     # 6: West
            (r - 1, c - 1), # 7: NW
        ]
        for pos in candidates:
            rr, cc = pos
            if 0 <= rr < 7 and 0 <= cc < 7:
                ring.append(pos)
            else:
                ring.append(pos)
        return ring
    
    def _ring_index(self, op_row: int, op_col: int, pos: Pos) -> Optional[int]:
        """Return ring index 0-7 for a position adjacent to opponent, or None if not on ring."""
        ring = self._ring_positions(op_row, op_col)
        try:
            return ring.index(pos)
        except ValueError:
            return None
    
    def _collect_ring_indices_from_tail(self, path: List[Pos], op_row: int, op_col: int) -> List[int]:
        """Collect ring indices after entry (first adjacent) and following moves.
        Entry tile itself is NOT counted as a step; indices start from the first move after entry.
        """
        ring_indices: List[int] = []
        entry_found = False
        for pos in path:
            idx = self._ring_index(op_row, op_col, pos)
            if idx is not None:
                if not entry_found:
                    entry_found = True
                    print(f"[PATTERN DEBUG] entry adjacent pos={pos}, entry_index={idx}")
                    # Do NOT append entry; steps start after this tile
                else:
                    ring_indices.append(idx)
            else:
                if entry_found:
                    break
        print(f"[PATTERN DEBUG] collected ring indices={ring_indices}")
        return ring_indices
    
    def _analyze_ring_sequence(self, indices: List[int]) -> Optional[tuple]:
        """Given ordered ring indices starting from entry, compute run length along a single direction.
        Returns (direction, run_length) where direction is +1 or -1 (mod 8), or None if invalid.
        The run always starts at indices[0] and stops at first deviation.
        """
        if len(indices) < 2:
            return None
        first = indices[0]
        second = indices[1]
        delta = (second - first) % 8
        if delta == 1:
            direction = 1
        elif delta == 7:
            direction = -1
        else:
            return None
        run_length = 2  # we already have first -> second as step 1, second -> third would be step 2, etc.
        current = second
        for idx in indices[2:]:
            expected = (current + direction) % 8
            if idx != expected:
                break
            run_length += 1
            current = idx
        return direction, run_length
    
    def _detect_circle(self, path: List[Pos], op_row: int, op_col: int) -> bool:
        indices = self._collect_ring_indices_from_tail(path, op_row, op_col)
        print(f"[PATTERN DEBUG] circle indices={indices}")
        if len(indices) < 8:
            return False
        tail_indices = indices[-8:]
        analyzed = self._analyze_ring_sequence(tail_indices)
        print(f"[PATTERN DEBUG] circle tail_indices={tail_indices}, analyzed={analyzed}")
        if not analyzed:
            return False
        direction, run_length = analyzed
        return run_length == 8
    
    def _detect_half_circle(self, path: List[Pos], op_row: int, op_col: int) -> bool:
        indices = self._collect_ring_indices_from_tail(path, op_row, op_col)
        print(f"[PATTERN DEBUG] half-circle indices={indices}")
        if len(indices) < 4:
            return False
        analyzed = self._analyze_ring_sequence(indices)
        print(f"[PATTERN DEBUG] half-circle analyzed={analyzed}")
        if not analyzed:
            return False
        direction, run_length = analyzed
        return 4 <= run_length <= 7
    
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

        print(f"[PATTERN DEBUG] evaluate: path={path}, opponent={opponent}, facing={facing}")

        # Proximity check: is last position adjacent to opponent?
        last_pos = path[-1]
        on_ring = opponent is not None and (self._ring_index(op_row, op_col, last_pos) is not None)
        print(f"[PATTERN DEBUG] proximity: last_pos={last_pos}, adjacent_to_opponent={on_ring}")

        # If adjacent, construct ideal CW/CCW paths from entry for circle/half-circle
        if opponent is not None and on_ring:
            entry_idx = self._ring_index(op_row, op_col, last_pos)
            ring = self._ring_positions(op_row, op_col)
            cw_path = []
            ccw_path = []
            if entry_idx is not None:
                for step in range(1, 9):
                    cw_pos = ring[(entry_idx + step) % 8]
                    ccw_pos = ring[(entry_idx - step) % 8]
                    cw_path.append(cw_pos)
                    ccw_path.append(ccw_pos)
            print(f"[PATTERN DEBUG] ideal CW path from entry={entry_idx}: {cw_path}")
            print(f"[PATTERN DEBUG] ideal CCW path from entry={entry_idx}: {ccw_path}")

        # Check in configured priority order
        for name in self.priority:
            if name == 'circle_360' and opponent:
                detected = self._detect_circle(path, op_row, op_col)
                print(f"[PATTERN DEBUG] circle_360 detected={detected}")
                if detected:
                    return {'name': name, **self.magnitudes[name]}
            if name == 'half_circle' and opponent:
                detected = self._detect_half_circle(path, op_row, op_col)
                print(f"[PATTERN DEBUG] half_circle detected={detected}")
                if detected:
                    return {'name': name, **self.magnitudes[name]}
            if name == 'zig_zag_l1':
                detected = self._detect_zig_zag_l1(dirs)
                if detected:
                    print(f"[PATTERN DEBUG] zig_zag_l1 detected")
                    return {'name': name, **self.magnitudes[name]}
            if name == 'zig_zag_l2':
                detected = self._detect_zig_zag_l2(dirs)
                if detected:
                    print(f"[PATTERN DEBUG] zig_zag_l2 detected")
                    return {'name': name, **self.magnitudes[name]}
            if name == 'zig_zag_l3':
                detected = self._detect_zig_zag_l3(dirs)
                if detected:
                    print(f"[PATTERN DEBUG] zig_zag_l3 detected")
                    return {'name': name, **self.magnitudes[name]}
            if name == 'spearhead_l1' and facing is not None:
                detected = self._detect_spearhead(dirs, facing, level=1)
                print(f"[PATTERN DEBUG] spearhead_l1 detected={detected}")
                if detected:
                    return {'name': name, **self.magnitudes[name]}
            if name == 'spearhead_l2' and facing is not None:
                detected = self._detect_spearhead(dirs, facing, level=2)
                print(f"[PATTERN DEBUG] spearhead_l2 detected={detected}")
                if detected:
                    return {'name': name, **self.magnitudes[name]}
            if name == 'knights_tour':
                detected = self._detect_knights_tour(dirs)
                print(f"[PATTERN DEBUG] knights_tour detected={detected}")
                if detected:
                    return {'name': name, **self.magnitudes[name]}

        print("[PATTERN DEBUG] no pattern detected")
        return None
    
    # --- Specific detectors ---
    def _detect_zig_zag_l1(self, dirs: List[Dir]) -> bool:
        """Level 1 (Tight): any 3-step zig-zag between adjacent diagonals (back-and-forth).
        Examples: NE→SE→NE, SE→NE→SE, NE→NW→NE, NW→NE→NW, SW→NW→SW, NW→SW→NW, SE→SW→SE, SW→SE→SW.
        """
        if len(dirs) < 3:
            return False
        d0, d1, d2 = dirs[-3:]

        def is_diag(v: Dir) -> bool:
            return v[0] != 0 and v[1] != 0

        if not (is_diag(d0) and is_diag(d1) and is_diag(d2)):
            return False

        def is_adjacent_diag(a: Dir, b: Dir) -> bool:
            return (a[0] == b[0] and a[1] == -b[1]) or (a[1] == b[1] and a[0] == -b[0])

        return is_adjacent_diag(d0, d1) and d2 == d0

    def _detect_zig_zag_l2(self, dirs: List[Dir]) -> bool:
        """Level 2 (Wide): AA→BB where A and B are adjacent diagonals (2 moves each)."""
        if len(dirs) < 4:
            return False
        tail = dirs[-4:]
        d0, d1, d2, d3 = tail

        def is_diag(v: Dir) -> bool:
            return v[0] != 0 and v[1] != 0

        if not all(is_diag(d) for d in tail):
            return False

        def is_adjacent_diag(a: Dir, b: Dir) -> bool:
            return (a[0] == b[0] and a[1] == -b[1]) or (a[1] == b[1] and a[0] == -b[0])

        return d0 == d1 and d2 == d3 and is_adjacent_diag(d0, d2)

    def _detect_zig_zag_l3(self, dirs: List[Dir]) -> bool:
        """Level 3 (Triple): AAA→BBB where A and B are adjacent diagonals (3 moves each)."""
        if len(dirs) < 6:
            return False
        tail = dirs[-6:]
        d0, d1, d2, d3, d4, d5 = tail

        def is_diag(v: Dir) -> bool:
            return v[0] != 0 and v[1] != 0

        if not all(is_diag(d) for d in tail):
            return False

        def is_adjacent_diag(a: Dir, b: Dir) -> bool:
            return (a[0] == b[0] and a[1] == -b[1]) or (a[1] == b[1] and a[0] == -b[0])

        return d0 == d1 == d2 and d3 == d4 == d5 and is_adjacent_diag(d0, d3)
    
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