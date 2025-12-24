screen sp_character_select_dual_gallery():
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
        except:
            character_presets = []
        
        # Grid settings
        cell_width = 160
        cell_height = 260
        spacing_size = 15
        cols_per_row = 4
        
        # Calculate dimensions
        total_presets = len(character_presets)
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
            
            text "CHOOSE CHARACTERS" size 40 xalign 0.5
            
            hbox:
                spacing 40
                xalign 0.5
                
                # PLAYER 1 GALLERY - LEFT
                vbox:
                    spacing 10
                    
                    text "PLAYER 1" size 30 xalign 0.5 color "#00ffff"
                    
                    frame:
                        xsize 700
                        ysize 600
                        background "#0000ff"
                        padding (5, 5)
                        
                        hbox:
                            spacing 0
                            
                            viewport:
                                id "p1_gallery_viewport"
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
                                        
                                        # SQUARES
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
                                                        background "#808080"
                                                        action SetVariable("main_menu_sp_p1_selected", preset_name)
                                                        
                                                        $ picture_path = preset.get("picture", "")
                                                        
                                                        if picture_path:
                                                            add picture_path:
                                                                xsize cell_size_w
                                                                ysize cell_size_h
                                                                fit "contain"
                                                        
                                                        text preset_name size 20 color "#ffffff" bold True xalign 0.5 ypos cell_size_h - 25
                            
                            vbar:
                                value YScrollValue("p1_gallery_viewport")
                                unscrollable "hide"
                    
                    text "Selected: [main_menu_sp_p1_selected]" size 18 xalign 0.5 color "#00ffff"
                
                # PLAYER 2 GALLERY - RIGHT
                vbox:
                    spacing 10
                    
                    text "PLAYER 2" size 30 xalign 0.5 color "#ffff00"
                    
                    frame:
                        xsize 700
                        ysize 600
                        background "#ff0000"
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
                                        
                                        # SQUARES
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
                                                        background "#808080"
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
                    
                    text "Selected: [main_menu_sp_p2_selected]" size 18 xalign 0.5 color "#ffff00"
            
            hbox:
                spacing 40
                xalign 0.5
                
                textbutton "START GAME" action NullAction() xminimum 200
                textbutton "BACK" action Show("main_menu_shell") xminimum 200
