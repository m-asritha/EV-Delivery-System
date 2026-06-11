# world.py — Map generation, grid, traffic, road blocks, pathfinding ────────
import heapq, random
from collections import deque
from config import *

# ─── Grid / road layout ──────────────────────────────────────────────────────
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

# ─── Warehouses (Upgrade 7: multiple warehouses) ─────────────────────────────
# We place 3 warehouses spread across the map. Each EV is assigned to / can
# return to any warehouse; orders are dispatched from the NEAREST warehouse
# to the order's house (see orders.nearest_warehouse_to).
NUM_WAREHOUSES = 3
warehouses, wh_roads = [], []
att = 0
while len(warehouses) < NUM_WAREHOUSES and att < 30000:
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
    for r,c in [(hr[i],vc[j]) for i in range(len(hr)) for j in range(len(vc))][:NUM_WAREHOUSES]:
        if grid[r][c]==1:
            grid[r][c]=2; warehouses.append((r,c)); wh_roads.append((r,c))
    wh_road_set = set(wh_roads)

# ─── Chargers ────────────────────────────────────────────────────────────────
chargers = []
att = 0
while len(chargers) < 5 and att < 80000:
    att += 1
    r = random.randint(2, Rows-3); c = random.randint(2, Cols-3)
    if grid[r][c]!=0 or not road_adj(r,c): continue
    if any(abs(r-cr)+abs(c-cc)<10 for cr,cc in chargers): continue
    if any(abs(r-wr[0])+abs(c-wr[1])<10 for wr in warehouses): continue
    grid[r][c] = 3; chargers.append((r,c))

# ─── Houses ──────────────────────────────────────────────────────────────────
houses, labels, hid = [], {}, 1
for r in range(Rows):
    for c in range(Cols):
        if grid[r][c]==0 and road_adj(r,c) and random.random()<0.7:
            grid[r][c]=4; houses.append((r,c)); labels[(r,c)]=str(hid); hid+=1

# ─── Traffic-aware grid (Upgrade 4) ──────────────────────────────────────────
# traffic_grid[r][c] holds a congestion level (TRAFFIC_GREEN/YELLOW/RED) for
# every road-type cell (1 = road, 3 = charger-adjacent road also usable).
# Levels are randomly re-rolled periodically per-cell to simulate dynamic
# traffic. A* uses TRAFFIC_COST[level] as the step cost instead of a flat 1,
# so the search naturally avoids congested roads while still finding a path
# even if all roads are jammed (cost is never infinite).
traffic_grid = [[TRAFFIC_GREEN]*Cols for _ in range(Rows)]

def update_traffic():
    """Randomly re-roll traffic levels for a subset of road cells.
    Called periodically from the main loop (see TRAFFIC_UPDATE_INTERVAL)."""
    for r in range(Rows):
        for c in range(Cols):
            if grid[r][c] in (1, 3):
                # Only a fraction of cells change each tick to keep things
                # visually stable rather than flickering every cell at once.
                if random.random() < 0.08:
                    traffic_grid[r][c] = random.choice(TRAFFIC_WEIGHTS)

# ─── Dynamic road blocks (Upgrade 5) ─────────────────────────────────────────
# blocked_roads: dict[(r,c)] -> frame at which the block expires.
# When a road cell is blocked, A* treats it as impassable (like a building),
# forcing automatic route recalculation for any EV whose path crosses it.
blocked_roads = {}
# Broadcast log of block/unblock events for the fleet panel (Upgrade 1/14).
road_block_events = []

def update_road_blocks(frame):
    """Randomly create new road blocks and expire old ones."""
    # Expire old blocks
    expired = [pos for pos, exp in blocked_roads.items() if frame >= exp]
    for pos in expired:
        del blocked_roads[pos]
        road_block_events.append((frame, "CLEAR", pos))

    # Possibly create a new block
    if (len(blocked_roads) < ROAD_BLOCK_MAX_ACTIVE
            and frame % ROAD_BLOCK_INTERVAL == 0 and frame > 0):
        candidates = [(r, c) for r in range(Rows) for c in range(Cols)
                       if grid[r][c] == 1 and (r, c) not in blocked_roads
                       and (r, c) not in wh_road_set]
        if candidates:
            pos = random.choice(candidates)
            blocked_roads[pos] = frame + ROAD_BLOCK_DURATION
            road_block_events.append((frame, "BLOCK", pos))

    # Trim event log
    if len(road_block_events) > 30:
        del road_block_events[:-30]

# ─── A* with traffic + dynamic blocks ────────────────────────────────────────
def heuristic(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def astar(start, goal):
    """Traffic-aware A*. Step cost = TRAFFIC_COST[traffic_grid[cell]].
    Cells in `blocked_roads` are treated as impassable (cost = infinity),
    causing the search to route around them entirely. Warehouses (2) and
    chargers (3) are always passable with their own traffic cost."""
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
                if neighbor in blocked_roads:
                    continue   # dynamically blocked — impassable
                step_cost = TRAFFIC_COST.get(traffic_grid[nx][ny], 1)
                new_g = g + step_cost
                if neighbor not in g_cost or new_g < g_cost[neighbor]:
                    g_cost[neighbor] = new_g
                    f_cost = new_g + heuristic(neighbor, goal)
                    parent[neighbor] = current
                    heapq.heappush(open_set, (f_cost, new_g, neighbor))
    return []

def path_cost(path):
    """Total traffic-weighted cost of a path (used for battery prediction)."""
    if not path or len(path) < 2:
        return 0
    total = 0
    for (r, c) in path[1:]:
        total += TRAFFIC_COST.get(traffic_grid[r][c], 1)
    return total

def nearest_wh_path(pos):
    """Shortest path to the nearest reachable warehouse road node."""
    if not wh_roads: return []
    best, bl = [], 9999
    for wr in sorted(wh_roads, key=lambda w: abs(w[0]-pos[0])+abs(w[1]-pos[1])):
        if abs(wr[0]-pos[0])+abs(wr[1]-pos[1]) >= bl: continue
        p = astar(pos, wr)
        if p and len(p) < bl: best, bl = p, len(p)
    return best

def nearest_wh_index(pos):
    """Index of the nearest warehouse (by road-path length) to pos."""
    best_i, best_len = 0, 9999
    for i, wr in enumerate(wh_roads):
        p = astar(pos, wr)
        if p and len(p) < best_len:
            best_i, best_len = i, len(p)
    return best_i

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