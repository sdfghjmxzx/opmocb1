init python:
    import pygame, math
    from controller import CombatGame
    from engine.combat import calculate_hit_chance
    combat_game = CombatGame()

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
                        # Build chain groups with action indices
                        chain_groups = combat_game.get_move_chain_groups()
                        
                        # Map action index to chain info
                        action_to_chain = {}
                        for group in chain_groups:
                            for act_idx in group["action_indices"]:
                                action_to_chain[act_idx] = group
                        
                        # Map move index to chain for finding last in chain
                        move_to_chain = {}
                        for group in chain_groups:
                            for idx in range(group["start_idx"], group["end_idx"] + 1):
                                move_to_chain[idx] = group
                        
                        # Calculate cost for each move index
                        base_cost = 15 if combat_game.phase == "attack" else 30
                        move_index = 0
                        # Bonus previews
                        pat = combat_game.pattern_active_bonus
                        pat_hit_pct = int((pat.get('hit_bonus', 0.0))*100) if pat else 0
                        pat_dmg_pct = int((pat.get('damage_bonus', 0.0))*100) if pat else 0
                        # Bounce percentages: use scaling rates [10,12.5,15,17.5,20]
                        bounce_rates = [10, 12, 15, 17, 20]
                        bounce_hit_rates = [10, 12, 15, 17, 20]
                        bounce_idx = min(max(1, combat_game.bounce_chain_length), 5) - 1 if combat_game.bounce_active else 0
                        bounce_pct = bounce_rates[bounce_idx] if combat_game.bounce_active else 0
                        bounce_hit_pct = bounce_hit_rates[bounce_idx] if combat_game.bounce_active else 0

                    
                    for act_idx, action in enumerate(combat_game.planned_actions):
                        if action[0] == "move":
                            $ tile_name = action[1]["tile"]
                            python:
                                # Determine if this is the last move in its chain
                                is_last_in_chain = False
                                chain_bonus_pct = 0
                                move_cost = base_cost
                                total_chain_cost = base_cost
                                chain_color = "#FFFF00"
                                
                                if move_index in move_to_chain:
                                    group = move_to_chain[move_index]
                                    is_last_in_chain = (move_index == group["end_idx"])
                                    # Only use chain color if this action is IN the chain's action_indices
                                    if act_idx in action_to_chain:
                                        chain_color = action_to_chain[act_idx]["color"]
                                    if is_last_in_chain:
                                        # Calculate cumulative chain bonus for this group
                                        chain_len = group["chain_len"]
                                        chain_bonus = min(0.10 * chain_len, 0.50)
                                        chain_bonus_pct = int(chain_bonus * 100)
                                        # Single move cost
                                        move_cost = int(base_cost * (1.0 - chain_bonus))
                                        # Total cost for all moves in chain
                                        total_chain_cost = int(base_cost * chain_len * (1.0 - chain_bonus))
                                
                                move_index += 1
                            
                            if is_last_in_chain:
                                $ b_label = ('Bd' if combat_game.bounce_type == 'diagonal' else ('Bc' if combat_game.bounce_type == 'cardinal' else ''))
                                python:
                                    # Apply bounce only to eligible moves within this chain
                                    bounce_applicable_count = 0
                                    if combat_game.bounce_start_move_idx is not None:
                                        last_idx = combat_game.bounce_end_move_idx if combat_game.bounce_end_move_idx is not None else (move_index - 1)
                                        start_overlap = max(group["start_idx"], combat_game.bounce_start_move_idx)
                                        end_overlap = min(group["end_idx"], last_idx)
                                        if end_overlap >= start_overlap:
                                            bounce_applicable_count = end_overlap - start_overlap + 1
                                            # Adjust total_chain_cost for eligible moves with SCALING
                                            # rates: 10,12.5,15,17.5,20
                                            rates = [0.10, 0.125, 0.15, 0.175, 0.20]
                                            per_step_after_chain = int(base_cost * (1.0 - chain_bonus)) if chain_bonus_pct > 0 else base_cost
                                            local_total = total_chain_cost

                                            for k in range(bounce_applicable_count):

                                                local_total -= int(per_step_after_chain * rates[min(k, 4)])
                                            total_chain_cost = local_total
                                            # Adjust single move cost if this last move is eligible
                                            if (move_index - 1) >= start_overlap and (move_index - 1) <= end_overlap:
                                                # Calculate position in bounce chain
                                                pos = (move_index - 1) - combat_game.bounce_start_move_idx
                                                move_cost = int(move_cost * (1.0 - rates[min(pos, 4)]))
                                text f"  {tile_name} - {total_chain_cost} ({move_cost}) Stamina {(f'(Dir -{chain_bonus_pct}%)' if chain_bonus_pct>0 else '')} {(f'({b_label} -{bounce_pct}%)' if bounce_pct>0 and b_label else '')} {(f'(Pattern +{pat_hit_pct}% Hit +{pat_dmg_pct}% Dmg)' if pat_hit_pct or pat_dmg_pct else '')}" size 14 color chain_color xalign 0.5
                            elif act_idx in action_to_chain:
                                # In chain but not last
                                text f"  {tile_name}" size 14 color chain_color xalign 0.5
                            else:
                                # Not in any chain - show base cost
                                $ b_label = ('Bd' if combat_game.bounce_type == 'diagonal' else ('Bc' if combat_game.bounce_type == 'cardinal' else ''))
                                python:
                                    eff_cost = base_cost
                                    b_pct = 0
                                    bounce_applicable = False
                                    if combat_game.bounce_start_move_idx is not None:
                                        last_idx = combat_game.bounce_end_move_idx if combat_game.bounce_end_move_idx is not None else (move_index - 1)
                                        bounce_applicable = ((move_index - 1) >= combat_game.bounce_start_move_idx) and ((move_index - 1) <= last_idx)
                                    if bounce_applicable:
                                        # Calculate position in bounce chain for scaling
                                        rates = [0.10, 0.125, 0.15, 0.175, 0.20]
                                        pos = (move_index - 1) - combat_game.bounce_start_move_idx
                                        rate = rates[min(pos, 4)]

                                        eff_cost = int(base_cost * (1.0 - rate))
                                        b_pct = int(rate * 100)
                                text f"  {tile_name} - {eff_cost} Stamina {f'({b_label} -{b_pct}%)' if b_pct>0 and b_label else ''}" size 14 color "#FFFF00" xalign 0.5
                        elif action[0] == "bounce":
                            python:
                                _unused = None
                        elif action[0] == "rotate":
                            python:
                                # Check if rotation is part of a chain
                                rot_color = "#FFFF00"
                                rot_cost = 0  # Placeholder for future
                                if act_idx in action_to_chain:
                                    rot_color = action_to_chain[act_idx]["color"]
                            text f"  Rotate {action[1]} deg - {rot_cost} Stamina" size 14 color rot_color xalign 0.5
                        elif action[0] == "attack":
                            python:
                                atk_kind = action[1]
                                facing_bonus = min(0.10 * combat_game.facing_chain_length, 0.50) if combat_game.facing_chain_length > 0 else 0.0
                                bounce_bonus = combat_game.bounce_hit_bonus if combat_game.bounce_active else 0.0
                                pattern_hit = pat['hit_bonus'] if pat else 0.0
                                hit_pct = int(calculate_hit_chance(combat_game.get_current_player(), combat_game.get_opponent(), atk_kind, None, facing_bonus, bounce_bonus, pattern_hit, None, 0.0, 0.0, False) * 100)
                                fb_pct = int(facing_bonus * 100)
                                bb_pct = int(bounce_bonus * 100)
                                ph_pct = int(pattern_hit * 100)
                                pd_pct = pat_dmg_pct
                                pos_dmg_pct = int((min(facing_bonus, 0.15) + min(bounce_bonus * 0.4, 0.10) + min((pat['damage_bonus'] if pat else 0.0), 0.25)) * 100)
                            text f"  {action[1].title()} Attack (Hit {hit_pct}%){f' (Dmg +{pos_dmg_pct}%)' if pos_dmg_pct else ''}{f' (Dir +{fb_pct}%)' if fb_pct else ''}{f' (Bounce +{bb_pct}%)' if bb_pct else ''}{f' (Pattern +{ph_pct}% Hit +{pd_pct}% Dmg)' if ph_pct or pd_pct else ''}" size 14 color "#FFFF00" xalign 0.5
                        elif action[0] == "defense":
                            text f"  {action[1].title()} Defense" size 14 color "#FFFF00" xalign 0.5
                vbox:
                    xalign 0.5
                    spacing 6
                    text "Bonuses" size 14 color "#FFFF00" xalign 0.5
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
                        text f"  Facing chain: -{dir_pct}% cost" size 12 color "#FFFF00" xalign 0.5
                    if combat_game.bounce_active:
                        text f"  Bounce (Move {combat_game.bounce_chain_length}): -{bounce_pct}% cost{f' (+{bounce_hit_pct}% Hit)' if bounce_hit_pct else ''}" size 12 color "#FFFF00" xalign 0.5
                    if pat:
                        text f"  Pattern: {pat.get('name','')} +{pat_hit_pct}% Hit +{pat_dmg_pct}% Dmg" size 12 color "#FFFF00" xalign 0.5
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
