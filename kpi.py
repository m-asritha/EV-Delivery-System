# kpi.py — KPI analytics, end-of-sim report data, delivery heatmap ──────────
"""
Tracks fleet-wide performance metrics for the dashboard (Upgrade 11),
end-of-simulation report (Upgrade 12), and delivery heatmap (Upgrade 13).

All times are stored in frames (30 fps) and converted to seconds for display.
"""
from collections import defaultdict

class KPITracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.total_deliveries   = 0
        self.on_time_deliveries = 0
        self.late_deliveries    = 0
        self.delivery_times     = []   # frames from order placed -> delivered
        self.wait_times         = []   # frames from order placed -> EV departs WH
        self.distance_travelled = 0    # total cells moved by all EVs
        self.energy_consumed    = 0    # total battery % consumed
        self.charging_events    = 0
        self.transfer_events    = 0
        # heatmap: house -> delivery count
        self.heatmap = defaultdict(int)

    # ── Recording hooks ──────────────────────────────────────────────────
    def record_delivery(self, order, frame_now, on_time):
        self.total_deliveries += 1
        if on_time:
            self.on_time_deliveries += 1
        else:
            self.late_deliveries += 1
        placed = order.get("placed_frame", frame_now)
        self.delivery_times.append(max(0, frame_now - placed))
        self.heatmap[order["house"]] += 1

    def record_departure_wait(self, order, frame_now):
        placed = order.get("placed_frame", frame_now)
        self.wait_times.append(max(0, frame_now - placed))

    def record_move(self, steps=1):
        self.distance_travelled += steps

    def record_energy(self, amount=1):
        self.energy_consumed += amount

    def record_charge_event(self):
        self.charging_events += 1

    def record_transfer(self):
        self.transfer_events += 1

    # ── Derived stats ────────────────────────────────────────────────────
    def avg_delivery_time_sec(self):
        if not self.delivery_times: return 0.0
        return (sum(self.delivery_times) / len(self.delivery_times)) / 30.0

    def avg_wait_time_sec(self):
        if not self.wait_times: return 0.0
        return (sum(self.wait_times) / len(self.wait_times)) / 30.0

    def on_time_pct(self):
        if self.total_deliveries == 0: return 100.0
        return 100.0 * self.on_time_deliveries / self.total_deliveries

    def top_heatmap_locations(self, n=5):
        return sorted(self.heatmap.items(), key=lambda x: -x[1])[:n]


# Global singleton used by the whole sim
kpi = KPITracker()

# Late-delivery threshold (in frames) — deliveries taking longer than this
# from placement are counted as "late" for the on-time percentage.
LATE_THRESHOLD_FRAMES = 60 * 30  # 60 seconds
