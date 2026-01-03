## Battle System - Main Script
## This file contains the entry point for the game

# Initialize battle log
init python:
    global_battle_log = []

# Skip main menu and go straight to battle
label main_menu:
    if not use_main_menu_shell:
        return

    call screen main_menu_shell
    return

label start:
    # Clear any previous battle log
    $ global_battle_log = []

    # Initialize combat game
    $ combat_game = CombatGame()

    # Show battle screen
    call screen battle_screen

    return

label sp_game_start:
    "DEBUG: sp_game_start label started. P1=[main_menu_sp_p1_selected] P2=[main_menu_sp_p2_selected]"

    # Load selected character data
    python:
        global combat_game
        import json
        import os

        # Load characters.json
        json_path = os.path.join(renpy.config.gamedir, "data", "characters.json")
        with open(json_path, "r") as f:
            data = json.load(f)
            presets = data.get("presets", [])

        # Combine permanent and temporary presets
        all_presets = presets + main_menu_sp_temp_presets

        # Find P1 and P2 preset data
        p1_preset = None
        p2_preset = None

        renpy.say(None, "Searching in {} presets".format(len(all_presets)))

        for preset in all_presets:
            if preset.get("name") == main_menu_sp_p1_selected:
                p1_preset = preset
                renpy.say(None, "Found P1: {} with power {}".format(preset.get("name"), preset.get("power")))
            if preset.get("name") == main_menu_sp_p2_selected:
                p2_preset = preset
                renpy.say(None, "Found P2: {} with power {}".format(preset.get("name"), preset.get("power")))

        # Clear battle log
        global_battle_log = []

        # Initialize combat game with selected character stats
        new_combat_game = CombatGame()

        # Apply P1 stats (combat_game.player1, not p1)
        if p1_preset:
            p1_stats = p1_preset.get("stats", {})
            new_combat_game.player1.strength = p1_stats.get("strength", 50)
            new_combat_game.player1.defense = p1_stats.get("defense", 50)
            new_combat_game.player1.speed = p1_stats.get("speed", 50)
            new_combat_game.player1.reaction = p1_stats.get("reaction", 50)
            new_combat_game.player1.endurance = p1_stats.get("endurance", 50)
            new_combat_game.player1.willpower = p1_stats.get("willpower", 50)
            new_combat_game.player1.haki_armament = p1_stats.get("haki", 50)
            new_combat_game.player1.haki_observation = p1_stats.get("haki", 50)
            new_combat_game.player1.haki_conqueror = p1_stats.get("haki", 50)
            new_combat_game.player1.devil_fruit_mastery = p1_stats.get("devil_fruit", 50)

            # Apply devil fruit type (clear if None)
            p1_power = p1_preset.get("power")
            renpy.log("P1 Preset: {} | Power in JSON: {} | Type: {}".format(p1_preset.get("name"), p1_power, type(p1_power)))

            if p1_power and p1_power != "None":
                new_combat_game.player1.devil_fruit_type = p1_power
                renpy.log("P1 Devil Fruit SET TO: {}".format(p1_power))

                # Load full devil fruit data
                import json
                import os
                df_json_path = os.path.join(renpy.config.gamedir, "data", "devil_fruits.json")
                try:
                    with open(df_json_path, "r") as f:
                        df_data = json.load(f)
                        for fruit in df_data.get("fruits", []):
                            if fruit.get("id") == p1_power:
                                new_combat_game.player1.devil_fruit_data = fruit
                                new_combat_game.player1.devil_fruit_type_advantages = fruit.get('type_advantages')
                                break
                except:
                    pass
            else:
                new_combat_game.player1.devil_fruit_type = None
                new_combat_game.player1.devil_fruit_data = None
                new_combat_game.player1.devil_fruit_type_advantages = None
                renpy.log("P1 Devil Fruit CLEARED (was None or 'None')")

            # Recalculate pools
            new_combat_game.player1.max_health = new_combat_game.player1._calculate_max_health()
            new_combat_game.player1.max_stamina = new_combat_game.player1._calculate_max_stamina()
            new_combat_game.player1.health = new_combat_game.player1.max_health
            new_combat_game.player1.stamina = new_combat_game.player1.max_stamina
            new_combat_game.player1.haki_stamina = new_combat_game.player1._calculate_max_haki_stamina()
            new_combat_game.player1.devil_fruit_stamina = new_combat_game.player1._calculate_max_df_stamina()

        # Apply P2 stats (combat_game.player2, not p2)
        if p2_preset:
            p2_stats = p2_preset.get("stats", {})
            new_combat_game.player2.strength = p2_stats.get("strength", 50)
            new_combat_game.player2.defense = p2_stats.get("defense", 50)
            new_combat_game.player2.speed = p2_stats.get("speed", 50)
            new_combat_game.player2.reaction = p2_stats.get("reaction", 50)
            new_combat_game.player2.endurance = p2_stats.get("endurance", 50)
            new_combat_game.player2.willpower = p2_stats.get("willpower", 50)
            new_combat_game.player2.haki_armament = p2_stats.get("haki", 50)
            new_combat_game.player2.haki_observation = p2_stats.get("haki", 50)
            new_combat_game.player2.haki_conqueror = p2_stats.get("haki", 50)
            new_combat_game.player2.devil_fruit_mastery = p2_stats.get("devil_fruit", 50)

            # Apply devil fruit type (clear if None)
            p2_power = p2_preset.get("power")
            if p2_power and p2_power != "None":
                new_combat_game.player2.devil_fruit_type = p2_power

                # Load full devil fruit data
                import json
                import os
                df_json_path = os.path.join(renpy.config.gamedir, "data", "devil_fruits.json")
                try:
                    with open(df_json_path, "r") as f:
                        df_data = json.load(f)
                        for fruit in df_data.get("fruits", []):
                            if fruit.get("id") == p2_power:
                                new_combat_game.player2.devil_fruit_data = fruit
                                new_combat_game.player2.devil_fruit_type_advantages = fruit.get('type_advantages')
                                break
                except:
                    pass
            else:
                new_combat_game.player2.devil_fruit_type = None
                new_combat_game.player2.devil_fruit_data = None
                new_combat_game.player2.devil_fruit_type_advantages = None

            # Recalculate pools
            new_combat_game.player2.max_health = new_combat_game.player2._calculate_max_health()
            new_combat_game.player2.max_stamina = new_combat_game.player2._calculate_max_stamina()
            new_combat_game.player2.health = new_combat_game.player2.max_health
            new_combat_game.player2.stamina = new_combat_game.player2.max_stamina
            new_combat_game.player2.haki_stamina = new_combat_game.player2._calculate_max_haki_stamina()
            new_combat_game.player2.devil_fruit_stamina = new_combat_game.player2._calculate_max_df_stamina()

        # Assign to global variable
        global combat_game
        combat_game = new_combat_game

        # Console debug - show all player attributes
        import sys
        print("=== PLAYER 1 ATTRIBUTES ===")
        p1 = combat_game.player1
        print(f"Name: {p1.name}")
        print(f"Stats - Str: {p1.strength}, Def: {p1.defense}, Spd: {p1.speed}, Rea: {p1.reaction}, End: {p1.endurance}, Will: {p1.willpower}")
        print(f"Haki - Arm: {p1.haki_armament}, Obs: {p1.haki_observation}, Conq: {p1.haki_conqueror}")
        print(f"Devil Fruit - Type: {p1.devil_fruit_type}, Mastery: {p1.devil_fruit_mastery}, Data: {p1.devil_fruit_data is not None}")
        print(f"Pools - Health: {p1.health}/{p1.max_health}, Stamina: {p1.stamina}/{p1.max_stamina}, Haki: {p1.haki_stamina}, DF: {p1.devil_fruit_stamina}/{p1._calculate_max_df_stamina()}")
        print(f"Position - Row: {p1.row}, Col: {p1.col}, Facing: {p1.facing}")

        print("=== PLAYER 2 ATTRIBUTES ===")
        p2 = combat_game.player2
        print(f"Name: {p2.name}")
        print(f"Stats - Str: {p2.strength}, Def: {p2.defense}, Spd: {p2.speed}, Rea: {p2.reaction}, End: {p2.endurance}, Will: {p2.willpower}")
        print(f"Haki - Arm: {p2.haki_armament}, Obs: {p2.haki_observation}, Conq: {p2.haki_conqueror}")
        print(f"Devil Fruit - Type: {p2.devil_fruit_type}, Mastery: {p2.devil_fruit_mastery}, Data: {p2.devil_fruit_data is not None}")
        print(f"Pools - Health: {p2.health}/{p2.max_health}, Stamina: {p2.stamina}/{p2.max_stamina}, Haki: {p2.haki_stamina}, DF: {p2.devil_fruit_stamina}/{p2._calculate_max_df_stamina()}")
        print(f"Position - Row: {p2.row}, Col: {p2.col}, Facing: {p2.facing}")

        print("=== COMBAT GAME INITIALIZED ===")
        sys.stdout.flush()  # Ensure output is displayed immediately

    # Start battle screen
    call screen battle_screen

    return

label mp_game_start:
    # Load multiplayer game data and initialize combat
    python:
        global combat_game
        import json
        import os

        # Get game data from server
        game_data = main_menu_mp_game_data
        print(f"[MP GAME START] game_data type: {type(game_data)}")
        print(f"[MP GAME START] game_data value: {game_data}")
        
        if not game_data:
            renpy.say(None, "ERROR: No game data received from server!")
            renpy.jump("main_menu")

        # Extract player session info
        host_session = game_data.get("host_session")
        guest_session = game_data.get("guest_session")
        players_data = game_data.get("players", {})

        # Determine which player we are (host = player1, guest = player2)
        # We need to figure out our session_id by checking username match
        i_am_host = False
        for session_id, player_info in players_data.items():
            if player_info.get("name") == main_menu_mp_username:
                if session_id == host_session:
                    i_am_host = True
                break

        # Get selected characters from server data
        host_character = players_data.get(host_session, {}).get("selected_character", "None")
        guest_character = players_data.get(guest_session, {}).get("selected_character", "None")

        # Load characters.json to get preset data
        json_path = os.path.join(renpy.config.gamedir, "data", "characters.json")
        with open(json_path, "r") as f:
            data = json.load(f)
            presets = data.get("presets", [])

        # Find presets for both players
        p1_preset = None  # Host
        p2_preset = None  # Guest

        for preset in presets:
            if preset.get("name") == host_character:
                p1_preset = preset
            if preset.get("name") == guest_character:
                p2_preset = preset

        # Clear battle log
        global_battle_log = []

        # Initialize combat game
        new_combat_game = CombatGame()

        # Apply P1 stats (Host)
        if p1_preset:
            p1_stats = p1_preset.get("stats", {})
            new_combat_game.player1.strength = p1_stats.get("strength", 50)
            new_combat_game.player1.defense = p1_stats.get("defense", 50)
            new_combat_game.player1.speed = p1_stats.get("speed", 50)
            new_combat_game.player1.reaction = p1_stats.get("reaction", 50)
            new_combat_game.player1.endurance = p1_stats.get("endurance", 50)
            new_combat_game.player1.willpower = p1_stats.get("willpower", 50)
            new_combat_game.player1.haki_armament = p1_stats.get("haki", 50)
            new_combat_game.player1.haki_observation = p1_stats.get("haki", 50)
            new_combat_game.player1.haki_conqueror = p1_stats.get("haki", 50)
            new_combat_game.player1.devil_fruit_mastery = p1_stats.get("devil_fruit", 50)

            # Apply devil fruit
            p1_power = p1_preset.get("power")
            if p1_power and p1_power != "None":
                new_combat_game.player1.devil_fruit_type = p1_power

                # Load devil fruit data
                df_json_path = os.path.join(renpy.config.gamedir, "data", "devil_fruits.json")
                try:
                    with open(df_json_path, "r") as f:
                        df_data = json.load(f)
                        for fruit in df_data.get("fruits", []):
                            if fruit.get("id") == p1_power:
                                new_combat_game.player1.devil_fruit_data = fruit
                                new_combat_game.player1.devil_fruit_type_advantages = fruit.get('type_advantages')
                                break
                except:
                    pass
            else:
                new_combat_game.player1.devil_fruit_type = None
                new_combat_game.player1.devil_fruit_data = None
                new_combat_game.player1.devil_fruit_type_advantages = None

            # Recalculate pools
            new_combat_game.player1.max_health = new_combat_game.player1._calculate_max_health()
            new_combat_game.player1.max_stamina = new_combat_game.player1._calculate_max_stamina()
            new_combat_game.player1.health = new_combat_game.player1.max_health
            new_combat_game.player1.stamina = new_combat_game.player1.max_stamina
            new_combat_game.player1.haki_stamina = new_combat_game.player1._calculate_max_haki_stamina()
            new_combat_game.player1.devil_fruit_stamina = new_combat_game.player1._calculate_max_df_stamina()

        # Apply P2 stats (Guest)
        if p2_preset:
            p2_stats = p2_preset.get("stats", {})
            new_combat_game.player2.strength = p2_stats.get("strength", 50)
            new_combat_game.player2.defense = p2_stats.get("defense", 50)
            new_combat_game.player2.speed = p2_stats.get("speed", 50)
            new_combat_game.player2.reaction = p2_stats.get("reaction", 50)
            new_combat_game.player2.endurance = p2_stats.get("endurance", 50)
            new_combat_game.player2.willpower = p2_stats.get("willpower", 50)
            new_combat_game.player2.haki_armament = p2_stats.get("haki", 50)
            new_combat_game.player2.haki_observation = p2_stats.get("haki", 50)
            new_combat_game.player2.haki_conqueror = p2_stats.get("haki", 50)
            new_combat_game.player2.devil_fruit_mastery = p2_stats.get("devil_fruit", 50)

            # Apply devil fruit
            p2_power = p2_preset.get("power")
            if p2_power and p2_power != "None":
                new_combat_game.player2.devil_fruit_type = p2_power

                # Load devil fruit data
                df_json_path = os.path.join(renpy.config.gamedir, "data", "devil_fruits.json")
                try:
                    with open(df_json_path, "r") as f:
                        df_data = json.load(f)
                        for fruit in df_data.get("fruits", []):
                            if fruit.get("id") == p2_power:
                                new_combat_game.player2.devil_fruit_data = fruit
                                new_combat_game.player2.devil_fruit_type_advantages = fruit.get('type_advantages')
                                break
                except:
                    pass
            else:
                new_combat_game.player2.devil_fruit_type = None
                new_combat_game.player2.devil_fruit_data = None
                new_combat_game.player2.devil_fruit_type_advantages = None

            # Recalculate pools
            new_combat_game.player2.max_health = new_combat_game.player2._calculate_max_health()
            new_combat_game.player2.max_stamina = new_combat_game.player2._calculate_max_stamina()
            new_combat_game.player2.health = new_combat_game.player2.max_health
            new_combat_game.player2.stamina = new_combat_game.player2.max_stamina
            new_combat_game.player2.haki_stamina = new_combat_game.player2._calculate_max_haki_stamina()
            new_combat_game.player2.devil_fruit_stamina = new_combat_game.player2._calculate_max_df_stamina()

        # Assign to global variable
        combat_game = new_combat_game
        
        # CRITICAL: Set multiplayer mode flags on the new instance
        combat_game.is_multiplayer = True
        combat_game.use_local_tile_spawns = False  # Use server-driven spawns
        print(f"[MP] Flags set on combat_game: is_multiplayer={combat_game.is_multiplayer}, use_local_tile_spawns={combat_game.use_local_tile_spawns}")
        
        # Multiplayer: reset map from server, if provided
        try:
            # Direct dict access - avoid isinstance() due to Ren'Py sandboxing
            map_init = None
            if game_data and hasattr(game_data, 'get'):
                map_init = game_data.get("map_init")
            print(f"[MP MAP INIT] map_init received: {map_init}")
            if hasattr(combat_game, "reset_map_for_multiplayer"):
                print(f"[MP MAP INIT] Calling reset_map_for_multiplayer with map_init")
                combat_game.reset_map_for_multiplayer(map_init)
                print(f"[MP MAP INIT] reset_map_for_multiplayer completed successfully")
            else:
                print(f"[MP MAP INIT ERROR] combat_game missing reset_map_for_multiplayer method!")
        except Exception as e:
            print(f"[MP MAP INIT ERROR] Exception during reset_map_for_multiplayer: {e}")
            import traceback
            traceback.print_exc()
        
        # Set player names to usernames from lobby
        host_username = players_data.get(host_session, {}).get("name", "Player 1")
        guest_username = players_data.get(guest_session, {}).get("name", "Player 2")
        combat_game.player1.name = host_username
        combat_game.player2.name = guest_username

        # Debug output
        import sys
        print("=== MULTIPLAYER GAME START ===")
        print(f"Host (P1): {host_character} | Guest (P2): {guest_character}")
        print(f"I am: {'Host/Player1' if i_am_host else 'Guest/Player2'}")
        print("=== PLAYER 1 (HOST) ===")
        p1 = combat_game.player1
        print(f"Stats - Str: {p1.strength}, Def: {p1.defense}, Spd: {p1.speed}")
        print(f"Devil Fruit: {p1.devil_fruit_type}")
        print(f"Health: {p1.health}/{p1.max_health}")
        print("=== PLAYER 2 (GUEST) ===")
        p2 = combat_game.player2
        print(f"Stats - Str: {p2.strength}, Def: {p2.defense}, Spd: {p2.speed}")
        print(f"Devil Fruit: {p2.devil_fruit_type}")
        print(f"Health: {p2.health}/{p2.max_health}")
        sys.stdout.flush()

    # Store role globally for battle_screen_mp
    $ mp_i_am_player1 = i_am_host
    
    # Hide lobby screen before showing battle screen
    hide screen mp_lobby_screen
    
    # Start battle screen
    call screen battle_screen_mp

    return
