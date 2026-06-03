# ─── ev.py ────────────────────────────────────────────────────────────────────
from config import *
from world  import (nearest_road, nearest_wh_path, nearby_road_nodes, astar, road_adj,
                        wh_road_set, wh_roads, chargers, labels)
from orders import (order_queue, sim_time, get_ready_orders,
                        order_sort_key, Mode_SCHEDULED,
                        Mode_NAMES, Batch_Size, WH_Wait,
                        get_spatial_batch, requeue_stranded_orders)
from world import grid as _grid

DLG_TIMEOUT = 180   # blocked-route dialog auto-skips

def _build_charger_adj(grid):
    adj  = {}
    flat = set()
    for ch in chargers:
        neighbours = []
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = ch[0] + dr, ch[1] + dc
            if 0 <= nr < Rows and 0 <= nc < Cols and grid[nr][nc] in (1, 3):
                neighbours.append((nr, nc))
        adj[ch] = neighbours
        flat.update(neighbours)
    return adj, flat

_charger_adj_map, _all_charger_adj = _build_charger_adj(_grid)

def _best_charger_path(pos):
    best, bl = [], 9999
    for adj_nodes in _charger_adj_map.values():
        for rn in adj_nodes:
            if abs(rn[0] - pos[0]) + abs(rn[1] - pos[1]) >= bl:
                continue
            p = astar(pos, rn)
            if p and len(p) < bl:
                best, bl = p, len(p)
    return best

def pick_best_ev_for_order(evs, order):
    candidates = [ev for ev in evs
                  if ev.phase == "idle" and ev.at_wh()
                  and not ev.path and ev.battery > Low_Battery]
    if not candidates:
        return None

    target_rn = nearest_road(order["house"])
    if target_rn is None:
        return candidates[0]

    scored = []
    for ev in candidates:
        p    = astar(ev.pos, target_rn)
        dist = len(p) if p else 9999
        scored.append((dist, ev))
    scored.sort(key=lambda x: x[0])

    sufficient = [(d, ev) for d, ev in scored if ev.battery > Low_Battery]
    low_batt   = [(d, ev) for d, ev in scored if ev.battery <= Low_Battery]

    if sufficient:
        return sufficient[0][1]
    elif low_batt:
        low_batt.sort(key=lambda x: -x[1].battery)
        return low_batt[0][1]
    return candidates[0]

class EV:
    def __init__(self, idx):
        self.idx   = idx
        self.name  = EV_Names[idx]
        self.color = EV_Colors[idx]
        self.pos   = wh_roads[idx % len(wh_roads)] if wh_roads else (Rows // 2, Cols // 2)

        self.battery   = Max_Battery
        self.path      = []
        self.full_path = []

        self.loaded    = []
        self.target    = None
        self.target_rn = None

        self.phase     = "idle"
        self.status    = "Idle"
        self.wh_wait   = 0
        self.move_tick = 0
        self.delivered = 0

        self._going_to_charge = False
        # Blocked-route dialog
        self.dlg              = False
        self.dlg_house        = None
        self.dlg_nodes        = []
        self._dlg_start_frame = 0

    def at_wh(self):
        return self.pos in wh_road_set

    def set_status(self, s):
        self.status = s

    def sort_loaded(self):
        self.loaded.sort(key=order_sort_key)

    def _near_charger(self):
        return self.pos in _all_charger_adj

    def _clear_target(self):
        self.target = None
        self.target_rn = None
        self.full_path = []

    def _drop_target_order(self):
        if self.target:
            self.loaded = [o for o in self.loaded if o["house"] != self.target]

    def _can_reach_charger(self):
        cp = _best_charger_path(self.pos)
        if not cp:
            return [], False
        cost = len(cp) - 1   
        return cp, self.battery > cost

    def _can_reach_wh(self):
        p = nearest_wh_path(self.pos)
        if not p:
            return [], False
        cost = len(p) - 1
        return p, self.battery > cost

    def _go_charge(self):
        cp, charger_ok = self._can_reach_charger()
        if charger_ok:
            self._going_to_charge = True
            self.path      = cp[1:]
            self.full_path = list(cp)
            self.phase     = "charging"
            self._clear_target()
            self.set_status(f"Low batt ({self.battery}%) → charger")
            return True

        wp, wh_ok = self._can_reach_wh()
        if wh_ok:
            self._going_to_charge = False
            self.path      = wp[1:]
            self.full_path = list(wp)
            self.phase     = "returning"
            self._clear_target()
            self.set_status(f"Low batt ({self.battery}%) → WH (no charger)")
            return True

        # STRANDED — cannot reach charger or WH
        self._going_to_charge = False
        self._handle_stranded()
        return False

    def _handle_stranded(self):
        if self.loaded:
            requeue_stranded_orders(list(self.loaded))
            self.loaded = []
        self._clear_target()
        self.path             = []
        self.full_path        = []
        self._going_to_charge = False
        self.phase            = "idle"
        self.set_status(f"⚠ STRANDED (batt={self.battery}%)")

    def _arrive_at_charger(self):
        self.battery          = Max_Battery
        self._going_to_charge = False
        self.path             = []
        self.full_path        = []
        self.set_status("Charged ✓")
        if self.loaded:
            self.next_delivery()
        else:
            self.after_batch()

    def check_express_reroute(self):
        if not self.loaded or self.phase != "delivering":
            return
        self.sort_loaded()
        if self.loaded[0]["house"] != self.target:
            self._clear_target()
            self.path = []
            self.next_delivery()

    def load_and_go(self):
        ready = get_ready_orders()
        if not ready:
            return

        anchor = ready[0]                               # highest-priority order
        batch  = get_spatial_batch(anchor, Batch_Size)  # spatially grouped

        for o in batch:
            order_queue.remove(o)

        batch.sort(key=order_sort_key)
        self.loaded  = batch
        self.phase   = "loading"
        self.wh_wait = WH_Wait
        self.set_status(f"Loading {len(self.loaded)} pkg(s)")

    def finish_loading(self):
        self.set_status(f"Departed — {len(self.loaded)} pkg(s)")
        self.next_delivery()

    def next_delivery(self):
        self.sort_loaded()
        cap     = len(self.loaded)
        attempt = 0

        while self.loaded and attempt < cap:
            order   = self.loaded[0]
            attempt += 1

            if (order["mode"] == Mode_SCHEDULED
                    and order["scheduled_frame"]
                    and sim_time[0] * 30 < order["scheduled_frame"]):
                if len(self.loaded) > 1:
                    self.loaded.append(self.loaded.pop(0))
                    continue
                else:
                    self.after_batch()
                    return

            h  = order["house"]
            if not road_adj(h[0], h[1]):
                nodes = nearby_road_nodes(h)
                if nodes:
                    self.dlg = True
                    self.dlg_house = h
                    self.dlg_nodes = nodes
                    self.set_status(f"{labels[h]} unreachable")
                    return
                else:
                    self.loaded.pop(0)
                    continue

            rn = nearest_road(h)
            if rn is None:
                self.loaded.pop(0)
                continue

            p = astar(self.pos, rn)
            # p = []    # To try the blocked route
            if p:
                self.target    = h
                self.target_rn = rn
                self.full_path = list(p)
                self.phase     = "delivering"
                self.set_status(f"→ {labels[h]} [{Mode_NAMES[order['mode']]}]")
                # Already at the delivery node — deliver immediately
                if self.pos == rn:
                    self.path = []
                    self.loaded.pop(0)
                    self.delivered += 1
                    self.set_status(f"Delivered {labels.get(h, '?')}")
                    self._clear_target()
                    if self.loaded:
                        self.sort_loaded()
                        self.next_delivery()
                    else:
                        self.after_batch()
                else:
                    self.path = p[1:]
                return
            else:
                nodes = nearby_road_nodes(h)
                if nodes:
                    self.dlg              = True
                    self.dlg_house        = h
                    self.dlg_nodes        = nodes
                    self._dlg_start_frame = 0
                    self.set_status(f"{labels[h]} blocked")
                    return
                else:
                    self.loaded.pop(0)
                    continue

        self.after_batch()

    def after_batch(self):
        if self.at_wh():
            if get_ready_orders():
                self.load_and_go()
            else:
                self.phase = "idle"
                self.set_status("Idle at WH")
            return
        p = nearest_wh_path(self.pos)
        if p:
            self.path      = p[1:]
            self.full_path = list(p)
            self.phase     = "returning"
            self.set_status("Returning to WH")
        else:
            self.phase = "idle"
            self.set_status("Idle")

    def tick(self, frame):
        if self.phase == "idle" and self.loaded:
            self.next_delivery()
            return

        if self.phase == "idle" and self.at_wh() and get_ready_orders():
            self.load_and_go()
            return
        if self.phase == "loading":
            self.wh_wait -= 1
            if self.wh_wait <= 0:
                self.finish_loading()
            return

        if self.dlg:
            if self._dlg_start_frame == 0:
                self._dlg_start_frame = frame
            if frame - self._dlg_start_frame > DLG_TIMEOUT:
                h = self.dlg_house
                self.loaded           = [o for o in self.loaded if o["house"] != h]
                self.dlg              = False
                self.dlg_house        = None
                self.dlg_nodes        = []
                self._dlg_start_frame = 0
                self.next_delivery()
            return

        if (self.battery <= Low_Battery
                and self.phase not in ("charging", "loading", "idle")
                and not self._going_to_charge):
            self._go_charge()

        if not self.path and self.phase not in ("loading", "idle"):

            if self.phase == "delivering":
                if not self.loaded:
                    self.after_batch()

                elif not self.target:
                    self.next_delivery()

                else:
                    if self.target_rn and self.pos == self.target_rn:
                        if self.loaded and self.loaded[0]["house"] == self.target:
                            self.loaded.pop(0)
                        self.delivered += 1
                        self.set_status(f"Delivered {labels.get(self.target, '?')}")
                        self._clear_target()
                        if self.loaded:
                            self.sort_loaded()
                            self.next_delivery()
                        else:
                            self.after_batch()
                    else:
                        rn = nearest_road(self.target)
                        if rn:
                            p = astar(self.pos, rn)
                            if p:
                                self.target_rn = rn
                                self.full_path = list(p)
                                if self.pos == rn:
                                    # Already at delivery node — deliver immediately
                                    self.path = []
                                    if self.loaded and self.loaded[0]["house"] == self.target:
                                        self.loaded.pop(0)
                                    self.delivered += 1
                                    self.set_status(f"Delivered {labels.get(self.target, '?')}")
                                    self._clear_target()
                                    if self.loaded:
                                        self.sort_loaded()
                                        self.next_delivery()
                                    else:
                                        self.after_batch()
                                else:
                                    self.path = p[1:]
                            else:
                                self._drop_target_order()
                                self._clear_target()
                                self.next_delivery()
                        else:
                            self._drop_target_order()
                            self._clear_target()
                            self.next_delivery()

            elif self.phase == "returning":
                if self.at_wh():
                    if get_ready_orders():
                        self.load_and_go()
                    else:
                        self.phase = "idle"
                        self.set_status("Idle at WH")
                else:
                    p = nearest_wh_path(self.pos)
                    if p:
                        self.path      = p[1:]
                        self.full_path = list(p)
                    else:
                        self.phase = "idle"
                        self.set_status("Idle")

            elif self.phase == "charging":
                if self._near_charger():
                    self._arrive_at_charger()
                else:
                    self._going_to_charge = False
                    if not self._go_charge():   # _go_charge handles WH fallback and stranded case
                        pass

        self.move_tick += 1
        if self.move_tick >= EV_Speed and self.path:
            self.move_tick = 0
            self.pos       = self.path.pop(0)
            self.battery   = max(0, self.battery - 1)  # 1 unit per step
            if self.phase == "charging" and self._near_charger():
                self._arrive_at_charger()
                return
            
            if self.at_wh() and self.phase == "returning" and not self.path:
                if get_ready_orders():
                    self.load_and_go()
                else:
                    self.phase = "idle"
                    self.set_status("Idle at WH")

            if (self.phase == "delivering"
                    and self.target_rn
                    and self.pos == self.target_rn
                    and not self.path):
                if self.loaded and self.loaded[0]["house"] == self.target:
                    self.loaded.pop(0)
                self.delivered += 1
                self.set_status(f"Delivered {labels.get(self.target, '?')}")
                self._clear_target()
                
                if self.loaded:
                    self.sort_loaded()
                    self.next_delivery()
                else:
                    self.after_batch()