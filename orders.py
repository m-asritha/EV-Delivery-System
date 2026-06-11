# orders.py — Order creation, queue management, priority, weight, warehouse ─
import random
from config import *
from world import wh_roads, astar, nearest_road

order_queue      = []
order_id_counter = [0]
sim_time         = [0]   # current second (frame // 30)

AGING_INTERVAL_FRAMES = 150   # 5 seconds at 30 fps
STANDARD_BOOST_RATE   = 0.30
EXPRESS_BOOST_RATE    = 0.10

# ─── Multi-warehouse assignment (Upgrade 7) ──────────────────────────────────
def nearest_warehouse_to(house):
    """Return the index of the warehouse with the shortest road-path to
    `house`. Used so each order is dispatched from its nearest warehouse."""
    rn = nearest_road(house)
    if rn is None or not wh_roads:
        return 0
    best_i, best_len = 0, 9999
    for i, wr in enumerate(wh_roads):
        p = astar(wr, rn)
        if p and len(p) < best_len:
            best_i, best_len = i, len(p)
    return best_i

# ─── Factory ──────────────────────────────────────────────────────────────────
def make_order(house, mode=None, scheduled_frame=None, priority_boost=False):
    if mode is None:
        mode = random.choice(Mode_WEIGHTS)
    order_id_counter[0] += 1
    sched = None
    if mode == Mode_SCHEDULED:
        if scheduled_frame is not None:
            sched = scheduled_frame
        else:
            secs  = random.randint(30, Max_SCHEDULE_SECONDS)
            sched = sim_time[0] * 30 + secs * 30
    return {
        "house":           house,
        "mode":            mode,
        "id":              order_id_counter[0],
        "scheduled_frame": sched,
        "placed_frame":    sim_time[0] * 30,   # used for aging
        "priority_boost":  priority_boost,      # True -> was stranded, re-queued
        "weight":          random.randint(Order_Min_Weight, Order_Max_Weight),
        "warehouse":       nearest_warehouse_to(house),  # Upgrade 7
    }

# ─── Priority key (with aging) ─────────────────────────────────────────────────
def order_sort_key(o):
    current_frame = sim_time[0] * 30
    placed        = o.get("placed_frame", current_frame)
    waited        = max(0, current_frame - placed)
    intervals     = waited // AGING_INTERVAL_FRAMES
    if o["mode"] == Mode_SCHEDULED:
        if o["scheduled_frame"] and current_frame < o["scheduled_frame"]:
            return (10, o["scheduled_frame"], o["id"])   # not yet due — defer
        return (0, 0, o["id"])                           # due now — top priority
    if o.get("priority_boost"):
        return (0.5, 0, o["id"])                         # just above fresh EXPRESS
    if o["mode"] == Mode_EXPRESS:
        aged = max(0.0, 1.0 - intervals * EXPRESS_BOOST_RATE)
        return (aged, 0, o["id"])
    aged = max(0.0, 2.0 - intervals * STANDARD_BOOST_RATE)
    return (aged, 0, o["id"])

# ─── Queue operations ──────────────────────────────────────────────────────────
def enqueue_order(order):
    order_queue.append(order)
    order_queue.sort(key=order_sort_key)

def requeue_stranded_orders(orders):
    for o in orders:
        o["priority_boost"] = True
        o["placed_frame"]   = sim_time[0] * 30   # restart aging clock
        if o not in order_queue:
            order_queue.append(o)
    order_queue.sort(key=order_sort_key)

def resort_queue():
    order_queue.sort(key=order_sort_key)

def get_ready_orders():
    return [o for o in order_queue if not (
        o["mode"] == Mode_SCHEDULED
        and o["scheduled_frame"]
        and sim_time[0] * 30 < o["scheduled_frame"]
    )]

# ─── Spatial + weight-aware batching (Upgrade 8) ───────────────────────────────
def get_spatial_batch(anchor_order, max_size, capacity=None):
    """Group nearby ready orders with the anchor, but stop adding orders
    once the cumulative weight would exceed `capacity` (if given).
    Falls back to count-based limiting (max_size) when capacity is None."""
    ready = get_ready_orders()
    if not ready:
        return []

    ah, aw = anchor_order["house"]
    others = [o for o in ready if o is not anchor_order]
    scored = sorted(
        others,
        key=lambda o: abs(o["house"][0] - ah) + abs(o["house"][1] - aw)
    )

    batch = [anchor_order]
    total_w = anchor_order.get("weight", 1)

    for o in scored:
        if len(batch) >= max_size:
            break
        w = o.get("weight", 1)
        if capacity is not None and total_w + w > capacity:
            continue
        batch.append(o)
        total_w += w

    return batch

def batch_weight(batch):
    return sum(o.get("weight", 1) for o in batch)

# ─── Query helpers ──────────────────────────────────────────────────────────────
def house_in_queue(h):
    return any(o["house"] == h for o in order_queue)

def house_assigned(h, evs):
    for ev in evs:
        if ev.target == h:
            return True
        if any(o["house"] == h for o in ev.loaded):
            return True
        if ev.dlg and ev.dlg_house == h:
            return True
    return False