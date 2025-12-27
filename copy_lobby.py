import re

# Read full SP screen
with open('game/screens.rpy', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Extract lines 3273-5237 (screen sp_character_select_screen to end of overlay)
sp_screen = ''.join(lines[3272:5237])

# Replace all sp → mp
mp_screen = sp_screen.replace('main_menu_sp_', 'main_menu_mp_')
mp_screen = mp_screen.replace('sp_character_select_screen', 'mp_lobby_screen')
mp_screen = mp_screen.replace('"images/menu/singleplayer_background.png"', '"images/menu/multiplayer_background.png"')

# Write to output
with open('mp_lobby_screen.txt', 'w', encoding='utf-8') as f:
    f.write(mp_screen)

print("MP lobby screen copied successfully!")
print("Lines written:", len(mp_screen.splitlines()))
