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
    # Load selected character data
    python:
        import json
        import os
        
        # Load characters.json
        json_path = os.path.join(renpy.config.gamedir, "data", "characters.json")
        with open(json_path, "r") as f:
            data = json.load(f)
            presets = data.get("presets", [])
        
        # Find P1 and P2 preset data
        p1_preset = None
        p2_preset = None
        
        for preset in presets:
            if preset.get("name") == main_menu_sp_p1_selected:
                p1_preset = preset
            if preset.get("name") == main_menu_sp_p2_selected:
                p2_preset = preset
        
        # Clear battle log
        global_battle_log = []
        
        # Initialize combat game with selected character stats
        combat_game = CombatGame()
        
        # Apply P1 stats (combat_game.player1, not p1)
        if p1_preset:
            p1_stats = p1_preset.get("stats", {})
            combat_game.player1.strength = p1_stats.get("strength", 50)
            combat_game.player1.defense = p1_stats.get("defense", 50)
            combat_game.player1.speed = p1_stats.get("speed", 50)
            combat_game.player1.reaction = p1_stats.get("reaction", 50)
            combat_game.player1.endurance = p1_stats.get("endurance", 50)
            combat_game.player1.willpower = p1_stats.get("willpower", 50)
            combat_game.player1.haki_armament = p1_stats.get("haki", 50)
            combat_game.player1.haki_observation = p1_stats.get("haki", 50)
            combat_game.player1.haki_conqueror = p1_stats.get("haki", 50)
            combat_game.player1.devil_fruit_mastery = p1_stats.get("devil_fruit", 50)
            # Apply devil fruit type
            p1_power = p1_preset.get("power")
            if p1_power:
                combat_game.player1.devil_fruit_type = p1_power
            # Recalculate pools
            combat_game.player1.max_health = combat_game.player1._calculate_max_health()
            combat_game.player1.max_stamina = combat_game.player1._calculate_max_stamina()
            combat_game.player1.health = combat_game.player1.max_health
            combat_game.player1.stamina = combat_game.player1.max_stamina
            combat_game.player1.haki_stamina = combat_game.player1._calculate_max_haki_stamina()
            combat_game.player1.devil_fruit_stamina = combat_game.player1._calculate_max_df_stamina()
        
        # Apply P2 stats (combat_game.player2, not p2)
        if p2_preset:
            p2_stats = p2_preset.get("stats", {})
            combat_game.player2.strength = p2_stats.get("strength", 50)
            combat_game.player2.defense = p2_stats.get("defense", 50)
            combat_game.player2.speed = p2_stats.get("speed", 50)
            combat_game.player2.reaction = p2_stats.get("reaction", 50)
            combat_game.player2.endurance = p2_stats.get("endurance", 50)
            combat_game.player2.willpower = p2_stats.get("willpower", 50)
            combat_game.player2.haki_armament = p2_stats.get("haki", 50)
            combat_game.player2.haki_observation = p2_stats.get("haki", 50)
            combat_game.player2.haki_conqueror = p2_stats.get("haki", 50)
            combat_game.player2.devil_fruit_mastery = p2_stats.get("devil_fruit", 50)
            # Apply devil fruit type
            p2_power = p2_preset.get("power")
            if p2_power:
                combat_game.player2.devil_fruit_type = p2_power
            # Recalculate pools
            combat_game.player2.max_health = combat_game.player2._calculate_max_health()
            combat_game.player2.max_stamina = combat_game.player2._calculate_max_stamina()
            combat_game.player2.health = combat_game.player2.max_health
            combat_game.player2.stamina = combat_game.player2.max_stamina
            combat_game.player2.haki_stamina = combat_game.player2._calculate_max_haki_stamina()
            combat_game.player2.devil_fruit_stamina = combat_game.player2._calculate_max_df_stamina()
    
    # Start battle screen
    call screen battle_screen
    
    return
