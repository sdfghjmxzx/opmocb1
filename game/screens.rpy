init python:
    import pygame, math, sys, tempfile, subprocess, os
    from controller import CombatGame
    from engine.combat import calculate_hit_chance
    # combat_game will be initialized by script.rpy labels (start or sp_game_start)
    # Initialize with empty instance to prevent errors
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
    def get_player_zoom(player, extra_scale=1.0):
        # Base figurine zoom
        base = 0.12
        return base * extra_scale
    
    # Auto-scroll viewport helper
    _viewport_content_sizes = {}
    
    def _auto_scroll_viewport(vp_id):
        """Auto-scroll viewport to bottom only when content changes."""
        try:
            vp = renpy.get_widget("battle_screen", vp_id)
            if not vp:
                return
            
            adj = vp.yadjustment
            if not adj:
                return
            
            # Track content size - only scroll if content grew
            current_size = adj.range
            last_size = _viewport_content_sizes.get(vp_id, 0)
            
            if current_size > last_size:
                # Content grew - scroll to bottom
                adj.change(adj.range)
                _viewport_content_sizes[vp_id] = current_size
            elif current_size < last_size:
                # Content shrunk - update tracking
                _viewport_content_sizes[vp_id] = current_size
        except:
            pass
    
    # ===== ANIMATION SYSTEM HELPERS =====
    
    def lerp(a, b, t):
        """Linear interpolation between a and b by factor t (0.0 to 1.0)."""
        return a + (b - a) * t
    
    def ease_hop(progress, height=0.3):
        """Hop animation curve: 0→0, 0.5→height, 1→0 using sine wave."""
        import math
        return 1.0 + height * math.sin(progress * math.pi)
    
    def ease_dip(progress, depth=0.2):
        """Dip animation curve: 0→0, 0.5→-depth, 1→0 using sine wave."""
        import math
        return 1.0 - depth * math.sin(progress * math.pi)
    
    # Animation playback state (shared for both players)
    animation_playing = False
    animation_start_time = 0.0
    animation_group_duration = 0.0
    
    def get_animation_progress():
        """Get progress (0.0 to 1.0) through current animation group."""
        global animation_playing, animation_start_time, animation_group_duration
        if not combat_game.animation_system.is_playing() or not animation_playing or animation_group_duration <= 0:
            return 0.0
        import time
        now = time.time()
        t = max(0.0, min(1.0, (now - animation_start_time) / animation_group_duration))
        return t
    
    def update_animation_state():
        """Manage animation playback lifecycle - called every frame."""
        global animation_playing, animation_start_time, animation_group_duration
        
        if combat_game.animation_system.is_playing():
            if not animation_playing:
                # Start new animation group
                group = combat_game.animation_system.get_current_group()
                if not group:
                    completed = combat_game.animation_system.mark_current_complete()
                    combat_game.apply_completed_animations(completed)
                    animation_playing = False
                    return
                # Use max duration among animations in group for concurrent playback
                durations = [combat_game.animation_system.get_animation_duration(anim) for anim in group]
                animation_group_duration = max(durations) if durations else 0.5
                import time
                animation_start_time = time.time()
                animation_playing = True
            else:
                # Check if current animation group is complete
                import time
                now = time.time()
                if animation_group_duration > 0 and (now - animation_start_time) >= animation_group_duration:
                    # Advance to next group and apply state changes
                    completed = combat_game.animation_system.mark_current_complete()
                    combat_game.apply_completed_animations(completed)
                    animation_playing = False
        else:
            animation_playing = False
    
    def get_player_display_state(player_id):
        """Return (row, col, facing, zoom_scale) for rendering the player figurine.
        
        Uses animation_system when playing; otherwise returns actual player state and scale=1.0.
        """
        # Base state from combat_game
        if player_id == "player1":
            player = combat_game.player1
        else:
            player = combat_game.player2
        
        row = float(player.row)
        col = float(player.col)
        facing = float(player.facing)
        zoom_scale = 1.0
        
        if not combat_game.animation_system.is_playing():
            return row, col, facing, zoom_scale
        
        group = combat_game.animation_system.get_current_group()
        if not group:
            return row, col, facing, zoom_scale
        
        progress = get_animation_progress()
        
        # Process flash animations FIRST (they're not player-specific)
        for anim in group:
            if anim.anim_type == "flash":
                # Single flash animation: set flash pattern and visibility
                pattern = anim.params.get("pattern", [])
                speed_multiplier = anim.params.get("speed_multiplier", 1.0) or 1.0
                flash_duration = 0.4 / speed_multiplier  # Same formula as movement/rotation
                # Flash is visible for 70% of duration, off for 30%
                visible_duration = flash_duration * 0.7
                elapsed = progress * flash_duration
                combat_game.animation_system.current_flash_pattern = pattern
                combat_game.animation_system.flash_visible = (elapsed < visible_duration)
                break  # Only one flash animation per group
            elif anim.anim_type == "combat_flash":
                # Combat flash: alternating attacker and defender patterns
                # Take max duration of attack/defense (they run concurrently)
                # Divide by 3 (no counter) or 6 (with counter) to get per-flash duration
                attacker_pattern = anim.params.get("attacker_pattern", [])
                defender_pattern = anim.params.get("defender_pattern", [])
                
                # Calculate elapsed time
                import time
                now = time.time()
                elapsed = now - animation_start_time
                total_duration = animation_group_duration  # Max of attack/defense animations
                
                if total_duration > 0:
                    # Determine total number of flashes and duration per flash
                    if defender_pattern:
                        # Counter: 6 flashes total (3 attacker + 3 defender, alternating)
                        total_flashes = 6
                        single_flash_duration = total_duration / 6.0
                    else:
                        # No counter: 3 flashes total (all attacker)
                        total_flashes = 3
                        single_flash_duration = total_duration / 3.0
                    
                    # Calculate which flash we're currently in (0-5 or 0-2)
                    flash_index = int(elapsed / single_flash_duration)
                    flash_progress = (elapsed % single_flash_duration) / single_flash_duration
                    
                    if flash_index < total_flashes:
                        # Determine which pattern to show
                        if defender_pattern:
                            # Alternate: even indices = attacker, odd indices = defender
                            if flash_index % 2 == 0:
                                combat_game.animation_system.current_flash_pattern = attacker_pattern
                            else:
                                combat_game.animation_system.current_flash_pattern = defender_pattern
                        else:
                            # No counter: always attacker
                            combat_game.animation_system.current_flash_pattern = attacker_pattern
                        
                        # Flash visible for 70% of its duration, off for 30%
                        combat_game.animation_system.flash_visible = (flash_progress < 0.7)
                    else:
                        # All flashes complete
                        combat_game.animation_system.current_flash_pattern = []
                        combat_game.animation_system.flash_visible = False
                else:
                    combat_game.animation_system.current_flash_pattern = []
                    combat_game.animation_system.flash_visible = False
                break  # Only one flash animation per group
        
        # When animating, use animation params for base facing instead of player.facing
        # This prevents instant snap to final facing
        facing_from_anim = None
        
        for anim in group:
            if anim.player_id != player_id:
                continue
            if anim.anim_type == "movement":
                fr = anim.params.get("from_row", row)
                fc = anim.params.get("from_col", col)
                tr = anim.params.get("to_row", row)
                tc = anim.params.get("to_col", col)
                row = lerp(fr, tr, progress)
                col = lerp(fc, tc, progress)
                # Movement hop animation
                zoom_scale = ease_hop(progress, height=0.3)
            elif anim.anim_type == "push":
                # Push animation - slide from start to end position
                fr = anim.params.get("from_row", row)
                fc = anim.params.get("from_col", col)
                tr = anim.params.get("to_row", row)
                tc = anim.params.get("to_col", col)
                row = lerp(fr, tr, progress)
                col = lerp(fc, tc, progress)
                zoom_scale = 1.0  # No hop for push
            elif anim.anim_type == "rotation":
                ff = float(anim.params.get("from_facing", facing))
                tf = float(anim.params.get("to_facing", facing))
                # Use from_facing as base if this is the first rotation in group
                if facing_from_anim is None:
                    facing_from_anim = ff
                # Handle 360° wrapping - take shortest path
                diff = tf - ff
                if diff > 180:
                    diff -= 360
                elif diff < -180:
                    diff += 360
                facing = ff + diff * progress
                # Rotation hop animation
                zoom_scale = ease_hop(progress, height=0.3)
            elif anim.anim_type == "attack":
                is_skip = bool(anim.params.get("is_skip", False))
                is_hit = bool(anim.params.get("is_hit", False))
                dmg = int(anim.params.get("damage_output", 0))
                if is_skip:
                    # Skip: dip animation
                    zoom_scale = ease_dip(progress, depth=0.2)
                else:
                    # Attack animation:
                    # ALWAYS one hop, then SECOND hop only if attack HIT (based on hit chance roll)
                    
                    if is_hit:
                        # HIT: Split progress into two hops: 0-0.5 = first hop, 0.5-1.0 = second hop
                        if progress <= 0.5:
                            # First hop: always 0.3 height (= 1.3 zoom)
                            hop_progress = progress * 2.0  # Remap 0-0.5 to 0-1
                            zoom_scale = ease_hop(hop_progress, height=0.3)
                        else:
                            # Second hop: damage-scaled height
                            hop_progress = (progress - 0.5) * 2.0  # Remap 0.5-1.0 to 0-1
                            # Base damage = 20, dmg_factor = 1.0 at 20 damage
                            # Formula from plan: zoom = 1.3 + (damage_percent / 100) * 0.3
                            # Height = zoom - 1.0, so height = 0.3 + (damage_percent / 100) * 0.3
                            damage_percent = (dmg / 20.0) * 100.0
                            height = 0.3 + (damage_percent / 100.0) * 0.3
                            zoom_scale = ease_hop(hop_progress, height=height)
                    else:
                        # MISS: Single hop throughout entire animation
                        zoom_scale = ease_hop(progress, height=0.3)
            elif anim.anim_type == "defense":
                defense_type = anim.params.get("defense_type")
                # Use player's current position as base for defense animations
                # Defense animations (tank, defend, evade, counter) are in-place at current location
                base_row = row
                base_col = col
                base_facing = facing
                
                if defense_type == "tank":
                    # Tank: dip animation like skip
                    zoom_scale = ease_dip(progress, depth=0.2)
                elif defense_type == "defend":
                    # Defend: rotation sequence +45°→0°→-45°→0° repeated 3 times (6 rotations total)
                    # Progress 0-1 maps to 6 segments
                    segment_duration = 1.0 / 6.0
                    segment_index = int(progress / segment_duration)
                    segment_progress = (progress % segment_duration) / segment_duration
                    
                    # Rotation pattern: [+45, 0, -45, 0, +45, 0] relative to base facing
                    rotation_deltas = [45, 0, -45, 0, 45, 0]
                    
                    if segment_index < 6:
                        from_delta = rotation_deltas[segment_index - 1] if segment_index > 0 else 0
                        to_delta = rotation_deltas[segment_index]
                        
                        # Interpolate rotation delta
                        current_delta = lerp(from_delta, to_delta, segment_progress)
                        facing = base_facing + current_delta
                    
                    # Maintain hop throughout
                    zoom_scale = ease_hop(progress, height=0.15)
                elif defense_type == "evade":
                    # Evade: shake sequence - horizontal movement perpendicular to facing
                    # Progress 0-1 maps to 6 segments
                    segment_duration = 1.0 / 6.0
                    segment_index = int(progress / segment_duration)
                    segment_progress = (progress % segment_duration) / segment_duration
                    
                    # Horizontal offset pattern: [+0.5, 0, -0.5, 0, +0.5, 0]
                    horizontal_offsets = [0.5, 0, -0.5, 0, 0.5, 0]
                    
                    if segment_index < 6:
                        from_offset = horizontal_offsets[segment_index - 1] if segment_index > 0 else 0
                        to_offset = horizontal_offsets[segment_index]
                        
                        # Interpolate horizontal offset
                        current_offset = lerp(from_offset, to_offset, segment_progress)
                        
                        # Convert offset to row/col based on perpendicular to facing
                        # Perpendicular right = facing - 90 degrees
                        import math
                        perp_facing = (base_facing - 90) % 360
                        perp_rad = math.radians(perp_facing)
                        row = base_row + current_offset * math.sin(perp_rad)
                        col = base_col + current_offset * math.cos(perp_rad)
                    
                    # Maintain hop throughout
                    zoom_scale = ease_hop(progress, height=0.15)
                elif defense_type == "counter":
                    # Counter: single hop like attack
                    zoom_scale = ease_hop(progress, height=0.3)
            elif anim.anim_type == "doom":
                # Doom: sink/shrink effect
                zoom_scale = ease_dip(progress, depth=0.4)
        
        return row, col, facing, zoom_scale

# Transform for player images
transform player_transform(angle, zoom_level=1.0):
    rotate angle
    zoom zoom_level

screen battle_screen():
    tag game

    # Drive animation playback and doom/gameover checks
    if combat_game.animation_system.is_playing():
        timer 0.016 repeat True action Function(update_animation_state)
    timer 0.1 repeat True action Function(combat_game.check_animation_completion)

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
                        # Check if this tile is part of a flash animation
                        $ is_flash_tile = (row, col) in combat_game.animation_system.current_flash_pattern and combat_game.animation_system.flash_visible
                        
                        if is_flash_tile:
                            $ bg_color = "#ff000024"  # Red for flash tiles (same as attack pattern)
                        elif is_enemy_attack:
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
                            
                            # COMBAT PATTERN FLASH - show overlay during flash animations
                            if is_flash_tile:
                                add "attack_circle.png":
                                    xalign 0.5 yalign 0.5
                                    size (70, 70)
                                    alpha 0.8
                            
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
            # Tile image - just visual, doesn't capture clicks
            add Transform(tile_img, xysize=(square_size - 3, square_size - 3), alpha=0.8):
                xpos tile_x
                ypos tile_y
                anchor (0.55, 0.59)
            # Invisible hover detector on top that DOESN'T block clicks (no action)
            # Note: In Ren'Py, buttons with no action or NullAction() still block clicks
            # So we just remove the hover functionality - HP will show in planning mode anyway
        
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
    # Get animated display state for VISUAL rendering only
    $ p1_row, p1_col, p1_facing, p1_zoom_scale = get_player_display_state("player1")
    $ p1_visual_x = int(925 + (p1_col - 3) * (square_size + spacing) + square_size/2)
    $ p1_visual_y = int(510 + (p1_row - 3) * (square_size + spacing) + square_size/2)
    
    # Calculate ACTUAL (non-animated) position for button hitbox - uses player.row/col integers
    $ p1_button_x = int(925 + (combat_game.player1.col - 3) * (square_size + spacing) + square_size/2)
    $ p1_button_y = int(510 + (combat_game.player1.row - 3) * (square_size + spacing) + square_size/2)
    
    $ sea_offset_player = 100
    $ p1_on_sea = combat_game.p1_sea_doom
    if p1_on_sea:
        if combat_game.player1.row == 0:
            $ p1_visual_y -= sea_offset_player
            $ p1_button_y -= sea_offset_player
        elif combat_game.player1.row == 6:
            $ p1_visual_y += sea_offset_player
            $ p1_button_y += sea_offset_player
        if combat_game.player1.col == 0:
            $ p1_visual_x -= sea_offset_player
            $ p1_button_x -= sea_offset_player
        elif combat_game.player1.col == 6:
            $ p1_visual_x += sea_offset_player
            $ p1_button_x += sea_offset_player

    # Calculate zoom based on hover state
    $ p1_base_zoom = get_player_zoom(combat_game.player1, p1_zoom_scale)
    $ p1_final_zoom = p1_base_zoom * 1.2 if hovered_p1 else p1_base_zoom
    
    # Render player sprite with current zoom at ANIMATED position
    add Transform("player1.png", rotate=p1_facing, zoom=p1_final_zoom):
        xpos p1_visual_x
        ypos p1_visual_y
        anchor (0.5, 0.5)
    
    # Invisible button overlay for interaction at FIXED ACTUAL position
    # Sensitive when: 1) current player not in planning, OR 2) enemy in defensive planning
    $ p1_is_current = (combat_game.get_current_player() == combat_game.player1)
    $ p1_is_enemy_in_defense = (is_defensive_planning and not p1_is_current)
    button:
        xpos p1_button_x - 60
        ypos p1_button_y - 60
        xsize 120
        ysize 120
        background None
        action [SetScreenVariable("hovered_p1", False), If((p1_is_current and not combat_game.planning_mode), Function(combat_game.start_movement_planning), NullAction())]
        hovered [SetScreenVariable("hovered_p1", True), If(p1_is_enemy_in_defense, SetScreenVariable("hovered_enemy_in_defense", True), NullAction())]
        unhovered [SetScreenVariable("hovered_p1", False), SetScreenVariable("hovered_enemy_in_defense", False)]
        sensitive (p1_is_enemy_in_defense or (p1_is_current and not combat_game.planning_mode))

    # Player 2 - same pattern
    # Get animated display state for VISUAL rendering only
    $ p2_row, p2_col, p2_facing, p2_zoom_scale = get_player_display_state("player2")
    $ p2_visual_x = int(925 + (p2_col - 3) * (square_size + spacing) + square_size/2)
    $ p2_visual_y = int(510 + (p2_row - 3) * (square_size + spacing) + square_size/2)
    
    # Calculate ACTUAL (non-animated) position for button hitbox - uses player.row/col integers
    $ p2_button_x = int(925 + (combat_game.player2.col - 3) * (square_size + spacing) + square_size/2)
    $ p2_button_y = int(510 + (combat_game.player2.row - 3) * (square_size + spacing) + square_size/2)
    
    $ p2_on_sea = combat_game.p2_sea_doom
    if p2_on_sea:
        if combat_game.player2.row == 0:
            $ p2_visual_y -= sea_offset_player
            $ p2_button_y -= sea_offset_player
        elif combat_game.player2.row == 6:
            $ p2_visual_y += sea_offset_player
            $ p2_button_y += sea_offset_player
        if combat_game.player2.col == 0:
            $ p2_visual_x -= sea_offset_player
            $ p2_button_x -= sea_offset_player
        elif combat_game.player2.col == 6:
            $ p2_visual_x += sea_offset_player
            $ p2_button_x += sea_offset_player

    # Calculate zoom based on hover state
    $ p2_base_zoom = get_player_zoom(combat_game.player2, p2_zoom_scale)
    $ p2_final_zoom = p2_base_zoom * 1.2 if hovered_p2 else p2_base_zoom
    
    # Render player sprite with current zoom at ANIMATED position
    add Transform("player2.png", rotate=p2_facing, zoom=p2_final_zoom):
        xpos p2_visual_x
        ypos p2_visual_y
        anchor (0.5, 0.5)
    
    # Invisible button overlay for interaction at FIXED ACTUAL position
    # Sensitive when: 1) current player not in planning, OR 2) enemy in defensive planning
    $ p2_is_current = (combat_game.get_current_player() == combat_game.player2)
    $ p2_is_enemy_in_defense = (is_defensive_planning and not p2_is_current)
    button:
        xpos p2_button_x - 60
        ypos p2_button_y - 60
        xsize 120
        ysize 120
        background None
        action [SetScreenVariable("hovered_p2", False), If((p2_is_current and not combat_game.planning_mode), Function(combat_game.start_movement_planning), NullAction())]
        hovered [SetScreenVariable("hovered_p2", True), If(p2_is_enemy_in_defense, SetScreenVariable("hovered_enemy_in_defense", True), NullAction())]
        unhovered [SetScreenVariable("hovered_p2", False), SetScreenVariable("hovered_enemy_in_defense", False)]
        sensitive (p2_is_enemy_in_defense or (p2_is_current and not combat_game.planning_mode))

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
                
                # Planned Actions with scrollable viewport
                vbox:
                    spacing 5
                    xalign 0.5
                    xsize 240
                    ysize 140
                    
                    text "Planned Actions:" size 16 color "#FFFF00" xalign 0.5
                    
                    hbox:
                        spacing 0
                        xalign 0.5
                        
                        viewport:
                            id "planned_actions_vp"
                            mousewheel True
                            draggable True
                            xsize 200
                            ysize 100
                            
                            vbox:
                                spacing 2
                                xalign 0.5
                                
                                python:
                                    display = combat_game.get_planned_actions_display()
                                    # Auto-scroll: get the adjustment and set value to max
                                    try:
                                        vp_adj = ui.adjustment()
                                        if vp_adj and hasattr(vp_adj, 'range'):
                                            vp_adj.change(vp_adj.range)
                                    except:
                                        pass
                                
                                for entry in display:
                                    python:
                                        # Determine text size: larger for attack/defense
                                        is_action = entry.get("type") in ("attack", "defense")
                                        text_size = 16 if is_action else 14
                                    text entry["text"] size text_size color entry["color"] xalign 0.5
                        
                        vbar:
                            value YScrollValue("planned_actions_vp")
                            unscrollable "hide"
                    
                    # Auto-scroll to bottom on content change
                    timer 0.1 repeat True:
                        action Function(lambda: _auto_scroll_viewport("planned_actions_vp"))

                vbox:
                    xalign 0.5
                    spacing 5
                    xsize 240
                    ysize 90
                    
                    text "Active Bonuses" size 14 color "#FFFF00" xalign 0.5
                    
                    hbox:
                        spacing 0
                        xalign 0.5
                        
                        viewport:
                            id "active_bonuses_vp"
                            mousewheel True
                            draggable True
                            xsize 220
                            ysize 50
                            
                            vbox:
                                spacing 2
                                xalign 0.5
                                
                                python:
                                    # Auto-scroll: get the adjustment and set value to max
                                    try:
                                        vp_adj = ui.adjustment()
                                        if vp_adj and hasattr(vp_adj, 'range'):
                                            vp_adj.change(vp_adj.range)
                                    except:
                                        pass
                                
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
                        
                        vbar:
                            value YScrollValue("active_bonuses_vp")
                            unscrollable "hide"
                    
                    # Auto-scroll to bottom on content change
                    timer 0.1 repeat True:
                        action Function(lambda: _auto_scroll_viewport("active_bonuses_vp"))
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
                if combat_game.planned_actions:
                    textbutton "UNDO LAST ACTION" action Function(combat_game.undo_last_planned_action) background "#ff000050" text_color "#FFFF00" xalign 0.5
                else:
                    textbutton "UNDO LAST ACTION" action NullAction() background "#44444450" text_color "#888888" xalign 0.5
                hbox:
                    xalign 0.5
                    spacing 10
                    textbutton "CONFIRM TURN" action Function(combat_game.confirm_turn) background "#0d00ff50" text_color "#FFFF00"
                    textbutton "CANCEL" action Function(combat_game.cancel_planning) background "#053efb6e" text_color "#FFFF00"

    # Battle Log with WORKING scrollbar
    frame:
        xpos 20
        ypos 400
        xsize 250
        ysize 250
        background Solid("#222233AA")
        
        vbox:
            spacing 5
            
            text "BATTLE LOG" size 20 color "#FFFF00" xalign 0.5
            
            hbox:
                spacing 0
                
                viewport:
                    id "battle_log_vp"
                    mousewheel True
                    draggable True
                    xsize 230
                    ysize 215
                    
                    vbox:
                        spacing 2
                        
                        python:
                            history = combat_game.battle_history
                            # Auto-scroll: get the adjustment and set value to max
                            try:
                                vp_adj = ui.adjustment()
                                if vp_adj and hasattr(vp_adj, 'range'):
                                    vp_adj.change(vp_adj.range)
                            except:
                                pass
                        
                        # Show turn separator and phases
                        for turn_record in history:
                            python:
                                turn_num = turn_record.get('turn', '?')
                                player_name = turn_record.get('player', '?')
                                player_col = turn_record.get('player_color', '#FFF')
                                moves_list = turn_record.get('moves', [])
                                action_text = turn_record.get('action')
                                results_list = turn_record.get('results', [])
                            
                            text "=== Turn [turn_num] ===" size 14 color "#FFFF00"
                            text player_name size 13 color player_col
                            
                            if moves_list:
                                python:
                                    move_str = "  " + " -> ".join(moves_list)
                                text move_str size 11 color "#AAA"
                            
                            if action_text:
                                python:
                                    act_str = "  " + action_text
                                text act_str size 11 color "#FFF"
                            
                            for res_text in results_list:
                                python:
                                    res_str = "  " + res_text
                                text res_str size 10 color "#FA0"
                
                vbar:
                    value YScrollValue("battle_log_vp")
                    unscrollable "hide"
            
            # Auto-scroll to bottom on content change
            timer 0.1 repeat True:
                action Function(lambda: _auto_scroll_viewport("battle_log_vp"))

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

# ===== MAIN MENU SHELL STATE =====

default main_menu_sp_mode = "vs_computer"
default main_menu_sp_selected_label = "Empty Slot"
default main_menu_sp_enemy_type = "computer_ai"
default main_menu_sp_gallery_search = ""
default main_menu_sp_gallery_selected = ""
default main_menu_sp_p1_selected = "None"
default main_menu_sp_p2_selected = "None"
default main_menu_sp_p1_mode = "preset"  # "preset" or "custom"
default main_menu_sp_p2_mode = "preset"  # "preset" or "custom"
default main_menu_sp_p1_custom_name = ""
default main_menu_sp_p1_custom_strength = 50
default main_menu_sp_p1_custom_defense = 50
default main_menu_sp_p1_custom_speed = 50
default main_menu_sp_p1_custom_reaction = 50
default main_menu_sp_p1_custom_endurance = 50
default main_menu_sp_p1_custom_willpower = 50
default main_menu_sp_p1_custom_haki = 50
default main_menu_sp_p1_custom_devil_fruit = 50
default main_menu_sp_p1_custom_power = "None"
default main_menu_sp_temp_presets = []  # Temporary custom characters for current session
default main_menu_cc_name = ""
default main_menu_cc_points_total = 300
default main_menu_cc_strength = 50
default main_menu_cc_defense = 30
default main_menu_cc_speed = 50
default main_menu_cc_reaction = 25
default main_menu_cc_endurance = 45
default main_menu_cc_willpower = 20
default main_menu_cc_haki = 35
default main_menu_cc_devil_fruit = 10

default main_menu_cc_power_search = ""
default main_menu_cc_power_category = "All"
default main_menu_cc_power_subfilter = "All"
default main_menu_cc_selected_power = ""
default main_menu_cc_category_open = False
default main_menu_cc_filter_open = False

default main_menu_cc_powers = [
    { "name": "Flame Logia", "category": "Logia", "sub": "Elemental" },
    { "name": "Ice Logia", "category": "Logia", "sub": "Elemental" },
    { "name": "Smoke Logia", "category": "Logia", "sub": "Physical" },
    { "name": "Light Logia", "category": "Logia", "sub": "Physical" },
    { "name": "Rubber Paramecia", "category": "Paramecia", "sub": "Unique" },
    { "name": "Clone Paramecia", "category": "Paramecia", "sub": "Unique" },
    { "name": "Wolf Zoan", "category": "Zoan", "sub": "Animal" },
    { "name": "Eagle Zoan", "category": "Zoan", "sub": "Animal" },
    { "name": "Vine Zoan", "category": "Zoan", "sub": "Plant" },
]

default main_menu_cc_category_options = ["All", "Logia", "Paramecia", "Zoan"]
default main_menu_cc_filter_options = {
    "All": ["All"],
    "Logia": ["All", "Elemental", "Physical"],
    "Paramecia": ["All", "Unique"],
    "Zoan": ["All", "Animal", "Plant"]
}

init python:
    import json
    import renpy.exports as renpy
    character_presets = []
    main_menu_sp_presets = []
    
    # Function to get character stats by name
    def get_char_stat(char_name, stat_key, default=50):
        # Check if custom mode and return custom stats
        if char_name == "Custom Fighter":
            stat_map = {
                "strength": main_menu_sp_p1_custom_strength,
                "defense": main_menu_sp_p1_custom_defense,
                "speed": main_menu_sp_p1_custom_speed,
                "reaction": main_menu_sp_p1_custom_reaction,
                "endurance": main_menu_sp_p1_custom_endurance,
                "willpower": main_menu_sp_p1_custom_willpower,
                "haki": main_menu_sp_p1_custom_haki,
                "devil_fruit": main_menu_sp_p1_custom_devil_fruit
            }
            return stat_map.get(stat_key, default)
        
        # Check temp presets
        for preset in main_menu_sp_temp_presets:
            if preset.get("name") == char_name:
                return preset.get("stats", {}).get(stat_key, default)
        
        # Check permanent presets
        for preset in character_presets:
            if preset.get("name") == char_name:
                return preset.get("stats", {}).get(stat_key, default)
        return default
    
    def save_custom_preset(name, stats, power):
        """Save custom character to characters.json"""
        import json
        import os
        
        json_path = os.path.join(renpy.config.gamedir, "data", "characters.json")
        
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
        except:
            data = {"presets": []}
        
        # Check if name already exists
        existing_names = [p.get("name") for p in data.get("presets", [])]
        if name in existing_names:
            return None  # Name already exists, don't save
        
        # Create new preset
        new_preset = {
            "id": name.lower().replace(" ", "_"),
            "name": name,
            "picture": "images/characters/unknown.png",
            "stats": stats,
            "power": power,
            "is_custom": True
        }
        
        # Add to presets
        data["presets"].append(new_preset)
        
        # Save file
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)
        
        # Reload presets
        global character_presets
        character_presets = data.get("presets", [])
        
        # Also add to temp presets and select it
        global main_menu_sp_temp_presets, main_menu_sp_p1_selected, main_menu_sp_p1_mode
        # Remove existing temp with same name
        main_menu_sp_temp_presets[:] = [p for p in main_menu_sp_temp_presets if p.get("name") != name]
        # Select the newly saved preset
        main_menu_sp_p1_selected = name
        main_menu_sp_p1_mode = "preset"
        
        return None
    
    def delete_custom_preset(name):
        """Delete custom character from characters.json"""
        import json
        import os
        
        json_path = os.path.join(renpy.config.gamedir, "data", "characters.json")
        
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
        except:
            return None
        
        # Remove preset if it's custom
        presets = data.get("presets", [])
        data["presets"] = [p for p in presets if not (p.get("name") == name and p.get("is_custom", False))]
        
        # Save file
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)
        
        # Reload presets
        global character_presets
        character_presets = data.get("presets", [])
        
        return None
    
    try:
        data_path = renpy.loader.transfn("data/characters.json")
        with open(data_path, "r") as f:
            data = json.load(f)
            character_presets = data.get("presets", [])
            main_menu_sp_presets = [p["name"] for p in character_presets]
    except Exception as e:
        main_menu_sp_presets = ["Error loading: " + str(e)]

default main_menu_mp_lobby_name = ""
default main_menu_mp_is_host = True
default main_menu_mp_room_status = "waiting"
default main_menu_mp_host_ready = False
default main_menu_mp_guest_ready = False

default main_menu_mp_chat_input = ""

default main_menu_mp_global_chat_lines = [
    "Player1: Anyone up for a match?",
    "Player2: Creating lobby now"
]

default main_menu_mp_lobby_chat_lines = [
    "Luffy_93: Ready when you are!",
    "ZoroSwords: One sec, picking character"
]

# ===== MAIN MENU ROOT SCREEN =====
transform main_menu_button:
    anchor (0.5, 0.5)
    on idle:
        zoom 1.0
    on hover:
        zoom 1.05


screen main_menu_shell():
    tag main_menu_shell

    add Solid("#000000")

    frame:
        xalign 0.5
        yalign 0.5
        xmaximum 600
        ymaximum 400
        add "images/menu/Background2.png":
            xalign 0.5
            yalign 0.5
            zoom 1.1
          
        vbox:
            spacing 20
            xalign 0.8
            yalign 0.1
            
            fixed:
                # Translucent background frame
                frame:
                    xalign 0.5
                    yalign -0.5
                    background Solid("#00000077")  # Use Solid for the background
                    xpadding 20
                    ypadding 15
                
                vbox:
                    xsize 250
                    spacing 10
                    xalign 0.5
                    yalign 0.5
                    
                    fixed:
                        xsize 250
                        ysize 50
                        imagebutton:
                            idle Transform("images/menu/singleplayer.png", ysize=40, fit="contain")
                            hover Transform("images/menu/singleplayer.png", ysize=40, fit="contain")
                            action Show("sp_character_select_screen")
                            xalign 0.5
                            yalign 0.5
                            at main_menu_button
                    null height 20
                    fixed:
                        xsize 250
                        ysize 50
                        imagebutton:
                            idle Transform("images/menu/multiplayer.png", ysize=40, fit="contain")
                            hover Transform("images/menu/multiplayer.png", ysize=40, fit="contain")
                            action Show("mp_hub_screen")
                            xalign 0.5
                            yalign 0.5
                            at main_menu_button
                    null height 20
                    fixed:
                        xsize 250
                        ysize 50
                        imagebutton:
                            idle Transform("images/menu/options.png", ysize=40, fit="contain")
                            hover Transform("images/menu/options.png", ysize=40, fit="contain")
                            action Show("sp_character_select_screen")
                            xalign 0.5
                            yalign 0.5
                            at main_menu_button
                    null height 20
                    fixed:
                        xsize 250
                        ysize 50
                        imagebutton:
                            idle Transform("images/menu/quit.png", ysize=40, fit="contain")
                            hover Transform("images/menu/quit.png", ysize=40, fit="contain")
                            action Show("sp_character_select_screen")
                            xalign 0.5
                            yalign 0.5
                            at main_menu_button
                

# ===== SINGLE PLAYER FLOW SCREENS =====

screen sp_mode_select_screen():
    tag main_menu_shell

    add Solid("#000000")

    frame:
        xalign 0.5
        yalign 0.5
        xmaximum 700
        ymaximum 400
        background Solid("#000000CC")

        vbox:
            spacing 20
            xalign 0.5

            text "SINGLE PLAYER: Select Game Mode" size 32 xalign 0.5

            hbox:
                spacing 40
                xalign 0.5

                textbutton "VS Computer":
                    xminimum 250
                    action SetVariable("main_menu_sp_mode", "vs_computer")
                    selected main_menu_sp_mode == "vs_computer"

                textbutton "2 Players":
                    xminimum 250
                    action SetVariable("main_menu_sp_mode", "two_player")
                    selected main_menu_sp_mode == "two_player"

            hbox:
                spacing 40
                xalign 0.5

                textbutton "CONTINUE" action Show("sp_character_select_screen")
                textbutton "BACK" action Show("main_menu_shell")


screen sp_character_select_screen():
    tag main_menu_shell

    add Solid("#000000")
    add "images/menu/singleplayer_background.png":
        fit "cover"

    python:
        # Load character presets from JSON
        import json
        import os
        character_presets = []
        devil_fruits = []
        all_presets = []  # Combined permanent + temp
        
        json_path = os.path.join(renpy.config.gamedir, "data", "characters.json")
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
                character_presets = data.get("presets", [])
        except:
            character_presets = []
        
        # Combine permanent and temp presets
        all_presets = character_presets + main_menu_sp_temp_presets
        
        # Load devil fruits
        df_json_path = os.path.join(renpy.config.gamedir, "data", "devil_fruits.json")
        try:
            with open(df_json_path, "r") as f:
                df_data = json.load(f)
                devil_fruits = df_data.get("fruits", [])
        except:
            devil_fruits = []
        
        # Grid settings
        cell_width = 160
        cell_height = 260
        spacing_size = 15
        cols_per_row = 4
        
        # Calculate dimensions
        total_presets = len(all_presets)
        total_rows = (total_presets + cols_per_row - 1) // cols_per_row
        square_height = cell_height + 30
        content_height = (total_rows * square_height) + ((total_rows - 1) * spacing_size)
        content_width = (cols_per_row * cell_width)

    frame:
        xalign 0.5
        yalign 0.5
        xmaximum 1920
        ymaximum 1080
        background Solid("#000000CC")

        vbox:
            spacing 20
            xalign 0.5
            
            
            
            hbox:
                spacing 40
                xalign 0.5
                
                # PLAYER 1 GALLERY - LEFT
                vbox:
                    spacing 10
                    imagebutton:
                            idle Transform("images/menu/player1.png", ysize=40, fit="contain")
                            xalign 0.99
                    # Toggle Preset
                    hbox:
                        spacing 25
                        xalign 0.5
                        
                        $ bg_color = "#8888885a"  # Or any color you prefer for the toggle background
                        
                        text "{b}Preset{/b}":
                            size 18
                            color ("#ffff00" if main_menu_sp_p1_mode == "preset" else "#888")
                            yalign 0.5
                        
                        button:
                            xsize 50
                            ysize 25
                            background If(main_menu_sp_p1_mode == "preset", bg_color, bg_color)
                            hover_background If(main_menu_sp_p1_mode == "preset", bg_color, bg_color)
                            action [Play("sound", "audio/button_click.wav"), SetVariable("main_menu_sp_p1_mode", "preset" if main_menu_sp_p1_mode != "preset" else "custom")]
                            text "●" size 42 color "#fff" outlines [(2, "#000", 0, 0)] yoffset -18 xalign (0 if main_menu_sp_p1_mode == "preset" else 10) xoffset (-20 if main_menu_sp_p1_mode == "preset" else 30)
                        
                        text "{b}Custom{/b}":
                            size 18
                            color ("#ffff00" if main_menu_sp_p1_mode == "custom" else "#888")
                            yalign 0.5
                    
                    
                    if main_menu_sp_p1_mode == "preset":
                        frame:
                            xsize 700
                            ysize 600
                            background "#33333346"
                            padding (5, 5)
                        
                            hbox:
                                spacing 0
                                
                                viewport:
                                    id "p1_gallery_viewport"
                                    mousewheel True
                                    draggable True
                                    xsize content_width + 35
                                    ysize 580
                            
                                    vbox:
                                        spacing 0
                                        xalign 0.5
                                        
                                        fixed:
                                            xsize content_width
                                            ysize content_height
                                            
                                            # GRID LINES
                                            for col_idx in range(cols_per_row + 1):
                                                $ line_x = col_idx * cell_width
                                                add Solid("#00000000"):
                                                    xpos line_x 
                                                    ypos 0
                                                    xsize 2
                                                    ysize content_height
                                            
                                            for row_idx in range(total_rows + 1):
                                                $ line_y = row_idx * cell_height
                                                add Solid("#00000000"):
                                                    xpos 0
                                                    ypos line_y
                                                    xsize (cols_per_row * cell_width)
                                                    ysize 2
                                            
                                            # SQUARES
                                            for row_idx in range(total_rows):
                                                for col_idx in range(min(cols_per_row, total_presets - row_idx * cols_per_row)):
                                                    python:
                                                        preset_idx = row_idx * cols_per_row + col_idx
                                                        if preset_idx < total_presets:
                                                            preset = all_presets[preset_idx]
                                                            preset_name = preset.get("name", "Unknown")
                                                            cell_x = col_idx * cell_width + 35
                                                            cell_y = row_idx * cell_height + 25
                                                            cell_size_w = cell_width - 10
                                                            cell_size_h = cell_height - 10
                                                            is_custom_preset = preset.get("is_custom", False)
                                                    
                                                    if preset_idx < total_presets:
                                                        button:
                                                            xpos cell_x
                                                            ypos cell_y
                                                            xsize cell_size_w
                                                            ysize cell_size_h
                                                            background "#80808000"
                                                            action SetVariable("main_menu_sp_p1_selected", preset_name)
                                                            
                                                            $ picture_path = preset.get("picture", "")
                                                            
                                                            if picture_path:
                                                                add picture_path:
                                                                    xsize cell_size_w
                                                                    ysize cell_size_h
                                                                    fit "contain"
                                                            
                                                            text preset_name size 20 color "#ffffff" bold True xalign 0.5 ypos cell_size_h - 25
                                                        
                                                        # DELETE button for custom presets
                                                        if is_custom_preset:
                                                            button:
                                                                xpos cell_x + cell_size_w - 25
                                                                ypos cell_y + 5
                                                                xsize 20
                                                                ysize 20
                                                                background "#ff0000cc"
                                                                action Function(delete_custom_preset, preset_name)
                                                                text "X" size 20 color "#ffffff"  xalign 0.8 yalign 0.5
                                
                                vbar:
                                    value YScrollValue("p1_gallery_viewport")
                                    unscrollable "hide"
                    
                    else:
                        # Custom character creator
                        frame:
                            xsize 700
                            ysize 600
                            background "#33333346"
                            padding (30, 30)
                            
                            viewport:
                                mousewheel True
                                draggable True
                                xsize 680
                                ysize 580
                                
                                vbox:
                                    spacing 15
                                    
                                    text "CREATE CHARACTER" size 24 color "#ffffff" bold True xalign 0.5
                                    
                                    # Name input
                                    hbox:
                                        xalign 0.5
                                        spacing 10
                                        text "Name:" size 18 color "#ffffff" yalign 0.5 xsize 100
                                        frame:
                                            xsize 300
                                            ysize 30
                                            background "#333333"
                                            padding (5, 5)
                                            
                                            input:
                                                default main_menu_sp_p1_custom_name
                                                value VariableInputValue("main_menu_sp_p1_custom_name", default=True, returnable=False)
                                                size 16
                                                color "#ffea00"
                                                bold True
                                                length 20
                                                copypaste True
                                    
                                    null height 10
                                    
                                    text "STATS" size 20 color "#00ffff" bold True xalign 0.5
                                    
                                    #First 2 
                                    hbox: 
                                        xalign 0.5
                                        spacing 40
                                        # Strength
                                        vbox:
                                            spacing 10
                                            text "Strength:" size 16 color "#ffffff" yalign 0.5 xsize 120
                                            hbox:
                                                spacing 20
                                                bar:
                                                    value VariableValue("main_menu_sp_p1_custom_strength", 100, style="slider")
                                                    xsize 250
                                                    ysize 20
                                                    left_bar "#0077ff"
                                                    right_bar "#333333"
                                                text "[main_menu_sp_p1_custom_strength]" size 16 color "#00ccff" bold True yalign 0.5 xsize 40
                                        
                                        # Defense
                                        vbox:
                                            spacing 10
                                            text "Defense:" size 16 color "#ffffff" yalign 0.5 xsize 120
                                            hbox:
                                                spacing 20
                                                bar:
                                                    value VariableValue("main_menu_sp_p1_custom_defense", 100, style="slider")
                                                    xsize 250
                                                    ysize 20
                                                    left_bar "#0077ff"
                                                    right_bar "#333333"
                                                text "[main_menu_sp_p1_custom_defense]" size 16 color "#00ccff" bold True yalign 0.5 xsize 40
                                    
                                    #Second 2 
                                    hbox:
                                        spacing 40
                                        xalign 0.5
                                        # Speed
                                        vbox:
                                            spacing 10
                                            text "Speed:" size 16 color "#ffffff" yalign 0.5 xsize 120
                                            hbox:
                                                spacing 20
                                                bar:
                                                    value VariableValue("main_menu_sp_p1_custom_speed", 100, style="slider")
                                                    xsize 250
                                                    ysize 20
                                                    left_bar "#0077ff"
                                                    right_bar "#333333"
                                                text "[main_menu_sp_p1_custom_speed]" size 16 color "#00ccff" bold True yalign 0.5 xsize 40
                                        
                                        # Reaction
                                        vbox:
                                            spacing 10
                                            text "Reaction:" size 16 color "#ffffff" yalign 0.5 xsize 120
                                            hbox:
                                                spacing 20
                                                bar:
                                                    value VariableValue("main_menu_sp_p1_custom_reaction", 100, style="slider")
                                                    xsize 250
                                                    ysize 20
                                                    left_bar "#0077ff"
                                                    right_bar "#333333"
                                                text "[main_menu_sp_p1_custom_reaction]" size 16 color "#00ccff" bold True yalign 0.5 xsize 40
                                    
                                    #Third 2
                                    hbox:
                                        spacing 40
                                        xalign 0.5
                                        # Endurance
                                        vbox:
                                            spacing 10
                                            text "Endurance:" size 16 color "#ffffff" yalign 0.5 xsize 120
                                            hbox:
                                                spacing 20
                                                bar:
                                                    value VariableValue("main_menu_sp_p1_custom_endurance", 100, style="slider")
                                                    xsize 250
                                                    ysize 20
                                                    left_bar "#0077ff"
                                                    right_bar "#333333"
                                                text "[main_menu_sp_p1_custom_endurance]" size 16 color "#00ccff" bold True yalign 0.5 xsize 40
                                        
                                        # Willpower
                                        vbox:
                                            spacing 10
                                            text "Willpower:" size 16 color "#ffffff" yalign 0.5 xsize 120
                                            hbox:
                                                spacing 20
                                                bar:
                                                    value VariableValue("main_menu_sp_p1_custom_willpower", 100, style="slider")
                                                    xsize 250
                                                    ysize 20
                                                    left_bar "#0077ff"
                                                    right_bar "#333333"
                                                text "[main_menu_sp_p1_custom_willpower]" size 16 color "#00ccff" bold True yalign 0.5 xsize 40
                                    
                                    #Forth 2
                                    hbox:
                                        spacing 40
                                        xalign 0.5
                                        # Haki
                                        vbox:
                                            spacing 10
                                            text "Haki:" size 16 color "#ffffff" yalign 0.5 xsize 120
                                            hbox:
                                                spacing 20
                                                bar:
                                                    value VariableValue("main_menu_sp_p1_custom_haki", 100, style="slider")
                                                    xsize 250
                                                    ysize 20
                                                    left_bar "#0077ff"
                                                    right_bar "#333333"
                                                text "[main_menu_sp_p1_custom_haki]" size 16 color "#00ccff" bold True yalign 0.5 xsize 40
                                        
                                        # Devil Fruit
                                        vbox:
                                            spacing 10
                                            text "Devil Fruit:" size 16 color "#ffffff" yalign 0.5 xsize 120
                                            hbox:
                                                spacing 20
                                                bar:
                                                    value VariableValue("main_menu_sp_p1_custom_devil_fruit", 100, style="slider")
                                                    xsize 250
                                                    ysize 20
                                                    left_bar "#0077ff"
                                                    right_bar "#333333"
                                                text "[main_menu_sp_p1_custom_devil_fruit]" size 16 color "#00ccff" bold True yalign 0.5 xsize 40
                                    
                                    null height 10
                                    
                                    python:
                                        p1_total_stats = (main_menu_sp_p1_custom_strength + main_menu_sp_p1_custom_defense + 
                                                        main_menu_sp_p1_custom_speed + main_menu_sp_p1_custom_reaction + 
                                                        main_menu_sp_p1_custom_endurance + main_menu_sp_p1_custom_willpower + 
                                                        main_menu_sp_p1_custom_haki + main_menu_sp_p1_custom_devil_fruit)
                                                                                        
                                    
                                    
                                    null height 15
                                    
                                    text "DEVIL FRUIT POWER" size 20 color "#00ffff" bold True xalign 0.5
                                    
                                    # Devil Fruit Power Gallery
                                    frame:
                                        xsize 660
                                        ysize 200
                                        background "#22222259"
                                        padding (5, 5)
                                        
                                        hbox:
                                            spacing 0
                                            
                                            viewport:
                                                id "p1_power_viewport"
                                                mousewheel True
                                                draggable True
                                                xsize 645
                                                ysize 190
                                                
                                                python:
                                                    power_cell_width = 120
                                                    power_cell_height = 90
                                                    power_cols = 5
                                                    total_powers = len(devil_fruits)
                                                    power_rows = (total_powers + power_cols - 1) // power_cols
                                                    power_content_width = power_cols * power_cell_width
                                                    power_content_height = power_rows * power_cell_height
                                                
                                                vbox:
                                                    spacing 0
                                                    
                                                    fixed:
                                                        xsize power_content_width
                                                        ysize power_content_height
                                                        
                                                        # Power squares
                                                        for row_idx in range(power_rows):
                                                            for col_idx in range(min(power_cols, total_powers - row_idx * power_cols)):
                                                                python:
                                                                    power_idx = row_idx * power_cols + col_idx
                                                                    if power_idx < total_powers:
                                                                        power = devil_fruits[power_idx]
                                                                        power_id = power.get("id", "")
                                                                        power_name = power.get("name", "Unknown")
                                                                        power_group = power.get("main_group", "")
                                                                        power_x = col_idx * power_cell_width + 3
                                                                        power_y = row_idx * power_cell_height + 3
                                                                        power_w = power_cell_width - 6
                                                                        power_h = power_cell_height - 6
                                                                        is_selected = (main_menu_sp_p1_custom_power == power_name)

                                                                
                                                                if power_idx < total_powers:
                                                                    $ button_bg = "#ffaa00" if is_selected else "#444444"
                                                                    button:
                                                                        xpos power_x
                                                                        ypos power_y
                                                                        xsize power_w
                                                                        ysize power_h
                                                                        background button_bg
                                                                        action SetVariable("main_menu_sp_p1_custom_power", power_name)
                                                                        
                                                                        vbox:
                                                                            spacing 2
                                                                            xalign 0.5
                                                                            yalign 0.5
                                                                            
                                                                            
                                                                            $ power_image = power.get("image", "")
                                                                            
                                                                            if power_image:
                                                                                add power_image:
                                                                                    xsize power_w - 10
                                                                                    ysize power_h - 30
                                                                                    fit "contain"
                                                                            
                                                                            text power_name size 12 color "#ffffff" bold True xalign 0.5
                                                                            text power_group size 10 color "#aaaaaa" xalign 0.5
                                                                
                                            vbar:
                                                value YScrollValue("p1_power_viewport")
                                                unscrollable "hide"
                                    
                                    text "Selected Power: [main_menu_sp_p1_custom_power]" size 14 color "#ffaa00" xalign 0.5
                                                                                        
                                    null height 20
                        
                    if main_menu_sp_p1_mode == "preset":
                        text "Selected: [main_menu_sp_p1_selected]" size 25 xalign 0.5 bold True color "#00ffff"
                    else:
                        hbox:
                            xalign 0.5
                            yalign 0.5
                            spacing 30
                            text "Total Points: [p1_total_stats]" size 18 color "#00ffff" bold True xalign 0.5
                            text "Character: [main_menu_sp_p1_custom_name]" size 18 xalign 0.5 color "#00ffff" bold True
                        null height 10
                        # Action buttons
                        hbox:
                            spacing 15
                            xalign 0.6
                            ysize 30
                                                                                
                            python:
                                # Check for name conflicts
                                existing_preset_names = [p.get("name") for p in character_presets]
                                existing_temp_names = [p.get("name") for p in main_menu_sp_temp_presets if p.get("name") != main_menu_sp_p1_custom_name]
                                all_existing = existing_preset_names + existing_temp_names
                                can_select = (main_menu_sp_p1_custom_name.strip() != "" and main_menu_sp_p1_custom_name not in all_existing)
                                                                                
                            if can_select:
                                imagebutton:
                                    idle Transform("images/menu/select.png", ysize=40, fit="contain")
                                    hover Transform("images/menu/select.png", ysize=40, fit="contain")
                                    xminimum 150
                                    action [
                                        Function(lambda: (
                                            # Remove existing temp preset with same name
                                            [main_menu_sp_temp_presets.remove(p) for p in main_menu_sp_temp_presets[:] if p.get("name") == main_menu_sp_p1_custom_name],
                                            # Add new temp preset
                                            main_menu_sp_temp_presets.append({
                                                "name": main_menu_sp_p1_custom_name,
                                                "picture": "images/characters/unknown.png",
                                                "stats": {
                                                    "strength": main_menu_sp_p1_custom_strength,
                                                    "defense": main_menu_sp_p1_custom_defense,
                                                    "speed": main_menu_sp_p1_custom_speed,
                                                    "reaction": main_menu_sp_p1_custom_reaction,
                                                    "endurance": main_menu_sp_p1_custom_endurance,
                                                    "willpower": main_menu_sp_p1_custom_willpower,
                                                    "haki": main_menu_sp_p1_custom_haki,
                                                    "devil_fruit": main_menu_sp_p1_custom_devil_fruit
                                                },
                                                "power": main_menu_sp_p1_custom_power,
                                                "is_temp": True
                                            })
                                        )[-1]),
                                        SetVariable("main_menu_sp_p1_selected", main_menu_sp_p1_custom_name),
                                        SetVariable("main_menu_sp_p1_mode", "preset")
                                    ]
                                                                                        
                                imagebutton:
                                    idle Transform("images/menu/save_as_preset.png", ysize=40, fit="contain")
                                    hover Transform("images/menu/save_as_preset.png", ysize=40, fit="contain")
                                    xminimum 150
                                    action Function(save_custom_preset, main_menu_sp_p1_custom_name, {
                                        "strength": main_menu_sp_p1_custom_strength,
                                        "defense": main_menu_sp_p1_custom_defense,
                                        "speed": main_menu_sp_p1_custom_speed,
                                        "reaction": main_menu_sp_p1_custom_reaction,
                                        "endurance": main_menu_sp_p1_custom_endurance,
                                        "willpower": main_menu_sp_p1_custom_willpower,
                                        "haki": main_menu_sp_p1_custom_haki,
                                        "devil_fruit": main_menu_sp_p1_custom_devil_fruit
                                    }, main_menu_sp_p1_custom_power)
                            else:
                                text "Name already exists or empty" size 14 color "#ff0000" xalign 0.5
                    
                    
                
                # RADAR CHART - CENTER
                vbox:

                    add "images/menu/choose_characters.png" xsize (0.4)
                    spacing 10
                    null height 40

                    text "STATS COMPARISON" size 30 xalign 0.5 color "#ffffff"
                    
                    frame:
                        xsize 400
                        ysize 600
                        background "#1a1a1a00"
                        padding (10, 10)
                        xalign 0.5
                        yalign 0.5
                        
                        python:
                            # Stat values as lists
                            stat_names = ["Strength", "Defense", "Speed", "Reaction", "Endurance", "Willpower", "Haki", "Devil Fruit"]
                        
                        vbox:
                            spacing 20
                            xalign 0.5
                            yalign 0.5
                            
                            # Overlay both charts in fixed container
                            fixed:
                                xsize 300
                                ysize 300
                                xalign 0.5
                                
                                # P2 Radar Chart (Red - behind)
                                add RadarChart(
                                    maximum=5, 
                                    expressions=[
                                        "get_char_stat(main_menu_sp_p2_selected, 'strength', 50)/20.0",
                                        "get_char_stat(main_menu_sp_p2_selected, 'defense', 50)/20.0",
                                        "get_char_stat(main_menu_sp_p2_selected, 'speed', 50)/20.0",
                                        "get_char_stat(main_menu_sp_p2_selected, 'reaction', 50)/20.0",
                                        "get_char_stat(main_menu_sp_p2_selected, 'endurance', 50)/20.0",
                                        "get_char_stat(main_menu_sp_p2_selected, 'willpower', 50)/20.0",
                                        "get_char_stat(main_menu_sp_p2_selected, 'haki', 50)/20.0",
                                        "get_char_stat(main_menu_sp_p2_selected, 'devil_fruit', 50)/20.0"
                                    ],
                                    color1="#ff0000e9", 
                                    color2="#666666", 
                                    opacity=0.6, 
                                    size=300, 
                                    show_lines=False
                                ):
                                    xpos 0
                                    ypos 0
                                
                                # P1 Radar Chart (Blue - front)
                                add RadarChart(
                                    maximum=5, 
                                    expressions=[
                                        "(main_menu_sp_p1_custom_strength if main_menu_sp_p1_mode == 'custom' else get_char_stat(main_menu_sp_p1_selected, 'strength', 50))/20.0",
                                        "(main_menu_sp_p1_custom_defense if main_menu_sp_p1_mode == 'custom' else get_char_stat(main_menu_sp_p1_selected, 'defense', 50))/20.0",
                                        "(main_menu_sp_p1_custom_speed if main_menu_sp_p1_mode == 'custom' else get_char_stat(main_menu_sp_p1_selected, 'speed', 50))/20.0",
                                        "(main_menu_sp_p1_custom_reaction if main_menu_sp_p1_mode == 'custom' else get_char_stat(main_menu_sp_p1_selected, 'reaction', 50))/20.0",
                                        "(main_menu_sp_p1_custom_endurance if main_menu_sp_p1_mode == 'custom' else get_char_stat(main_menu_sp_p1_selected, 'endurance', 50))/20.0",
                                        "(main_menu_sp_p1_custom_willpower if main_menu_sp_p1_mode == 'custom' else get_char_stat(main_menu_sp_p1_selected, 'willpower', 50))/20.0",
                                        "(main_menu_sp_p1_custom_haki if main_menu_sp_p1_mode == 'custom' else get_char_stat(main_menu_sp_p1_selected, 'haki', 50))/20.0",
                                        "(main_menu_sp_p1_custom_devil_fruit if main_menu_sp_p1_mode == 'custom' else get_char_stat(main_menu_sp_p1_selected, 'devil_fruit', 50))/20.0"
                                    ],
                                    color1="#00ccffb9", 
                                    color2="#ffffff", 
                                    opacity=0.8, 
                                    size=300, 
                                    show_lines=True
                                ):
                                    xpos 0
                                    ypos 0
                            
                            # Stat Labels with values
                            vbox:
                                spacing 5
                                xalign 0.5
                                
                                for i, stat in enumerate(stat_names):
                                    python:
                                        stat_key = ["strength", "defense", "speed", "reaction", "endurance", "willpower", "haki", "devil_fruit"][i]
                                        if main_menu_sp_p1_mode == "custom":
                                            p1_value = [main_menu_sp_p1_custom_strength, main_menu_sp_p1_custom_defense, main_menu_sp_p1_custom_speed, main_menu_sp_p1_custom_reaction, main_menu_sp_p1_custom_endurance, main_menu_sp_p1_custom_willpower, main_menu_sp_p1_custom_haki, main_menu_sp_p1_custom_devil_fruit][i]
                                        else:
                                            p1_value = get_char_stat(main_menu_sp_p1_selected, stat_key, 50)
                                        p2_value = get_char_stat(main_menu_sp_p2_selected, stat_key, 50)
                                    
                                    hbox:
                                        spacing 15
                                        xalign 0.5
                                        
                                        text str(p1_value) size 16 color "#00ccff" bold True xalign 1.0 xsize 40
                                        text stat size 16 color "#ffffff" xalign 0.5 xsize 120
                                        text str(p2_value) size 16 color "#ff0000" bold True xalign 0.0 xsize 40
                
                
                # PLAYER 2 GALLERY - RIGHT
                vbox:
                    spacing 10
                    
                    imagebutton:
                            idle Transform("images/menu/player2.png", ysize=40, fit="contain")
                    
                    frame:
                        xsize 700
                        ysize 600
                        background "#ff000000"
                        padding (5, 5)
                        
                        hbox:
                            spacing 0
                            
                            viewport:
                                id "p2_gallery_viewport"
                                mousewheel True
                                draggable True
                                xsize content_width + 10
                                ysize 580
                            
                                vbox:
                                    spacing 0
                                    xalign 0.5
                                    
                                    fixed:
                                        xsize content_width
                                        ysize content_height
                                        
                                        # GRID LINES
                                        for col_idx in range(cols_per_row + 1):
                                            $ line_x = col_idx * cell_width
                                            add Solid("#00000000"):
                                                xpos line_x
                                                ypos 0
                                                xsize 2
                                                ysize content_height
                                        
                                        for row_idx in range(total_rows + 1):
                                            $ line_y = row_idx * cell_height
                                            add Solid("#00000000"):
                                                xpos 0
                                                ypos line_y
                                                xsize (cols_per_row * cell_width)
                                                ysize 2
                                        
                                        # SQUARES
                                        for row_idx in range(total_rows):
                                            for col_idx in range(min(cols_per_row, total_presets - row_idx * cols_per_row)):
                                                python:
                                                    preset_idx = row_idx * cols_per_row + col_idx
                                                    if preset_idx < total_presets:
                                                        preset = all_presets[preset_idx]
                                                        preset_name = preset.get("name", "Unknown")
                                                        cell_x = col_idx * cell_width + 5
                                                        cell_y = row_idx * cell_height + 5
                                                        cell_size_w = cell_width - 10
                                                        cell_size_h = cell_height - 10
                                                
                                                if preset_idx < total_presets:
                                                    button:
                                                        xpos cell_x
                                                        ypos cell_y
                                                        xsize cell_size_w
                                                        ysize cell_size_h
                                                        background "#80808000"
                                                        action SetVariable("main_menu_sp_p2_selected", preset_name)
                                                        
                                                        $ picture_path = preset.get("picture", "")
                                                        
                                                        if picture_path:
                                                            add picture_path:
                                                                xsize cell_size_w
                                                                ysize cell_size_h
                                                                fit "contain"
                                                        
                                                        text preset_name size 20 color "#ffffff" bold True xalign 0.5 ypos cell_size_h - 25
                            
                            vbar:
                                value YScrollValue("p2_gallery_viewport")
                                unscrollable "hide"
                    
                    text "Selected: [main_menu_sp_p2_selected]" size 25 xalign 0.5 color "#ffff00"
            
            hbox:
                spacing 40
                xalign 0.5
                
                python:
                    # Check if both players selected
                    both_selected = (main_menu_sp_p1_selected != "None" and main_menu_sp_p2_selected != "None")
                
                if both_selected:
                    imagebutton:
                            idle Transform("images/menu/start_game.png", ysize=40, fit="contain")
                            hover Transform("images/menu/start_game.png", ysize=40, fit="contain")
                            action Jump("sp_game_start") xminimum 200
                else:
                    imagebutton:
                            idle Transform("images/menu/start_game.png", ysize=40, fit="contain")
                            hover Transform("images/menu/start_game.png", ysize=40, fit="contain")
                            action NullAction() 
                
                imagebutton:
                            idle Transform("images/menu/back.png", ysize=40, fit="contain")
                            hover Transform("images/menu/back.png", ysize=40, fit="contain")
                            action Show("main_menu_shell") xminimum 200
            null height 15

screen sp_preset_gallery_screen():
    tag main_menu_shell

    add Solid("#000000")

    python:
        # Load character presets from JSON
        import json
        import os
        character_presets = []
        json_path = os.path.join(renpy.config.gamedir, "data", "characters.json")
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
                character_presets = data.get("presets", [])
        except Exception as e:
            # If JSON fails, leave empty - no fallback
            character_presets = []
        
        # Calculate grid dimensions
        screen_width = int(1920 * 0.9)
        screen_height = int(1080 * 0.9)
        
        # Square size and spacing
        cell_width = 160
        cell_height = 260
        spacing_size = 15
        
        # Calculate columns based on viewport width
        viewport_width = screen_width - 100
        cols_per_row = 4
        
        # Calculate number of rows needed
        total_presets = len(character_presets)
        total_rows = (total_presets + cols_per_row - 1) // cols_per_row
        
        # Calculate content dimensions
        square_height = cell_height + 30
        content_height = (total_rows * square_height) + ((total_rows - 1) * spacing_size)
        content_width = (cols_per_row * cell_width)

    frame:
        xalign 0.1
        yalign 0.4
        xmaximum screen_width
        ymaximum screen_height
        background Solid("#000000CC")

        vbox:
            spacing 10
            xalign 0.5

            text "CHARACTERS" size 30 xalign 0.5

            # Grid container frame
            frame:
                xalign 0.5
                xsize 700
                ymaximum int(screen_height * 0.75)
                background "#0000ff74"  # BLUE background
                padding (20, 20)
                
                hbox:
                    spacing 0
                    
                    viewport:
                        id "preset_gallery_viewport"
                        mousewheel True
                        draggable True
                        xsize content_width + 10
                        ysize int(screen_height * 0.70)
                    
                        vbox:
                            spacing 0
                            xalign 0.5
                            
                            fixed:
                                xsize content_width
                                ysize content_height
                                
                                # GRID LINES
                                for col_idx in range(cols_per_row + 1):
                                    $ line_x = col_idx * cell_width
                                    add Solid("#000000"):
                                        xpos line_x
                                        ypos 0
                                        xsize 2
                                        ysize content_height
                                
                                for row_idx in range(total_rows + 1):
                                    $ line_y = row_idx * cell_height
                                    add Solid("#000000"):
                                        xpos 0
                                        ypos line_y
                                        xsize (cols_per_row * cell_width)
                                        ysize 2
                                
                                # SQUARES - POSITIONED BY GRID
                                for row_idx in range(total_rows):
                                    for col_idx in range(min(cols_per_row, total_presets - row_idx * cols_per_row)):
                                        python:
                                            preset_idx = row_idx * cols_per_row + col_idx
                                            if preset_idx < total_presets:
                                                preset = character_presets[preset_idx]
                                                preset_name = preset.get("name", "Unknown")
                                                cell_x = col_idx * cell_width + 5
                                                cell_y = row_idx * cell_height + 5
                                                cell_size_w = cell_width - 10
                                                cell_size_h = cell_height - 10
                                        
                                        if preset_idx < total_presets:
                                            button:
                                                xpos cell_x
                                                ypos cell_y
                                                xsize cell_size_w
                                                ysize cell_size_h
                                                background "#80808000"
                                                action SetVariable("main_menu_sp_selected_label", preset_name)
                                                
                                                $ picture_path = preset.get("picture", "")
                                                
                                                if picture_path:
                                                    add picture_path:
                                                        xsize cell_size_w
                                                        ysize cell_size_h
                                                        fit "contain"
                                                
                                                text preset_name size 24 color "#ffffff" bold True xalign 0.5 ypos cell_size_h - 30
                    
                    vbar:
                        value YScrollValue("preset_gallery_viewport")
                        unscrollable "hide"

            vbox:
                spacing 8
                xalign 0.5

                text "Selected: [main_menu_sp_selected_label]" size 20
                text "Stats Preview: (placeholder)" size 16

            hbox:
                spacing 20
                xalign 0.5

                textbutton "CONFIRM" action Show("sp_character_select_screen")
                textbutton "CANCEL" action Show("sp_character_select_screen")


screen sp_character_creator_screen():
    tag main_menu_shell

    add Solid("#000000")

    frame:
        xalign 0.5
        yalign 0.5
        xmaximum 1000
        ymaximum 650
        background Solid("#000000CC")

        vbox:
            spacing 10
            xalign 0.5

            hbox:
                xalign 1.0
                text "CUSTOM CHARACTER CREATION" size 28
                textbutton "X" action Show("sp_character_select_screen")

            hbox:
                spacing 10
                xalign 0.5

                text "Name:" size 20 color "#aaa"
                input:
                    value VariableInputValue("main_menu_cc_name")
                    length 24
                    copypaste True
                    color "#fffb00"
                    xsize 300
                    changed renpy.restart_interaction

            hbox:
                spacing 40
                xalign 0.5

                frame:
                    xmaximum 450
                    background Solid("#111133AA")

                    vbox:
                        spacing 8
                        xalign 0.5

                        text "ATTRIBUTES" size 20 xalign 0.5

                        $ total_points = main_menu_cc_points_total
                        $ points_spent = (main_menu_cc_strength + main_menu_cc_defense + main_menu_cc_speed + main_menu_cc_reaction + main_menu_cc_endurance + main_menu_cc_willpower + main_menu_cc_haki + main_menu_cc_devil_fruit)
                        $ points_remaining = total_points - points_spent

                        text "Points: [points_remaining]/[total_points] Remaining" size 16 xalign 0.5

                        hbox:
                            spacing 8
                            text "Strength ([main_menu_cc_strength]):" size 16 color "#fff"
                            bar:
                                value VariableValue("main_menu_cc_strength", 100)
                                range 100
                                xsize 220
                                ysize 16
                                left_bar "#00ff00"
                                right_bar "#333333"

                        hbox:
                            spacing 8
                            text "Defense ([main_menu_cc_defense]):" size 16 color "#fff"
                            bar:
                                value VariableValue("main_menu_cc_defense", 100)
                                range 100
                                xsize 220
                                ysize 16
                                left_bar "#0088ff"
                                right_bar "#333333"

                        hbox:
                            spacing 8
                            text "Speed ([main_menu_cc_speed]):" size 16 color "#fff"
                            bar:
                                value VariableValue("main_menu_cc_speed", 100)
                                range 100
                                xsize 220
                                ysize 16
                                left_bar "#ffff00"
                                right_bar "#333333"

                        hbox:
                            spacing 8
                            text "Reaction ([main_menu_cc_reaction]):" size 16 color "#fff"
                            bar:
                                value VariableValue("main_menu_cc_reaction", 100)
                                range 100
                                xsize 220
                                ysize 16
                                left_bar "#ff8800"
                                right_bar "#333333"

                        hbox:
                            spacing 8
                            text "Endurance ([main_menu_cc_endurance]):" size 16 color "#fff"
                            bar:
                                value VariableValue("main_menu_cc_endurance", 100)
                                range 100
                                xsize 220
                                ysize 16
                                left_bar "#ff0000"
                                right_bar "#333333"

                        hbox:
                            spacing 8
                            text "Willpower ([main_menu_cc_willpower]):" size 16 color "#fff"
                            bar:
                                value VariableValue("main_menu_cc_willpower", 100)
                                range 100
                                xsize 220
                                ysize 16
                                left_bar "#ff00ff"
                                right_bar "#333333"

                        hbox:
                            spacing 8
                            text "Haki ([main_menu_cc_haki]):" size 16 color "#fff"
                            bar:
                                value VariableValue("main_menu_cc_haki", 100)
                                range 100
                                xsize 220
                                ysize 16
                                left_bar "#8800ff"
                                right_bar "#333333"

                        hbox:
                            spacing 8
                            text "Devil Fruit ([main_menu_cc_devil_fruit]):" size 16 color "#fff"
                            bar:
                                value VariableValue("main_menu_cc_devil_fruit", 100)
                                range 100
                                xsize 220
                                ysize 16
                                left_bar "#00ffff"
                                right_bar "#333333"

                frame:
                    xmaximum 450
                    background Solid("#111133AA")

                    vbox:
                        spacing 8

                        text "POWER SELECTION" size 20 xalign 0.5

                        hbox:
                            spacing 8
                            xalign 0.5

                            text "Search:" size 16
                            input:
                                value VariableInputValue("main_menu_cc_power_search")
                                length 20
                                copypaste True
                                color "#ffffff"
                                xsize 200

                        vbox:
                            text "Category:" size 16 color "#aaa" yoffset -10
                            vbox:
                                button:
                                    xsize 250
                                    ysize 40
                                    background "#0a0a1a"
                                    hover_background "#0a0a2a"
                                    action SetScreenVariable("main_menu_cc_category_open", not main_menu_cc_category_open)
                                    text "[main_menu_cc_power_category]" size 18 color "#ffff00" xalign 0.0 xoffset 10
                                if main_menu_cc_category_open:
                                    frame:
                                        xsize 250
                                        ysize 150
                                        background "#1a1a2a"
                                        padding (5, 5)
                                        viewport:
                                            scrollbars "vertical"
                                            mousewheel True
                                            draggable True
                                            yinitial 0.0
                                            vbox:
                                                spacing 5
                                                for cat in main_menu_cc_category_options:
                                                    textbutton cat:
                                                        xsize 240
                                                        text_size 18
                                                        background "#333344"
                                                        hover_background "#444455"
                                                        action [
                                                            SetVariable("main_menu_cc_power_category", cat),
                                                            SetVariable("main_menu_cc_power_subfilter", "All"),
                                                            SetScreenVariable("main_menu_cc_category_open", False)
                                                        ]
                                                        text_color ("#ffff00" if cat == main_menu_cc_power_category else "#ffffff")

                        vbox:
                            text "Filter:" size 16 color "#aaa" yoffset -10
                            vbox:
                                button:
                                    xsize 250
                                    ysize 40
                                    background "#0a0a1a"
                                    hover_background "#0a0a2a"
                                    action SetScreenVariable("main_menu_cc_filter_open", not main_menu_cc_filter_open)
                                    text "[main_menu_cc_power_subfilter]" size 18 color "#ffff00" xalign 0.0 xoffset 10
                                if main_menu_cc_filter_open:
                                    $ available_filters = main_menu_cc_filter_options.get(main_menu_cc_power_category, ["All"])
                                    frame:
                                        xsize 250
                                        ysize 150
                                        background "#1a1a2a"
                                        padding (5, 5)
                                        viewport:
                                            scrollbars "vertical"
                                            mousewheel True
                                            draggable True
                                            yinitial 0.0
                                            vbox:
                                                spacing 5
                                                for filt in available_filters:
                                                    textbutton filt:
                                                        xsize 240
                                                        text_size 18
                                                        background "#333344"
                                                        hover_background "#444455"
                                                        action [
                                                            SetVariable("main_menu_cc_power_subfilter", filt),
                                                            SetScreenVariable("main_menu_cc_filter_open", False)
                                                        ]
                                                        text_color ("#ffff00" if filt == main_menu_cc_power_subfilter else "#ffffff")

                        viewport:
                            draggable True
                            mousewheel True
                            xmaximum 430
                            ymaximum 260

                            vbox:
                                spacing 4

                                for p in main_menu_cc_powers:
                                    $ name = p["name"]
                                    $ cat = p["category"]
                                    $ sub = p["sub"]
                                    $ search_ok = not main_menu_cc_power_search or main_menu_cc_power_search.lower() in name.lower()
                                    $ cat_ok = (main_menu_cc_power_category == "All" or main_menu_cc_power_category == cat)
                                    $ sub_ok = (main_menu_cc_power_subfilter == "All" or main_menu_cc_power_subfilter == sub)
                                    if search_ok and cat_ok and sub_ok:
                                        textbutton name:
                                            action SetVariable("main_menu_cc_selected_power", name)
                                            selected main_menu_cc_selected_power == name

                        text "Selected Power: [main_menu_cc_selected_power if main_menu_cc_selected_power else 'None']" size 16 xalign 0.5

            hbox:
                spacing 20
                xalign 0.5

                textbutton "CANCEL" action Show("sp_character_select_screen")
                textbutton "SAVE & USE":
                    action [
                        SetVariable("main_menu_sp_selected_label", main_menu_cc_name if main_menu_cc_name else "Custom Character"),
                        Show("sp_character_select_screen")
                    ]


# ===== MULTIPLAYER FLOW SCREENS =====

screen mp_hub_screen():
    tag main_menu_shell
    add Solid("#000000")
    add "images/menu/multiplayer_background.png":
            fit "contain"
    frame:
        xalign 0.5
        yalign 0.5
        xmaximum 1100
        ymaximum 650
        background Solid("#000000CC")
        add "images/menu/multiplayer.png" xalign 0.5 yalign -0.3

        vbox:
            spacing 15
            xalign 0.5
            
            
            

            hbox:
                spacing 40
                xalign 0.5

                frame:
                    xmaximum 250
                    background Solid("#111133AA")

                    vbox:
                        spacing 10
                        xalign 0.5

                        imagebutton:
                            idle Transform("images/menu/find_match.png", ysize=40, fit="contain")
                            hover Transform("images/menu/find_match.png", ysize=40, fit="contain")
                            action NullAction()
                            xminimum 200
                        imagebutton:
                            idle Transform("images/menu/create_lobby.png", ysize=40, fit="contain")
                            hover Transform("images/menu/create_lobby.png", ysize=40, fit="contain")
                            xminimum 200
                            action [
                                SetVariable("main_menu_mp_lobby_name", "New Lobby"),
                                Show("mp_lobby_screen")
                            ]
                        imagebutton:
                            idle Transform("images/menu/back.png", ysize=40, fit="contain")
                            hover Transform("images/menu/back.png", ysize=40, fit="contain")
                            action Show("main_menu_shell")
                            xminimum 200
                

                frame:
                    xmaximum 800
                    background Solid("#111133AA")

                    vbox:
                        spacing 5

                        text "AVAILABLE LOBBIES" size 20

                        text "Search:" size 16

                        viewport:
                            draggable True
                            mousewheel True
                            xmaximum 780
                            ymaximum 800

                            vbox:
                                spacing 4

                                text "\"Epic Duel\"  | Host: Luffy_93    | 1/2    | Locked" size 16
                                text "\"Noobs Only\" | Host: ZoroSwords | 2/2    | Open" size 16

                                textbutton "Join \"Epic Duel\"":
                                    action [
                                        SetVariable("main_menu_mp_lobby_name", "Epic Duel"),
                                        Show("mp_lobby_screen")
                                    ]

            

    frame:
            xmaximum 400
            background Solid("#111133AA")
            yfill True
            xalign 1.0
            vbox:
                spacing 5

                text "GLOBAL CHAT" size 20

                viewport:
                    draggable True
                    mousewheel True
                    xmaximum 400

                    vbox:
                        spacing 4
                        for line in main_menu_mp_global_chat_lines:
                            text line size 16

                hbox:
                    spacing 10
                    input value VariableInputValue("main_menu_mp_chat_input") length 30
                    textbutton "SEND" action NullAction()

screen mp_lobby_screen():
    tag main_menu_shell

    add Solid("#000000")

    frame:
        xalign 0.5
        yalign 0.5
        xmaximum 1100
        ymaximum 650
        background Solid("#000000CC")

        vbox:
            spacing 15
            xalign 0.5

            text "LOBBY: [main_menu_mp_lobby_name]" size 28 xalign 0.5

            hbox:
                spacing 40
                xalign 0.5

                frame:
                    xmaximum 200
                    background Solid("#111133AA")

                    vbox:
                        spacing 5
                        text "HOST" size 18
                        text "Name: Luffy_93" size 16
                        text ("Ready: ✓" if main_menu_mp_host_ready else "Ready: ✗") size 16

                frame:
                    xmaximum 200
                    background Solid("#111133AA")

                    vbox:
                        spacing 5
                        text "GUEST" size 18
                        text "Name: ZoroSwords" size 16
                        text ("Ready: ✓" if main_menu_mp_guest_ready else "Ready: ✗") size 16

            frame:
                xmaximum 500
                background Solid("#111133AA")

                vbox:
                    spacing 5

                    text "CHAT" size 20

                    viewport:
                        draggable True
                        mousewheel True
                        xmaximum 480
                        ymaximum 200

                        vbox:
                            spacing 4
                            for line in main_menu_mp_lobby_chat_lines:
                                text line size 16

                    hbox:
                        spacing 10
                        input value VariableInputValue("main_menu_mp_chat_input") length 30
                        textbutton "SEND" action NullAction()

            frame:
                xmaximum 700
                background Solid("#111133AA")

                vbox:
                    spacing 10
                    xalign 0.5

                    text "CHARACTER SELECTION (shell)" size 20 xalign 0.5
                    text "This will reuse single player selection UI in future phases." size 16 xalign 0.5

            hbox:
                spacing 40
                xalign 0.5

                textbutton "LEAVE LOBBY" action Show("mp_hub_screen")
                textbutton "READY / UNREADY" action ToggleVariable("main_menu_mp_host_ready")
