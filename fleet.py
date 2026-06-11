# fleet.py — EV-to-EV communication bus & shared fleet state (Upgrades 1, 6) ─
"""
This module is the shared "radio channel" all EVs broadcast on.

fleet_state[idx] = {
    "pos", "battery", "status", "phase", "target", "load", "next_node"
}
  - Updated every tick by each EV (broadcast()).
  - Read by other EVs to make cooperative decisions (order transfer,
    collision avoidance, nearest-EV selection).

messages: rolling log of human-readable broadcast messages for the
          Fleet Coordination Dashboard (Upgrade 14).

Collision avoidance (Upgrade 6):
  Each EV publishes its `next_node` (the cell it intends to move into this
  tick). Before moving, an EV checks whether another EV with HIGHER
  movement priority has already claimed that node. If so, it waits one
  tick. Priority order: EXPRESS delivery > SCHEDULED (due) > STANDARD >
  idle/returning. Ties broken by EV index (lower index wins).
"""

fleet_state = {}     # ev_idx -> dict snapshot
messages    = []     # list[(frame, text)]

# next_node_claims: ev_idx -> node the EV wants to move into this tick
next_node_claims = {}

PRIORITY_RANK = {
    "express": 0,
    "scheduled": 1,
    "standard": 2,
    "other": 3,
}

def broadcast(ev_idx, snapshot):
    """Each EV calls this once per tick to publish its current state."""
    fleet_state[ev_idx] = snapshot

def log(frame, text):
    messages.append((frame, text))
    if len(messages) > 40:
        del messages[:-40]

def claim_next_node(ev_idx, node, priority_key):
    next_node_claims[ev_idx] = (node, priority_key)

def clear_claim(ev_idx):
    next_node_claims.pop(ev_idx, None)

def can_move_to(ev_idx, node, priority_key):
    """Return True if no higher-priority EV has already claimed `node`."""
    my_rank = PRIORITY_RANK.get(priority_key, 3)
    for other_idx, (other_node, other_key) in next_node_claims.items():
        if other_idx == ev_idx or other_node != node:
            continue
        other_rank = PRIORITY_RANK.get(other_key, 3)
        if other_rank < my_rank:
            return False
        if other_rank == my_rank and other_idx < ev_idx:
            return False
    return True

def reset():
    fleet_state.clear()
    messages.clear()
    next_node_claims.clear()