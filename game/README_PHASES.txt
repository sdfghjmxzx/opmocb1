Mastery of Chessboxing – Development Phases (Registry & Guide)

Purpose
- Track phase-by-phase implementation and serve as a quick reference for how the system works and connects.
- This guide mirrors the architecture plan and stays focused on the working vertical slices to support early visual testing.

Phase 1 – Vertical Slice (Working UI)
- What you can test:
  - Launch game; single battle_screen renders board, players, ghost overlays, wheel, controls, and log.
  - Click a player to enter planning; add/remove movement steps; wheel drag updates both wheel_rotation and ghost_facing.
  - Confirm/cancel turns; simple attack/defense selection enters terminal state; illegal sequences blocked.
  - Cost previews come from controller (15 attack / 30 defense per step), not hardcoded in UI.
- Connected modules:
  - controller (CombatGame): turn/phase, planning state, highlights, wheel API, costs.
  - screen: calls controller methods only; no rules in UI.
- Notes:
  - Attack preview is minimal (one tile ahead). Pattern detectors and full combat resolution are deferred.

Phase 2 – Movement, Facing Chains, Bounce Scaffolding
- Add Chebyshev-1 movement blockers (walls, borders, unpassable tiles) and base costs (attack 15/defense 30).
- Track facing-direction chain per rules; apply multiplicative cost reduction; do not break on rotations.
- Bounce validation (cardinal/diagonal) with discounts (movement 30%, next terminal action: 30% cost + 20% hit chance bonus).
- UI impact: highlights update; cost previews reflect chain and bounce.

Phase 3 – Combat Resolution Slice
- Implement hit chance and damage formulas (clamped 5–95%).
- DF effective stats integration (type advantages, mastery scaling, defender mitigation) with base data.
- Haki alloys with nullification only when both sides use same haki.
- UI impact: attack_highlighted_squares recalculated on ghost changes; confirm shows outcomes.

Phase 4 – Walls & Tiles
- WallSystem HP tiers, placement and breakthrough; TileSystem spawn mechanics, interaction matrix; Sea Tile doom.
- UI impact: placement highlights; wall/tile overlays; push interactions; game-over overlay.

Phase 5 – Pattern Mastery
- Pattern detectors: circle, half-circle, zig-zag tiers, knight’s tour, spearhead; first-match-wins priority list.
- Bonuses applied once per planning phase; memory persists across turns; disrupted by push.
- UI impact: visual feedback when pattern triggers; modifiers reflected in previews.

Phase 6 – JSON-Driven Theme & Validation
- Data files: stats_config.json, devil_fruits.json, haki_config.json, movement_bonuses.json, tile_config.json, status_effects.json.
- ValidationLayer: load status_effects.json first; validate all effect references at start; fail fast with precise messages.
- Swap Test verified: base attacks work without devil_fruits.json; haki_config.json changes reflected at runtime; new patterns auto-applied.

Phase 7 – UX Parity & Polish
- Match old script’s feel for rotation wheel, ghost planning, overlays, animation cadence.
- Enforce per-turn limits and terminal state; finalize cost and bonus caps.
- Add robust logging and test hooks.

How it connects (at a glance)
- battle_screen → CombatGame (controller) → engine rules → JSON data.
- UI calls controller methods; controller returns highlights, costs, and outcomes; UI renders only.
- JSON defines tunable numbers and effects; engine validates and applies; removing or changing JSON does not break core loops.

Testing tips per phase
- Always verify terminal state: after selecting attack/defense, movement/rotation/creation must be disabled until confirm/cancel.
- Use wheel drag to rotate ghost; confirm turn to see phase alternation and skip/miss effects.
- Introduce a dummy wall/tile and confirm it blocks movement before enabling full tile system.
- Add a simple pattern (e.g., circle_360) in movement_bonuses.json and verify first-match priority.

Registry updates
- After each phase, append short notes here: what was added, where it lives, and how to test it.

Phase 1 Summary (Complete)
- What was added:
  - game/controller.py: CombatGame with planning state, ghost tracking, wheel drag, terminal state enforcement, cost preview.
  - game/engine/: Skeleton modules (grid, movement, turn, combat, effects, pattern, walls, tiles, push_bounce, haki, devil_fruit).
  - game/data/status_effects.json: Minimal effect registry.
  - game/screens.rpy: Single battle_screen with embedded controls, log, and game-over overlay.
  - game/script.rpy: label start to launch battle_screen.
- Where it lives:
  - Controller: game/controller.py
  - UI: game/screens.rpy and game/script.rpy
  - Engine stubs: game/engine/
  - Data: game/data/
- How to test:
  - Launch game; click current player to enter planning.
  - Move to adjacent tiles; path and ghost update.
  - Drag wheel; ghost facing and attack preview update.
  - Cost preview shows 15 (attack) or 30 (defense) per step.
  - Select attack/defense; movement/rotation blocked until confirm/cancel.
  - Confirm turn; phase alternates; skip/miss rules apply.

Phase 2 Summary (Complete)
- What was added:
  - Movement blockers: Opponent position blocks target tile.
  - Facing Direction chain: Tracks consecutive moves in current facing direction; applies cost reduction (10% per move, max 50%).
  - Chain recomputation: Chain is derived from current_path + ghost_facing on every change (moves/rotations/undo).
  - Bounce detection stub: Placeholder for entry → wall → exit pattern; applies 30% discount when active.
  - Cost modifiers: get_movement_cost() applies chain and bounce discounts multiplicatively.
- Where it lives:
  - controller.py: _update_facing_chain() recomputes from path history, called after moves/rotations/undo.
  - engine/movement.py: get_neighbors(), is_blocked() checks opponent position.
  - engine/push_bounce.py: detect_bounce() stub, apply_bounce_discount().
- How to test:
  - Move in current facing direction multiple times; cost per step reduces.
  - Rotate mid-planning; chain recalculates for new facing direction.
  - Try to move onto opponent's tile; movement is blocked (tile not highlighted).
  - Bounce detection is stubbed; will activate in later phase when walls are present.

Phase 3 Summary (Complete)
- What was added:
  - Hit chance formula: calculate_hit_chance() with stat nullification, CI, aura, facing/bounce/pattern bonuses, DF multipliers, Haki obs.
  - Damage formula: calculate_damage() with stat/aura modifiers, willpower reduction, DF component, Haki armament, additive bonuses.
  - Attack quality tiers: get_attack_quality() determines bad/good/excellent based on damage ratio.
  - Push distance: get_push_distance() returns 0/1/2 based on quality.
  - DF type advantages: calculate_type_advantage() handles vs/weak_vs matchups, mastery scaling, defender mitigation.
  - Haki system: calculate_haki_effectiveness() with nullification when both sides use Haki; calculate_haki_cost() for stamina.
  - Player stats: strength, defense, speed, reaction, endurance, willpower, combat_instinct, aura, haki stats, DF type/mastery.
  - Combat preview: preview_attack_outcome() in controller returns hit chance, damage, quality, push for attack types.
- Where it lives:
  - engine/combat.py: calculate_hit_chance(), calculate_damage(), get_attack_quality(), get_push_distance().
  - engine/devil_fruit.py: calculate_type_advantage().
  - engine/haki.py: calculate_haki_effectiveness(), calculate_haki_cost().
  - controller.py: Player class with stats, preview_attack_outcome().
- How to test:
  - Enter planning mode, add attack action (quick/normal/heavy).
  - Call preview_attack_outcome(attack_type) to see hit chance, damage, quality, push.
  - Modify player stats to see formula effects (e.g., increase strength → higher damage).
  - Set DF type/mastery to test type advantage scaling.
  - All formulas clamped per spec (hit chance 5-95%, bonuses capped).

Phase 4 Summary (Complete)
- What was added:
  - WallSystem: Wall class with HP, tiers (fragile/standard/reinforced/border), damage tracking, breakthrough.
  - Wall placement: spawn_initial_walls() creates 3-5 random walls with dynamic HP based on avg player stats.
  - Wall blocking: is_wall_blocking() checks if wall blocks movement between tiles.
  - Wall damage: damage_wall() applies damage and removes wall if destroyed.
  - TileSystem: Tile class with types (unpassable, trap_continuous, trap_momentary, drop_continuous, drop_momentary), HP, duration.
  - Tile spawn: spawn_initial_tiles() (2% per type), spawn_per_turn_tiles() (1% per type with caps).
  - Sea Tiles: SeaTile class, _spawn_sea_tiles() with edge groups (1-4 groups per edge, 4-7 tiles each).
  - Tile effects: apply_tile_effect() handles health/stamina restore, debuffs; tiles vanish per spec.
  - Tile blocking: is_tile_blocking_movement() checks unpassable tiles, is_sea_tile_at_edge() for doom detection.
  - Tile damage: damage_tile() applies damage and removes tile if destroyed.
  - Duration tracking: tick_durations() decrements momentary tile timers.
  - Controller integration: wall_system and tile_system initialized with avg_primary_sum for dynamic HP.
- Where it lives:
  - engine/walls.py: Wall class, WallSystem with spawn, damage, blocking.
  - engine/tiles.py: Tile class, SeaTile class, TileSystem with spawn, effects, damage, Sea Tile doom.
  - controller.py: CombatGame.__init__() creates and initializes wall_system and tile_system.
- How to test:
  - Launch game; walls and tiles spawn at start (visible via wall_system.get_visible_walls(), tile_system.get_all_tiles()).
  - Movement blocked by walls (is_wall_blocking) and unpassable tiles.
  - Tiles apply effects when entered (health/stamina restore, debuffs).
  - Sea Tiles at edges block movement and trigger game-over if pushed into.
