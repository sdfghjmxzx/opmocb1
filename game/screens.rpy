init python:
    import pygame, math, sys, tempfile, subprocess, os
    from controller import CombatGame
    from engine.combat import calculate_hit_chance
    combat_game = CombatGame()

    class _StdoutCapture:
        def __init__(self, original):
            self._orig = original
            self.buffer = []
        def write(self, s):
            try:
                self.buffer.append(s)
            except:
                pass
            return self._orig.write(s)
        def flush(self):
            try:
                self._orig.flush()
            except:
                pass
    # Install global stdout capture
    stdout_capture = _StdoutCapture(sys.stdout)
    sys.stdout = stdout_capture

    def get_console_text():
        try:
            return "".join(stdout_capture.buffer)
        except:
            return ""

    import builtins
    _orig_print = builtins.print
    def _cap_print(*args, **kwargs):
        try:
            msg = " ".join(str(a) for a in args)
            end = kwargs.get('end', '\n')
            stdout_capture.buffer.append(msg + ('' if end == '' else end))
        except:
            pass
        return _orig_print(*args, **kwargs)
    builtins.print = _cap_print

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

    # Hover tracking
    default hovered_p1 = False
    default hovered_p2 = False
    default wheel_hovered = False

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
                text f"Health: {p1.health}" size 15 color "#FFFF00"
                text f"Stamina: {p1.stamina}" size 15 color "#FFFF00"
            hbox:
                spacing 15
                text f"Position: {p1.get_position_str()}" size 15 color "#FFFF00"
                text f"Facing: {p1.facing}°" size 15 color "#FFFF00"

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
                text f"Health: {p2.health}" size 15 color "#FFFF00"
                text f"Stamina: {p2.stamina}" size 15 color "#FFFF00"
            hbox:
                spacing 15
                text f"Position: {p2.get_position_str()}" size 15 color "#FFFF00"
                text f"Facing: {p2.facing}°" size 15 color "#FFFF00"

    # LAYER 2: Board with transparent squares (checkerboard shows through)
    $ square_size = 80
    $ spacing = 3
    $ board_start_x = int(1234/2 - (7 * (square_size + spacing) - spacing) / 2)
    $ board_start_y = int(678/2 - (7 * (square_size + spacing) - spacing) / 2)
    
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
                        $ is_highlighted = (row, col) in combat_game.highlighted_squares
                        $ is_in_path = (row, col) in combat_game.current_path
                        $ is_last_in_path = combat_game.current_path and (row, col) == combat_game.current_path[-1]
                        $ is_attack_highlighted = (row, col) in combat_game.attack_highlighted_squares
                        $ bg_color = "#4182b100"
                        if is_attack_highlighted:
                            $ bg_color = "#ff000024"
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
                            if is_attack_highlighted:
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
                            elif is_highlighted:
                                add "avalable_circle.png":
                                    xalign 0.5 yalign 0.5
                                    size (45, 45)
                                    alpha 0.5
                            
                            if is_highlighted and combat_game.movement_mode:
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
    
    # LAYER 4: Tiles Visualization
    for tile_info in combat_game.tile_system.get_all_tiles():
        $ tile_row, tile_col, tile_type = tile_info
        # Using same coordinate system as players
        $ tile_x = int(925 + (tile_col - 3) * (square_size + spacing) + square_size/2)
        $ tile_y = int(510 + (tile_row - 3) * (square_size + spacing) + square_size/2)
        
        if tile_type == 'unpassable':
            add "tile_unpassable.png":
                xpos tile_x
                ypos tile_y
                anchor (0.50, 0.60)
                xsize square_size - 3
                ysize square_size - 3
                alpha 0.6
        elif tile_type == 'trap_continuous':
            add "tile_trap_continuous.png":
                xpos tile_x
                ypos tile_y
                anchor (0.55, 0.59)
                xsize square_size -3
                ysize square_size -3
                alpha 0.8
        elif tile_type == 'trap_momentary':
            add "tile_trap_momentary.png":
                xpos tile_x
                ypos tile_y
                anchor (0.55, 0.59)
                xsize square_size -3
                ysize square_size -3
                alpha 0.8
        elif tile_type == 'drop_continuous':
            add "tile_drop_continuous.png":
                xpos tile_x
                ypos tile_y
                anchor (0.55, 0.59)
                xsize square_size -3
                ysize square_size -3
                alpha 0.8
        elif tile_type == 'drop_momentary':
            add "tile_drop_momentary.png":
                xpos tile_x
                ypos tile_y
                anchor (0.55, 0.59)
                xsize square_size -3
                ysize square_size -3
                alpha 0.8

    # Wheel & drag (fixed to active square)
    if combat_game.planning_mode and combat_game.current_path:
        $ active_tile = combat_game.current_path[-1]
        $ active_row, active_col = active_tile
        $ wheel_rotation = combat_game.get_wheel_rotation()
        $ wheel_x = int(925 + (active_col - 3) * (square_size + spacing) + square_size/2)
        $ wheel_y = int(510 + (active_row - 3) * (square_size + spacing) + square_size/2)
        button:
            xpos wheel_x - 50
            ypos wheel_y - 50
            xsize 100
            ysize 100
            background Solid("#00000001")
            action NullAction()
            mouse "pointer"
            hovered SetScreenVariable("wheel_hovered", True)
            unhovered [SetScreenVariable("wheel_hovered", False)]
        add Transform("rotation_wheel.png", rotate=wheel_rotation, zoom=0.12, alpha=0.0):
            xpos wheel_x
            ypos wheel_y
            anchor (0.5, 0.5)
        if wheel_hovered:
            timer 0.016 repeat True action Function(check_wheel_drag_state, wheel_x, wheel_y)

    # Ghost overlays
    if combat_game.planning_mode and combat_game.ghost_row is not None and combat_game.ghost_col is not None:
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
    imagebutton:
        idle Transform("player1.png", rotate=combat_game.player1.facing, zoom=get_player_zoom(combat_game.player1))
        hover Transform("player1.png", rotate=combat_game.player1.facing, zoom=get_player_zoom(combat_game.player1)*1.1)
        xpos int(925 + (combat_game.player1.col - 3) * (square_size + spacing) + square_size/2)
        ypos int(510 + (combat_game.player1.row - 3) * (square_size + spacing) + square_size/2)
        anchor (0.5, 0.5)
        action If((combat_game.get_current_player() == combat_game.player1 and not combat_game.planning_mode), Function(combat_game.start_movement_planning), None)
        hovered SetScreenVariable("hovered_p1", True)
        unhovered SetScreenVariable("hovered_p1", False)
        focus_mask True
        sensitive True

    imagebutton:
        idle Transform("player2.png", rotate=combat_game.player2.facing, zoom=get_player_zoom(combat_game.player2))
        hover Transform("player2.png", rotate=combat_game.player2.facing, zoom=get_player_zoom(combat_game.player2)*1.1)
        xpos int(925 + (combat_game.player2.col - 3) * (square_size + spacing) + square_size/2)
        ypos int(510 + (combat_game.player2.row - 3) * (square_size + spacing) + square_size/2)
        anchor (0.5, 0.5)
        action If((combat_game.get_current_player() == combat_game.player2 and not combat_game.planning_mode), Function(combat_game.start_movement_planning), None)
        hovered SetScreenVariable("hovered_p2", True)
        unhovered SetScreenVariable("hovered_p2", False)
        focus_mask True
        sensitive True

    # Track mouse release globally when dragging
    if combat_game.wheel_dragging:
        key "mouseup_1" action Function(combat_game.end_wheel_drag)

    # LAYER 5: Walls Visualization (AFTER tiles, BEFORE players)
    # Use same coordinate system as players: base at (925, 510), offset from center (3, 3)
    $ wall_list = combat_game.wall_system.get_visible_walls()
    text f"Walls: {len(wall_list)}" size 16 color "#FF00FF" xpos 400 ypos 10
    
    for wall_pos in wall_list:
        $ row, col, orientation = wall_pos
        $ wall_obj = combat_game.wall_system.get_wall_at(row, col, orientation)
        
        if orientation == 'h':
            # Horizontal wall between row and row+1
            # Position at bottom edge of square at (row, col)
            $ wall_center_x = int(925 + (col - 3) * (square_size + spacing) + square_size/2)
            $ wall_center_y = int(510 + (row - 3) * (square_size + spacing) + square_size + spacing/2)
            
            add "wall_horizontal.png":
                xpos wall_center_x
                ypos wall_center_y
                anchor (0.5, 0.55)
                xsize square_size
                ysize 40
                alpha 1.0
            
            # HP display above horizontal wall
            if wall_obj and wall_obj.tier != 'border':
                $ hp_text = f"{wall_obj.hp}/{wall_obj.max_hp}"
                $ hp_color = "#00FF00" if wall_obj.hp > wall_obj.max_hp * 0.66 else ("#FFFF00" if wall_obj.hp > wall_obj.max_hp * 0.33 else "#FF0000")
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
            
            add "wall_vertical.png":
                xpos wall_center_x
                ypos wall_center_y
                anchor (0.55, 0.6)
                xsize 40
                ysize square_size 
                alpha 1.0
            
            # HP display to the right of vertical wall
            if wall_obj and wall_obj.tier != 'border':
                $ hp_text = f"{wall_obj.hp}/{wall_obj.max_hp}"
                $ hp_color = "#00FF00" if wall_obj.hp > wall_obj.max_hp * 0.66 else ("#FFFF00" if wall_obj.hp > wall_obj.max_hp * 0.33 else "#FF0000")
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
                text f"Total Cost: {total_cost} stamina" size 18 color "#FFFF00" xalign 0.5
                text f"Remaining: {player.stamina - total_cost} stamina" size 18 color "#FFFF00" xalign 0.5
                if combat_game.planned_actions:
                    text "Planned Actions:" size 16 color "#FFFF00" xalign 0.5
                    python:
                        display = combat_game.get_planned_actions_display()
                    for entry in display:
                        text entry["text"] size 14 color entry["color"] xalign 0.5

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
                vbox:
                    xalign 0.5
                    spacing 10
                    vbox:
                        xalign 0.5
                        text "ROTATION" size 16 color "#FFFF00" xalign 0.5
                        grid 2 2:
                            spacing 5
                            textbutton "-45°" action Function(combat_game.add_rotation, -45)
                            textbutton "+45°" action Function(combat_game.add_rotation, 45)
                            textbutton "-90°" action Function(combat_game.add_rotation, -90)
                            textbutton "+90°" action Function(combat_game.add_rotation, 90)
                    vbox:
                        xalign 0.5
                        if combat_game.phase == "attack":
                            text "ATTACKS" size 16 color "#FFFF00" xalign 0.5
                            grid 2 2:
                                spacing 5
                                textbutton "QUICK" action Function(combat_game.add_attack, "quick")
                                textbutton "NORMAL" action Function(combat_game.add_attack, "normal")
                                textbutton "HEAVY" action Function(combat_game.add_attack, "heavy")
                                textbutton "SKIP" action Function(combat_game.add_attack, "skip")
                        else:
                            text "DEFENSE" size 16 color "#FFFF00" xalign 0.5
                            grid 2 2:
                                spacing 5
                                textbutton "EVADE" action Function(combat_game.add_defense, "evade")
                                textbutton "DEFEND" action Function(combat_game.add_defense, "defend")
                                textbutton "COUNTER" action Function(combat_game.add_defense, "counter")
                                textbutton "TANK" action Function(combat_game.add_defense, "tank")
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
                        textbutton "COPY PS CMD" action Function(copy_debug_everything_notify) background "#0aa00050" text_color "#FFFF00" xalign 0.5

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

    def copy_planned_actions_debug():
        try:
            renpy.clipboard = get_console_text()
            renpy.notify("Console buffer copied (raw)")
        except Exception as ex:
            renpy.notify(f"Copy failed: {ex}")
