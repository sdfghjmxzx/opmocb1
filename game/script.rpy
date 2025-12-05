## Battle System - Main Script
## This file contains the entry point for the game

# Initialize battle log
init python:
    global_battle_log = []

# Skip main menu and go straight to battle
label main_menu:
    return

label start:
    # Clear any previous battle log
    $ global_battle_log = []
    
    # Initialize combat game
    $ combat_game = CombatGame()
    
    # Show battle screen
    call screen battle_screen
    
    return
