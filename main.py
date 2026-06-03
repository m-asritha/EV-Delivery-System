"""Smart EV Delivery System Using A* with Battery Constraint"""
# ─── main.py — Game loop only ─────────────────────────────────────────────────
import pygame, random, sys

from config import *
from world  import grid, houses, wh_roads
from orders import (order_queue, sim_time, make_order, enqueue_order,
                        resort_queue, get_ready_orders, house_in_queue,
                        house_assigned, get_spatial_batch,order_sort_key)
from ev import EV, pick_best_ev_for_order, nearest_road, astar,nearest_wh_path
from ui import (init_fonts, startup_screen, draw_roads, draw_map_tiles,
                    draw_paths, draw_order_pins, draw_evs,
                    draw_dlg, draw_hover_tooltip, draw_sched_input_dialog,
                    draw_bottom_panel, draw_sim_clock, cell_center)

pygame.init()
screen = pygame.display.set_mode((Width, Height))
pygame.display.set_caption("Smart EV Delivery System")
clock = pygame.time.Clock()
init_fonts()

def _assign_nearest_evs(evs):
    ready = get_ready_orders()
    if not ready:
        return
    free_evs = [ev for ev in evs
                if ev.phase in ("idle", "returning")
                and not ev._going_to_charge
                and ev.battery > Low_Battery]
    if not free_evs:
        return
    assigned_ev_ids = set()
    claimed_orders  = set()

    # Score every (order, ev) pair by path distance
    pairs = []
    for order in ready:
        rn = nearest_road(order["house"])
        if rn is None:
            continue
        for ev in free_evs:
            p    = astar(ev.pos, rn)
            dist = len(p) if p else 9999
            pairs.append((dist, order["id"], order, ev))

    pairs.sort(key=lambda x: x[0])

    for dist, _, order, ev in pairs:
        if order["id"] in claimed_orders:
            continue
        if id(ev) in assigned_ev_ids:
            continue
        _load_ev_with_anchor(ev, order)
        assigned_ev_ids.add(id(ev))
        for o in ev.loaded:
            claimed_orders.add(o["id"])

    remaining = [o for o in order_queue if o["id"] not in claimed_orders]
    for order in remaining:
        ev = pick_best_ev_for_order(evs, order)
        if ev and id(ev) not in assigned_ev_ids:
            _load_ev_with_anchor(ev, order)
            assigned_ev_ids.add(id(ev))
            for o in ev.loaded:
                claimed_orders.add(o["id"])
                
def _load_ev_with_anchor(ev, anchor_order):
    """Load an EV starting from a specific anchor order, then batch nearby ones."""
    if anchor_order not in order_queue:
        return
    batch = get_spatial_batch(anchor_order, Batch_Size)
    for o in batch:
        if o in order_queue:
            order_queue.remove(o)
    batch.sort(key=order_sort_key)
    # Preserve orders the EV is already carrying — never discard them
    existing = [o for o in ev.loaded if o not in batch]
    ev.loaded = existing + batch
    ev.loaded.sort(key=order_sort_key)
    if ev.at_wh():
        ev.phase   = "loading"
        ev.wh_wait = WH_Wait
        ev.set_status(f"Loading {len(ev.loaded)} pkg(s)")
    else:
        ev.phase = "returning"
        ev.set_status(f"Returning (picked up {len(ev.loaded)} pkg(s))")
        if not ev.path:
            p = nearest_wh_path(ev.pos)
            if p:
                ev.path      = p[1:]
                ev.full_path = list(p)

def run_sim(auto_mode):
    evs = [EV(i) for i in range(Num_EVs)]
    order_queue.clear()

    paused = False
    timer               = 0
    frame               = 0
    hover_h             = None
    manual_mode         = Mode_STANDARD
    show_sched_input    = False
    sched_input_text    = ""
    sched_input_error   = ""
    sched_pending_house = None
    path_surf           = pygame.Surface((Width, Map), pygame.SRCALPHA)
    click_flash         = []
    back_r              = pygame.Rect(0, 0, 1, 1)

    running = True
    while running:
        if not paused:
            frame      += 1
            sim_time[0] = frame // 30
            resort_queue()
        
        clock.tick(30)

        mx, my   = pygame.mouse.get_pos()
        mr, mc_g = my // Cell, mx // Cell
        hover_h  = None
        if (not auto_mode and not show_sched_input
                and 0 <= mr < Rows and 0 <= mc_g < Cols and my < Map):
            h = (mr, mc_g)
            if (grid[mr][mc_g] == 4
                    and not house_in_queue(h)
                    and not house_assigned(h, evs)):
                hover_h = h

        # ── Events ────────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            # Scheduled dialog
            if show_sched_input:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_BACKSPACE:
                        sched_input_text = sched_input_text[:-1]
                        sched_input_error = ""
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        try:
                            val = int(sched_input_text)
                            if val <= 0:
                                sched_input_error = "Please enter a positive number!"
                            elif val > Max_SCHEDULE_SECONDS:
                                sched_input_error = f"Not possible! Max is {Max_SCHEDULE_SECONDS}s."
                            else:
                                enqueue_order(make_order(sched_pending_house, Mode_SCHEDULED,
                                                         frame + val * 30))
                                show_sched_input = False
                                sched_input_text = sched_input_error = ""
                                sched_pending_house = None
                                _assign_nearest_evs(evs)
                        except ValueError:
                            sched_input_error = "Please enter a valid number!"
                    elif event.key == pygame.K_ESCAPE:
                        show_sched_input = False
                        sched_input_text = sched_input_error = ""
                        sched_pending_house = None
                    elif event.unicode.isdigit() and len(sched_input_text) < 5:
                        sched_input_text += event.unicode
                        sched_input_error = ""
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    conf_r, canc_r = draw_sched_input_dialog(screen, sched_input_text,
                                                              sched_input_error)
                    if conf_r.collidepoint(event.pos):
                        try:
                            val = int(sched_input_text)
                            if val <= 0:
                                sched_input_error = "Please enter a positive number!"
                            elif val > Max_SCHEDULE_SECONDS:
                                sched_input_error = f"Not possible! Max is {Max_SCHEDULE_SECONDS}s."
                            else:
                                enqueue_order(make_order(sched_pending_house, Mode_SCHEDULED,
                                                         frame + val * 30))
                                show_sched_input = False
                                sched_input_text = sched_input_error = ""
                                sched_pending_house = None
                                _assign_nearest_evs(evs)
                        except ValueError:
                            sched_input_error = "Please enter a valid number!"
                    elif canc_r.collidepoint(event.pos):
                        show_sched_input = False
                        sched_input_text = sched_input_error = ""
                        sched_pending_house = None
                continue

            # Keyboard
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "menu"

                if event.key == pygame.K_r:
                    order_queue.clear()
                    for ev in evs:
                        ev.pos = wh_roads[ev.idx % len(wh_roads)]
                        ev.battery = Max_Battery
                        ev.loaded = []; ev.target = None; ev.target_rn = None
                        ev.path = []; ev.full_path = []
                        ev.dlg = False; ev.dlg_house = None; ev.dlg_nodes = []
                        ev._going_to_charge = False
                        ev.phase = "idle"; ev.set_status("Idle"); ev.delivered = 0

                if event.key == pygame.K_p:
                    paused = not paused
                if event.key == pygame.K_1:
                    manual_mode = Mode_EXPRESS
                if event.key == pygame.K_2:
                    manual_mode = Mode_STANDARD
                if event.key == pygame.K_3:
                    manual_mode = Mode_SCHEDULED

                # ── TEST-CASE SHORTCUTS ───────────────────────────────────────
                # T → drain all EVs to low battery
                if event.key == pygame.K_t:
                    for ev in evs:
                        ev.battery = Low_Battery - 1

                # S → simulate a stranded EV (drain to 0, keep orders)
                if event.key == pygame.K_s:
                    for ev in evs:
                        if ev.loaded:
                            ev.battery = 0
                            break

            # Mouse
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back_r.collidepoint(event.pos):
                    click_flash.append([event.pos[0], event.pos[1], 4, 255])
                    pygame.time.wait(80)
                    return "menu"

                if not auto_mode and not any(ev.dlg for ev in evs):
                    pill_rects, _ = draw_bottom_panel(screen, evs, auto_mode,
                                                      manual_mode, frame)
                    clicked_btn = False
                    for rect, mode in pill_rects:
                        if rect.collidepoint(event.pos):
                            manual_mode = mode
                            clicked_btn = True
                            click_flash.append([event.pos[0], event.pos[1], 4, 255])
                            break
                    if clicked_btn:
                        continue

                    if hover_h:
                        click_flash.append([event.pos[0], event.pos[1], 4, 255])
                        if manual_mode == Mode_SCHEDULED:
                            show_sched_input = True
                            sched_pending_house = hover_h
                            sched_input_text = sched_input_error = ""
                        else:
                            order = make_order(hover_h, manual_mode)
                            enqueue_order(order)
                            if manual_mode == Mode_EXPRESS:
                                for ev in evs:
                                    if ev.loaded and ev.phase == "delivering":
                                        ev.check_express_reroute()
                            _assign_nearest_evs(evs)

                # Blocked-route dialog
                for ev in evs:
                    if not ev.dlg or not ev.dlg_nodes:
                        continue
                    chosen = None
                    for i, node in enumerate(ev.dlg_nodes):
                        ncx, ncy = cell_center(node[0], node[1])
                        if (mx - ncx) ** 2 + (my - ncy) ** 2 <= 11 ** 2:
                            chosen = node
                            break
                    if chosen:
                        from world import astar
                        h = ev.dlg_house
                        p = astar(ev.pos, chosen)
                        if p:
                            ev.target = h; ev.target_rn = chosen
                            ev.path = p[1:]; ev.full_path = list(p)
                            ev.phase = "delivering"
                        else:
                            ev.loaded = [o for o in ev.loaded if o["house"] != h]
                            ev.next_delivery()
                        ev.dlg = False; ev.dlg_house = None
                        ev.dlg_nodes = []; ev._dlg_start_frame = 0
                        continue
                    skip_r = pygame.Rect(Width // 2 + 80, Map // 2 + 22, 88, 24)
                    if skip_r.collidepoint(event.pos):
                        h = ev.dlg_house
                        ev.loaded = [o for o in ev.loaded if o["house"] != h]
                        ev.dlg = False; ev.dlg_house = None
                        ev.dlg_nodes = []; ev._dlg_start_frame = 0
                        ev.next_delivery()

        if not paused:
            # ── Auto spawning ──────────────────────────────────────────────────────
            timer += 1
            if auto_mode and timer > Order_Interval and houses:
                timer = 0
                busy = set()
                for ev in evs:
                    if ev.target:
                        busy.add(ev.target)
                    for o in ev.loaded:
                        busy.add(o["house"])
                    if ev.dlg and ev.dlg_house:
                        busy.add(ev.dlg_house)
                for o in order_queue:
                    busy.add(o["house"])
                cands = [h for h in houses if h not in busy]
                if cands:
                    count   = random.randint(2, min(3, len(cands)))
                    batch_h = random.sample(cands, count)
                    any_express = False
                    for bh in batch_h:
                        o = make_order(bh)
                        enqueue_order(o)
                        if o["mode"] == Mode_EXPRESS:
                            any_express = True
                    if any_express:
                        for ev in evs:
                            if ev.loaded and ev.phase == "delivering":
                                ev.check_express_reroute()
                    _assign_nearest_evs(evs)

            # ── EV ticks ──────────────────────────────────────────────────────────
            for ev in evs:
                ev.tick(frame)

        # ── Draw ──────────────────────────────────────────────────────────────
        screen.fill(C_Bg)
        draw_roads(screen, grid)
        draw_map_tiles(screen, grid, hover_h, frame, evs)
        draw_paths(screen, evs, path_surf)
        draw_order_pins(screen, evs, frame)
        draw_evs(screen, evs, frame)
        draw_dlg(screen, evs, mx, my)

        if not auto_mode:
            draw_hover_tooltip(screen, hover_h, manual_mode, mx, my, show_sched_input)
        if show_sched_input:
            draw_sched_input_dialog(screen, sched_input_text, sched_input_error)

        pill_rects, back_r = draw_bottom_panel(screen, evs, auto_mode, manual_mode, frame, paused)
        draw_sim_clock(screen, sim_time[0])

        pygame.display.flip()
    return "menu"

while True:
    auto_mode = startup_screen(screen, clock)
    result    = run_sim(auto_mode)
    if result == "quit":
        break

pygame.quit()
sys.exit()