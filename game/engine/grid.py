"""Grid module (theme-agnostic).
Phase 1: provides board size and helpers.
"""
BOARD_ROWS = 7
BOARD_COLS = 7

def in_bounds(row: int, col: int) -> bool:
    return 0 <= row < BOARD_ROWS and 0 <= col < BOARD_COLS
