# config.py — All constants and shared configuration ─────────────────────
Width, Height  = 1280, 780
Cell           = 28
Panel_h        = 140
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

# Delivery Modes
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

# Colours
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