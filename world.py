# new_world.py — Map generation, grid, pathfinding 
import heapq, random
from collections import deque
from config import *

# Grid / road layout
H_ROAD_Rows = set()
for i in range(1, 5):
    H_ROAD_Rows.add(i * (Rows // 5))

V_ROAD_Cols = set()
_c = 0; _toggle = True
while _c < Cols:
    V_ROAD_Cols.add(_c)
    _c += 7 if _toggle else 8
    _toggle = not _toggle

grid = [[0]*Cols for _ in range(Rows)]
for r in range(Rows):
    for c in range(Cols):
        if r in H_ROAD_Rows or c in V_ROAD_Cols:
            grid[r][c] = 1

def road_adj(r, c):
    for dr, dc in ((1,0),(-1,0),(0,1),(0,-1)):
        nr, nc = r+dr, c+dc
        if 0<=nr<Rows and 0<=nc<Cols and grid[nr][nc]==1:
            return True
    return False

def nearest_road(pos):
    if grid[pos[0]][pos[1]] in (1, 3): return pos
    q, vis = deque([pos]), {pos}
    while q:
        r, c = q.popleft()
        if grid[r][c] in (1, 3): return (r, c)
        for dr, dc in ((1,0),(-1,0),(0,1),(0,-1)):
            nb = (r+dr, c+dc)
            if nb not in vis and 0<=nb[0]<Rows and 0<=nb[1]<Cols:
                vis.add(nb); q.append(nb)
    return None

# Warehouses 
warehouses, wh_roads = [], []
att = 0
while len(warehouses) < 4 and att < 30000:
    att += 1
    r = random.randint(3, Rows-4); c = random.randint(3, Cols-4)
    if grid[r][c]!=0 or not road_adj(r,c): continue
    if any(abs(r-wr[0])+abs(c-wr[1])<16 for wr in warehouses): continue
    grid[r][c] = 2
    wr = nearest_road((r, c))
    if wr is None: grid[r][c]=0; continue
    warehouses.append((r,c)); wh_roads.append(wr)

wh_road_set = set(wh_roads)
if not warehouses:
    hr = sorted(H_ROAD_Rows); vc = sorted(V_ROAD_Cols)
    for r,c in [(hr[i],vc[j]) for i in range(len(hr)) for j in range(len(vc))][:4]:
        if grid[r][c]==1:
            grid[r][c]=2; warehouses.append((r,c)); wh_roads.append((r,c))
    wh_road_set = set(wh_roads)

# Chargers
chargers = []
att = 0
while len(chargers) < 5 and att < 80000:
    att += 1
    r = random.randint(2, Rows-3); c = random.randint(2, Cols-3)
    if grid[r][c]!=0 or not road_adj(r,c): continue
    if any(abs(r-cr)+abs(c-cc)<10 for cr,cc in chargers): continue
    if any(abs(r-wr[0])+abs(c-wr[1])<10 for wr in warehouses): continue
    grid[r][c] = 3; chargers.append((r,c))

# Houses
houses, labels, hid = [], {}, 1
for r in range(Rows):
    for c in range(Cols):
        if grid[r][c]==0 and road_adj(r,c) and random.random()<0.7:
            grid[r][c]=4; houses.append((r,c)); labels[(r,c)]=str(hid); hid+=1
        # if grid[r][c]==0 and not road_adj(r,c) and random.random()<0.05:
        #     grid[r][c]=4; houses.append((r,c)); labels[(r,c)]=str(hid); hid+=1

# A* 
def heuristic(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
def astar(start, goal):
    if start == goal:
        return [start]
    open_set = []
    heapq.heappush(open_set, (heuristic(start, goal), 0, start))
    parent = {}
    g_cost = {start: 0}
    visited = set()
    while open_set:
        f, g, current = heapq.heappop(open_set)
        if current in visited:
            continue
        visited.add(current)
        if current == goal:
            path = []
            while current != start:
                path.append(current)
                current = parent[current]
            path.append(start)
            return path[::-1]
        x, y = current
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = x + dx, y + dy
            neighbor = (nx, ny)
            if 0 <= nx < Rows and 0 <= ny < Cols:
                if grid[nx][ny] not in (1,2,3):
                    continue
                new_g = g + 1
                if neighbor not in g_cost or new_g < g_cost[neighbor]:
                    g_cost[neighbor] = new_g
                    f_cost = new_g + heuristic(neighbor, goal)
                    parent[neighbor] = current
                    heapq.heappush(open_set, (f_cost, new_g, neighbor))

    return []

def nearest_wh_path(pos):
    if not wh_roads: return []
    best,bl=[],9999
    for wr in sorted(wh_roads,key=lambda w:abs(w[0]-pos[0])+abs(w[1]-pos[1])):
        if abs(wr[0]-pos[0])+abs(wr[1]-pos[1])>=bl: break
        p=astar(pos,wr)
        if p and len(p)<bl: best,bl=p,len(p)
    return best

def nearby_road_nodes(house, count=5):
    cands=[]
    for dr in range(-8,9):
        for dc in range(-8,9):
            nr,nc=house[0]+dr,house[1]+dc
            if 0<=nr<Rows and 0<=nc<Cols and grid[nr][nc] in (1,3):
                cands.append((abs(dr)+abs(dc),(nr,nc)))
    cands.sort(); seen,result=set(),[]
    for _,node in cands:
        if node not in seen: seen.add(node); result.append(node)
        if len(result)==count: break
    return result
