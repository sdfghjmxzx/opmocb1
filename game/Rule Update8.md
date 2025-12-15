Cascading Breakthrough

## Logic

- **Scope**: Applies to all attacks that can hit walls (normal attacks, specials, counters), in both attack and defense phases.
- **Line-based model**: For each attack, consider rays (lines) starting from the attacker along the directions covered by the attack pattern.
- **Blocking walls on a line**:
  - Only walls that actually block the path on that line (by orientation and position) participate in cascading breakthrough.
  - Side walls that only "border" the pattern but are not in front of the attacker on that line still take wall damage, but do **not** affect breakthrough propagation along that line.
- **Sequential damage propagation**:
  - For each line and its ordered blocking walls (closest to farthest from attacker), start with `remaining_damage = wall_damage` for that line.
  - For each wall in order:
    - Apply damage to that wall.
    - Let `hp_before` be the wall's HP before the hit.
    - If `remaining_damage >= hp_before`, the wall is destroyed and `remaining_damage = remaining_damage - hp_before`.
    - If `remaining_damage < hp_before`, the wall survives with `hp_after = hp_before - remaining_damage`, `remaining_damage = 0`, and the cascade on this line stops (no breakthrough behind this wall).
  - Walls that are destroyed remain destroyed for the rest of the attack; their HP must not be restored.
- **Breakthrough tile creation**:
  - Breakthrough tiles are created **only behind the last destroyed wall on a line**, and only if `remaining_damage > 0` after processing all blocking walls on that line.
  - For each such line, all tiles strictly behind the last destroyed wall **up to the end of the attack pattern on that line or until the next wall** become breakthrough tiles with stored damage `remaining_damage`.
  - If the cascade stops on a surviving wall (because `remaining_damage` became 0 before destroying it), all tiles behind that surviving wall on that line remain blocked (no breakthrough tiles created beyond it for this attack).
- **Intermediate breakthrough segments**:
  - If there are gaps between blocking walls on a line (e.g., attacker → wall A → several empty tiles → wall B → more tiles), then:
    - After wall A is destroyed with `remaining_damage_A`, tiles between wall A and wall B become breakthrough tiles with damage `remaining_damage_A`.
    - Wall B is then processed with `remaining_damage_A` as its input damage for that line.
    - If wall B is also destroyed and `remaining_damage_B > 0`, new breakthrough tiles are created after wall B with damage `remaining_damage_B`, and so on for further walls.
  - Each breakthrough tile stores the damage value from the stage at which it was created; later walls use only the damage that reaches them, not the original attack damage.
- **Side/bordering walls**:
  - Walls that border an attacked square but are not in front of the attacker on the main ray for that tile take a full `wall_damage` hit independently.
  - These side hits never contribute to cascading breakthrough along the main line; they are just normal wall damage.
- **Preview vs resolution**:
  - During planning (preview), cascading breakthrough must be computed using the current wall HP values **without actually modifying wall HP**.
  - During combat resolution, the same logic is applied but wall HP is updated permanently, and breakthrough tiles are used to decide defender damage.

## Implementation Tasks

1. **Add a non-mutating cascading breakthrough preview calculator**
   - Given: attacker position, attack pattern tiles, wall damage, and current wall HPs.
   - Compute, per line, which tiles become breakthrough tiles and their stored damage using the sequential propagation rules above, without changing wall HP.
   - Use this in `_separate_breakthrough_tiles` so that previewed breakthrough tiles match the final resolution logic.
2. **Refactor wall damage resolution to use cascading propagation**
   - Update `_apply_wall_damage_to_pattern` so it:
     - Groups walls into lines based on attacker position and attack pattern.
     - Applies damage sequentially along each line.
     - Updates wall HP and destruction state according to the cascading rules.
     - Produces a `breakthrough_tiles_damage` map that is consistent with the preview calculator.
3. **Ensure cardinal and diagonal attacks share the same cascade rules**
   - For cardinal directions, use row/column based lines.
   - For diagonals, respect existing diagonal blocking rules and derive lines using the same attacker-to-tile geometry that filtering uses.
   - In all cases, only walls that actually block the path (per existing blocking rules) participate in cascade on that line.
4. **Integrate cascade with counter-attacks**
   - Ensure counter wall damage also uses the same cascading function so that counter-based breakthrough behaves identically to normal attacks.
5. **Maintain and reuse `blocked_tiles_map` correctly**
   - Ensure `blocked_tiles_map` is populated before preview and resolution.
   - After resolution, keep `blocked_tiles_map` consistent with destroyed/surviving walls so later logic sees correct blocked tiles.

## Required Updates

- **`controller.py`**:
  - `_separate_breakthrough_tiles`: switch from simple `wall_damage` threshold logic to the new non-mutating cascading preview calculator.
  - `_apply_wall_damage_to_pattern`: refactor to group walls per line and apply sequential damage propagation, producing `breakthrough_tiles_damage` consistent with the preview.
  - Any helper functions needed to compute line membership and ordering for walls/tiles should live here.
  - Counter-attack handling must call the updated `_apply_wall_damage_to_pattern` with the correct attacker position.
- **`walls.py`**:
  - No functional changes expected, but wall HP/destroy behavior must remain compatible (HP reaching 0 means destroyed and removed, and must not be resurrected later).
- **`screens.rpy`**:
  - No structural changes required if it already uses `breakthrough_squares` / `breakthrough_tiles_damage` from the engine.
  - Visuals should automatically reflect the new cascade behavior once engine data is correct.
- **Documentation**:
  - This `Rule Update8.md` serves as the authoritative spec for cascading breakthrough and should be kept in sync with any future adjustments to the logic.
