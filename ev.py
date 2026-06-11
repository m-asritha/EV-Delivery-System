# ev.py — EV agent: movement, battery, cooperation, charging, collisions ────
from config import *
from world  import (nearest_road, nearest_wh_path, nearby_road_nodes, astar,
                     road_adj, wh_road_set, wh_roads, chargers, labels,
                     path_cost, blocked_roads, grid as _grid)
from orders import (order_queue, sim_time, get_ready_orders,
                     order_sort_key, Mode_SCHEDULED, Mode_EXPRESS,
                     Mode_NAMES, Batch_Size, WH_Wait,
                     get_spatial_batch, requeue_stranded_orders, batch_weight)
import fleet, chargers as charger_mgr, weather
from kpi import kpi, LATE_THRESHOLD_FRAMES

DLG_TIMEOUT = 180   # blocked-route dialog auto-skips


# ─── Charger adjacency (precomputed once) ───────────────────────────────────
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
# Reverse map: road-node -> charger it belongs to (for reservation release)
_road_to_charger = {}
for _ch, _nodes in _charger_adj_map.items():
    for _n in _nodes:
        _road_to_charger[_n] = _ch


def _best_charger_paths(pos):
    """Return list of (path, charger_pos, cost) sorted by cost, for ALL
    chargers reachable from pos — used so an EV can pick an UNRESERVED
    charger instead of always the closest one (Upgrade 3)."""
    results = []
    for ch, adj_nodes in _charger_adj_map.items():
        best, bl = [], 9999
        for rn in adj_nodes:
            if abs(rn[0]-pos[0])+abs(rn[1]-pos[1]) >= bl:
                continue
            p = astar(pos, rn)
            if p and len(p) < bl:
                best, bl = p, len(p)
        if best:
            results.append((best, ch, path_cost(best)))
    results.sort(key=lambda x: x[2])
    return results


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
        dist = path_cost(p) if p else 9999
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
        self.home_wh = idx % max(1, len(wh_roads))   # assigned home warehouse

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
        self._reserved_charger = None   # charger pos this EV holds/queued for

        # Blocked-route dialog
        self.dlg              = False
        self.dlg_house        = None
        self.dlg_nodes        = []
        self._dlg_start_frame = 0

    # ── Helpers ───────────────────────────────────────────────────────────
    def at_wh(self):
        return self.pos in wh_road_set

    def set_status(self, s):
        self.status = s

    def sort_loaded(self):
        self.loaded.sort(key=order_sort_key)

    def current_weight(self):
        return batch_weight(self.loaded)

    def free_capacity(self):
        return EV_Max_Payload - self.current_weight()

    def _near_charger(self):
        return self.pos in _all_charger_adj

    def _clear_target(self):
        self.target = None
        self.target_rn = None
        self.full_path = []

    def _drop_target_order(self):
        if self.target:
            self.loaded = [o for o in self.loaded if o["house"] != self.target]

    def _priority_key(self):
        """Movement priority for collision avoidance (Upgrade 6)."""
        if self.loaded and self.loaded[0]["mode"] == Mode_EXPRESS:
            return "express"
        if self.loaded and self.loaded[0]["mode"] == Mode_SCHEDULED:
            return "scheduled"
        if self.loaded:
            return "standard"
        return "other"

    # ── Fleet broadcast (Upgrade 1) ─────────────────────────────────────────
    def broadcast(self):
        next_node = self.path[0] if self.path else self.pos
        fleet.broadcast(self.idx, {
            "name": self.name, "pos": self.pos, "battery": self.battery,
            "status": self.status, "phase": self.phase,
            "target": self.target, "load": len(self.loaded),
            "weight": self.current_weight(), "next_node": next_node,
        })
        fleet.claim_next_node(self.idx, next_node, self._priority_key())

    # ── Charger / WH reachability ───────────────────────────────────────────
    def _can_reach_wh(self):
        p = nearest_wh_path(self.pos)
        if not p:
            return [], False
        cost = path_cost(p)
        return p, self.battery > cost

    def battery_sufficient_for_route_and_return(self, route_path):
        """Smart charging prediction (Upgrade 9): would the EV have enough
        battery to finish `route_path` AND get back to a warehouse from the
        route's destination?"""
        if not route_path:
            return True
        out_cost = path_cost(route_path)
        dest = route_path[-1]
        ret_path = nearest_wh_path(dest)
        ret_cost = path_cost(ret_path) if ret_path else out_cost  # fallback estimate
        margin = 5  # safety buffer
        return self.battery > (out_cost + ret_cost + margin)

    # ── Charger reservation logic (Upgrade 3) ───────────────────────────────
    def _go_charge(self, frame=0):
        # If already holding a reservation, head straight there
        options = _best_charger_paths(self.pos)

        # Prefer an unreserved charger; fall back to queueing at the closest
        for cp, ch, cost in options:
            if self.battery <= cost:
                continue
            if not charger_mgr.is_reserved_by_other(ch, self.idx):
                if charger_mgr.reserve(ch, self.idx, frame):
                    self._reserved_charger = ch
                    self._going_to_charge = True
                    self.path      = cp[1:]
                    self.full_path = list(cp)
                    self.phase     = "charging"
                    self._clear_target()
                    self.set_status(f"Low batt ({self.battery}%) -> charger {ch}")
                    fleet.log(frame, f"{self.name} reserved charger {ch}")
                    return True

        # All reachable chargers reserved by others — join the queue at the
        # nearest one we can still reach, OR head to a warehouse instead.
        if options:
            cp, ch, cost = options[0]
            if self.battery > cost:
                charger_mgr.reserve(ch, self.idx, frame)  # joins wait queue
                self._reserved_charger = ch
                self._going_to_charge = True
                self.path      = cp[1:]
                self.full_path = list(cp)
                self.phase     = "charging"
                self._clear_target()
                pos_q = charger_mgr.queue_position(ch, self.idx)
                self.set_status(f"Low batt ({self.battery}%) -> queue@{ch} (#{pos_q})")
                fleet.log(frame, f"{self.name} queued for charger {ch} (#{pos_q})")
                return True

        wp, wh_ok = self._can_reach_wh()
        if wh_ok:
            self._going_to_charge = False
            self.path      = wp[1:]
            self.full_path = list(wp)
            self.phase     = "returning"
            self._clear_target()
            self.set_status(f"Low batt ({self.battery}%) -> WH (no charger)")
            return True

        # STRANDED — try cooperative transfer before giving up (Upgrade 2)
        if self._attempt_order_transfer(frame):
            return True

        self._going_to_charge = False
        self._handle_stranded(frame)
        return False

    def _handle_stranded(self, frame=0):
        if self.loaded:
            requeue_stranded_orders(list(self.loaded))
            fleet.log(frame, f"{self.name} stranded — {len(self.loaded)} orders requeued")
            self.loaded = []
        self._clear_target()
        self.path             = []
        self.full_path        = []
        self._going_to_charge = False
        self.phase            = "idle"
        self.set_status(f"⚠ STRANDED (batt={self.battery}%)")

    def _release_charger(self, frame=0):
        if self._reserved_charger is not None:
            charger_mgr.release(self._reserved_charger, self.idx, frame)
            self._reserved_charger = None

    def _arrive_at_charger(self, frame=0):
        self.battery          = Max_Battery
        self._going_to_charge = False
        self.path             = []
        self.full_path        = []
        self.set_status("Charged ✓")
        kpi.record_charge_event()
        self._release_charger(frame)
        fleet.log(frame, f"{self.name} finished charging")
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

    # ── Cooperative order transfer (Upgrade 2) ──────────────────────────────
    def _attempt_order_transfer(self, frame=0):
        """If this EV is in trouble (low battery, can't reach charger/WH, or
        stranded) and still carrying orders, try to hand them off to another
        EV with shortest distance + highest battery among those that accept
        (battery above Low_Battery and have free capacity)."""
        if not self.loaded:
            return False

        candidates = []
        for other in _ALL_EVS:
            if other.idx == self.idx:
                continue
            if other.battery <= Low_Battery:
                continue
            if other.phase not in ("idle", "returning", "delivering"):
                continue
            free_cap = other.free_capacity()
            if free_cap <= 0:
                continue
            # distance from other EV's position to this EV's position
            p = astar(other.pos, self.pos)
            dist = path_cost(p) if p else 9999
            if dist == 9999:
                continue
            candidates.append((dist, -other.battery, other, free_cap))

        if not candidates:
            return False

        candidates.sort(key=lambda x: (x[0], x[1]))  # shortest dist, then highest battery
        _, _, receiver, free_cap = candidates[0]

        # Transfer as many orders as fit, prioritized order
        self.sort_loaded()
        transferred = []
        for o in list(self.loaded):
            w = o.get("weight", 1)
            if w <= free_cap:
                transferred.append(o)
                free_cap -= w
            if free_cap <= 0:
                break

        if not transferred:
            return False

        for o in transferred:
            self.loaded.remove(o)
            receiver.loaded.append(o)
            kpi.record_transfer()
        receiver.sort_loaded()

        fleet.log(frame, f"{self.name} -> {receiver.name}: transferred "
                          f"{len(transferred)} order(s)")
        self.set_status(f"Transferred {len(transferred)} order(s) to {receiver.name}")

        # Receiver may need to (re)plan its route
        if receiver.phase in ("idle",) and receiver.at_wh():
            receiver.phase = "loading"
            receiver.wh_wait = WH_Wait
            receiver.set_status(f"Loading {len(receiver.loaded)} pkg(s) (transfer)")
        elif receiver.phase == "returning" and not receiver.target:
            pass  # will pick up delivery after reaching WH or via next tick
        elif not receiver.target:
            receiver.next_delivery()

        # If we still have orders left, try again recursively next call;
        # for now just continue with remaining (handled by caller).
        return True

    # ── Loading ───────────────────────────────────────────────────────────
    def load_and_go(self):
        ready = get_ready_orders()
        if not ready:
            return

        anchor = ready[0]
        # Weight-aware batching (Upgrade 8): respect free payload capacity
        batch  = get_spatial_batch(anchor, Batch_Size, capacity=self.free_capacity())
        if not batch:
            return

        for o in batch:
            order_queue.remove(o)
            kpi.record_departure_wait(o, sim_time[0] * 30)

        existing = list(self.loaded)
        self.loaded = existing + batch
        self.sort_loaded()
        self.phase   = "loading"
        self.wh_wait = WH_Wait
        self.set_status(f"Loading {len(self.loaded)} pkg(s) "
                         f"({self.current_weight()}/{EV_Max_Payload}kg)")

    def finish_loading(self):
        self.set_status(f"Departed — {len(self.loaded)} pkg(s)")
        self.next_delivery()

    # ── Delivery routing (traffic-aware + smart charging) ───────────────────
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
            if p:
                # Smart charging (Upgrade 9): if battery won't cover this
                # route + return to WH, proactively go charge first instead
                # of risking a stranding mid-route.
                if (not self.battery_sufficient_for_route_and_return(p)
                        and self.battery > Low_Battery
                        and not self._going_to_charge):
                    self.target    = h
                    self.target_rn = rn
                    self.full_path = list(p)
                    self.phase     = "delivering"
                    self.set_status(f"Battery margin low — pre-emptive charge planned")
                    self._go_charge()
                    return

                self.target    = h
                self.target_rn = rn
                self.full_path = list(p)
                self.phase     = "delivering"
                self.set_status(f"-> {labels[h]} [{Mode_NAMES[order['mode']]}]")
                if self.pos == rn:
                    self.path = []
                    self.loaded.pop(0)
                    self.delivered += 1
                    self._record_delivery(order)
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

    def _record_delivery(self, order):
        frame_now = sim_time[0] * 30
        on_time = (frame_now - order.get("placed_frame", frame_now)) <= LATE_THRESHOLD_FRAMES
        if order["mode"] == Mode_SCHEDULED and order["scheduled_frame"]:
            on_time = frame_now <= order["scheduled_frame"] + 30
        kpi.record_delivery(order, frame_now, on_time)

    def after_batch(self):
        if self.at_wh():
            if get_ready_orders() and self.free_capacity() > 0:
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

    # ── Re-routing around dynamic blocks (Upgrade 5) ─────────────────────────
    def _replan_if_blocked(self, frame=0):
        """If the next step in our path has become blocked, recompute the
        route from our current position to the same destination."""
        if not self.path:
            return
        if self.path[0] not in blocked_roads:
            return

        dest = self.full_path[-1] if self.full_path else self.path[-1]
        new_path = astar(self.pos, dest)
        if new_path and len(new_path) > 1:
            self.path      = new_path[1:]
            self.full_path = list(new_path)
            fleet.log(frame, f"{self.name} rerouted around block near {dest}")
        else:
            # Can't reach destination at all right now — drop path, let
            # next tick's planning logic decide (may trigger dlg/charge/etc.)
            self.path = []
            self.full_path = []
            fleet.log(frame, f"{self.name} route fully blocked, replanning")

    # ── Main tick ─────────────────────────────────────────────────────────
    def tick(self, frame):
        # React to dynamic road blocks before anything else
        self._replan_if_blocked(frame)

        if self.phase == "idle" and self.loaded:
            self.next_delivery()
            self.broadcast()
            return

        if self.phase == "idle" and self.at_wh() and get_ready_orders() and self.free_capacity() > 0:
            self.load_and_go()
            self.broadcast()
            return
        if self.phase == "loading":
            self.wh_wait -= 1
            if self.wh_wait <= 0:
                self.finish_loading()
            self.broadcast()
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
            self.broadcast()
            return

        if (self.battery <= Low_Battery
                and self.phase not in ("charging", "loading", "idle")
                and not self._going_to_charge):
            self._go_charge(frame)

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
                        order_done = None
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
                    if get_ready_orders() and self.free_capacity() > 0:
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
                    self._arrive_at_charger(frame)
                else:
                    self._going_to_charge = False
                    if not self._go_charge(frame):
                        pass

        # ── Movement (with weather + collision avoidance) ───────────────────
        speed_threshold = max(1, int(round(EV_Speed * weather.speed_mult())))
        self.move_tick += 1
        if self.move_tick >= speed_threshold and self.path:
            next_node = self.path[0]

            # Collision avoidance (Upgrade 6): wait if a higher-priority EV
            # has claimed the same next node this tick.
            if not fleet.can_move_to(self.idx, next_node, self._priority_key()):
                self.broadcast()
                return

            self.move_tick = 0
            self.pos       = self.path.pop(0)
            drain = max(1, int(round(1 * weather.drain_mult())))
            self.battery   = max(0, self.battery - drain)
            kpi.record_move(1)
            kpi.record_energy(drain)

            if self.phase == "charging" and self._near_charger():
                self._arrive_at_charger(frame)
                self.broadcast()
                return

            if self.at_wh() and self.phase == "returning" and not self.path:
                if get_ready_orders() and self.free_capacity() > 0:
                    self.load_and_go()
                else:
                    self.phase = "idle"
                    self.set_status("Idle at WH")

            if (self.phase == "delivering"
                    and self.target_rn
                    and self.pos == self.target_rn
                    and not self.path):
                if self.loaded and self.loaded[0]["house"] == self.target:
                    order = self.loaded.pop(0)
                    self.delivered += 1
                    self._record_delivery(order)
                self.set_status(f"Delivered {labels.get(self.target, '?')}")
                self._clear_target()

                if self.loaded:
                    self.sort_loaded()
                    self.next_delivery()
                else:
                    self.after_batch()

        self.broadcast()


# Module-level reference to all EVs, used by cooperative transfer logic.
# Set by main.py after construction.
_ALL_EVS = []

def register_evs(evs):
    global _ALL_EVS
    _ALL_EVS = evs