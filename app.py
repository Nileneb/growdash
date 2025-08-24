import os, time, json, glob, pathlib, threading, asyncio, re, uuid, datetime
from typing import Optional, List, Dict, Any, Set, Tuple, Union

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, Response

import serial
import httpx

# Scheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from zoneinfo import ZoneInfo
# Robust ISO8601 parser for calendar (handles 'Z' and missing tzinfo)
def _parse_iso(s: str) -> datetime.datetime:
    s = (s or "").replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(TZ))
    return dt
# Helper: parse action (tolerant gegen alten String oder neues Objekt)
def _parse_action(a):
    if isinstance(a, dict):
        return a
    if isinstance(a, str):
        # Legacy: nur Typ als String
        return {"type": a}
    return {"type": str(a)}


# ---------- Konfig (env) ----------
SERIAL_PORT = os.getenv("SERIAL_PORT")                 # z.B. /dev/ttyACM0 (oder leer = auto)
BAUD        = int(os.getenv("BAUD", "9600"))

CAM_DEVICE   = os.getenv("CAM_DEVICE", "1")           # "0" oder "/dev/video0"
CAM_W        = int(os.getenv("CAM_W", "640"))
CAM_H        = int(os.getenv("CAM_H", "360"))
CAM_FPS      = int(os.getenv("CAM_FPS", "7"))
JPEG_Q       = int(os.getenv("JPEG_Q", "80"))

TZ          = os.getenv("TZ", "Europe/Berlin")

BASE_DIR = pathlib.Path(__file__).parent.resolve()
STATIC_DIR = BASE_DIR / "static"
DATA_DIR   = BASE_DIR / "data"; DATA_DIR.mkdir(exist_ok=True)
CAP_DIR    = BASE_DIR / "captures"; CAP_DIR.mkdir(exist_ok=True)

DEV_DB = DATA_DIR / "devices.json"
CAL_DB = DATA_DIR / "calendar.json"

# ---------- Serial ----------
class SerialMgr:
    def __init__(self, port: Optional[str], baud: int):
        self.port = port
        self.baud = baud
        self.ser: Optional[serial.Serial] = None
        self.lock = threading.Lock()
        self.log_lines: List[str] = []
        self.seq = 0
        self._stop = threading.Event()
        self.t_reader: Optional[threading.Thread] = None
        self._open()

    @staticmethod
    def candidates() -> List[str]:
        return sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))

    def _open(self):
        last = None
        ports = [self.port] if self.port else self.candidates()
        for p in ports:
            if not p: continue
            try:
                s = serial.Serial(p, self.baud, timeout=0.1)
                time.sleep(0.2)
                self.ser = s
                self.port = p
                self._start_reader()
                return
            except Exception as e:
                last = e
        raise RuntimeError(f"Serial open failed. Tried {ports}. Last: {last}")

    def _start_reader(self):
        if self.t_reader and self.t_reader.is_alive(): return
        self._stop.clear()
        self.t_reader = threading.Thread(target=self._reader_loop, daemon=True)
        self.t_reader.start()

    def _reader_loop(self):
        while not self._stop.is_set():
            try:
                if not self.ser or not self.ser.is_open:
                    time.sleep(0.2); continue
                b = self.ser.readline()
                if b:
                    line = b.decode("utf-8", errors="ignore").rstrip()
                    self.log_lines.append(line)
                    if len(self.log_lines) > 3000:
                        self.log_lines = self.log_lines[-2000:]
                    self.seq += 1
                else:
                    time.sleep(0.02)
            except Exception:
                time.sleep(0.2)

    def write(self, cmd: str):
        with self.lock:
            if not self.ser or not self.ser.is_open:
                self._open()
            self.ser.write((cmd.strip() + "\n").encode("utf-8"))
            self.ser.flush()

    def get_since(self, since_seq: int) -> Tuple[List[str], int]:
        cur = self.seq
        if cur == since_seq or not self.log_lines:
            return [], cur
        return self.log_lines[:], cur

mgr = SerialMgr(SERIAL_PORT, BAUD)

# ---------- Webcam ----------
import os, time, threading, cv2

def _find_device(explicit: Optional[str]):
    # 1) explizit
    if explicit and os.path.exists(explicit): return explicit
    # 2) übliche Kandidaten
    for d in ("/dev/video0","/dev/video1","/dev/video2","/dev/video3"):
        if os.path.exists(d): return d
    return None

class Camera:
    def __init__(self, width=800, height=450, fps=8):
        self.width  = int(os.getenv("CAM_WIDTH",  width))
        self.height = int(os.getenv("CAM_HEIGHT", height))
        self.fps    = int(os.getenv("CAM_FPS",    fps))
        self.dev    = _find_device(os.getenv("CAM_DEVICE"))
        self.cap    = None
        self.latest = None
        self._lock  = threading.Lock()
        self._id    = 0
        self._stop  = False
        self._thr   = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def _open(self):
        dev = _find_device(os.getenv("CAM_DEVICE"))
        if not dev: return False
        if self.cap: self.cap.release()
        self.dev = dev
        self.cap = cv2.VideoCapture(self.dev, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS,          self.fps)
        return self.cap.isOpened()

    def _loop(self):
        backoff = 0.5
        while not self._stop:
            if not self.cap or not self.cap.isOpened():
                if self._open():
                    backoff = 0.5
                else:
                    time.sleep(min(backoff, 5)); backoff = min(backoff*1.5, 5); continue
            ok, frame = self.cap.read()
            if not ok:
                # verloren -> neu verbinden
                self.cap.release()
                time.sleep(0.2)
                continue
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                with self._lock:
                    self.latest = buf.tobytes()
                    self._id += 1
            time.sleep(1.0/max(self.fps,1))

    def wait_new(self, last_id, timeout=2.0):
        t0 = time.time()
        while time.time()-t0 < timeout:
            with self._lock:
                if self._id != last_id and self.latest is not None:
                    return self.latest, self._id
            time.sleep(0.02)
        return None, last_id

CAM = Camera()

# ---------- WS Hub ----------
class Hub:
    def __init__(self):
        self.clients:Set[WebSocket]=set()
        self.status:Optional[Dict[str,Any]]=None
        self.tds:Optional[Dict[str,Any]]=None
        self.lock=asyncio.Lock()
    async def add(self, ws:WebSocket):
        await ws.accept()
        async with self.lock: self.clients.add(ws)
        if self.status: await ws.send_json({"type":"status","data":self.status})
        if self.tds:    await ws.send_json({"type":"tds","data":self.tds})
    async def rm(self, ws:WebSocket):
        async with self.lock: self.clients.discard(ws)
    async def bcast(self, payload:Dict[str,Any]):
        async with self.lock: clients=list(self.clients)
        dead=[]
        for ws in clients:
            try: await ws.send_json(payload)
            except: dead.append(ws)
        if dead:
            async with self.lock:
                for w in dead: self.clients.discard(w)
hub = Hub()

# ---------- Parser ----------
re_kv = re.compile(r"(\w+)=([^\s]+)")

def parse_status(lines: List[str]) -> Optional[Dict[str,Any]]:
    for ln in reversed(lines or []):
        if "dist_cm=" in ln and "liters=" in ln:
            kv=dict(re_kv.findall(ln))
            def f(x):
                if x is None: return None
                s=str(x)
                if s.lower()=="nan": return None
                try: return float(s)
                except: return s
            return {
                "dist_cm":f(kv.get("dist_cm")), "liters":f(kv.get("liters")),
                "Spray": kv.get("Spray","-"), "Tab": kv.get("Tab","-"),
                "LvlSw": kv.get("LvlSw","-"), "LvlRel": kv.get("LvlRel","-"),
                "age_ms": f(kv.get("age_ms")), "MAX_L": f(kv.get("MAX_L"))
            }
    return None

def parse_tds(lines: List[str]) -> Optional[Dict[str,Any]]:
    for ln in reversed(lines or []):
        m = re.search(r"TDS[ := ]\s*([0-9.]+).*?(TempC|Temp)[ := ]\s*([0-9.]+|NaN)", ln, re.I)
        if m:
            tds = float(m.group(1))
            tc = m.group(3)
            temp = float('nan') if str(tc).lower() == 'nan' else float(tc)
            return {"tds": tds, "temp": temp}
    return None

# ---------- Pusher ----------
async def pusher():
    last=0
    while True:
        try:
            mgr.write("Status")
            await asyncio.sleep(0.05)
            lines,cur=mgr.get_since(last)
            if cur!=last and lines:
                # Log
                for ln in lines[-50:]:
                    await hub.bcast({"type":"log","data":ln})
                # Status
                st=parse_status(lines)
                if st: hub.status=st; await hub.bcast({"type":"status","data":st})
                # TDS
                t=parse_tds(lines)
                if t: hub.tds=t; await hub.bcast({"type":"tds","data":t})
                last=cur
        except Exception:
            pass
        await asyncio.sleep(0.5)

# ---------- Scheduler (einfach: one-shot Events) ----------
scheduler = AsyncIOScheduler(timezone=ZoneInfo(TZ))
scheduler_started=False

def _load_json(p: pathlib.Path, default):
    try: return json.loads(p.read_text("utf-8"))
    except: p.write_text(json.dumps(default,indent=2),encoding="utf-8"); return default
def _save_json(p: pathlib.Path, obj):
    tmp=p.with_suffix(".tmp"); tmp.write_text(json.dumps(obj,indent=2),encoding="utf-8"); os.replace(tmp,p)

DEV = _load_json(DEV_DB, {"devices":[]})
CAL = _load_json(CAL_DB, {"events":[]})

def dev_get(did:str): return next((d for d in DEV["devices"] if d["id"]==did), None)
def dev_add(d:Dict[str,Any]): DEV["devices"].append(d); _save_json(DEV_DB,DEV); return d
def dev_del(did:str): DEV["devices"]=[x for x in DEV["devices"] if x["id"]!=did]; _save_json(DEV_DB,DEV)

async def shelly_status(c:httpx.AsyncClient, d:Dict[str,Any]) -> Dict[str,Any]:
    ip=d["ip"]; gen=int(d.get("gen",2)); ch=int(d.get("channel",0))
    auth=httpx.BasicAuth(d.get("user",""), d.get("pass","")) if (d.get("user") or d.get("pass")) else None
    if gen==2:
        r=await c.get(f"http://{ip}/rpc/Switch.Get?id={ch}",timeout=2,auth=auth); r.raise_for_status()
        j=r.json(); return {"on":bool(j.get("output", j.get("on",False)))}
    else:
        r=await c.get(f"http://{ip}/relay/{ch}",timeout=2,auth=auth); r.raise_for_status()
        j=r.json(); return {"on":bool(j.get("ison",False))}

async def shelly_cmd(c:httpx.AsyncClient, d:Dict[str,Any], cmd:str) -> Dict[str,Any]:
    ip=d["ip"]; gen=int(d.get("gen",2)); ch=int(d.get("channel",0))
    auth=httpx.BasicAuth(d.get("user",""), d.get("pass","")) if (d.get("user") or d.get("pass")) else None
    if cmd=="toggle":
        st=await shelly_status(c,d); target=not st.get("on",False)
    else:
        target=(cmd=="on")
    if gen==2:
        r=await c.get(f"http://{ip}/rpc/Switch.Set?id={ch}&on={'true' if target else 'false'}",timeout=2,auth=auth); r.raise_for_status()
        return r.json()
    else:
        r=await c.get(f"http://{ip}/relay/{ch}?turn={'on' if target else 'off'}",timeout=2,auth=auth); r.raise_for_status()
        return {"ok":True}

# Event-Executor (eine Aktion pro Event)
async def run_action(a:Union[Dict[str,Any], str]):
    a = _parse_action(a)
    t = a.get("type")
    if t == "spray":
        ms = int(a.get("ms", 800)); mgr.write(f"Spray {ms}")
    elif t == "fill":
        l = float(a.get("liters", 2.0)); mgr.write(f"FillL {l}")
    elif t == "serial":
        cmd = (a.get("cmd") or "").strip();
        if cmd: mgr.write(cmd)
    elif t == "photo":
        b, _ = CAM.wait_new(-1, 2.0)
        if b:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            p = CAP_DIR / f"cap_{ts}.jpg"; p.write_bytes(b)
            await hub.bcast({"type": "photo", "data": f"/captures/{p.name}"})
    elif t == "shelly":
        did = a.get("id"); cmd = a.get("cmd", "toggle")
        d = dev_get(did)
        if d:
            async with httpx.AsyncClient() as c:
                try: await shelly_cmd(c, d, cmd)
                except: pass
    await hub.bcast({"type": "log", "data": f"[CAL] action={t} done"})

def _schedule(ev:Dict[str,Any]):
    when=datetime.datetime.fromisoformat(ev["start"])
    trigger=DateTrigger(run_date=when)
    scheduler.add_job(lambda ev=ev: asyncio.create_task(run_action(ev["action"])),
                      trigger, id=ev["id"], replace_existing=True, misfire_grace_time=120)

def cal_add(title:str, start_iso:str, action:Dict[str,Any]) -> Dict[str,Any]:
    ev={"id":f"evt-{uuid.uuid4().hex[:10]}", "title":title, "start":start_iso, "action":action}
    CAL["events"].append(ev); _save_json(CAL_DB,CAL); _schedule(ev); return ev
def cal_upd(eid:str, patch:Dict[str,Any]) -> Dict[str,Any]:
    for e in CAL["events"]:
        if e["id"]==eid:
            e.update(patch); _save_json(CAL_DB,CAL); _schedule(e); return e
    raise KeyError("not found")
def cal_del(eid:str):
    CAL["events"]=[e for e in CAL["events"] if e["id"]!=eid]; _save_json(CAL_DB,CAL)
    try: scheduler.remove_job(eid)
    except: pass

# ---------- FastAPI ----------
app = FastAPI(title="GrowDash", version="3.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/captures", StaticFiles(directory=str(CAP_DIR)), name="captures")

@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR/"index.html"))

@app.get("/snapshot")
def snapshot():
    b,_ = CAM.wait_new(-1, 2.0)
    if b is None:
        return Response(status_code=503)
    return Response(content=b, media_type="image/jpeg",
                    headers={"Cache-Control":"no-store","Pragma":"no-cache"})

@app.get("/snapshot.jpg")
def snapshot_jpg():
    return snapshot()

@app.get("/video.mjpg")
def video_mjpg():
    boundary = b"frame"
    def gen():
        last = -1
        while True:
            b, last = CAM.wait_new(last, 2.0)
            if not b:
                continue
            yield (b"--" + boundary + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Cache-Control: no-store\r\nPragma: no-cache\r\n"
                   b"Content-Length: " + str(len(b)).encode() + b"\r\n\r\n" + b + b"\r\n")
    return StreamingResponse(
        gen(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"}
    )

# Actions
@app.post("/api/spray/on")
def api_spray_on():
    mgr.write("SprayOn")
    return {"ok": True}

@app.post("/api/spray/off")
def api_spray_off():
    mgr.write("SprayOff")
    return {"ok": True}

@app.post("/api/spray/pulse")
def api_spray_pulse(ms: int = Body(..., embed=True)):
    if ms <= 0:
        raise HTTPException(400, "ms>0")
    mgr.write(f"Spray {ms}")
    return {"ok": True}

@app.post("/api/fill")
def api_fill(liters: float = Body(..., embed=True)):
    if liters <= 0:
        raise HTTPException(400, "liters>0")
    mgr.write(f"FillL {liters}")
    return {"ok": True}

@app.post("/api/fill/cancel")
def api_fill_cancel():
    mgr.write("CancelFill")
    return {"ok": True}

# --- TDS synchron + Polling-Endpoint ---
def wait_tds(timeout=2.0):
    """Warte kurz auf eine frische TDS-Zeile, liefere dict oder {}."""
    import time
    t_end = time.time() + timeout
    # Start-Snapshot
    _, cur0 = mgr.get_since(0)
    mgr.write("TDS")
    last = cur0
    while time.time() < t_end:
        lines, cur = mgr.get_since(last)
        if cur != last and lines:
            t = parse_tds(lines)
            if t:
                return t
            last = cur
        time.sleep(0.05)
    return {}

@app.post("/api/tds")
def api_tds():
    # synchroner Rückkanal -> UI kann sofort anzeigen
    try:
        return wait_tds(timeout=2.0)
    except Exception:
        return {}

@app.get("/api/tds/last")
def api_tds_last():
    lines, _ = mgr.get_since(0)
    t = parse_tds(lines)
    return t or {}

# Devices (Shelly)
@app.get("/api/dev")
def api_dev_list():
    return DEV["devices"]
@app.post("/api/dev")
def api_dev_add(payload: Dict[str, Any]):
    name = (payload.get("name") or "").strip()
    ip = (payload.get("ip") or "").strip()
    if not name or not ip:
        raise HTTPException(400, "name/ip")
    d = {"id": f"shelly-{uuid.uuid4().hex[:8]}", "name": name, "kind": "shelly",
         "ip": ip, "gen": int(payload.get("gen", 2)), "channel": int(payload.get("channel", 0)),
         "user": payload.get("user", ""), "pass": payload.get("pass", "")}
    return dev_add(d)
@app.delete("/api/dev/{did}")
def api_dev_delete(did: str):
    dev_del(did)
    return {"ok": True}
@app.get("/api/dev/status")
async def api_dev_status_all():
    out = []
    async with httpx.AsyncClient() as c:
        for d in DEV["devices"]:
            try:
                st = await shelly_status(c, d)
            except Exception as e:
                st = {"error": str(e)}
            out.append({**d, **st})
    return out
@app.post("/api/dev/{did}/action")
async def api_dev_action(did:str, cmd:str=Body(...,embed=True)):
    if cmd not in ("on","off","toggle"): raise HTTPException(400,"cmd")
    d = dev_get(did)
    if not d:
        raise HTTPException(404, "not found")
    async with httpx.AsyncClient() as c:
        try: res=await shelly_cmd(c,d,cmd)
        except Exception as e: raise HTTPException(503,str(e))
    return {"ok":True,"result":res}

# Calendar (FullCalendar: start ISO per Event)
@app.get("/api/cal/events")
def cal_events():
    return CAL["events"]
@app.post("/api/cal/events")
def cal_events_add(title: str = Body(...), start: str = Body(...), action: Union[dict, str] = Body(...)):
    # Robust gegen 'Z' und fehlende TZ
    ev = cal_add(title, _parse_iso(start).isoformat(), _parse_action(action))
    return ev
@app.put("/api/cal/events/{eid}")
def cal_events_upd(eid: str, start: str = Body(...)):
    return cal_upd(eid, {"start": _parse_iso(start).isoformat()})
@app.delete("/api/cal/events/{eid}")
def cal_events_del(eid: str):
    cal_del(eid)
    return {"ok": True}
@app.post("/api/cal/events/{eid}/run")
async def cal_run_now(eid:str):
    e=next((x for x in CAL["events"] if x["id"]==eid),None)
    if not e: raise HTTPException(404,"not found")
    await run_action(e["action"]); return {"ok":True}

# Status
@app.get("/api/ports")
def api_ports():
    return {"candidates": SerialMgr.candidates(), "current": mgr.port}

@app.get("/api/status")
def api_status():
    lines, _ = mgr.get_since(0)
    return parse_status(lines) or {}

# WebSocket
@app.websocket("/ws")
async def ws(ws:WebSocket):
    await hub.add(ws)
    try:
        while True:
            msg=(await ws.receive_text()).strip().lower()
            if msg=="tds": mgr.write("TDS")
    except WebSocketDisconnect:
        await hub.rm(ws)

# Startup
@app.on_event("startup")
async def on_start():
    # CAM startet automatisch im Konstruktor
    asyncio.create_task(pusher())
    for e in CAL["events"]:
        try: _schedule(e)
        except: pass
    global scheduler_started
    if not scheduler_started:
        scheduler.start(); scheduler_started=True

@app.on_event("shutdown")
async def on_stop():
    CAM._stop = True
    if scheduler_started: scheduler.shutdown(wait=False)
