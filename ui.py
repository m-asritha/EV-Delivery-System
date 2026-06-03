#─ ui.py — All pygame drawing / UI code, zero routing logic──────────────
import pygame
from config import *
from world  import labels
from orders import sim_time, order_queue

fonts = {}

def init_fonts():
    for key, size, bold in [
        ("xs",13,0),("sm",15,0),("md",17,1),("lg",21,1),
        ("xl",28,1),("tt",42,1),("h",12,1),("leg",16,1),
    ]:
        fonts[key] = pygame.font.SysFont("consolas", size, bold)

def txt(screen, t, x, y, key="sm", color=C_Text, surf=None):
    (surf or screen).blit(fonts[key].render(str(t), True, color), (x, y))

def txt_center(screen, t, y, key="sm", color=C_Text):
    s = fonts[key].render(str(t), True, color)
    screen.blit(s, (Width//2 - s.get_width()//2, y))

def cell_center(r, c):
    return c*Cell + Cell//2, r*Cell + Cell//2

def draw_rounded_rect(surf, color, rect, radius=6, alpha=255, border=0, border_color=None):
    if alpha < 255:
        tmp = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        pygame.draw.rect(tmp, (*color, alpha), (0,0,rect[2],rect[3]), border_radius=radius)
        surf.blit(tmp, (rect[0], rect[1]))
    else:
        pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(surf, border_color, rect, border, border_radius=radius)

def draw_batt(screen, x, y, w, h, pct, color):
    pygame.draw.rect(screen, C_Panel_BD, (x,y,w,h), border_radius=3)
    fw = max(0, int(w*pct/Max_Battery))
    if fw: pygame.draw.rect(screen, color, (x,y,fw,h), border_radius=3)
    pygame.draw.rect(screen, C_Panel_BD, (x,y,w,h), 1, border_radius=3)

def batt_col(b):
    return C_Green if b>50 else C_Yellow if b>25 else C_Red

def _blit_centered(screen, s, cx, cy):
    screen.blit(s, (cx - s.get_width()//2, cy - s.get_height()//2))

def _mode_letter(mode):
    return "E" if mode==Mode_EXPRESS else ("S" if mode==Mode_STANDARD else "T")

def _is_sched_waiting(o):
    return (o["mode"]==Mode_SCHEDULED and o["scheduled_frame"]
            and sim_time[0]*30 < o["scheduled_frame"])

# Map drawing 
def draw_roads(screen, grid):
    for axis, rng_outer, rng_inner, rect_fn in [
        (0, Rows, Cols, lambda s,e,c: (s*Cell,c*Cell,(e-s)*Cell,Cell)),
        (1, Cols, Rows, lambda s,e,c: (c*Cell,s*Cell,Cell,(e-s)*Cell)),
    ]:
        for i in range(rng_outer):
            s = None
            for j in range(rng_inner+1):
                rd = j<rng_inner and (grid[i][j] if axis==0 else grid[j][i])==1
                if rd and s is None: s=j
                elif not rd and s is not None:
                    pygame.draw.rect(screen, C_Road, rect_fn(s,j,i)); s=None

def draw_building(screen, r, c, fill, border, tcol, lbl, key="xs"):
    x,y = c*Cell+2, r*Cell+2; w,h = Cell-4, Cell-4
    pygame.draw.rect(screen, fill,   (x,y,w,h), border_radius=2)
    pygame.draw.rect(screen, border, (x,y,w,h), 1, border_radius=2)
    _blit_centered(screen, fonts[key].render(lbl, True, tcol), x+w//2, y+h//2)

def draw_pin(screen, r, c, pin_color, pulse=0.0, label=None):
    cx,cy = cell_center(r,c); hy = cy-Cell+4
    if pulse>0:
        hr = int(7+pulse*5)
        hs = pygame.Surface((hr*2+4, hr*2+4), pygame.SRCALPHA)
        pygame.draw.circle(hs, (*pin_color, int(80*pulse)), (hr+2,hr+2), hr, 2)
        screen.blit(hs, (cx-hr-2, hy-hr-2))
    pygame.draw.circle(screen, pin_color, (cx,hy), 8)
    pygame.draw.polygon(screen, pin_color, [(cx-7,hy+1),(cx+7,hy+1),(cx,cy-4)])
    pygame.draw.circle(screen, (255,255,255), (cx,hy), 3)
    if label:
        _blit_centered(screen, fonts["xs"].render(label, True, (0,0,0)), cx, hy)

def draw_node_option(screen, node, idx, hovered, mx, my):
    cx,cy = cell_center(node[0],node[1])
    pygame.draw.circle(screen, C_Hover if hovered else C_Node_Opt, (cx,cy), 10)
    pygame.draw.circle(screen, (255,255,255), (cx,cy), 10, 2)
    _blit_centered(screen, fonts["xs"].render(str(idx+1), True, (0,0,0)), cx, cy)

# Map tiles
def draw_map_tiles(screen, grid, hover_h, frame, evs=None):

    for r in range(Rows):
        for c in range(Cols):
            v = grid[r][c]
            if   v==2:
                draw_building(screen, r, c, C_Wh_F, C_Wh_B, C_Wh_B, "WH", "md")

                # 🔥 Draw EV dots if EV is docked near this warehouse
                if evs:
                    cx, cy = cell_center(r, c)

                    # find nearby EVs (distance = 1 tile → adjacent road)
                    docked = [ev for ev in evs
                            if ev.phase in ("idle", "loading")
                            and abs(ev.pos[0] - r) + abs(ev.pos[1] - c) == 1]

                    for i, ev in enumerate(docked):
                        dx = cx - 6 + i * 6
                        dy = cy + 6
                        pygame.draw.circle(screen, ev.color, (dx, dy), 3)
                        pygame.draw.circle(screen, (0, 0, 0), (dx, dy), 3, 1)
            elif v==3: draw_building(screen,r,c,C_Ch_F,C_Ch_B,C_Ch_B,"C","sm")
            elif v==4:
                ih  = (hover_h==(r,c))
                op  = next((o["mode"] for o in order_queue if o["house"]==(r,c)), None)
                brd = Mode_COLORS[op] if op is not None else C_Hover if ih else C_House_B
                draw_building(screen,r,c,(46,28,6) if ih else C_House_F,brd,brd,labels[(r,c)],"h")
                if op is not None:
                    txt(screen,_mode_letter(op),c*Cell+2,r*Cell+2,"xs",Mode_COLORS[op])

# EV paths
def draw_paths(screen, evs, path_surf):
    path_surf.fill((0,0,0,0))
    for ev in evs:
        ec = ev.color
        if ev.full_path and len(ev.full_path)>1:
            pygame.draw.lines(path_surf,(*ec,28),False,[cell_center(r,c) for r,c in ev.full_path],3)
        rem = [ev.pos]+ev.path
        if len(rem)>1:
            pygame.draw.lines(path_surf,(*ec,155),False,[cell_center(r,c) for r,c in rem],3)
    screen.blit(path_surf,(0,0))

# Order pins
def draw_order_pins(screen, evs, frame):
    pulse = 0.5+0.5*abs((frame%24)/12-1)
    for o in order_queue:
        h = o["house"]
        draw_pin(screen,h[0],h[1],Mode_COLORS[o["mode"]],0 if _is_sched_waiting(o) else pulse,_mode_letter(o["mode"]))
    for ev in evs:
        for o in ev.loaded:
            h = o["house"]
            if h != ev.target:
                draw_pin(screen,h[0],h[1],Mode_COLORS[o["mode"]],pulse*0.4)
        if ev.target:
            tm = ev.loaded[0]["mode"] if ev.loaded else Mode_STANDARD
            draw_pin(screen,ev.target[0],ev.target[1],Mode_COLORS[tm],pulse*0.7)

# EV sprites
def draw_evs(screen, evs, frame):
    for ev in evs:
        ex,ey = cell_center(ev.pos[0],ev.pos[1])
        if ev.phase=="loading":
            glow = int(28+22*abs((frame%20)/10-1))
            gs = pygame.Surface((32,32),pygame.SRCALPHA)
            pygame.draw.circle(gs,(*C_Wh_B,glow),(16,16),14)
            screen.blit(gs,(ex-16,ey-16))
        pygame.draw.circle(screen,(0,0,0),(ex+2,ey+2),10)
        pygame.draw.circle(screen,ev.color,(ex,ey),10)
        pygame.draw.circle(screen,(255,255,255),(ex,ey),10,2)
        _blit_centered(screen, fonts["xs"].render(ev.name[-1],True,(255,255,255)), ex, ey)
        bw=20; bc=batt_col(ev.battery); fw=max(0,int(bw*ev.battery/Max_Battery))
        pygame.draw.rect(screen,C_Panel_BD,(ex-bw//2,ey+12,bw,4),border_radius=2)
        if fw: pygame.draw.rect(screen,bc,(ex-bw//2,ey+12,fw,4),border_radius=2)

# Blocked-route dialog
def draw_dlg(screen, evs, mx, my):
    for ev in evs:
        if not ev.dlg or not ev.dlg_nodes: continue
        for i,node in enumerate(ev.dlg_nodes):
            draw_node_option(screen,node,i,False,mx,my)
        dw2,dh2=470,86; dx2,dy2=Width//2-dw2//2,Map//2-dh2//2
        pygame.draw.rect(screen,(14,18,32),(dx2,dy2,dw2,dh2),border_radius=8)
        pygame.draw.rect(screen,C_Orange,(dx2,dy2,dw2,dh2),1,border_radius=8)
        txt(screen,f"{labels.get(ev.dlg_house,'?')} blocked - no direct route ({ev.name})",dx2+10,dy2+10,"sm",C_Text)
        txt(screen,"Click a numbered node to deliver nearby.",dx2+10,dy2+28,"xs",C_Muted)
        skip_r=pygame.Rect(Width//2+80,Map//2+22,88,24)
        pygame.draw.rect(screen,C_Red,skip_r,border_radius=4)
        txt(screen,"Skip order",skip_r.x+8,skip_r.y+6,"xs",(255,255,255))

# Hover tooltip 
def draw_hover_tooltip(screen, hover_h, manual_mode, mx, my, show_sched_input):
    if not hover_h or my>=Map or show_sched_input: return
    hint = f"{Mode_ICONS[manual_mode]} {Mode_NAMES[manual_mode]} -> {labels.get(hover_h,'?')}"
    hs = fonts["xs"].render(hint, True, Mode_COLORS[manual_mode])
    screen.blit(hs,(min(mx+12,Width-hs.get_width()-4), max(4,my-16)))

# Scheduled input dialog 
def draw_sched_input_dialog(screen, sched_input_text, sched_input_error):
    dw,dh=420,200; dx,dy=Width//2-dw//2,Map//2-dh//2
    dim=pygame.Surface((Width,Map),pygame.SRCALPHA); dim.fill((0,0,0,150))
    screen.blit(dim,(0,0))
    pygame.draw.rect(screen,(10,14,26),(dx,dy,dw,dh),border_radius=10)
    pygame.draw.rect(screen,Mode_COLORS[Mode_SCHEDULED],(dx,dy,dw,dh),2,border_radius=10)
    txt(screen,f"{Mode_ICONS[Mode_SCHEDULED]} Schedule Your Order",dx+12,dy+12,"md",Mode_COLORS[Mode_SCHEDULED])
    txt(screen,"Enter delivery delay in seconds (1 - 200):",dx+12,dy+40,"sm",C_Text)
    txt(screen,"Orders beyond 200 seconds cannot be guaranteed.",dx+12,dy+58,"xs",C_Muted)
    ibx,iby,ibw,ibh=dx+12,dy+82,dw-24,34
    pygame.draw.rect(screen,(20,26,44),(ibx,iby,ibw,ibh),border_radius=6)
    pygame.draw.rect(screen,Mode_COLORS[Mode_SCHEDULED],(ibx,iby,ibw,ibh),2,border_radius=6)
    screen.blit(fonts["lg"].render(sched_input_text+"|",True,C_White),(ibx+8,iby+5))
    if sched_input_error:
        txt(screen,sched_input_error,dx+12,dy+122,"sm",C_Red)
    conf_r=pygame.Rect(dx+dw-110,dy+dh-40,100,30)
    canc_r=pygame.Rect(dx+10,dy+dh-40,80,30)
    draw_rounded_rect(screen,Mode_COLORS[Mode_SCHEDULED],conf_r,radius=5)
    txt(screen,"Confirm",conf_r.x+10,conf_r.y+8,"xs",(0,0,0))
    draw_rounded_rect(screen,C_Red,canc_r,radius=5,alpha=180)
    draw_rounded_rect(screen,(0,0,0),canc_r,radius=5,border=1,border_color=C_Red)
    txt(screen,"Cancel",canc_r.x+10,canc_r.y+8,"xs",C_Red)
    return conf_r, canc_r

# Bottom panel──────────
PANEL_LEFT_W  = 160
PANEL_RIGHT_W = 320
PANEL_EV_W    = (Width - PANEL_LEFT_W - PANEL_RIGHT_W) // Num_EVs

PH_COLORS = {"idle":C_Muted,"loading":C_Green,"delivering":C_Green,"returning":C_Blue,"charging":C_Yellow}
PH_LABELS = {"idle":"IDLE","loading":"LOADING","delivering":"DELIVER","returning":"RETURN","charging":"CHARGE"}

def draw_bottom_panel(screen, evs, auto_mode, manual_mode, frame, paused=False):
    PY = Map
    pygame.draw.rect(screen,C_Panel,(0,PY,Width,Panel_h))
    pygame.draw.line(screen,C_Panel_BD,(0,PY),(Width,PY),2)
    sx,sy=6,PY+5

    mc_col = C_Green if auto_mode else C_Orange
    mr2=pygame.Rect(sx,sy,138,26)
    draw_rounded_rect(screen,mc_col,mr2,radius=5,alpha=35)
    draw_rounded_rect(screen,(0,0,0),mr2,radius=5,border=2,border_color=mc_col)
    s=fonts["md"].render("AUTO" if auto_mode else "MANUAL",True,mc_col)
    screen.blit(s,(sx+(138-s.get_width())//2,sy+4))
    txt(screen,"Orders: auto" if auto_mode else "Click house",sx,sy+32,"xs",(155,168,200))
    if paused:
        pr = pygame.Rect(sx, sy + 70, 138, 20)
        pygame.draw.rect(screen, (60, 50, 0), pr, border_radius=4)
        pygame.draw.rect(screen, C_Yellow, pr, 1, border_radius=4)
        pb = fonts["xs"].render("⏸ PAUSED", True, C_Yellow)
        screen.blit(pb, (pr.x + (138 - pb.get_width()) // 2, pr.y + 4))

    q_col=C_Red if len(order_queue)>6 else C_Yellow if len(order_queue)>2 else C_Green
    qr=pygame.Rect(sx,sy+47,138,20)
    draw_rounded_rect(screen,q_col,qr,radius=4,alpha=30)
    draw_rounded_rect(screen,(0,0,0),qr,radius=4,border=1,border_color=q_col)
    txt(screen,f"QUEUE: {len(order_queue)}",sx+6,sy+51,"xs",q_col)
    sw=sum(1 for o in order_queue if _is_sched_waiting(o))
    if sw: txt(screen,f"Sched wait: {sw}",sx,sy+72,"xs",Mode_COLORS[Mode_SCHEDULED])
    txt(screen,"[R]Reset  [1/2/3]Mode",sx,sy+96,"xs",(155,168,200))
    pygame.draw.line(screen,C_Divider,(PANEL_LEFT_W,PY+5),(PANEL_LEFT_W,PY+Panel_h-5),1)

    for i,ev in enumerate(evs):
        bx=PANEL_LEFT_W+i*PANEL_EV_W+4; by=PY+4; cw=PANEL_EV_W-8; ch=Panel_h-8
        draw_rounded_rect(screen,C_Panel2,(bx,by,cw,ch),radius=5)
        draw_rounded_rect(screen,(0,0,0),(bx,by,cw,ch),radius=5,border=1,border_color=ev.color)
        pygame.draw.circle(screen,ev.color,(bx+11,by+11),6)
        screen.blit(fonts["md"].render(ev.name,True,ev.color),(bx+20,by+3))
        ph_col=PH_COLORS.get(ev.phase,C_Text)
        ph_rect=pygame.Rect(bx+cw-66,by+3,60,15)
        draw_rounded_rect(screen,ph_col,ph_rect,radius=3,alpha=35)
        draw_rounded_rect(screen,(0,0,0),ph_rect,radius=3,border=1,border_color=ph_col)
        _blit_centered(screen, fonts["xs"].render(PH_LABELS.get(ev.phase,ev.phase.upper()),True,ph_col),
                       ph_rect.x+30, ph_rect.y+7)
        bc_col=batt_col(ev.battery)
        draw_batt(screen,bx+4,by+24,cw-8,6,ev.battery,bc_col)
        txt(screen,f"{ev.battery}%",bx+4,by+32,"xs",bc_col)
        txt(screen,f"Del:{ev.delivered}",bx+4,by+46,"xs",C_Text)
        if ev.loaded:
            px2,py2=bx+4,by+62
            for o in ev.loaded[:6]:
                col=Mode_COLORS[o["mode"]]; badge_w=18
                house_label = labels.get(o["house"], "?")
                badge_w = max(18, len(house_label)*8)
                rb=pygame.Rect(px2,py2,badge_w,11)
                draw_rounded_rect(screen,col,rb,radius=2,alpha=180)
                _blit_centered(screen, fonts["xs"].render(house_label,True,(0,0,0)),
                               px2+badge_w//2, py2+5)
                px2+=badge_w+2
        txt(screen,ev.status[:26],bx+4,by+78,"xs",C_Muted)
        if i<Num_EVs-1:
            pygame.draw.line(screen,C_Divider,(PANEL_LEFT_W+(i+1)*PANEL_EV_W,PY+5),
                             (PANEL_LEFT_W+(i+1)*PANEL_EV_W,PY+Panel_h-5),1)

    rx=Width-PANEL_RIGHT_W+6; ry=PY+5
    pygame.draw.line(screen,C_Divider,(rx-6,PY+5),(rx-6,PY+Panel_h-5),1)
    pill_rects=[]
    if not auto_mode:
        txt(screen,"DELIVERY MODE",rx,ry,"xs",(180,190,215))
        pill_w,pill_h=90,22
        for idx,(mode,label) in enumerate([(Mode_EXPRESS,"EXPRESS - 1"),
                                            (Mode_STANDARD,"STANDARD - 2"),
                                            (Mode_SCHEDULED,"SCHEDULED - 3")]):
            py2=ry+16+idx*(pill_h+8); sel=(manual_mode==mode); col_c=Mode_COLORS[mode]
            r_pill=pygame.Rect(rx,py2,pill_w,pill_h)
            pygame.draw.rect(screen,col_c if sel else (col_c[0]//5,col_c[1]//5,col_c[2]//5),r_pill,border_radius=4)
            pygame.draw.rect(screen,col_c,r_pill,2 if sel else 1,border_radius=4)
            _blit_centered(screen, fonts["xs"].render(label,True,(0,0,0) if sel else col_c),
                           r_pill.centerx, r_pill.centery)
            pill_rects.append((r_pill,mode))
        txt(screen,f"Mode: {Mode_NAMES[manual_mode]}",rx,ry+16+3*(pill_h+8)+6,"xs",Mode_COLORS[manual_mode])
    else:
        txt(screen,"DELIVERY MODES",rx,ry,"xs",(180,190,215))
        for idx,(mode,name) in enumerate(Mode_NAMES.items()):
            py2=ry+13+idx*22; col=Mode_COLORS[mode]
            pygame.draw.rect(screen,col,(rx,py2,9,9),border_radius=2)
            txt(screen,f"{name} - {idx}",rx+13,py2-1,"xs",col)

    qx=Width-PANEL_RIGHT_W+120
    pygame.draw.line(screen,C_Divider,(qx-4,PY+5),(qx-4,PY+Panel_h-5),1)
    txt(screen,"QUEUED ORDERS",qx,ry,"xs",(180,190,215))
    for qi,o in enumerate(order_queue[:5]):
        qy2=ry+13+qi*22; mc=Mode_COLORS[o["mode"]]
        is_sw=_is_sched_waiting(o)
        wt=f" ~{max(0,(o['scheduled_frame']-sim_time[0]*30)//30)}s" if is_sw else ""
        pygame.draw.circle(screen,mc,(qx+5,qy2+6),4)
        txt(screen,f"{Mode_NAMES[o['mode']][:3]} {labels.get(o['house'],'?')}{wt}"[:20],
            qx+13,qy2,"xs",(100,115,145) if is_sw else mc)
    if not order_queue:
        txt(screen,"No orders queued",qx,ry+13,"xs",(100,115,145))

    back_r=pygame.Rect(sx,sy+112,138,22)
    hov=back_r.collidepoint(*pygame.mouse.get_pos())
    pygame.draw.rect(screen,(100,30,30) if hov else (50,20,20),back_r,border_radius=4)
    pygame.draw.rect(screen,C_Red,back_r,1,border_radius=4)
    lb=fonts["xs"].render("◀ Main Menu",True,(255,180,180) if hov else C_Red)
    screen.blit(lb,(back_r.x+(138-lb.get_width())//2,back_r.y+5))
    return pill_rects, back_r

def draw_sim_clock(screen, elapsed):
    ts=fonts["xs"].render(
        f"SIM {elapsed//3600:02d}:{(elapsed%3600)//60:02d}:{elapsed%60:02d}",
        True,C_Muted)
    screen.blit(ts,(Width-ts.get_width()-6,4))

# Legend & startup──────
def draw_map_legend_startup(screen, y_start):
    ex0=Width//2-500; label_col=(220,230,255); title_col=(255,255,255)
    txt(screen,"MAP ELEMENTS",ex0,y_start,"leg",title_col)
    for i,(sym,bc,fc,name) in enumerate([("WH",C_Wh_B,C_Wh_F,"Warehouse"),
                                          ("C",C_Ch_B,C_Ch_F,"Charger"),
                                          ("H#",C_House_B,C_House_F,"House")]):
        ex,ey=ex0+i*130,y_start+20
        pygame.draw.rect(screen,fc,(ex,ey,30,18),border_radius=2)
        pygame.draw.rect(screen,bc,(ex,ey,30,18),1,border_radius=2)
        _blit_centered(screen, fonts["sm"].render(sym,True,bc), ex+15, ey+9)
        txt(screen,name,ex+34,ey+2,"leg",label_col)
    ev_x=ex0+420
    txt(screen,"ELECTRIC VEHICLES",ev_x,y_start,"leg",title_col)
    for i in range(Num_EVs):
        ex,ey=ev_x+i*100,y_start+32
        pygame.draw.circle(screen,EV_Colors[i],(ex+8,ey),9)
        pygame.draw.circle(screen,(255,255,255),(ex+8,ey),9,2)
        _blit_centered(screen, fonts["xs"].render(str(i+1),True,(255,255,255)), ex+8, ey)
        txt(screen,f"EV-{i+1}",ex+22,ey-7,"leg",EV_Colors[i])
    pin_x=ex0+730
    txt(screen,"ORDER PINS (colour = mode)",pin_x,y_start,"leg",title_col)
    for i,(mode,name) in enumerate(Mode_NAMES.items()):
        px,py=pin_x+i*125,y_start+16; col=Mode_COLORS[mode]
        pygame.draw.circle(screen,col,(px+7,py+6),8)
        pygame.draw.polygon(screen,col,[(px,py+10),(px+14,py+10),(px+7,py+22)])
        pygame.draw.circle(screen,(255,255,255),(px+7,py+6),3)
        txt(screen,name,px+18,py+1,"leg",col)

def startup_screen(screen, clock):
    selected=None
    Card_W,Card_H=360,210; card_gap=80
    card_xa=Width//2-(Card_W*2+card_gap)//2
    card_xm=card_xa+Card_W+card_gap
    card_y=Height//2-Card_H//2-20
    btn_auto=pygame.Rect(card_xa,card_y,Card_W,Card_H)
    btn_manual=pygame.Rect(card_xm,card_y,Card_W,Card_H)

    CARDS = [
        (btn_auto,  C_Green,  (50,140,70),  (10,50,22),  "A","AUTO MODE",
         ["Orders spawn automatically","in random modes."]),
        (btn_manual,C_Orange, (160,80,20),  (55,28,8),   "M","MANUAL MODE",
         ["Click any house to order.","Choose Express / Standard /",
          "Scheduled (enter seconds)."]),
    ]

    while selected is None:
        clock.tick(30)
        for event in pygame.event.get():
            if event.type==pygame.QUIT: pygame.quit(); import sys; sys.exit()
            if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
                mx,my=event.pos
                if btn_auto.collidepoint(mx,my):   selected=True
                if btn_manual.collidepoint(mx,my): selected=False
        mx,my=pygame.mouse.get_pos()
        hover=("auto" if btn_auto.collidepoint(mx,my)
          else "manual" if btn_manual.collidepoint(mx,my) else None)
        screen.fill(C_Bg)
        txt_center(screen,"EV DELIVERY",100,"tt",C_Gold)
        pygame.draw.line(screen,C_Panel_BD,(Width//2-540,152),(Width//2+540,152),1)
        txt_center(screen,"SELECT SIMULATION MODE",card_y-32,"lg",(240,245,255))

        for (btn,glow_on,glow_off,cf_on,icon,label,desc_lines) in CARDS:
            key = "auto" if btn==btn_auto else "manual"
            hov = (hover==key)
            glow=glow_on if hov else glow_off
            pygame.draw.rect(screen,cf_on if hov else (18,24,38),btn,border_radius=12)
            pygame.draw.rect(screen,glow,btn,3 if hov else 2,border_radius=12)
            if hov:
                gs=pygame.Surface((btn.width,btn.height),pygame.SRCALPHA)
                pygame.draw.rect(gs,(*glow,18),(0,0,btn.width,btn.height),border_radius=12)
                screen.blit(gs,(btn.x,btn.y))
            icon_r=22; gap1=6; gap2=8; line_h=17
            label_h=fonts["lg"].get_height()
            block_top=btn.centery-(icon_r*2+gap1+label_h+gap2+len(desc_lines)*line_h)//2
            iy=block_top+icon_r
            pygame.draw.circle(screen,glow,(btn.centerx,iy),icon_r)
            _blit_centered(screen, fonts["xl"].render(icon,True,(0,0,0)), btn.centerx, iy)
            ly=block_top+(icon_r*2)+gap1
            sl=fonts["lg"].render(label,True,glow)
            screen.blit(sl,(btn.centerx-sl.get_width()//2,ly))
            dy2=ly+label_h+gap2
            for li,line in enumerate(desc_lines):
                lc=C_Gold if "EXPRESS" in line else (215,225,245)
                s3=fonts["xs"].render(line,True,lc)
                screen.blit(s3,(btn.centerx-s3.get_width()//2,dy2+li*line_h))
            if hov:
                sh=fonts["sm"].render("▶  Click to start",True,glow)
                screen.blit(sh,(btn.centerx-sh.get_width()//2,btn.bottom-26))

        leg_y=card_y+Card_H+22
        pygame.draw.line(screen,C_Panel_BD,(30,leg_y-6),(Width-30,leg_y-6),1)
        draw_map_legend_startup(screen,leg_y)
        pygame.display.flip()
    return selected