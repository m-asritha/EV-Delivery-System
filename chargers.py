# chargers.py — Charger reservation system (Upgrade 3) ──────────────────────
"""
Each charger has CHARGER_SLOTS concurrent slots and a FIFO waiting queue.

reservations: dict[charger_pos] -> list of EV indices currently occupying
              the charger (len <= CHARGER_SLOTS)
wait_queues:  dict[charger_pos] -> deque of EV indices waiting their turn

EVs call:
  - reserve(charger, ev_idx)  -> True if a slot was granted immediately,
                                  False if the EV was placed in the queue
  - release(charger, ev_idx)  -> frees the slot and promotes the next
                                  waiting EV (if any)
  - is_reserved_by_other(charger, ev_idx) -> True if charger is full and
                                  occupied by a different EV

This prevents multiple EVs from converging on the same charger
unnecessarily — an EV planning to charge first checks/reserves a slot,
and if it's busy, either queues or looks for a different charger.
"""
from collections import deque
from config import CHARGER_SLOTS

reservations = {}   # charger_pos -> list[ev_idx]
wait_queues   = {}  # charger_pos -> deque[ev_idx]

# Event log for the Fleet Coordination Dashboard (Upgrade 14)
reservation_events = []

def _ensure(charger):
    if charger not in reservations:
        reservations[charger] = []
    if charger not in wait_queues:
        wait_queues[charger] = deque()

def reserve(charger, ev_idx, frame=0):
    _ensure(charger)
    if ev_idx in reservations[charger]:
        return True
    if len(reservations[charger]) < CHARGER_SLOTS:
        reservations[charger].append(ev_idx)
        reservation_events.append((frame, "RESERVE", charger, ev_idx))
        return True
    if ev_idx not in wait_queues[charger]:
        wait_queues[charger].append(ev_idx)
        reservation_events.append((frame, "QUEUE", charger, ev_idx))
    return False

def release(charger, ev_idx, frame=0):
    _ensure(charger)
    if ev_idx in reservations[charger]:
        reservations[charger].remove(ev_idx)
        reservation_events.append((frame, "RELEASE", charger, ev_idx))
    # Promote next waiting EV
    if wait_queues[charger] and len(reservations[charger]) < CHARGER_SLOTS:
        nxt = wait_queues[charger].popleft()
        reservations[charger].append(nxt)
        reservation_events.append((frame, "PROMOTE", charger, nxt))

def cancel_wait(charger, ev_idx):
    _ensure(charger)
    if ev_idx in wait_queues[charger]:
        wq = wait_queues[charger]
        wait_queues[charger] = deque(x for x in wq if x != ev_idx)

def is_reserved_by_other(charger, ev_idx):
    _ensure(charger)
    return (len(reservations[charger]) >= CHARGER_SLOTS
            and ev_idx not in reservations[charger])

def queue_position(charger, ev_idx):
    _ensure(charger)
    wq = list(wait_queues[charger])
    return wq.index(ev_idx) + 1 if ev_idx in wq else 0

def trim_events(limit=30):
    if len(reservation_events) > limit:
        del reservation_events[:-limit]