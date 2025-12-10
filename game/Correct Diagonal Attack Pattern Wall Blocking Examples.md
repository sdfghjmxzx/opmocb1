Heavy Attack Indexing (Facing NE, relative to player (Pr,Pc))

For Player at row Pr, col Pc facing NE, heavy pattern uses engine index order:
Index → (dx, dy) → tile coordinate = (Pr+dy, Pc+dx)

0: (fx, 0)       → (Pr,   Pc+fx)
1: (0, fy)       → (Pr+fy, Pc)
2: (fx, fy)      → (Pr+fy, Pc+fx)
3: (2fx, fy)     → (Pr+fy, Pc+2fx)
4: (fx, 2fy)     → (Pr+2fy, Pc+fx)
5: (2fx, 0)      → (Pr,    Pc+2fx)
6: (0, 2fy)      → (Pr+2fy, Pc)
7: (2fx, 2fy)    → (Pr+2fy, Pc+2fx)

For NE (facing 315°), F = (fx, fy) = (1, -1).

---

1.Player - 7,B - Facing North East 
Wall - Between 5,C and 5,D
Local vector: dx=-2, dy=2
Heavy Attack Pattern - 7,C 7,D 6,B 6,C 6,D 5,B 5,C 5,D
Blocked tiles - 5,D
Blocked indices - {7}

2.Player - 6,B - Facing North East
Wall - Between 5,C and 5,D
Local vector: dx=-1, dy=2
Heavy Attack Pattern - 6,C 6,D 5,B 5,C 5,D 4,B 4,C 4,D
Blocked tiles - 5,D and 4,D
Blocked indices - {4,7}

3.Player - 5,B - Facing North East
Wall - Between 5,C and 5,D
Local vector: dx=0, dy=2
Heavy Attack Pattern -  5,C 5,D 4,B 4,C 4,D 3,B 3,C 3,D
Blocked tiles - 5,D
Blocked indices - {5}

This is all 3 positions for a player that is 1 square away from a vertical wall pla

1.Player - 7,C - Facing North East
Wall - Between 5,C and 5,D
Local vector: dx=-2, dy=1
Heavy Attack Pattern - 7,D 7,E 6,C 6,D 6,E 5,C 5,D 5,E
Blocked tiles - 6,D
Blocked indices - {2}

2.Player - 6,C - Facing North East
Wall - Between 5,C and 5,D
Local vector: dx=-1, dy=1
Heavy Attack Pattern -  6,D 6,E 5,C 5,D 5,E 4,C 4,D 4,E
Blocked tiles - 5,D , 4,D and 4,E
Blocked indices - {2,4,7}

3.Player - 5,C - Facing North East
Wall - Between 5,C and 5,D
Local vector: dx=0, dy=1
Heavy Attack Pattern - 5,D 5,E 4,C 4,D 4,E 3,C 3,D 3,E
Blocked tiles - 5,D , 4,D , 5,E , 4,E and 3,E
Blocked indices - {0,2,3,5,7}


This is all 3 positions for a player that is 0 squares away from a vertical wall

1.Player - 7,B - Facing North East
Wall - Between 5,D and 6,D
Local vector: dx=-2, dy=2
Heavy Attack Pattern - 7,C 7,D 6,B 6,C 6,D 5,B 5,C 5,D 
Blocked tiles - 5,D
Blocked indices - {7}

2.Player - 6,B - Facing North East
Wall - Between 5,D and 6,D
Local vector: dx=-1, dy=2
Heavy Attack Pattern - 6,C 6,D 5,B 5,C 5,D 4,B 4,C 4,D
Blocked tiles - 5,D
Blocked indices - {3}

3.Player - 5,B - Facing North East
Wall - Between 5,D and 6,D
Local vector: dx=0, dy=2
Heavy Attack Pattern -  5,C 5,D 4,B 4,C 4,D 3,B 3,C 3,D
Blocked tiles - none
Blocked indices - {}

This is all 3 positions for a player that is 1 square away from a horizontal wall

1.Player - 7,C - Facing North East
Wall - Between 5,D and 6,D
Local vector: dx=-2, dy=1
Heavy Attack Pattern - 7,D 7,E 6,C 6,D 6,E 5,C 5,D 5,E
Blocked tiles - 5,D and 5,E
Blocked indices - {4,7}

2.Player - 6,C - Facing North East
Wall - Between 5,D and 6,D
Local vector: dx=-1, dy=1
Heavy Attack Pattern -  6,D 6,E 5,C 5,D 5,E 4,C 4,D 4,E
Blocked tiles - 5,D , 4,D , 5,E and 4,E
Blocked indices - {2,3,4,7}

3.Player - 5,C - Facing North East
Wall - Between 5,D and 6,D
Local vector: dx=0, dy=1
Heavy Attack Pattern - 5,D 5,E 4,C 4,D 4,E 3,C 3,D 3,E
Blocked tiles - none
Blocked indices - {}

This is all 3 positions for a player that is 0 squares away from a horizontal wall

---

Heavy Attack Indexing (Facing NW, relative to player (Pr,Pc))

For Player at row Pr, col Pc facing NW, heavy pattern uses engine index order:
Index → (dx, dy) → tile coordinate = (Pr+dy, Pc+dx)

0: (fx, 0)       → (Pr,   Pc+fx)
1: (0, fy)       → (Pr+fy, Pc)
2: (fx, fy)      → (Pr+fy, Pc+fx)
3: (2fx, fy)     → (Pr+fy, Pc+2fx)
4: (fx, 2fy)     → (Pr+2fy, Pc+fx)
5: (2fx, 0)      → (Pr,    Pc+2fx)
6: (0, 2fy)      → (Pr+2fy, Pc)
7: (2fx, 2fy)    → (Pr+2fy, Pc+2fx)

For NW (facing 225°), F = (fx, fy) = (-1, -1).

---

1.Player - 7,E - Facing North West 
Wall - Between 5,C and 5,D
Local vector: dx=2, dy=1
Heavy Attack Pattern - 7,C 7,D 6,C 6,D 6,E 5,C 5,D 5,E
Blocked tiles - 5,C
Blocked indices - {7}

2.Player - 6,E - Facing North West
Wall - Between 5,C and 5,D
Local vector: dx=1, dy=1
Heavy Attack Pattern - 6,C 6,D 5,C 5,D 5,E 4,C 4,D 4,E
Blocked tiles - 5,C and 4,C
Blocked indices - {3,7}

3.Player - 5,E - Facing North West
Wall - Between 5,C and 5,D
Local vector: dx=0, dy=1
Heavy Attack Pattern - 5,C 5,D 4,C 4,D 4,E 3,C 3,D 3,E
Blocked tiles - 5,C
Blocked indices - {5}

This is all 3 positions for a player that is 1 square away from a vertical wall (NW)

1.Player - 7,D - Facing North West
Wall - Between 5,C and 5,D
Local vector: dx=2, dy=2
Heavy Attack Pattern - 7,B 7,C 6,B 6,C 6,D 5,B 5,C 5,D
Blocked tiles - 6,C
Blocked indices - {2}

2.Player - 6,D - Facing North West
Wall - Between 5,C and 5,D
Local vector: dx=1, dy=2
Heavy Attack Pattern - 6,B 6,C 5,B 5,C 5,D 4,B 4,C 4,D
Blocked tiles - 5,C , 4,C and 4,B
Blocked indices - {2,4,7}

3.Player - 5,D - Facing North West
Wall - Between 5,C and 5,D
Local vector: dx=0, dy=2
Heavy Attack Pattern - 5,B 5,C 4,B 4,C 4,D 3,B 3,C 3,D
Blocked tiles - 5,C , 4,C , 5,B , 4,B and 3,B
Blocked indices - {0,2,3,5,7}


This is all 3 positions for a player that is 0 squares away from a vertical wall (NW)

1.Player - 7,E - Facing North West
Wall - Between 5,D and 6,D
Local vector: dx=2, dy=2
Heavy Attack Pattern - 7,C 7,D 6,C 6,D 6,E 5,C 5,D 5,E
Blocked tiles - 5,D
Blocked indices - {4}

2.Player - 6,E - Facing North West
Wall - Between 5,D and 6,D
Local vector: dx=1, dy=2
Heavy Attack Pattern - 6,C 6,D 5,C 5,D 5,E 4,C 4,D 4,E
Blocked tiles - 5,D
Blocked indices - {2}

3.Player - 5,E - Facing North West
Wall - Between 5,D and 6,D
Local vector: dx=0, dy=2
Heavy Attack Pattern - 5,C 5,D 4,C 4,D 4,E 3,C 3,D 3,E
Blocked tiles - none
Blocked indices - {}

This is all 3 positions for a player that is 1 square away from a horizontal wall (NW)

1.Player - 7,D - Facing North West
Wall - Between 5,D and 6,D
Local vector: dx=2, dy=1
Heavy Attack Pattern - 7,B 7,C 6,B 6,C 6,D 5,B 5,C 5,D
Blocked tiles - 5,C and 5,D
Blocked indices - {4,6}

2.Player - 6,D - Facing North West
Wall - Between 5,D and 6,D
Local vector: dx=1, dy=1
Heavy Attack Pattern - 6,B 6,C 5,B 5,C 5,D 4,B 4,C 4,D
Blocked tiles - 5,C , 4,C , 5,D and 4,D
Blocked indices - {1,2,4,6}

3.Player - 5,D - Facing North West
Wall - Between 5,D and 6,D
Local vector: dx=0, dy=1
Heavy Attack Pattern - 5,B 5,C 4,B 4,C 4,D 3,B 3,C 3,D
Blocked tiles - none
Blocked indices - {}

This is all 3 positions for a player that is 0 squares away from a horizontal wall (NW)

