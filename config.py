# config.py — All constants and shared configuration ─────────────────────
Width, Height  = 1280, 820
Cell           = 28
Panel_h        = 180
Map            = Height - Panel_h
Rows           = Map // Cell
Cols           = Width  // Cell

Max_Battery    = 100
Low_Battery    = 25
Order_Interval = 180
EV_Speed       = 8
WH_Wait        = 22
Batch_Size     = 5
Num_EVs        = 3

Max_SCHEDULE_SECONDS = 200

# ─── Delivery Modes ─────────────────────────────────────────────────────────
Mode_EXPRESS   = 0
Mode_STANDARD  = 1
Mode_SCHEDULED = 2

Mode_NAMES  = {Mode_EXPRESS: "EXPRESS", Mode_STANDARD: "STANDARD", Mode_SCHEDULED: "SCHEDULED"}
Mode_ICONS  = {Mode_EXPRESS: "⚡",      Mode_STANDARD: "📦",        Mode_SCHEDULED: "🕐"}
Mode_COLORS = {
    Mode_EXPRESS:  (255, 90,  60),  # RED
    Mode_STANDARD: (70,  200, 110), # GREEN
    Mode_SCHEDULED:(90,  170, 255), # BLUE
}
Mode_DESCS  = {
    Mode_EXPRESS:  "Fastest — instant priority, reroutes EVs",
    Mode_STANDARD: "Regular queue, free delivery",
    Mode_SCHEDULED:"Enter seconds (max 200) for scheduled slot",
}
Mode_WEIGHTS = [Mode_EXPRESS]*5 + [Mode_STANDARD]*9 + [Mode_SCHEDULED]*1

EV_Colors = [(255, 90,  90), (60, 210, 200), (180, 120, 255)]
EV_Names  = ["EV-1", "EV-2", "EV-3"]

# ─── EV capacity (Upgrade 8) ────────────────────────────────────────────────
# Each order carries a "weight" (1-5 kg-ish units). Each EV has a max payload.
EV_Max_Payload = 12          # total weight an EV can carry at once
Order_Min_Weight = 1
Order_Max_Weight = 5

# ─── Traffic-aware routing (Upgrade 4) ──────────────────────────────────────
# Road "congestion levels" map to movement cost multipliers used by A*.
TRAFFIC_GREEN  = 0
TRAFFIC_YELLOW = 1
TRAFFIC_RED    = 2
TRAFFIC_COST   = {TRAFFIC_GREEN: 1, TRAFFIC_YELLOW: 3, TRAFFIC_RED: 5}
TRAFFIC_COLORS = {
    TRAFFIC_GREEN:  (60, 200, 100),
    TRAFFIC_YELLOW: (230, 200, 40),
    TRAFFIC_RED:    (220, 70, 70),
}
# How often (in frames) traffic levels are randomly re-rolled per road cell
TRAFFIC_UPDATE_INTERVAL = 240   # ~8 sec at 30fps
TRAFFIC_WEIGHTS = [TRAFFIC_GREEN]*6 + [TRAFFIC_YELLOW]*3 + [TRAFFIC_RED]*1

# ─── Dynamic road blocks (Upgrade 5) ────────────────────────────────────────
ROAD_BLOCK_INTERVAL   = 420   # avg frames between new blocks (~14s)
ROAD_BLOCK_DURATION   = 300   # how long a block lasts (~10s)
ROAD_BLOCK_MAX_ACTIVE = 3

# ─── Charger reservation (Upgrade 3) ────────────────────────────────────────
CHARGER_SLOTS = 1   # how many EVs a charger can serve simultaneously

# ─── Weather system (Upgrade 10) ────────────────────────────────────────────
WEATHER_SUNNY = 0
WEATHER_RAINY = 1
WEATHER_STORM = 2
WEATHER_NAMES = {WEATHER_SUNNY: "SUNNY", WEATHER_RAINY: "RAINY", WEATHER_STORM: "STORM"}
WEATHER_ICONS = {WEATHER_SUNNY: "☀", WEATHER_RAINY: "🌧", WEATHER_STORM: "⛈"}
# Multipliers applied to EV speed (higher = slower → fewer cells per tick handled
# by scaling move_tick threshold) and battery drain per step.
WEATHER_SPEED_MULT  = {WEATHER_SUNNY: 1.0, WEATHER_RAINY: 1.3, WEATHER_STORM: 1.8}
WEATHER_DRAIN_MULT  = {WEATHER_SUNNY: 1.0, WEATHER_RAINY: 1.25, WEATHER_STORM: 1.6}
WEATHER_CHANGE_INTERVAL = 1800   # ~60s — how often weather can change
WEATHER_COLORS = {
    WEATHER_SUNNY: (255, 215, 90),
    WEATHER_RAINY: (110, 160, 230),
    WEATHER_STORM: (180, 120, 255),
}

# ─── Colours ─────────────────────────────────────────────────────────────────
C_Bg       = (12,  15,  24)
C_Road     = (50,  60,  85)
C_House_F  = (45,  28,   6);  C_House_B = (210, 130,  45)
C_Wh_F     = ( 8,  40,  20);  C_Wh_B    = ( 55, 200, 100)
C_Ch_F     = ( 8,  22,  55);  C_Ch_B    = ( 80, 155, 255)
C_Panel    = (16,  20,  34);  C_Panel_BD= ( 35,  45,  70)
C_Panel2   = (20,  26,  42)
C_Muted    = (120, 130, 158)
C_Text     = (255, 255, 255)
C_Green    = ( 70, 210, 120)
C_Yellow   = (255, 200,  50)
C_Blue     = ( 80, 160, 255)
C_Orange   = (255, 140,  50)
C_Red      = (230,  60,  60)
C_Gold     = (255, 215,  60)
C_Hover    = (255, 220,  90)
C_Node_Opt = ( 80, 210, 255)
C_Divider  = ( 24,  30,  50)
C_White    = (255, 255, 255)