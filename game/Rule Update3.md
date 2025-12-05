## **DIAGONAL ATTACK PATTERN FORMULA**

Let **P = (pₓ, pᵧ)** be player coordinates (zero-indexed).  
Let **F = (fₓ, fᵧ)** be facing vector where fₓ, fᵧ ∈ {‑1, 0, 1}.

Define **S(k)** as the set of relative coordinates for attack type **k** (1=Quick, 2=Normal, 3=Heavy):

### **Quick Attack (3 tiles)**
```
S(1) = { (2fₓ, 2fᵧ), (fₓ, 2fᵧ), (2fₓ, fᵧ) }
```

### **Normal Attack (5 tiles)**
```
S(2) = S(1) ∪ { (2fₓ, 3fᵧ), (3fₓ, 2fᵧ) }
```

### **Heavy Attack (8 tiles)**
```
S(3) = S(2) ∪ { (3fₓ, 3fᵧ), (fₓ, 3fᵧ), (3fₓ, fᵧ) }
```

### **Final Tile Coordinates**
```
Tiles = { (pₓ + x, pᵧ + y) | (x, y) ∈ S(k) }
```

---

### **NW Facing Example (fₓ = ‑1, fᵧ = ‑1)**

**Quick**: { (‑2,‑2), (‑1,‑2), (‑2,‑1) } → **B3, C3, B4**  
**Normal**: + { (‑2,‑3), (‑3,‑2) } → **+ B2, A3**  
**Heavy**: + { (‑3,‑3), (‑1,‑3), (‑3,‑1) } → **+ A2, C2, A4**