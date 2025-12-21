init python:
    import pygame, math, sys, tempfile, subprocess, os
    from controller import CombatGame
    from engine.combat import calculate_hit_chance
    combat_game = CombatGame()

    def get_console_text():
        import builtins
        # Initialize shared console buffer on first load
        if not hasattr(builtins, "_console_buffer"):
            builtins._console_buffer = []
        buffer = builtins._console_buffer

        # Install print hook only once to capture all print output
        if not hasattr(builtins, "_orig_print_for_debug"):
            builtins._orig_print_for_debug = builtins.print

            def _debug_print(*args, **kwargs):
                try:
                    msg = " ".join(str(a) for a in args)
                    end = kwargs.get("end", "\n")
                    buffer.append(msg + ("" if end == "" else end))
                except Exception:
                    pass
                return builtins._orig_print_for_debug(*args, **kwargs)

            builtins.print = _debug_print

        # When called, return the captured console as a single string
        try:
            return "".join(buffer)
        except Exception:
            return ""


    def set_clipboard_via_powershell(text):
        try:
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
            tf.write(text)
            tf.close()
            ps = r"C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
            cmd = [ps, "-NoProfile", "-Command", f"Get-Content -Raw '{tf.name}' | Set-Clipboard"]
            result = subprocess.run(cmd, capture_output=True)
            return result.returncode == 0
        except Exception:
            return False

    def copy_debug_everything_notify():
        try:
            console = get_console_text()
            actions = "\n".join([e["text"] for e in combat_game.get_planned_actions_display()])
            log = "\n".join(combat_game.battle_log)
            payload_parts = []
            if console:
                payload_parts.append("=== Console ===\n" + console.strip())
            payload_parts.append("=== Planned Actions ===\n" + actions)
            payload_parts.append("=== Battle Log ===\n" + log)
            payload = "\n\n".join(payload_parts)
            ok = set_clipboard_via_powershell(payload)
            if ok:
                renpy.notify(f"Copied {len(payload)} chars to OS clipboard")
            else:
                renpy.notify("Copy failed: OS clipboard rejected content")
        except Exception as ex:
            renpy.notify(f"Copy failed: {ex}")

    # Simple zoom helper for Phase 1
    def get_player_zoom(player):
        return 0.12

# Transform for player images
transform player_transform(angle, zoom_level=1.0):
    rotate angle
    zoom zoom_level

screen battle_screen():
    tag game

    # Debug toggle
    key "K_BACKQUOTE" action ToggleScreenVariable("debug_mode")

    # Hover tracking
    default hovered_p1 = False
    default hovered_p2 = False
    default hovered_enemy_in_defense = False
    default wheel_hovered = False
    default hovered_tile = None
    default hovered_wall = None
    # Debug mode flag
    default debug_mode = False

    # LAYER 1: Checkerboard background
    add "checkerboard.png" xalign 0.5 yalign 0.5 zoom 1.05

    # Turn indicator
    frame:
        xalign 0.5
        yalign 0.02
        background "#0743a34b"
        xpadding 20
        ypadding 10
        vbox:
            text f"TURN: {combat_game.get_current_player().name}" size 28 color "#FFFFFF" xalign 0.5
            text f"PHASE: {combat_game.phase.upper()}" size 24 color "#FFFF00" xalign 0.5

    # Player 1 stats
    $ p1 = combat_game.player1
    frame:
        xalign 0.02
        yalign 0.01
        xsize 250
        background "#222233AA"
        xpadding 15
        ypadding 15
        vbox:
            xalign 0.5
            spacing 8
            text "PLAYER 1" size 24 color "#ff4444" xalign 0.5
            hbox:
                spacing 15
                python:
                    max_hp_p1 = getattr(p1, "max_health", 100)
                    hp_display_p1 = int((p1.health / max_hp_p1) * 100) if max_hp_p1 > 0 else 0
                    max_stam_p1 = getattr(p1, "max_stamina", 100)
                    stam_display_p1 = int((p1.stamina / max_stam_p1) * 100) if max_stam_p1 > 0 else 0
                text f"Health: {hp_display_p1}" size 15 color "#FFFF00"
                text f"Stamina: {stam_display_p1}" size 15 color "#FFFF00"
            hbox:
                spacing 15
                text f"Haki: {int(p1.haki_stamina)}" size 15 color "#FF00FF"
                python:
                    max_df_p1 = p1._calculate_max_df_stamina()
                    df_display_p1 = int((p1.devil_fruit_stamina / max_df_p1) * 100) if max_df_p1 > 0 else 0
                text f"DF Sta: {df_display_p1}" size 15 color "#00FFFF"
            hbox:
                spacing 15
                text f"Position: {p1.get_position_str()}" size 15 color "#FFFF00"
                text f"Facing: {p1.facing}°" size 15 color "#FFFF00"
            # Active Effects Display
            python:
                p1_effects = combat_game.active_effects.get(p1.name, [])
                # Load effect config
                import json
                effect_types_config = {}
                effect_categories_config = {}
                try:
                    with open("game/data/effect_types.json", "r") as f:
                        effect_types_config = json.load(f).get("effect_types", {})
                    with open("game/data/effect_categories.json", "r") as f:
                        effect_categories_config = json.load(f).get("effect_categories", {})
                except:
                    pass
            if p1_effects:
                text "Effects:" size 14 color "#FFFF00" xalign 0.5
                vbox:
                    spacing 2
                    for effect in p1_effects:
                        python:
                            # Get config for this effect type
                            type_config = effect_types_config.get(effect.effect_type, {})
                            cat_config = effect_categories_config.get(effect.category, {})
                            
                            # Count stacks
                            stack_count = sum(1 for e in p1_effects if e.effect_type == effect.effect_type and e.category == effect.category)
                            stack_display = f" x{stack_count}" if stack_count > 1 else ""
                            
                            # Get format template
                            format_template = type_config.get("stats_box_format", "{emoji} {type} {category}: {magnitude} [{duration}t]{stacks}")
                            
                            # Build replacements
                            emoji = type_config.get("emoji", "")
                            type_name = effect.effect_type.capitalize()
                            category_name = cat_config.get("display_name", effect.category)
                            
                            # Format text (replace {icon} with empty for text-only display)
                            effect_text = format_template.replace("{emoji}", emoji).replace("{icon}", "").replace("{type}", type_name).replace("{category}", category_name).replace("{magnitude}", str(effect.magnitude)).replace("{duration}", str(effect.duration)).replace("{stacks}", stack_display)
                            
                            # Get icon image if specified
                            icon_image = type_config.get("icon_image", None)
                        
                        hbox:
                            spacing 3
                            if icon_image:
                                add icon_image:
                                    xsize 16
                                    ysize 16
                            text "[effect_text]" size 12 color "#FF8800" xalign 0.0

    # Player 2 stats
    $ p2 = combat_game.player2
    frame:
        xalign 0.98
        yalign 0.01
        xsize 250
        background "#222233AA"
        xpadding 15
        ypadding 15
        vbox:
            xalign 0.5
            spacing 8
            text "PLAYER 2" size 24 color "#4444FF" xalign 0.5
            hbox:
                spacing 15
                python:
                    max_hp_p2 = getattr(p2, "max_health", 100)
                    hp_display_p2 = int((p2.health / max_hp_p2) * 100) if max_hp_p2 > 0 else 0
                    max_stam_p2 = getattr(p2, "max_stamina", 100)
                    stam_display_p2 = int((p2.stamina / max_stam_p2) * 100) if max_stam_p2 > 0 else 0
                text f"Health: {hp_display_p2}" size 15 color "#FFFF00"
                text f"Stamina: {stam_display_p2}" size 15 color "#FFFF00"
            hbox:
                spacing 15
                text f"Haki: {int(p2.haki_stamina)}" size 15 color "#FF00FF"
                python:
                    max_df = p2._calculate_max_df_stamina()
                    df_display = int((p2.devil_fruit_stamina / max_df) * 100) if max_df > 0 else 0
                text f"DF Sta: {df_display}" size 15 color "#00FFFF"
            hbox:
                spacing 15
                text f"Position: {p2.get_position_str()}" size 15 color "#FFFF00"
                text f"Facing: {p2.facing}°" size 15 color "#FFFF00"
            # Active Effects Display
            python:
                p2_effects = combat_game.active_effects.get(p2.name, [])
                # Load effect config
                import json
                effect_types_config = {}
                effect_categories_config = {}
                try:
                    with open("game/data/effect_types.json", "r") as f:
                        effect_types_config = json.load(f).get("effect_types", {})
                    with open("game/data/effect_categories.json", "r") as f:
                        effect_categories_config = json.load(f).get("effect_categories", {})
                except:
                    pass
            if p2_effects:
                text "Effects:" size 14 color "#FFFF00" xalign 0.5
                vbox:
                    spacing 2
                    for effect in p2_effects:
                        python:
                            # Get config for this effect type
                            type_config = effect_types_config.get(effect.effect_type, {})
                            cat_config = effect_categories_config.get(effect.category, {})
                            
                            # Count stacks
                            stack_count = sum(1 for e in p2_effects if e.effect_type == effect.effect_type and e.category == effect.category)
                            stack_display = f" x{stack_count}" if stack_count > 1 else ""
                            
                            # Get format template
                            format_template = type_config.get("stats_box_format", "{emoji} {type} {category}: {magnitude} [{duration}t]{stacks}")
                            
                            # Build replacements
                            emoji = type_config.get("emoji", "")
                            type_name = effect.effect_type.capitalize()
                            category_name = cat_config.get("display_name", effect.category)
                            
                            # Format text (replace {icon} with empty for text-only display)
                            effect_text = format_template.replace("{emoji}", emoji).replace("{icon}", "").replace("{type}", type_name).replace("{category}", category_name).replace("{magnitude}", str(effect.magnitude)).replace("{duration}", str(effect.duration)).replace("{stacks}", stack_display)
                            
                            # Get icon image if specified
                            icon_image = type_config.get("icon_image", None)
                        
                        hbox:
                            spacing 3
                            if icon_image:
                                add icon_image:
                                    xsize 16
                                    ysize 16
                            text "[effect_text]" size 12 color "#FF8800" xalign 0.0

    # LAYER 2: Board with transparent squares (checkerboard shows through)
    $ square_size = 80
    $ spacing = 3
    $ board_start_x = int(1234/2 - (7 * (square_size + spacing) - spacing) / 2)
    $ board_start_y = int(678/2 - (7 * (square_size + spacing) - spacing) / 2)

    # GRID OVERLAY: Rows, Columns, and Diagonal lines
    if debug_mode:
        python:
            # Draw vertical lines (columns 0-6)
            for col in range(7):
                x = int(925 + (col - 3) * (square_size + spacing) + square_size/2)
                y1 = int(510 + (0 - 3) * (square_size + spacing) + square_size/2)
                y2 = int(510 + (6 - 3) * (square_size + spacing) + square_size/2)
        for col in range(7):
            $ x = int(925 + (col - 3) * (square_size + spacing) + square_size/2)
            $ y1 = int(510 + (0 - 3) * (square_size + spacing) + square_size/2)
            $ y2 = int(510 + (6 - 3) * (square_size + spacing) + square_size/2)
            add Solid("#FFFFFF40"):
                xysize (1, abs(y2 - y1))
                pos (x, min(y1, y2))
        
        # Draw horizontal lines (rows 0-6)
        for row in range(7):
            $ y = int(510 + (row - 3) * (square_size + spacing) + square_size/2)
            $ x1 = int(925 + (0 - 3) * (square_size + spacing) + square_size/2)
            $ x2 = int(925 + (6 - 3) * (square_size + spacing) + square_size/2)
            add Solid("#FFFFFF40"):
                xysize (abs(x2 - x1), 1)
                pos (min(x1, x2), y)
        
        # Draw NE-SW diagonal lines (row + col = constant)
        python:
            ne_sw_segments = []
            for s in range(0, 13):
                coords = [(r, c) for r in range(7) for c in range(7) if r + c == s]
                coords.sort()  # Sort by row first, then col
                for i in range(len(coords) - 1):
                    r1, c1 = coords[i]
                    r2, c2 = coords[i + 1]
                    sx = int(925 + (c1 - 3) * (square_size + spacing) + square_size/2)
                    sy = int(510 + (r1 - 3) * (square_size + spacing) + square_size/2)
                    tx = int(925 + (c2 - 3) * (square_size + spacing) + square_size/2)
                    ty = int(510 + (r2 - 3) * (square_size + spacing) + square_size/2)
                    ne_sw_segments.append((sx, sy, tx, ty))
        for sx, sy, tx, ty in ne_sw_segments:
            $ dx = tx - sx
            $ dy = ty - sy
            $ steps = max(abs(dx), abs(dy))
            for step in range(steps + 1):
                $ t = step / float(steps) if steps > 0 else 0
                $ px = int(sx + dx * t)
                $ py = int(sy + dy * t)
                add Solid("#FFFF0080"):
                    xysize (2, 2)
                    pos (px - 1, py - 1)
        
        # Draw NW-SE diagonal lines (row - col = constant)
        python:
            nw_se_segments = []
            for d in range(-6, 7):
                coords = [(r, c) for r in range(7) for c in range(7) if r - c == d]
                coords.sort()  # Sort by row first, then col
                for i in range(len(coords) - 1):
                    r1, c1 = coords[i]
                    r2, c2 = coords[i + 1]
                    sx = int(925 + (c1 - 3) * (square_size + spacing) + square_size/2)
                    sy = int(510 + (r1 - 3) * (square_size + spacing) + square_size/2)
                    tx = int(925 + (c2 - 3) * (square_size + spacing) + square_size/2)
                    ty = int(510 + (r2 - 3) * (square_size + spacing) + square_size/2)
                    nw_se_segments.append((sx, sy, tx, ty))
        for sx, sy, tx, ty in nw_se_segments:
            $ dx = tx - sx
            $ dy = ty - sy
            $ steps = max(abs(dx), abs(dy))
            for step in range(steps + 1):
                $ t = step / float(steps) if steps > 0 else 0
                $ px = int(sx + dx * t)
                $ py = int(sy + dy * t)
                add Solid("#00FFFF80"):
                    xysize (2, 2)
                    pos (px - 1, py - 1)
    
    frame:
        xalign 0.50
        yalign 0.505
        background "#00000000"
        vbox:
            spacing 3
            for row in range(7):
                hbox:
                    spacing 3
                    for col in range(7):
                        $ pos_str = f"{row+1}{chr(65+col)}"
                        $ board_state = combat_game.get_board_state()
                        # Hide all UI elements when hovering enemy in defensive planning mode
                        $ is_highlighted = ((row, col) in combat_game.highlighted_squares and not combat_game.wall_mode) if not hovered_enemy_in_defense else False
                        $ is_in_path = (row, col) in combat_game.current_path if not hovered_enemy_in_defense else False
                        $ is_last_in_path = (combat_game.current_path and (row, col) == combat_game.current_path[-1]) if not hovered_enemy_in_defense else False
                        # When hovering enemy in defensive planning, show only enemy attack pattern
                        $ is_attack_highlighted = (row, col) in combat_game.attack_highlighted_squares if not hovered_enemy_in_defense else False
                        $ is_breakthrough = (row, col) in combat_game.breakthrough_squares if not hovered_enemy_in_defense else False
                        $ is_wall_placement = (row, col) in board_state.get('wall_placement_tiles', []) if not hovered_enemy_in_defense else False
                        $ is_wall_first_tile = (board_state.get('wall_first_tile') == (row, col)) if not hovered_enemy_in_defense else False
                        $ is_tile_placement = (row, col) in board_state.get('tile_placement_tiles', []) if not hovered_enemy_in_defense else False
                        $ is_tile_planned = (board_state.get('tile_planned_position') == (row, col)) if not hovered_enemy_in_defense else False
                        # Enemy attack pattern when hovering in defensive mode
                        $ is_enemy_attack = False
                        $ is_enemy_breakthrough = False
                        python:
                            if hovered_enemy_in_defense and combat_game.phase == "defense" and combat_game.planning_mode and combat_game.pending_attack:
                                from controller import CombatGame
                                
                                # Use latest calculated enemy pattern (stored in enemy_attack_tiles/enemy_breakthrough_tiles)
                                normal_attack_tiles = getattr(combat_game, 'enemy_attack_tiles', [])
                                breakthrough_tiles = getattr(combat_game, 'enemy_breakthrough_tiles', [])
                                
                                print(f"\n[ENEMY HOVER DEBUG] Normal attack tiles: {len(normal_attack_tiles)}")
                                print(f"[ENEMY HOVER DEBUG] Breakthrough tiles: {len(breakthrough_tiles)} = {breakthrough_tiles}")
                                print(f"[ENEMY HOVER DEBUG] Current tile ({row},{col}): attack={((row,col) in normal_attack_tiles)}, breakthrough={((row,col) in breakthrough_tiles)}\n")
                                
                                is_enemy_attack = (row, col) in normal_attack_tiles
                                is_enemy_breakthrough = (row, col) in breakthrough_tiles
                        $ bg_color = "#4182b100"
                        if is_enemy_attack:
                            $ bg_color = "#ff000024"  # Red for enemy blocked attack tiles
                        elif is_enemy_breakthrough:
                            $ bg_color = "#8b00ff24"  # Violet for enemy breakthrough tiles
                        elif is_wall_first_tile:
                            $ bg_color = "#00ff0040"  # Green for first selected wall tile
                        elif is_wall_placement:
                            $ bg_color = "#00ffff20"  # Cyan for wall placement tiles
                        elif is_tile_placement:
                            $ bg_color = "#00ffff20"  # Cyan for tile placement tiles
                        elif is_attack_highlighted:
                            $ bg_color = "#ff000024"
                        elif is_breakthrough:
                            $ bg_color = "#8b00ff24"  # Violet for breakthrough tiles
                        elif is_highlighted:
                            $ bg_color = "#ffff0000"
                        elif is_in_path:
                            if is_last_in_path:
                                $ bg_color = "#ff001e00"
                            else:
                                $ bg_color = "#01ff0100"
                        frame:
                            background bg_color
                            xsize square_size
                            ysize square_size
                            
                            # Add image overlays based on state
                            if is_enemy_attack:
                                add "attack_circle.png":
                                    xalign 0.5 yalign 0.5
                                    size (70, 70)
                                    alpha 0.8
                            elif is_enemy_breakthrough:
                                add "attack_circle.png":
                                    xalign 0.5 yalign 0.5
                                    size (70, 70)
                                    alpha 0.8
                            elif is_attack_highlighted:
                                add "attack_circle.png":
                                    xalign 0.5 yalign 0.5
                                    size (70, 70)
                                    alpha 0.8
                            elif is_breakthrough:
                                add "attack_circle.png":
                                    xalign 0.5 yalign 0.5
                                    size (70, 70)
                                    alpha 0.8
                            elif is_in_path and not is_last_in_path:
                                add "path_circle.png":
                                    xalign 0.5 yalign 0.5
                                    size (50, 50)
                                    alpha 0.5
                            elif is_last_in_path:
                                add "active_circle.png":
                                    xalign 0.7 yalign 0.7
                                    size (65, 65)
                                    alpha 0.7
                            elif is_tile_placement:
                                add "avalable_circle.png":
                                    xalign 0.5 yalign 0.5
                                    size (45, 45)
                                    alpha 0.5
                            elif is_wall_placement:
                                add "avalable_circle.png":
                                    xalign 0.5 yalign 0.5
                                    size (45, 45)
                                    alpha 0.5
                            elif is_highlighted:
                                add "avalable_circle.png":
                                    xalign 0.5 yalign 0.5
                                    size (45, 45)
                                    alpha 0.5
                            
                            # Show planned tile image if tile is planned at this position (even when tile_mode is off)
                            if is_tile_planned and combat_game.planned_tile_creation:
                                python:
                                    tile_config = combat_game.planned_tile_creation.get("tile_config", {})
                                    tile_type_map = tile_config.get("tile_type", "trap_continuous")
                                    tile_image = f"tile_{tile_type_map}.png"
                                add tile_image:
                                    xalign 0.5 yalign 0.5
                                    size (square_size - 3, square_size - 3)
                                    alpha 0.8
                                # Only allow repositioning if still in tile mode
                                if combat_game.tile_mode:
                                    button:
                                        action Function(handle_tile_click, row, col)
                                        background None
                                        xfill True
                                        yfill True
                            elif is_tile_placement and combat_game.tile_mode:
                                button:
                                    action Function(handle_tile_click, row, col)
                                    background None
                                    xfill True
                                    yfill True
                                    text pos_str size 14 color "#00000000" align (0.5, 0.5)
                            elif (is_wall_placement or is_wall_first_tile) and combat_game.wall_mode == "conjure":
                                button:
                                    action Function(combat_game.select_wall_tile, row, col)
                                    background None
                                    xfill True
                                    yfill True
                                    text pos_str size 14 color "#00000000" align (0.5, 0.5)
                            elif is_highlighted and combat_game.movement_mode:
                                button:
                                    action Function(combat_game.add_to_path, row, col)
                                    background None
                                    xfill True
                                    yfill True
                                    text pos_str size 14 color "#00000000" align (0.5, 0.5)
                            elif is_last_in_path and combat_game.movement_mode:
                                button:
                                    action Function(combat_game.remove_last_step)
                                    background None
                                    xfill True
                                    yfill True
                                    text pos_str size 14 color "#ffffff00" align (0.5, 0.5)
                            else:
                                text pos_str size 14 color "#ffffff00" align (0.5, 0.5)
    
    # LAYER 3.4: Debug HUD marker (to confirm debug overlay is active)
    if combat_game.planning_mode and debug_mode:
        text "GRID DEBUG ACTIVE" size 16 color "#FF00FF" xpos 10 ypos 200

    # LAYER 3.5: Debug Field Overlay (Front/Back/Left/Right)
    if combat_game.planning_mode and debug_mode:
        python:
            attacker = combat_game.get_current_player()
            base_row = combat_game.ghost_row if combat_game.ghost_row is not None else attacker.row
            base_col = combat_game.ghost_col if combat_game.ghost_col is not None else attacker.col
            base_facing = combat_game.ghost_facing if combat_game.ghost_facing is not None else attacker.facing
        for row in range(7):
            for col in range(7):
                python:
                    field = combat_game._classify_tile_field(base_row, base_col, base_facing, row, col)
                    if field == "Front":
                        field_color = "#00FF00"  # Green
                    elif field == "Back":
                        field_color = "#FFFF00"  # Yellow
                    elif field == "Left":
                        field_color = "#FFA500"  # Orange
                    elif field == "Right":
                        field_color = "#00FFFF"  # Light Blue
                    else:
                        field_color = None
                    tile_x = int(925 + (col - 3) * (square_size + spacing) + square_size/2)
                    tile_y = int(510 + (row - 3) * (square_size + spacing) + square_size/2)
                if field_color:
                    text field[0]:
                        size 14
                        color field_color
                        xpos tile_x
                        ypos tile_y
                        xanchor 0.1
                        yanchor 0.1
                        outlines [(2, "#000000", 0, 0)]

    # LAYER 3.6: Debug Ray Overlay (divider sources → tiles)
    if combat_game.planning_mode and debug_mode:
        python:
            debug_rays = getattr(combat_game, "debug_rays", [])
        for src_row, src_col, tile_row, tile_col in debug_rays:
            $ sx = int(925 + (src_col - 3) * (square_size + spacing) + square_size/2)
            $ sy = int(510 + (src_row - 3) * (square_size + spacing) + square_size/2)
            $ tx = int(925 + (tile_col - 3) * (square_size + spacing) + square_size/2)
            $ ty = int(510 + (tile_row - 3) * (square_size + spacing) + square_size/2)
            $ dx = tx - sx
            $ dy = ty - sy
            $ steps = max(abs(dx), abs(dy))
            for step in range(steps + 1):
                $ t = step / float(steps) if steps > 0 else 0
                $ px = int(sx + dx * t)
                $ py = int(sy + dy * t)
                add Solid("#FF00FF80"):
                    xysize (2, 2)
                    pos (px - 1, py - 1)


    # LAYER 3.8: Divider Overlay (dividers through attacker - mode-specific)
    if combat_game.planning_mode and debug_mode:
        python:
            attacker = combat_game.get_current_player()
            ghost_facing = combat_game.ghost_facing if combat_game.ghost_facing is not None else attacker.facing
            base_row = combat_game.ghost_row if combat_game.ghost_row is not None else attacker.row
            base_col = combat_game.ghost_col if combat_game.ghost_col is not None else attacker.col
            # Check if facing is diagonal (45, 135, 225, 315)
            is_diagonal = (ghost_facing % 90) == 45
        
        if not is_diagonal:
            python:
                USE_AXIS_CARDINAL_DIVIDERS = True
            if USE_AXIS_CARDINAL_DIVIDERS:
                python:
                    # Cardinal facing: build axis-aligned divider segments along field boundaries
                    # FL/FR = boundaries between Front and Left/Right fields
                    # BL/BR = boundaries between Back and Left/Right fields
                    color_by_role = {"FL": "#0000FFFF", "FR": "#FF0000FF", "BR": "#FFFF00FF", "BL": "#FF00FFFF"}
                    divider_segments = {"FL": [], "FR": [], "BR": [], "BL": []}

                    def tile_center(row, col):
                        # Local constants to avoid relying on outer screen variables
                        tile_size = 80
                        tile_spacing = 3
                        x = int(925 + (col - 3) * (tile_size + tile_spacing) + tile_size/2)
                        y = int(510 + (row - 3) * (tile_size + tile_spacing) + tile_size/2)
                        return x, y

                    # Vertical boundaries between (r,c) and (r,c+1)
                    for r in range(7):
                        for c in range(6):
                            f1 = combat_game._classify_tile_field(base_row, base_col, float(ghost_facing), r, c)
                            f2 = combat_game._classify_tile_field(base_row, base_col, float(ghost_facing), r, c + 1)
                            fields = {f1, f2}
                            role = None
                            if fields == {"Front", "Left"}:
                                role = "FL"
                            elif fields == {"Front", "Right"}:
                                role = "FR"
                            elif fields == {"Back", "Left"}:
                                role = "BL"
                            elif fields == {"Back", "Right"}:
                                role = "BR"
                            if role is not None:
                                x1, y1 = tile_center(r, c)
                                x2, _ = tile_center(r, c + 1)
                                sx = int((x1 + x2) / 2)
                                half_h = int(80 / 2)
                                sy = y1 - half_h
                                ty = y1 + half_h
                                divider_segments[role].append((sx, sy, sx, ty))

                    # Horizontal boundaries between (r,c) and (r+1,c)
                    for r in range(6):
                        for c in range(7):
                            f1 = combat_game._classify_tile_field(base_row, base_col, float(ghost_facing), r, c)
                            f2 = combat_game._classify_tile_field(base_row, base_col, float(ghost_facing), r + 1, c)
                            fields = {f1, f2}
                            role = None
                            if fields == {"Front", "Left"}:
                                role = "FL"
                            elif fields == {"Front", "Right"}:
                                role = "FR"
                            elif fields == {"Back", "Left"}:
                                role = "BL"
                            elif fields == {"Back", "Right"}:
                                role = "BR"
                            if role is not None:
                                x1, y1 = tile_center(r, c)
                                x2, y2 = tile_center(r + 1, c)
                                sy = int((y1 + y2) / 2)
                                half_w = int(80 / 2)
                                sx = x1 - half_w
                                tx = x1 + half_w
                                divider_segments[role].append((sx, sy, tx, sy))

                # Draw axis-aligned divider segments per role
                for role, segments in divider_segments.items():
                    $ color = color_by_role.get(role, "#808080FF")
                    for sx, sy, tx, ty in segments:
                        $ dx = tx - sx
                        $ dy = ty - sy
                        $ steps = max(abs(dx), abs(dy))
                        for step in range(steps + 1):
                            $ t = step / float(steps) if steps > 0 else 0
                            $ px_diag = int(sx + dx * t)
                            $ py_diag = int(sy + dy * t)
                            add Solid(color):
                                xysize (3, 3)
                                pos (px_diag - 1, py_diag - 1)

            else:
            # CARDINAL (fallback): Show ALL 4 diagonal dividers (original geometry)
                python:
                    import math
                    norm_facing = ghost_facing % 360
                    
                    # Calculate all 4 diagonal dividers from player position
                    ne_diff = base_row - base_col
                    ne_points = []
                    for r in range(base_row, -1, -1):
                        c = r - ne_diff
                        if 0 <= c < 7:
                            px = int(925 + (c - 3) * (square_size + spacing) + square_size/2)
                            py = int(510 + (r - 3) * (square_size + spacing) + square_size/2)
                            ne_points.append((px, py))
                    
                    nw_sum = base_row + base_col
                    nw_points = []
                    for r in range(base_row, -1, -1):
                        c = nw_sum - r
                        if 0 <= c < 7:
                            px = int(925 + (c - 3) * (square_size + spacing) + square_size/2)
                            py = int(510 + (r - 3) * (square_size + spacing) + square_size/2)
                            nw_points.append((px, py))
                    
                    se_points = []
                    for r in range(base_row, 7):
                        c = r - ne_diff
                        if 0 <= c < 7:
                            px = int(925 + (c - 3) * (square_size + spacing) + square_size/2)
                            py = int(510 + (r - 3) * (square_size + spacing) + square_size/2)
                            se_points.append((px, py))
                    
                    sw_points = []
                    for r in range(base_row, 7):
                        c = nw_sum - r
                        if 0 <= c < 7:
                            px = int(925 + (c - 3) * (square_size + spacing) + square_size/2)
                            py = int(510 + (r - 3) * (square_size + spacing) + square_size/2)
                            sw_points.append((px, py))
                    
                    # Compute stable colors per divider relative to facing (blue=FL, red=FR, yellow=BR, magenta=BL)
                    diag_points = [("NE", nw_points), ("SE", se_points), ("SW", sw_points), ("NW", ne_points)]
                    # Cardinal facing mapping: norm_facing in {0(E),90(S),180(W),270(N)}
                    q = int((norm_facing % 360) / 90) % 4  # 0=E,1=S,2=W,3=N
                    fr_idx = (q + 1) % 4
                    fl_idx = (fr_idx - 1) % 4
                    br_idx = (fr_idx + 1) % 4
                    bl_idx = (fr_idx + 2) % 4
                    color_by_role = {"FL": "#0000FFFF", "FR": "#FF0000FF", "BR": "#FFFF00FF", "BL": "#FF00FFFF"}
                    all_dividers = []
                    for idx, (label, pts) in enumerate(diag_points):
                        if idx == fl_idx:
                            role = "FL"
                        elif idx == fr_idx:
                            role = "FR"
                        elif idx == br_idx:
                            role = "BR"
                        elif idx == bl_idx:
                            role = "BL"
                        else:
                            role = ""
                        color = color_by_role.get(role, "#808080FF")
                        all_dividers.append((pts, color))
                
                # Draw all 4 diagonal dividers
                for divider_points, color in all_dividers:
                    for i in range(len(divider_points) - 1):
                        $ sx, sy = divider_points[i]
                        $ tx, ty = divider_points[i + 1]
                        $ dx = tx - sx
                        $ dy = ty - sy
                        $ steps = max(abs(dx), abs(dy))
                        for step in range(steps + 1):
                            $ t = step / float(steps) if steps > 0 else 0
                            $ px_diag = int(sx + dx * t)
                            $ py_diag = int(sy + dy * t)
                            add Solid(color):
                                xysize (3, 3)
                                pos (px_diag - 1, py_diag - 1)
        else:
            # DIAGONAL: Show ALL 4 cardinal dividers (fixed geometry), colors reflect Front vs Back for current facing
            python:
                norm_facing = ghost_facing % 360
                
                # Calculate horizontal and vertical dividers from player position
                h_left_points = []
                for c in range(base_col, -1, -1):
                    px = int(925 + (c - 3) * (square_size + spacing) + square_size/2)
                    py = int(510 + (base_row - 3) * (square_size + spacing) + square_size/2)
                    h_left_points.append((px, py))
                h_right_points = []
                for c in range(base_col, 7):
                    px = int(925 + (c - 3) * (square_size + spacing) + square_size/2)
                    py = int(510 + (base_row - 3) * (square_size + spacing) + square_size/2)
                    h_right_points.append((px, py))
                
                v_up_points = []
                for r in range(base_row, -1, -1):
                    px = int(925 + (base_col - 3) * (square_size + spacing) + square_size/2)
                    py = int(510 + (r - 3) * (square_size + spacing) + square_size/2)
                    v_up_points.append((px, py))
                v_down_points = []
                for r in range(base_row, 7):
                    px = int(925 + (base_col - 3) * (square_size + spacing) + square_size/2)
                    py = int(510 + (r - 3) * (square_size + spacing) + square_size/2)
                    v_down_points.append((px, py))
                
                # Compute stable colors per divider relative to diagonal facing (blue=FL, red=FR, yellow=BR, magenta=BL)
                card_points = [("E", h_right_points), ("S", v_down_points), ("W", h_left_points), ("N", v_up_points)]
                # Diagonal facing mapping: norm_facing in {315(NE),45(SE),135(SW),225(NW)}
                fr_idx_map = {315: 0, 45: 1, 135: 2, 225: 3}  # index into [E,S,W,N]
                fr_idx = fr_idx_map.get(int(norm_facing) % 360, 0)
                fl_idx = (fr_idx - 1) % 4
                br_idx = (fr_idx + 1) % 4
                bl_idx = (fr_idx + 2) % 4
                color_by_role = {"FL": "#0000FFFF", "FR": "#FF0000FF", "BR": "#FFFF00FF", "BL": "#FF00FFFF"}
                all_dividers = []
                for idx, (label, pts) in enumerate(card_points):
                    if idx == fl_idx:
                        role = "FL"
                    elif idx == fr_idx:
                        role = "FR"
                    elif idx == br_idx:
                        role = "BR"
                    elif idx == bl_idx:
                        role = "BL"
                    else:
                        role = ""
                    color = color_by_role.get(role, "#808080FF")
                    all_dividers.append((pts, color))
            
            # Draw all 4 cardinal dividers
            for divider_points, color in all_dividers:
                for i in range(len(divider_points) - 1):
                    $ sx, sy = divider_points[i]
                    $ tx, ty = divider_points[i + 1]
                    $ dx = tx - sx
                    $ dy = ty - sy
                    $ steps = max(abs(dx), abs(dy))
                    for step in range(steps + 1):
                        $ t = step / float(steps) if steps > 0 else 0
                        $ px_diag = int(sx + dx * t)
                        $ py_diag = int(sy + dy * t)
                        add Solid(color):
                            xysize (3, 3)
                            pos (px_diag - 1, py_diag - 1)

    # LAYER 4: Tiles Visualization (permanent tiles from tile_system)
    $ tile_config_data = {}
    python:
        try:
            import json
            with open("game/data/tile_config.json", "r") as f:
                tile_config_data = json.load(f).get("tile_types", {})
        except:
            tile_config_data = {}
    
    # LAYER 3.8: Sea Tiles Visualization (edge water around board)
    python:
        sea_image = tile_config_data.get("sea_tile", {}).get("image", "tile_sea.png")
        sea_tiles = combat_game.tile_system.get_sea_tiles()
        sea_sprites = []
        sea_offset = 40  # Adjust this value to move all sea tiles relative to grid center
        for edge, pos in sea_tiles:
            rotation = 0
            # Handle corners
            if edge.startswith('corner_'):
                # Decode: row*10 + col
                corner_row = pos // 10
                corner_col = pos % 10
                sea_x = int(925 + (corner_col - 3) * (square_size + spacing) + square_size/2)
                sea_y = int(510 + (corner_row - 3) * (square_size + spacing) + square_size/2)
                # Corner rotation based on which corner
                if 'north' in edge and 'west' in edge:
                    rotation = -45
                    sea_x -= sea_offset
                    sea_y -= sea_offset
                elif 'north' in edge and 'east' in edge:
                    rotation = 45
                    sea_x += sea_offset
                    sea_y -= sea_offset
                elif 'south' in edge and 'west' in edge:
                    rotation = -135
                    sea_x -= sea_offset
                    sea_y += sea_offset
                elif 'south' in edge and 'east' in edge:
                    rotation = 135
                    sea_x += sea_offset
                    sea_y += sea_offset
            elif edge in ('north', 'south'):
                sea_row = 0 if edge == 'north' else 6
                sea_col = pos
                sea_x = int(925 + (sea_col - 3) * (square_size + spacing) + square_size/2)
                sea_y = int(510 + (sea_row - 3) * (square_size + spacing) + square_size/2)
                if edge == 'north':
                    sea_y -= sea_offset + 10
                    rotation = 0
                else:
                    sea_y += sea_offset - 10
                    rotation = 180
            else:
                sea_row = pos
                sea_col = 0 if edge == 'west' else 6
                sea_x = int(925 + (sea_col - 3) * (square_size + spacing) + square_size/2)
                sea_y = int(510 + (sea_row - 3) * (square_size + spacing) + square_size/2)
                if edge == 'west':
                    sea_x -= sea_offset
                    rotation = -90
                else:
                    sea_x += sea_offset
                    rotation = 90
            sea_sprites.append((sea_x, sea_y, rotation))
    for sea_x, sea_y, rotation in sea_sprites:
        add Transform(sea_image, rotate=rotation, xsize=square_size, fit="contain", alpha=0.7):
            xpos sea_x
            ypos sea_y
            anchor (0.5, 0.5)
    
    for tile_info in combat_game.tile_system.get_all_tiles_with_hp():
        $ tile_row, tile_col, tile_type, tile_hp, tile_max_hp = tile_info
        # Using same coordinate system as players
        $ tile_x = int(925 + (tile_col - 3) * (square_size + spacing) + square_size/2)
        $ tile_y = int(510 + (tile_row - 3) * (square_size + spacing) + square_size/2)
        
        # Get tile image from config
        python:
            tile_img = tile_config_data.get(tile_type, {}).get("image", f"tile_{tile_type}.png")
        
        if combat_game.wall_mode == "conjure":
            add Transform(tile_img, xysize=(square_size - 3, square_size - 3), alpha=0.8):
                xpos tile_x
                ypos tile_y
                anchor (0.55, 0.59)
        else:
            imagebutton:
                idle Transform(tile_img, xysize=(square_size - 3, square_size - 3), alpha=0.8)
                hover Transform(tile_img, xysize=(square_size - 3, square_size - 3), alpha=0.8)
                xpos tile_x
                ypos tile_y
                anchor (0.55, 0.59)
                action NullAction()
                hovered SetScreenVariable("hovered_tile", (tile_row, tile_col))
                unhovered SetScreenVariable("hovered_tile", None)
        
        # HP display for destructible tiles
        if tile_hp > 0 and tile_max_hp > 0:
            $ hp_text = f"{tile_hp}/{tile_max_hp}"
            $ hp_color = "#00FF00" if tile_hp > tile_max_hp * 0.66 else ("#FFFF00" if tile_hp > tile_max_hp * 0.33 else "#FF0000")
            # Show HP: always in planning mode, only on hover when not in planning
            $ show_hp = combat_game.planning_mode or (hovered_tile == (tile_row, tile_col))
            if show_hp:
                text hp_text:
                    size 14
                    color hp_color
                    xpos tile_x
                    ypos tile_y - 20
                    xanchor 0.5
                    yanchor 0.5
                    outlines [(2, "#000000", 0, 0)]
    
    # LAYER 4.5: Planned Tile Visualization (like walls, shown during planning before confirmation)
    if combat_game.planned_tile_creation:
        python:
            planned_tile = combat_game.planned_tile_creation
            tile_row = planned_tile["row"]
            tile_col = planned_tile["col"]
            tile_config = planned_tile.get("tile_config", {})
            tile_type_map = tile_config.get("tile_type", "trap_continuous")
            # Get image from config or fallback
            tile_image = tile_config_data.get(tile_type_map, {}).get("image", f"tile_{tile_type_map}.png")
            tile_x = int(925 + (tile_col - 3) * (square_size + spacing) + square_size/2)
            tile_y = int(510 + (tile_row - 3) * (square_size + spacing) + square_size/2)
        
        add tile_image:
            xpos tile_x
            ypos tile_y
            anchor (0.55, 0.59)
            xsize square_size - 3
            ysize square_size - 3
            alpha 0.8
        
        # HP display for planned tile (use max HP from config)
        python:
            hp_range = tile_config.get("hp_range", [100, 100])
            if isinstance(hp_range, list) and len(hp_range) >= 2:
                planned_hp = hp_range[1]  # Use max HP
            else:
                planned_hp = 100
        
        if planned_hp > 0:
            $ hp_text = f"{planned_hp}/{planned_hp}"
            text hp_text:
                size 14
                color "#00FF00"
                xpos tile_x
                ypos tile_y - 20
                xanchor 0.5
                yanchor 0.5
                outlines [(2, "#000000", 0, 0)]

    # Wheel & drag (fixed to active square) - DISABLED IN WALL MODE AND TILE MODE
    if combat_game.planning_mode and combat_game.current_path and not combat_game.wall_mode and not combat_game.tile_mode:
        $ active_tile = combat_game.current_path[-1]
        $ active_row, active_col = active_tile
        $ wheel_rotation = combat_game.get_wheel_rotation()
        $ wheel_x = int(925 + (active_col - 3) * (square_size + spacing) + square_size/2)
        $ wheel_y = int(510 + (active_row - 3) * (square_size + spacing) + square_size/2)
        $ wheel_enabled = not combat_game.planning_terminal
        button:
            xpos wheel_x - 50
            ypos wheel_y - 50
            xsize 100
            ysize 100
            background Solid("#00000001")
            action NullAction()
            mouse "pointer"
            sensitive wheel_enabled
            hovered SetScreenVariable("wheel_hovered", True)
            unhovered [SetScreenVariable("wheel_hovered", False)]
        add Transform("rotation_wheel.png", rotate=wheel_rotation, zoom=0.12, alpha=0.0):
            xpos wheel_x
            ypos wheel_y
            anchor (0.5, 0.5)
        if wheel_hovered and wheel_enabled:
            timer 0.016 repeat True action Function(check_wheel_drag_state, wheel_x, wheel_y)

    # Ghost overlays - DISABLED IN WALL MODE AND TILE MODE
    if combat_game.planning_mode and combat_game.ghost_row is not None and combat_game.ghost_col is not None and not combat_game.wall_mode and not combat_game.tile_mode:
        add Transform("fov_image.png", rotate=combat_game.ghost_facing, alpha=0.3, zoom=0.3):
            xpos int(925 + (combat_game.ghost_col - 3) * (square_size + spacing) + square_size/2)
            ypos int(510 + (combat_game.ghost_row - 3) * (square_size + spacing) + square_size/2)
            anchor (0.5, 0.5)
        $ ghost_player_img = "player1.png" if combat_game.get_current_player() == combat_game.player1 else "player2.png"
        add Transform(ghost_player_img, rotate=combat_game.ghost_facing, zoom=0.12, alpha=0.5):
            xpos int(925 + (combat_game.ghost_col - 3) * (square_size + spacing) + square_size/2)
            ypos int(510 + (combat_game.ghost_row - 3) * (square_size + spacing) + square_size/2)
            anchor (0.5, 0.5)

    # Player markers (click to plan)
    # Determine if we should enable enemy hover in defensive planning
    $ is_defensive_planning = (combat_game.phase == "defense" and combat_game.planning_mode)
    $ current_is_p1 = (combat_game.get_current_player() == combat_game.player1)
    
    # Player 1 - Always hoverable in defensive planning OR when it's their turn
    $ p1_row = combat_game.player1.row
    $ p1_col = combat_game.player1.col
    $ p1_x = int(925 + (p1_col - 3) * (square_size + spacing) + square_size/2)
    $ p1_y = int(510 + (p1_row - 3) * (square_size + spacing) + square_size/2)
    $ sea_offset_player = 100
    $ p1_on_sea = combat_game.p1_sea_doom
    if p1_on_sea:
        if p1_row == 0:
            $ p1_y -= sea_offset_player
        elif p1_row == 6:
            $ p1_y += sea_offset_player
        if p1_col == 0:
            $ p1_x -= sea_offset_player
        elif p1_col == 6:
            $ p1_x += sea_offset_player

    imagebutton:
        idle Transform("player1.png", rotate=combat_game.player1.facing, zoom=get_player_zoom(combat_game.player1))
        hover Transform("player1.png", rotate=combat_game.player1.facing, zoom=get_player_zoom(combat_game.player1)*1.1)
        xpos p1_x
        ypos p1_y
        anchor (0.5, 0.5)
        action If((combat_game.get_current_player() == combat_game.player1 and not combat_game.planning_mode), Function(combat_game.start_movement_planning), NullAction())
        hovered [SetScreenVariable("hovered_p1", True), If(is_defensive_planning and not current_is_p1, SetScreenVariable("hovered_enemy_in_defense", True), NullAction())]
        unhovered [SetScreenVariable("hovered_p1", False), SetScreenVariable("hovered_enemy_in_defense", False)]
        focus_mask True
        # Always sensitive in defensive planning, otherwise only when it's player 1's turn
        sensitive (is_defensive_planning or combat_game.get_current_player() == combat_game.player1)

    $ p2_row = combat_game.player2.row
    $ p2_col = combat_game.player2.col
    $ p2_x = int(925 + (p2_col - 3) * (square_size + spacing) + square_size/2)
    $ p2_y = int(510 + (p2_row - 3) * (square_size + spacing) + square_size/2)
    $ p2_on_sea = combat_game.p2_sea_doom
    if p2_on_sea:
        if p2_row == 0:
            $ p2_y -= sea_offset_player
        elif p2_row == 6:
            $ p2_y += sea_offset_player
        if p2_col == 0:
            $ p2_x -= sea_offset_player
        elif p2_col == 6:
            $ p2_x += sea_offset_player

    imagebutton:
        idle Transform("player2.png", rotate=combat_game.player2.facing, zoom=get_player_zoom(combat_game.player2))
        hover Transform("player2.png", rotate=combat_game.player2.facing, zoom=get_player_zoom(combat_game.player2)*1.1)
        xpos p2_x
        ypos p2_y
        anchor (0.5, 0.5)
        action If((combat_game.get_current_player() == combat_game.player2 and not combat_game.planning_mode), Function(combat_game.start_movement_planning), NullAction())
        hovered [SetScreenVariable("hovered_p2", True), If(is_defensive_planning and current_is_p1, SetScreenVariable("hovered_enemy_in_defense", True), NullAction())]
        unhovered [SetScreenVariable("hovered_p2", False), SetScreenVariable("hovered_enemy_in_defense", False)]
        focus_mask True
        # Always sensitive in defensive planning, otherwise only when it's player 2's turn
        sensitive (is_defensive_planning or combat_game.get_current_player() == combat_game.player2)

    # Track mouse release globally when dragging
    if combat_game.wheel_dragging:
        key "mouseup_1" action Function(combat_game.end_wheel_drag)

    # LAYER 5: Walls Visualization (AFTER tiles, BEFORE players)
    # Use same coordinate system as players: base at (925, 510), offset from center (3, 3)
    $ wall_list = combat_game.wall_system.get_visible_walls()
    $ sea_tiles_present = len(combat_game.tile_system.get_sea_tiles()) > 0
    if debug_mode:
        text f"Walls: {len(wall_list)}" size 16 color "#FF00FF" xpos 400 ypos 10
        text f"Sea Tiles: {'Y' if sea_tiles_present else 'N'}" size 16 color "#00FFFF" xpos 400 ypos 30
    
    # FOV Position Indicator (updates in planning mode)
    $ fov_position = combat_game.get_fov_position_in_enemy_view()
    $ fov_color = "#00FF00" if fov_position == "FOV" else ("#FFFF00" if fov_position == "Periphery" else ("#FF0000" if fov_position == "Behind" else "#808080"))
    if debug_mode:
        text f"Enemy FOV: {fov_position}" size 16 color fov_color xpos 400 ypos 50
    
    for wall_pos in wall_list:
        $ row, col, orientation = wall_pos
        $ wall_obj = combat_game.wall_system.get_wall_at(row, col, orientation)
        $ is_reinforceable = (row, col, orientation) in combat_game.get_board_state().get('reinforceable_walls', [])
        
        # Get wall images from creator's DF config (if player wall) or use default
        python:
            wall_h_img = "wall_horizontal.png"
            wall_v_img = "wall_vertical.png"
            if wall_obj and wall_obj.creator:
                player_id = wall_obj.creator
                if player_id == "player1" and combat_game.player1.devil_fruit_data:
                    wall_config = combat_game.player1.devil_fruit_data.get("map_abilities", {}).get("wall_creation", {})
                    wall_h_img = wall_config.get("wall_horizontal_image", "wall_horizontal.png")
                    wall_v_img = wall_config.get("wall_vertical_image", "wall_vertical.png")
                elif player_id == "player2" and combat_game.player2.devil_fruit_data:
                    wall_config = combat_game.player2.devil_fruit_data.get("map_abilities", {}).get("wall_creation", {})
                    wall_h_img = wall_config.get("wall_horizontal_image", "wall_horizontal.png")
                    wall_v_img = wall_config.get("wall_vertical_image", "wall_vertical.png")
        
        if orientation == 'h':
            # Horizontal wall between row and row+1
            # Position at bottom edge of square at (row, col)
            $ wall_center_x = int(925 + (col - 3) * (square_size + spacing) + square_size/2)
            $ wall_center_y = int(510 + (row - 3) * (square_size + spacing) + square_size + spacing/2)
            
            # Check if wall is player-created and in planning mode
            $ is_clickable = wall_obj and wall_obj.creator and combat_game.planning_mode
            # Check if wall should pulsate (in reinforce mode and in range)
            $ should_pulsate = combat_game.wall_mode == "reinforce" and (row, col, orientation) in combat_game.get_board_state().get('reinforceable_walls', [])
            
            if is_clickable:
                if should_pulsate:
                    imagebutton:
                        idle Transform(wall_h_img, xysize=(square_size, 40))
                        hover Transform(wall_h_img, xysize=(square_size, 40))
                        xpos wall_center_x
                        ypos wall_center_y
                        anchor (0.5, 0.55)
                        action Function(combat_game.select_wall_for_reinforce, row, col, orientation)
                        focus_mask True
                        hovered SetScreenVariable("hovered_wall", (row, col, orientation))
                        unhovered SetScreenVariable("hovered_wall", None)
                        at transform:
                            alpha 1.0
                            ease 0.5 zoom 1.1
                            ease 0.5 zoom 1.0
                            repeat
                else:
                    imagebutton:
                        idle Transform(wall_h_img, xysize=(square_size, 40))
                        hover Transform(wall_h_img, xysize=(square_size, 40))
                        xpos wall_center_x
                        ypos wall_center_y
                        anchor (0.5, 0.55)
                        action Function(combat_game.select_wall_for_reinforce, row, col, orientation)
                        focus_mask True
                        hovered SetScreenVariable("hovered_wall", (row, col, orientation))
                        unhovered SetScreenVariable("hovered_wall", None)
            else:
                if should_pulsate:
                    add wall_h_img:
                        xpos wall_center_x
                        ypos wall_center_y
                        anchor (0.5, 0.55)
                        xysize (square_size, 40)
                        alpha 1.0
                        at transform:
                            alpha 1.0
                            ease 0.5 zoom 1.1
                            ease 0.5 zoom 1.0
                            repeat
                else:
                    imagebutton:
                        idle Transform(wall_h_img, xysize=(square_size, 40), alpha=1.0)
                        hover Transform(wall_h_img, xysize=(square_size, 40), alpha=1.0)
                        xpos wall_center_x
                        ypos wall_center_y
                        anchor (0.5, 0.55)
                        action NullAction()
                        hovered SetScreenVariable("hovered_wall", (row, col, orientation))
                        unhovered SetScreenVariable("hovered_wall", None)
            
            # HP display above horizontal wall
            if wall_obj and wall_obj.tier != 'border':
                $ hp_text = f"{wall_obj.hp}/{wall_obj.max_hp}"
                $ hp_color = "#00FF00" if wall_obj.hp > wall_obj.max_hp * 0.66 else ("#FFFF00" if wall_obj.hp > wall_obj.max_hp * 0.33 else "#FF0000")
                # Show HP: always in planning mode, only on hover when not in planning
                $ show_wall_hp = combat_game.planning_mode or (hovered_wall == (row, col, orientation))
                if show_wall_hp:
                    text hp_text:
                        size 16
                        color hp_color
                        xpos wall_center_x
                        ypos wall_center_y - 25
                        xanchor 0.5
                        yanchor 0.5
                        outlines [(2, "#000000", 0, 0)]
                
        else:  # 'v' - vertical wall
            # Vertical wall between col and col+1
            # Position at right edge of square at (row, col)
            $ wall_center_x = int(925 + (col - 3) * (square_size + spacing) + square_size + spacing/2)
            $ wall_center_y = int(510 + (row - 3) * (square_size + spacing) + square_size/2)
            
            # Check if wall is player-created and in planning mode
            $ is_clickable = wall_obj and wall_obj.creator and combat_game.planning_mode
            # Check if wall should pulsate (in reinforce mode and in range)
            $ should_pulsate = combat_game.wall_mode == "reinforce" and (row, col, orientation) in combat_game.get_board_state().get('reinforceable_walls', [])
            
            if is_clickable:
                if should_pulsate:
                    imagebutton:
                        idle Transform(wall_v_img, xysize=(40, square_size))
                        hover Transform(wall_v_img, xysize=(40, square_size))
                        xpos wall_center_x
                        ypos wall_center_y
                        anchor (0.55, 0.6)
                        action Function(combat_game.select_wall_for_reinforce, row, col, orientation)
                        focus_mask True
                        hovered SetScreenVariable("hovered_wall", (row, col, orientation))
                        unhovered SetScreenVariable("hovered_wall", None)
                        at transform:
                            alpha 1.0
                            ease 0.5 zoom 1.1
                            ease 0.5 zoom 1.0
                            repeat
                else:
                    imagebutton:
                        idle Transform(wall_v_img, xysize=(40, square_size))
                        hover Transform(wall_v_img, xysize=(40, square_size))
                        xpos wall_center_x
                        ypos wall_center_y
                        anchor (0.55, 0.6)
                        action Function(combat_game.select_wall_for_reinforce, row, col, orientation)
                        focus_mask True
                        hovered SetScreenVariable("hovered_wall", (row, col, orientation))
                        unhovered SetScreenVariable("hovered_wall", None)
            else:
                if should_pulsate:
                    add wall_v_img:
                        xpos wall_center_x
                        ypos wall_center_y
                        anchor (0.55, 0.6)
                        xysize (40, square_size)
                        alpha 1.0
                        at transform:
                            alpha 1.0
                            ease 0.5 zoom 1.1
                            ease 0.5 zoom 1.0
                            repeat
                else:
                    imagebutton:
                        idle Transform(wall_v_img, xysize=(40, square_size), alpha=1.0)
                        hover Transform(wall_v_img, xysize=(40, square_size), alpha=1.0)
                        xpos wall_center_x
                        ypos wall_center_y
                        anchor (0.55, 0.6)
                        action NullAction()
                        hovered SetScreenVariable("hovered_wall", (row, col, orientation))
                        unhovered SetScreenVariable("hovered_wall", None)
            
            # HP display to the right of vertical wall
            if wall_obj and wall_obj.tier != 'border':
                $ hp_text = f"{wall_obj.hp}/{wall_obj.max_hp}"
                $ hp_color = "#00FF00" if wall_obj.hp > wall_obj.max_hp * 0.66 else ("#FFFF00" if wall_obj.hp > wall_obj.max_hp * 0.33 else "#FF0000")
                # Show HP: always in planning mode, only on hover when not in planning
                $ show_wall_hp = combat_game.planning_mode or (hovered_wall == (row, col, orientation))
                if show_wall_hp:
                    text hp_text:
                        size 16
                        color hp_color
                        xpos wall_center_x + 25
                        ypos wall_center_y
                        xanchor 0.5
                        yanchor 0.5
                        outlines [(2, "#000000", 0, 0)]

    # Planning controls (embedded)
    if combat_game.planning_mode:
        frame:
            xalign 1.0
            yalign 0.8
            background "#222233AA"
            xpadding 20
            ypadding 15
            xsize 280
            vbox:
                xalign 0.5
                spacing 10
                text "TURN PLANNING" size 24 color "#FFFF00" xalign 0.5
                $ player = combat_game.get_current_player()
                $ movement_steps = len(combat_game.current_path) - 1
                $ movement_cost = combat_game.get_movement_cost(movement_steps)
                $ total_cost = combat_game.total_cost
                $ chain_length = combat_game.facing_chain_length
                $ chain_bonus = min(0.10 * chain_length, 0.50) if chain_length > 0 else 0.0
                $ max_haki = int(player._calculate_max_haki_stamina())
                python:
                    max_df = player._calculate_max_df_stamina()
                    
                    # Calculate planned DF stamina cost from special attacks/defenses
                    planned_df_cost = 0
                    for action in combat_game.planned_actions:
                        if action[0] in ("attack", "defense") and isinstance(action[1], str) and action[1].startswith("special:"):
                            special_name = action[1].replace("special:", "")
                            phase_key = "special_attacks" if action[0] == "attack" else "special_defenses"
                            special_actions = player.devil_fruit_data.get(phase_key, {}) if player.devil_fruit_data else {}
                            if special_name in special_actions:
                                base_cost = special_actions[special_name].get('df_stamina_cost', 0)
                                mastery_reduction = 1 - (player.devil_fruit_mastery * 0.003)
                                planned_df_cost += base_cost * mastery_reduction
                    
                    df_remaining = player.devil_fruit_stamina - planned_df_cost
                    df_display = int((df_remaining / max_df) * 100) if max_df > 0 else 0
                    
                $ current_stam = int(player.stamina - total_cost)
                $ max_stam = int(player.stamina)
                text f"Stamina: {current_stam}/{max_stam}" size 16 color "#FFFF00" xalign 0.5
                text f"Haki: {int(player.haki_stamina)}/{max_haki}" size 16 color "#FF00FF" xalign 0.5
                text f"DF Sta: {df_display}/{100}" size 16 color "#00FFFF" xalign 0.5
                if combat_game.planned_actions:
                    text "Planned Actions:" size 16 color "#FFFF00" xalign 0.5
                    python:
                        display = combat_game.get_planned_actions_display()
                    for entry in display:
                        python:
                            # Determine text size: larger for attack/defense
                            is_action = entry.get("type") in ("attack", "defense")
                            text_size = 16 if is_action else 14
                        text entry["text"] size text_size color entry["color"] xalign 0.5

                vbox:
                    xalign 0.5
                    spacing 6
                    text "Active Bonuses" size 14 color "#FFFF00" xalign 0.5
                    $ pat = combat_game.pattern_active_bonus
                    $ pat_hit_pct = int((pat.get('hit_bonus', 0.0))*100) if pat else 0
                    $ pat_dmg_pct = int((pat.get('damage_bonus', 0.0))*100) if pat else 0
                    # Bounce scaling: [10,12,15,17,20]
                    $ bounce_rates = [10, 12, 15, 17, 20]
                    $ bounce_idx = min(max(1, combat_game.bounce_chain_length), 5) - 1 if combat_game.bounce_active else 0
                    $ bounce_pct = bounce_rates[bounce_idx] if combat_game.bounce_active else 0
                    $ bounce_hit_pct = bounce_rates[bounce_idx] if combat_game.bounce_active else 0
                    if chain_length > 0:
                        $ dir_pct = int(min(0.10 * chain_length, 0.50) * 100)
                        text f"  Facing chain: -{dir_pct}% cost" size 12 color "#FF0000" xalign 0.5
                    if combat_game.bounce_active:
                        text f"  Bounce (Move {combat_game.bounce_chain_length}): -{bounce_pct}% cost{f' (+{bounce_hit_pct}% Hit)' if bounce_hit_pct else ''}" size 12 color "#0000FF" xalign 0.5
                    if pat:
                        text f"  Pattern: {pat.get('name','')} +{pat_hit_pct}% Hit +{pat_dmg_pct}% Dmg" size 12 color "#00FF00" xalign 0.5
                    # FOV-based stamina modifiers (defense phase only)
                    python:
                        fov_text = None
                        if combat_game.phase == "defense":
                            from engine.fov import get_fov_layer
                            defender = combat_game.get_current_player()
                            attacker = combat_game.get_opponent()
                            layer = get_fov_layer(defender.facing, (defender.row, defender.col), (attacker.row, attacker.col))
                            if layer == "FOV":
                                fov_text = "  FOV: -15% Move St, -30% Defense St"
                            elif layer == "Behind":
                                fov_text = "  FOV: +15% Move St"
                            elif layer == "Periphery":
                                fov_text = "  FOV: 0% (no cost change)"
                    if fov_text:
                        text f"{fov_text}" size 12 color "#FFFF00" xalign 0.5
                    
                    # Display stat debuff effects that affect actions
                    python:
                        current_player = combat_game.get_current_player()
                        player_effects = combat_game.active_effects.get(current_player.name, [])
                        
                        # Load effect config
                        import json
                        effect_types_config = {}
                        effect_categories_config = {}
                        try:
                            with open("game/data/effect_types.json", "r") as f:
                                effect_types_config = json.load(f).get("effect_types", {})
                            with open("game/data/effect_categories.json", "r") as f:
                                effect_categories_config = json.load(f).get("effect_categories", {})
                        except:
                            pass
                        
                        # Filter effects that should show in active bonuses
                        active_bonus_effects = [e for e in player_effects if effect_categories_config.get(e.category, {}).get("show_in_active_bonuses", False)]
                    
                    if active_bonus_effects:
                        for effect in active_bonus_effects:
                            python:
                                # Get config
                                type_config = effect_types_config.get(effect.effect_type, {})
                                cat_config = effect_categories_config.get(effect.category, {})
                                
                                # Count stacks
                                stack_count = sum(1 for e in active_bonus_effects if e.effect_type == effect.effect_type and e.category == effect.category)
                                stack_display = f" x{stack_count}" if stack_count > 1 else ""
                                
                                # Get format template
                                format_template = type_config.get("active_bonus_format", "{emoji} {type}: -{magnitude}%{stacks}")
                                
                                # Build replacements
                                emoji = type_config.get("emoji", "")
                                type_name = effect.effect_type.capitalize()
                                
                                # Format text (replace {icon} with empty for text-only display)
                                bonus_text = format_template.replace("{emoji}", emoji).replace("{icon}", "").replace("{type}", type_name).replace("{magnitude}", str(effect.magnitude)).replace("{stacks}", stack_display)
                                
                                # Get icon image if specified
                                icon_image = type_config.get("icon_image", None)
                            
                            hbox:
                                spacing 3
                                if icon_image:
                                    add icon_image:
                                        xsize 14
                                        ysize 14
                                text f"  {bonus_text}" size 12 color "#FF8800" xalign 0.0
                vbox:
                    xalign 0.5
                    spacing 10
                    # Tab selector
                    hbox:
                        xalign 0.5
                        spacing 3
                        $ tab_label = "ATTACKS" if combat_game.phase == "attack" else "DEFENSES"
                        $ player = combat_game.get_current_player()
                        $ has_df = player.devil_fruit_data is not None
                        $ df_name = player.devil_fruit_data.get('name', 'DF').upper() if has_df else "DF"
                        python:
                            # Calculate dynamic width for tabs to fit text
                            tab_label_width = max(60, len(tab_label) * 7)
                            if has_df:
                                df_tab_width = max(60, len(df_name) * 5.5)
                            else:
                                df_tab_width = 60
                            haki_width = 60
                        textbutton tab_label action SetField(combat_game, "selected_alloy_tab", "attack") background ("#0d00ff50" if combat_game.selected_alloy_tab == "attack" else "#222222AA") text_size 14 xsize tab_label_width text_xalign 0.5
                        if has_df:
                            textbutton df_name action SetField(combat_game, "selected_alloy_tab", "devil_fruit") background ("#0d00ff50" if combat_game.selected_alloy_tab == "devil_fruit" else "#222222AA") text_size 12 xsize df_tab_width text_xalign 0.5
                        textbutton "HAKI" action SetField(combat_game, "selected_alloy_tab", "haki") background ("#0d00ff50" if combat_game.selected_alloy_tab == "haki" else "#222222AA") text_size 14 xsize haki_width text_xalign 0.5
                    
                    # Tab content - FIXED SIZE BOX FOR ALL TABS
                    if combat_game.selected_alloy_tab == "attack":
                        vbox:
                            xalign 0.5
                            xsize 200
                            ysize 90
                            if combat_game.phase == "attack":
                                text "ATTACKS" size 16 color "#FFFF00" xalign 0.5
                                grid 2 2:
                                    spacing 5
                                    if not combat_game.wall_mode:
                                        textbutton "QUICK" action Function(combat_game.add_attack, "quick")
                                        textbutton "NORMAL" action Function(combat_game.add_attack, "normal")
                                        textbutton "HEAVY" action Function(combat_game.add_attack, "heavy")
                                        textbutton "SKIP" action Function(combat_game.add_attack, "skip")
                                    else:
                                        text "Disabled\n(Wall mode)" size 12 color "#888888" xalign 0.5
                            else:
                                text "DEFENSE" size 16 color "#FFFF00" xalign 0.5
                                grid 2 2:
                                    spacing 5
                                    if not combat_game.wall_mode:
                                        textbutton "EVADE" action Function(combat_game.add_defense, "evade")
                                        textbutton "DEFEND" action Function(combat_game.add_defense, "defend")
                                        textbutton "COUNTER" action Function(combat_game.add_defense, "counter")
                                        textbutton "TANK" action Function(combat_game.add_defense, "tank")
                                    else:
                                        text "Disabled\n(Wall mode)" size 12 color "#888888" xalign 0.5
                    elif combat_game.selected_alloy_tab == "devil_fruit":
                        vbox:
                            xalign 0.5
                            xsize 200
                            ysize 90
                            spacing 5
                            $ player = combat_game.get_current_player()
                            if player.devil_fruit_data:
                                python:
                                    df_data = player.devil_fruit_data
                                    phase_key = "special_attacks" if combat_game.phase == "attack" else "special_defenses"
                                    special_actions = df_data.get(phase_key, {})
                                    alloys = df_data.get("alloys_available", {})
                                    enabled_alloys = {k: v for k, v in alloys.items() if v.get("enabled", False)}
                                    map_abilities = df_data.get("map_abilities", {})
                                    walls_data = {k: v for k, v in map_abilities.items() if v.get("type") == "wall"}
                                    tiles_data = {k: v for k, v in map_abilities.items() if v.get("type") == "trap"}
                                    
                                    # Calculate max items across all tabs to determine button size
                                    max_items = max(
                                        len(special_actions),
                                        len(enabled_alloys),
                                        sum(1 for w_name, w_data in walls_data.items() for tier in ["fragile", "standard", "reinforced"] if tier in w_data.get("df_cost_tier", {})),
                                        len(tiles_data)
                                    )
                                    # Calculate grid rows needed (2 columns)
                                    grid_rows_needed = max(1, (max_items + 1) // 2)
                                    # Fixed button size that fits all tabs
                                    btn_ysize = min(25, max(15, 50 // grid_rows_needed))
                                    btn_text_size = 10 if max_items > 4 else 12
                                
                                # Sub-tab selector
                                hbox:
                                    xalign 0.5
                                    spacing 2
                                    $ phase_label = "ATK" if combat_game.phase == "attack" else "DEF"
                                    textbutton phase_label action SetField(combat_game, "df_sub_tab", "special_attacks") background ("#0d00ff50" if combat_game.df_sub_tab == "special_attacks" else "#222222AA") text_size 10 xsize 40 text_xalign 0.5
                                    textbutton "ALOY" action SetField(combat_game, "df_sub_tab", "alloys") background ("#0d00ff50" if combat_game.df_sub_tab == "alloys" else "#222222AA") text_size 10 xsize 40 text_xalign 0.5
                                    textbutton "WALL" action SetField(combat_game, "df_sub_tab", "walls") background ("#0d00ff50" if combat_game.df_sub_tab == "walls" else "#222222AA") text_size 10 xsize 40 text_xalign 0.5
                                    textbutton "TILE" action SetField(combat_game, "df_sub_tab", "tiles") background ("#0d00ff50" if combat_game.df_sub_tab == "tiles" else "#222222AA") text_size 10 xsize 40 text_xalign 0.5
                                
                                # Sub-tab content - ALL USE SAME BUTTON SIZE
                                if combat_game.df_sub_tab == "special_attacks":
                                    python:
                                        actions_list = list(special_actions.keys())
                                        num_actions = len(actions_list)
                                        grid_rows = max(1, (num_actions + 1) // 2)
                                    
                                    if num_actions > 0:
                                        grid 2 grid_rows:
                                            spacing 5
                                            for action_name in actions_list:
                                                $ display_name = action_name.replace("_", " ").title()
                                                if combat_game.phase == "attack":
                                                    textbutton display_name action Function(combat_game.add_special_attack, action_name) ysize btn_ysize text_size btn_text_size text_xalign 0.5
                                                else:
                                                    textbutton display_name action Function(combat_game.add_special_defense, action_name) ysize btn_ysize text_size btn_text_size text_xalign 0.5
                                            if num_actions % 2 == 1:
                                                null
                                    else:
                                        text "No actions" size 12 color "#888888" xalign 0.5
                                
                                elif combat_game.df_sub_tab == "alloys":
                                    # Check if in level selection mode
                                    if combat_game.df_alloy_level_select:
                                        python:
                                            # Level selection mode for width_boost or length_boost
                                            alloy_type = combat_game.df_alloy_level_select
                                            alloy_data = enabled_alloys.get(alloy_type, {})
                                            levels = sorted([int(k) for k in alloy_data.get("df_cost_per_level", {}).keys()])
                                            num_levels = len(levels)
                                            grid_rows = max(1, (num_levels + 2) // 2)  # +1 for back button
                                        
                                        vbox:
                                            spacing 5
                                            textbutton "<< Back" action Function(combat_game.cancel_df_alloy_level_select) ysize btn_ysize text_size btn_text_size text_xalign 0.5 xalign 0.5
                                            
                                            grid 2 grid_rows:
                                                spacing 5
                                                for level in levels:
                                                    textbutton f"Lvl {level}" action Function(combat_game.apply_df_alloy, alloy_type, level) ysize btn_ysize text_size btn_text_size text_xalign 0.5
                                                if num_levels % 2 == 1:
                                                    null
                                    
                                    else:
                                        python:
                                            # Filter alloys by phase
                                            current_phase = combat_game.phase
                                            
                                            # Check if counter is selected for attack alloys in defense phase
                                            is_counter = False
                                            for action in combat_game.planned_actions:
                                                if action[0] == "defense" and action[1] == "counter":
                                                    is_counter = True
                                                    break
                                            
                                            # Filter alloys
                                            filtered_alloys = []
                                            for alloy_name, alloy_data in enabled_alloys.items():
                                                alloy_phase = alloy_data.get("phase", "attack")
                                                
                                                # Include defense alloys in defense phase
                                                if alloy_phase == "defense" and current_phase == "defense":
                                                    filtered_alloys.append(alloy_name)
                                                # Include attack alloys in attack phase or counter
                                                elif alloy_phase == "attack" and (current_phase == "attack" or is_counter):
                                                    # For width/length boost, DON'T expand levels here
                                                    filtered_alloys.append(alloy_name)
                                            
                                            num_alloys = len(filtered_alloys)
                                            grid_rows = max(1, (num_alloys + 1) // 2)
                                        
                                        if num_alloys > 0:
                                            grid 2 grid_rows:
                                                spacing 5
                                                for alloy_name in filtered_alloys:
                                                    python:
                                                        display_name = alloy_name.replace("_", " ").title()
                                                        # For width/length boost, go to level selection
                                                        if alloy_name in ["width_boost", "length_boost"]:
                                                            action_fn = Function(combat_game.select_df_alloy_for_level, alloy_name)
                                                        else:
                                                            action_fn = Function(combat_game.apply_df_alloy, alloy_name)
                                                    textbutton display_name action action_fn ysize btn_ysize text_size btn_text_size text_xalign 0.5
                                                if num_alloys % 2 == 1:
                                                    null
                                        else:
                                            text "No alloys" size 12 color "#888888" xalign 0.5
                                
                                elif combat_game.df_sub_tab == "walls":
                                    python:
                                        # Check if player has wall creation ability
                                        player = combat_game.get_current_player()
                                        wall_config = player.devil_fruit_data.get("map_abilities", {}).get("wall_creation") if player.devil_fruit_data else None
                                        has_wall_ability = wall_config and wall_config.get("enabled", False)
                                        
                                        # Check if attack/defense is selected
                                        attack_defense_selected = any(action[0] in ["attack", "defense"] for action in combat_game.planned_actions)
                                        
                                        # Get player walls in range
                                        player_walls = combat_game.get_player_walls_in_range() if has_wall_ability else []
                                        # Include walls from planned actions
                                        for action in combat_game.planned_actions:
                                            if action[0] == "wall_create":
                                                wall_row, wall_col, orientation, cost = action[1]
                                                if (wall_row, wall_col, orientation) not in player_walls:
                                                    player_walls.append((wall_row, wall_col, orientation))
                                        has_player_walls = len(player_walls) > 0
                                    
                                    if has_wall_ability and combat_game.planning_mode and not attack_defense_selected:
                                        vbox:
                                            spacing 5
                                            
                                            # Show both Conjure and Reinforce buttons
                                            if not combat_game.wall_mode or combat_game.wall_mode == "conjure":
                                                textbutton "Conjure" action Function(combat_game.enter_wall_conjure_mode) ysize btn_ysize text_size btn_text_size text_xalign 0.5
                                            
                                            # Show Reinforce button if player has walls
                                            if has_player_walls:
                                                if combat_game.wall_mode == "reinforce" and combat_game.wall_selected_for_reinforce:
                                                    # In reinforce mode with wall selected - show reinforce button
                                                    textbutton "Reinforce" action Function(combat_game.reinforce_selected_wall) ysize btn_ysize text_size btn_text_size text_xalign 0.5
                                                elif not combat_game.wall_mode or combat_game.wall_mode == "reinforce":
                                                    # Show wall list for selection
                                                    textbutton "Reinforce" action Function(combat_game.enter_wall_reinforce_mode) ysize btn_ysize text_size btn_text_size text_xalign 0.5
                                                    
                                                    # If in reinforce mode, show wall list
                                                    if combat_game.wall_mode == "reinforce":
                                                        python:
                                                            num_walls = len(player_walls)
                                                            grid_rows = max(1, (num_walls + 1) // 2)
                                                        
                                                        text "Select wall:" size 12 color "#FFFF00" xalign 0.5
                                                        
                                                        if num_walls > 0:
                                                            grid 2 grid_rows:
                                                                spacing 5
                                                                for wall_row, wall_col, orientation in player_walls:
                                                                    python:
                                                                        # Get wall HP
                                                                        wall_hp = combat_game.wall_system.get_wall_hp(wall_row, wall_col, orientation)
                                                                        # Format tiles
                                                                        if orientation == 'v':
                                                                            tile1 = f"{wall_row}{chr(65+wall_col)}"
                                                                            tile2 = f"{wall_row}{chr(65+wall_col+1)}"
                                                                        else:
                                                                            tile1 = f"{wall_row}{chr(65+wall_col)}"
                                                                            tile2 = f"{wall_row+1}{chr(65+wall_col)}"
                                                                        display_name = f"{tile1}-{tile2} ({wall_hp} HP)"
                                                                    textbutton display_name action Function(combat_game.select_wall_for_reinforce, wall_row, wall_col, orientation) ysize btn_ysize text_size btn_text_size text_xalign 0.5
                                                                if num_walls % 2 == 1:
                                                                    null
                                            
                                            # Exit mode button if in any wall mode
                                            if combat_game.wall_mode:
                                                textbutton "Cancel" action Function(combat_game.exit_wall_mode) ysize btn_ysize text_size btn_text_size text_xalign 0.5
                                    elif not has_wall_ability:
                                        text "No wall ability" size 12 color "#888888" xalign 0.5
                                    elif attack_defense_selected:
                                        text "Cannot use walls\nwith attack/defense" size 12 color "#888888" xalign 0.5
                                    else:
                                        text "Planning inactive" size 12 color "#888888" xalign 0.5
                                
                                elif combat_game.df_sub_tab == "tiles":
                                    python:
                                        # Get available tiles
                                        player = combat_game.get_current_player()
                                        tiles_available = player.devil_fruit_data.get("map_abilities", {}).get("tiles_available", {}) if player.devil_fruit_data else {}
                                        has_tiles = len(tiles_available) > 0
                                        attack_defense_selected = any(a[0] in ("attack", "defense") for a in combat_game.planned_actions)
                                        three_actions_reached = combat_game.phase == "defense" and combat_game.wall_operations_this_phase >= 3
                                    
                                    if has_tiles and combat_game.planning_mode and not attack_defense_selected and not three_actions_reached:
                                        python:
                                            tiles_list = list(tiles_available.keys())
                                            num_tiles = len(tiles_list)
                                            grid_rows = max(1, (num_tiles + 1) // 2)
                                            btn_ysize = 20
                                            btn_text_size = 11
                                        
                                        if num_tiles > 0:
                                            grid 2 grid_rows:
                                                spacing 5
                                                for tile_key in tiles_list:
                                                    python:
                                                        tile_config = tiles_available[tile_key]
                                                        display_name = tile_config.get("label", tile_key.replace("_", " ").title())
                                                        is_selected = combat_game.tile_mode and combat_game.selected_tile_type == tile_key
                                                    if is_selected:
                                                        textbutton f"{display_name} (Active)" action Function(combat_game.confirm_tile_placement) ysize btn_ysize text_size btn_text_size text_xalign 0.5 background "#00FF0050"
                                                    else:
                                                        textbutton display_name action Function(combat_game.enter_tile_mode, tile_key) ysize btn_ysize text_size btn_text_size text_xalign 0.5
                                                if num_tiles % 2 == 1:
                                                    null
                                            
                                            # Show cancel button if in tile mode
                                            if combat_game.tile_mode:
                                                textbutton "Cancel" action Function(combat_game.exit_tile_mode) ysize btn_ysize text_size btn_text_size text_xalign 0.5
                                    elif not has_tiles:
                                        text "No tile abilities" size 12 color "#888888" xalign 0.5
                                    elif attack_defense_selected:
                                        text "Cannot use tiles\nwith attack/defense" size 12 color "#888888" xalign 0.5
                                    elif three_actions_reached:
                                        text "3 action limit\nreached" size 12 color "#888888" xalign 0.5
                                    else:
                                        text "Planning inactive" size 12 color "#888888" xalign 0.5
                            else:
                                text "NO DEVIL FRUIT" size 14 color "#888888" xalign 0.5
                    elif combat_game.selected_alloy_tab == "haki":
                        vbox:
                            xalign 0.5
                            xsize 200
                            ysize 90
                            text "HAKI ALLOYS" size 16 color "#FFFF00" xalign 0.5
                            $ player = combat_game.get_current_player()
                            python:
                                from engine.haki import calculate_haki_cost
                                arm_cost = calculate_haki_cost("armament", player.haki_armament)
                                obs_cost = calculate_haki_cost("observation", player.haki_observation)
                                con_cost = calculate_haki_cost("conqueror", player.haki_conqueror)
                            vbox:
                                spacing 5
                                textbutton "Armament" action Function(combat_game.apply_haki_alloy, "armament") ysize 18 text_xalign 0.5
                                textbutton "Observation" action Function(combat_game.apply_haki_alloy, "observation") ysize 18 text_xalign 0.5
                                textbutton "Conqueror" action Function(combat_game.apply_haki_alloy, "conqueror") ysize 18 text_xalign 0.5
                textbutton "UNDO LAST ACTION" action Function(combat_game.undo_last_planned_action) background "#ff000050" text_color "#FFFF00" xalign 0.5
                hbox:
                    xalign 0.5
                    spacing 10
                    textbutton "CONFIRM TURN" action Function(combat_game.confirm_turn) background "#0d00ff50" text_color "#FFFF00"
                    textbutton "CANCEL" action Function(combat_game.cancel_planning) background "#053efb6e" text_color "#FFFF00"

    # Battle log (embedded)
    frame:
        xpos 20
        ypos 400
        xsize 250
        ysize 250
        background Solid("#222233AA")
        vbox:
            spacing 5
            text "BATTLE LOG" size 22 color "#FFFF00"
            viewport:
                xsize 230
                ysize 210
                scrollbars "vertical"
                mousewheel True
                vbox:
                    spacing 3
                    python:
                        try:
                            log_entries = combat_game.battle_log
                        except:
                            log_entries = []
                    if len(log_entries) == 0:
                        text "<< No entries yet >>" size 14 color "#FF0000"
                    else:
                        for entry in log_entries:
                            text entry size 13 color "#FFFFFF" xmaximum 220
                        if debug_mode:
                            textbutton "COPY PS CMD" action Function(copy_debug_everything_notify) background "#0aa00050" text_color "#FFFF00" xalign 0.5

    if debug_mode:
        textbutton "COPY PS CMD" action Function(copy_debug_everything_notify) background "#0aa00050" text_color "#FFFF00" xalign 0.015 yalign 0.65

    # Game-over overlay inside same screen
    if not combat_game.game_active and combat_game.winner:
        frame:
            xalign 0.5
            yalign 0.5
            xsize 500
            ysize 300
            background Solid("#000000AA")
            vbox:
                xalign 0.5
                spacing 20
                text "BATTLE ENDED" size 60 color "#FFFFFF" xalign 0.5
                text f"WINNER: {combat_game.winner}" size 40 color "#FFFF00" xalign 0.5
                textbutton "RESTART BATTLE" action Function(renpy.restart_interaction) xalign 0.5 text_size 30
                textbutton "QUIT GAME" action Quit(confirm=False) xalign 0.5 text_size 30

# Wheel interaction helpers
init python:
    def check_wheel_drag_state(wheel_x, wheel_y):
        mouse_pressed = renpy.get_mouse_pos() and pygame.mouse.get_pressed()[0]
        if mouse_pressed:
            if not combat_game.wheel_dragging:
                mouse_x, mouse_y = renpy.get_mouse_pos()
                dx = mouse_x - wheel_x
                dy = mouse_y - wheel_y
                initial_mouse_angle = math.degrees(math.atan2(dy, dx))
                if initial_mouse_angle < 0:
                    initial_mouse_angle += 360
                combat_game.start_wheel_drag(initial_mouse_angle)
            update_wheel_from_mouse(wheel_x, wheel_y)
            renpy.restart_interaction()

    def update_wheel_from_mouse(wheel_x, wheel_y):
        if not combat_game.wheel_dragging:
            return
        mouse_x, mouse_y = renpy.get_mouse_pos()
        dx = mouse_x - wheel_x
        dy = mouse_y - wheel_y
        if dx == 0 and dy == 0:
            return
        current_mouse_angle = math.degrees(math.atan2(dy, dx))
        if current_mouse_angle < 0:
            current_mouse_angle += 360
        angle_delta = current_mouse_angle - combat_game.wheel_drag_initial_mouse_angle
        if angle_delta > 180:
            angle_delta -= 360
        elif angle_delta < -180:
            angle_delta += 360
        new_wheel_angle = (combat_game.wheel_drag_start_facing + angle_delta) % 360
        combat_game.update_wheel_drag(new_wheel_angle)
    
    # Double-click handler for tile placement
    last_tile_click = {'time': 0.0, 'pos': None}
    
    def handle_tile_click(row, col):
        import time
        current_time = time.time()
        click_pos = (row, col)
        
        # Check if this is a double-click (within 0.5 seconds, same position)
        if (current_time - last_tile_click['time'] < 0.5 and 
            last_tile_click['pos'] == click_pos):
            # Double-click detected
            combat_game.select_tile_position(row, col, True)
            last_tile_click['time'] = 0.0
            last_tile_click['pos'] = None
        else:
            # Single click
            combat_game.select_tile_position(row, col, False)
            last_tile_click['time'] = current_time
            last_tile_click['pos'] = click_pos

    def copy_planned_actions_debug():
        try:
            renpy.clipboard = get_console_text()
            renpy.notify("Console buffer copied (raw)")
        except Exception as ex:
            renpy.notify(f"Copy failed: {ex}")
        angle_delta = current_mouse_angle - combat_game.wheel_drag_initial_mouse_angle
        if angle_delta > 180:
            angle_delta -= 360
        elif angle_delta < -180:
            angle_delta += 360
        new_wheel_angle = (combat_game.wheel_drag_start_facing + angle_delta) % 360
        combat_game.update_wheel_drag(new_wheel_angle)

    def copy_planned_actions_debug():
        try:
            renpy.clipboard = get_console_text()
            renpy.notify("Console buffer copied (raw)")
        except Exception as ex:
            renpy.notify(f"Copy failed: {ex}")
        try:
            renpy.clipboard = get_console_text()
            renpy.notify("Console buffer copied (raw)")
        except Exception as ex:
            renpy.notify(f"Copy failed: {ex}")
        angle_delta = current_mouse_angle - combat_game.wheel_drag_initial_mouse_angle
        if angle_delta > 180:
            angle_delta -= 360
        elif angle_delta < -180:
            angle_delta += 360
        new_wheel_angle = (combat_game.wheel_drag_start_facing + angle_delta) % 360
        combat_game.update_wheel_drag(new_wheel_angle)

    def copy_planned_actions_debug():
        try:
            renpy.clipboard = get_console_text()
            renpy.notify("Console buffer copied (raw)")
        except Exception as ex:
            renpy.notify(f"Copy failed: {ex}")
