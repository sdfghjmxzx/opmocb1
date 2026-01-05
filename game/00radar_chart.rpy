#### RADAR CHART DISPLAYABLE by Devil Spiδεr####
# This code adds a self-updating radar chart to be added in-game. You can add updating stats to your character profiles, or you can dynamically preview multiple values at once using a singular displayables

## How to implement:
# To add a radar chart into your game, simply define a RadarChart() displayable. It takes several arguments (arguments marked with a * are optional):
#   maximum = the maximum rendered value (also the amount of radial lines shown)
#   expressions = a list of either ints/floats or strings. Use ints/floats for static values and strings for values that need to be update on a frame-by-frame basis
#   color1 = the color of the "blob" rendering out the stats
# * color2 = the color of radial lines (defaults to white)
# * opacity = the opacity of the blob - its border will always be opaque though (defaults to 1.0)
# * size = the size of the radar chart in pixels (defaults to 400)
# * show_lines = if True, lines showing the different axes are displayed (defaults to False)

# You can use the "add" statement in screens, or the "show expression" statement in dialogue. You can also define a radar-chart in an "image" statement




## CODE RESPONSIBLE FOR THE DISPLAYABLE:

init python:

    import pygame

    import math

    class RadarChart(renpy.Displayable):
        # Initialisation
        def __init__(self, maximum, expressions, color1, color2="#fff", opacity=1.0, size=400, show_lines=False, **kwargs): #, expressions=None
            super(RadarChart, self).__init__(**kwargs)
            self.expressions = expressions
            self.points = [eval(str(p)) for p in expressions]
            self.max = maximum
            self.color1 = color1
            self.color2 = color2
            self.opacity = opacity
            self.size = size
            self.show_lines = show_lines


        # This code renders out the displayable
        def render(self, width, height, st, at):
            s = self.size
            r = renpy.Render(s, s)
            canvas  = r.canvas()
            
            # Draw concentric circles FIRST (background)
            for k in range(1, self.max+1):
                base = []
                c = k/self.max
                for i in range(len(self.points)):
                    ang = i/len(self.points)*2*math.pi
                    base.append([(s/2)+(math.sin(ang)*(s/2)*c), (s/2)-(math.cos(ang)*(s/2)*c)])
                canvas.polygon(Color(self.color2), base, 1)
            
            # Draw axis guidelines (if enabled)
            if self.show_lines:
                for i in range(len(self.points)):
                    ang = i/len(self.points)*2*math.pi
                    canvas.line(self.color2, [s/2,s/2], [(s/2)+(math.sin(ang)*(s/2)),(s/2)-(math.cos(ang)*(s/2))])
            
            # Draw stat polygon LAST (foreground)
            base = []
            for i, point in enumerate(self.points):
                ang = i/len(self.points)*2*math.pi
                c = point/self.max
                base.append([(s/2)+(math.sin(ang)*(s/2)*c), (s/2)-(math.cos(ang)*(s/2)*c)])
            canvas.polygon(Color(self.color1).opacity(self.opacity), base, 0)
            canvas.polygon(self.color1, base, 1)

            return r

        # Change detection
        def event(self, ev, x, y, st):
            if (new_points :=[eval(str(p)) for p in self.expressions]) != self.points:
                self.points = new_points
                renpy.redraw(self, 0)
