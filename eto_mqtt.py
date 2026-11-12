# -*- coding: utf-8 -*-
"""
eto_mqtt.py
รับข้อมูลดิบจากสถานีทาง MQTT (Temp, Humid, Pressure, WindSpeed)
-> เก็บสะสม -> คำนวณ ETo (FAO-56 Penman-Monteith ด้วยวิธี Hargreaves)
-> ส่งค่า ETo รายวันซ้ำทุก 1 นาที และส่งค่าทดสอบไปที่ .../ETo/test
"""
import csv
import json
import math
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

import paho.mqtt.client as mqtt

# =========================================================
# 1) ตั้งค่าการเชื่อมต่อ
# =========================================================
BROKER_HOST = "i51611e5.ala.asia-southeast1.emqxsl.com"
BROKER_PORT = 8883
MQTT_USER   = "eto_app"
MQTT_PASS   = "smilekhonkaen"
CLIENT_ID   = "eto-calculator-01"

SUB_TOPIC = "KU/+"                
OUT_TOPIC = "KU/{station}/ETo"    

LATITUDE        = 15.870083
LONGITUDE       = 102.908028
ELEVATION_M     = 192
SENSOR_HEIGHT_M = 2.0      # ความสูงเซนเซอร์ลม

# Rs จาก Hargreaves: Rs = KRS * sqrt(Tmax - Tmin) * Ra  (ไม่เกิน Rso)
KRS            = 0.16      # 0.16 พื้นที่ในแผ่นดิน / 0.19 ชายฝั่งทะเล
RS_UNCERTAINTY = 0.15      # ความคลาดเคลื่อน Rs (±15 %)

VAR_MAP = {"Temp": "temp", "Humid": "rh", "Pressure": "pres", "WindSpeed": "wind", "WS": "wind"}
SCALE   = {"temp": 0.1, "rh": 0.1, "pres": 0.1, "wind": 0.1}
REQUIRED  = ["temp", "rh", "pres", "wind"]
TIME_KEYS = ["Time", "time", "Timestamp", "timestamp", "ts"]

DAY_START_HOUR    = 7
MIN_HOURS_COVERED = 20
U2_MIN            = 0.5

PUBLISH_INTERVAL_SEC = 60    # ส่งค่า ETo รายวันล่าสุดซ้ำทุก 60 วินาที
TEST_MODE         = True     # True = ส่งค่าทดสอบระหว่างวันไปที่ .../ETo/test ด้วย
TEST_INTERVAL_MIN = 1        # ส่งค่าทดสอบทุก 1 นาที
SHOW_DETAIL       = True     # พิมพ์ค่ากลางและบันทึกลง eto_detail_<station>.csv

TZ          = timezone(timedelta(hours=7))
DATA_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STATE_FILE  = os.path.join(DATA_DIR, "state.json")
LATEST_FILE = os.path.join(DATA_DIR, "latest_eto.json")

# =========================================================
# 2) ฟังก์ชันแปลงข้อความ
# =========================================================
FIELDS = ["time", "temp", "rh", "pres", "wind"]
LOOKUP = {k.lower(): v for k, v in VAR_MAP.items()}
PATTERN = re.compile(
    r"(" + "|".join(sorted((re.escape(k) for k in VAR_MAP), key=len, reverse=True))
    + r")[\"'\s:=]*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
file_lock = threading.Lock()


def parse_time(val):
    try:
        if isinstance(val, (int, float)):
            t = datetime.fromtimestamp(val / 1000 if val > 1e11 else val, TZ)
        else:
            s = str(val).replace("\u3164", " ").encode("ascii", "ignore").decode("ascii").strip()
            t = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=TZ)
        return t.astimezone(TZ)
    except (ValueError, OverflowError, OSError):
        return None


def parse_payload(text):
    values, msg_time = {}, None
    try:
        data = json.loads(text)
    except ValueError:
        data = None

    if isinstance(data, dict):
        for key, val in data.items():
            name = LOOKUP.get(str(key).lower())
            if name:
                try:
                    values[name] = float(val) * SCALE[name]
                except (TypeError, ValueError):
                    raise ValueError(f"ค่า {key} อ่านไม่ได้: {val}")
            elif key in TIME_KEYS:
                msg_time = parse_time(val)
    else:
        for key, num in PATTERN.findall(text):
            name = LOOKUP[key.lower()]
            values[name] = float(num) * SCALE[name]

    missing = [k for k in REQUIRED if k not in values]
    if missing:
        raise ValueError(f"ข้อมูลไม่ครบ ขาด {missing}")
    return values, msg_time

# =========================================================
# 3) จัดการไฟล์ข้อมูลสะสม
# =========================================================
def load_json(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def raw_file(station):
    return os.path.join(DATA_DIR, f"raw_{station}.csv")


def save_record(station, rec):
    path = raw_file(station)
    with file_lock:
        new = not os.path.exists(path)
        fields = FIELDS
        if not new:
            with open(path, encoding="utf-8") as f:
                fields = f.readline().strip().split(",")
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, restval="", extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(rec)


def load_window(station, start, end):
    rows, path = [], raw_file(station)
    if not os.path.exists(path):
        return rows
    with file_lock, open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = datetime.fromisoformat(r["time"])
            if start <= t < end:
                rows.append({"time": t, **{k: float(r[k]) for k in FIELDS[1:]}})
    return rows


def known_stations():
    return [f[4:-4] for f in os.listdir(DATA_DIR)
            if f.startswith("raw_") and f.endswith(".csv")]


def save_daily(station, result):
    path = os.path.join(DATA_DIR, f"eto_daily_{station}.csv")
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            header = f.readline().strip().split(",")
        if header != list(result.keys()):
            os.replace(path, path.replace(".csv", f"_old_{datetime.now(TZ):%Y%m%d%H%M%S}.csv"))
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(result.keys()))
        if new:
            w.writeheader()
        w.writerow(result)


def save_detail(station, detail):
    path = os.path.join(DATA_DIR, f"eto_detail_{station}.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(detail.keys()))
        if new:
            w.writeheader()
        w.writerow(detail)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

# =========================================================
# 4) สมการคำนวณ FAO-56
# =========================================================
def svp(t):
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def slope_svp(t):
    return 4098 * svp(t) / (t + 237.3) ** 2


def wind_to_2m(uz, z):
    return uz * 4.87 / math.log(67.8 * z - 5.42)


def ra_mj(lat_deg, doy):
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    dec = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(dec))))
    return (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(dec)
        + math.cos(phi) * math.cos(dec) * math.sin(ws))


def window_of(day):
    start = datetime(day.year, day.month, day.day, DAY_START_HOUR, tzinfo=TZ)
    return start, start + timedelta(days=1)


def hourly_mean(rows, key, fn=lambda v: v):
    bins = {}
    for r in rows:
        bins.setdefault(r["time"].strftime("%Y-%m-%d %H"), []).append(fn(r[key]))
    return sum(sum(v) / len(v) for v in bins.values()) / len(bins)


def compute_eto(station, rows, day, start, end, partial=False):
    n = len(rows)
    temps = [r["temp"] for r in rows]
    t_max, t_min = max(temps), min(temps)
    t_mean = hourly_mean(rows, "temp")
    rh = min(hourly_mean(rows, "rh"), 100.0)
    wind = hourly_mean(rows, "wind", lambda v: max(v, 0.0))
    pres = hourly_mean(rows, "pres")
    hours = len({r["time"].strftime("%Y-%m-%d %H") for r in rows})
    flags = []

    es = (svp(t_max) + svp(t_min)) / 2
    ea = rh / 100.0 * es
    delta = slope_svp(t_mean)
    gamma = 0.000665 * (pres / 10.0)
    u2 = wind_to_2m(wind, SENSOR_HEIGHT_M)
    if u2 < U2_MIN:
        u2 = U2_MIN
        flags.append("U2_MIN_APPLIED")

    doy = day.timetuple().tm_yday
    ra = ra_mj(LATITUDE, doy)
    rso = (0.75 + 2e-5 * ELEVATION_M) * ra

    rs_hg = KRS * math.sqrt(max(t_max - t_min, 0.0)) * ra
    rs = rs_hg
    if rs > rso:
        rs = rso
        flags.append("RS_CAPPED")

    def eto_from_rs(rs_):
        rns_ = 0.77 * rs_
        ratio = min(rs_ / rso, 1.0) if rso > 0 else 1.0
        rnl_ = (4.903e-9 * (((t_max + 273.16) ** 4 + (t_min + 273.16) ** 4) / 2)
                * (0.34 - 0.14 * math.sqrt(ea)) * (1.35 * ratio - 0.35))
        rn_ = rns_ - rnl_
        eto_ = ((0.408 * delta * rn_
                 + gamma * (900 / (t_mean + 273)) * u2 * (es - ea))
                / (delta + gamma * (1 + 0.34 * u2)))
        return max(eto_, 0.0), rns_, rnl_, rn_

    eto, rns, rnl, rn = eto_from_rs(rs)
    eto_low = eto_from_rs(rs * (1 - RS_UNCERTAINTY))[0]
    eto_high = eto_from_rs(min(rs * (1 + RS_UNCERTAINTY), rso))[0]

    if hours < MIN_HOURS_COVERED:
        flags.insert(0, "INCOMPLETE")
    if t_max - t_min <= 0:
        flags.append("NO_TEMP_RANGE")
    if partial:
        flags.insert(0, "PARTIAL_DAY")

    if SHOW_DETAIL and not partial:
        detail = {
            "station_id": station, "day": day.isoformat(), "doy": doy,
            "t_max": round(t_max, 2), "t_min": round(t_min, 2), "t_mean": round(t_mean, 2),
            "rh": round(rh, 2), "pres_hpa": round(pres, 2), "wind": round(wind, 3),
            "u2": round(u2, 3), "es": round(es, 4), "ea": round(ea, 4), "vpd": round(es - ea, 4),
            "delta": round(delta, 4), "gamma": round(gamma, 5), "ra": round(ra, 3),
            "rso": round(rso, 3), "rs": round(rs, 3), "rns": round(rns, 3),
            "rnl": round(rnl, 3), "rn": round(rn, 3), "eto": round(eto, 2),
            "eto_low": round(eto_low, 2), "eto_high": round(eto_high, 2),
        }
        save_detail(station, detail)

    return {
        "station_id": station,
        "date": (start + timedelta(days=1)).isoformat(),
        "eto_mm_day": round(eto, 2),
        "eto_low": round(eto_low, 1),
        "eto_high": round(eto_high, 1),
        "eto_text": (f"ETo ≈ {eto:.1f} mm/วัน  (ช่วงที่เป็นไปได้ "
                     f"{eto_low:.1f}–{eto_high:.1f} mm/วัน)"),
        "rs_method": "hargreaves",
        "flag": "|".join(flags) if flags else "OK",
        "n_records": n,
        "hours_covered": hours,
        "t_max_c": round(t_max, 2),
        "t_min_c": round(t_min, 2),
        "t_mean_c": round(t_mean, 2),
        "rh_mean_pct": round(rh, 2),
        "wind_mean_ms": round(wind, 2),
        "computed_at": datetime.now(TZ).isoformat(timespec="seconds"),
    }

# =========================================================
# 5) การจัดการ MQTT และรอบเวลา
# =========================================================
def publish_result(client, station, result, test=False):
    topic = OUT_TOPIC.format(station=station) + ("/test" if test else "")
    client.publish(topic, json.dumps(result, ensure_ascii=False),
                   qos=1, retain=not test)
    print(f"[ส่ง{'ทดสอบ' if test else ''}] {topic} -> {result['eto_text']} "
          f"({result['flag']}, {result['n_records']} รายการ)")


def daily_job(client, state, latest):
    now = datetime.now(TZ)
    finished = (now - timedelta(hours=DAY_START_HOUR)).date() - timedelta(days=1)
    updated = False
    for st in known_stations():
        if st not in state:
            state[st] = finished.isoformat()
            save_state(state)
            continue
        last = date.fromisoformat(state[st])
        while last < finished:
            last += timedelta(days=1)
            start, end = window_of(last)
            rows = load_window(st, start, end)
            if rows:
                result = compute_eto(st, rows, last, start, end)
                save_daily(st, result)
                latest[st] = result
                save_json(LATEST_FILE, latest)
                updated = True
                publish_result(client, st, result, test=False)
            state[st] = last.isoformat()
            save_state(state)
    return updated


def publish_latest(client, latest):
    if not latest or not client.is_connected():
        return False
    stamp = datetime.now(TZ).isoformat(timespec="seconds")
    for st, result in latest.items():
        topic = OUT_TOPIC.format(station=st)
        payload = dict(result, published_at=stamp)
        client.publish(topic, json.dumps(payload, ensure_ascii=False),
                       qos=1, retain=True)
        print(f"[ส่งซ้ำ] {stamp[11:19]} {topic} -> ETo = {result['eto_mm_day']} mm/วัน")
    return True


def test_job(client):
    now = datetime.now(TZ)
    day = (now - timedelta(hours=DAY_START_HOUR)).date()
    start, end = window_of(day)
    for st in known_stations():
        rows = load_window(st, start, now + timedelta(seconds=1))
        if rows:
            result = compute_eto(st, rows, day, start, end, partial=True)
            publish_result(client, st, result, test=True)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"[!] เชื่อมต่อไม่สำเร็จ: {reason_code}")
        return
    print("[OK] เชื่อมต่อ EMQX สำเร็จ")
    client.subscribe(SUB_TOPIC, qos=1)
    print(f"[*] รอรับข้อมูลที่ Topic: {SUB_TOPIC}")


def on_disconnect(client, userdata, flags, reason_code, properties):
    print(f"[!] หลุดการเชื่อมต่อ ({reason_code}) กำลังเชื่อมต่อใหม่...")


def on_message(client, userdata, msg):
    if "/ETo" in msg.topic:
        return
    station = msg.topic.split("/")[-1]
    text = msg.payload.decode("utf-8", errors="ignore")
    try:
        v, msg_time = parse_payload(text)
    except ValueError as e:
        print(f"[!] ข้าม {msg.topic}: {e}")
        return
    t = msg_time or datetime.now(TZ)
    rec = {"time": t.isoformat(timespec="seconds"),
           **{k: round(v[k], 3) for k in FIELDS[1:]}}
    save_record(station, rec)
    print(f"[รับ] {t:%H:%M:%S} {station}: Temp={rec['temp']} C "
          f"Humid={rec['rh']} % Pres={rec['pres']} hPa Wind={rec['wind']} m/s")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set()
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    print(f"[*] กำลังเชื่อมต่อ {BROKER_HOST}:{BROKER_PORT} ...")
    client.connect_async(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()

    state, latest = load_state(), load_json(LATEST_FILE)
    if latest:
        print(f"[*] โหลดค่า ETo ล่าสุดได้ {len(latest)} สถานี "
              f"จะส่งซ้ำทุก {PUBLISH_INTERVAL_SEC} วินาที")
    else:
        print("[*] ยังไม่มีค่า ETo รายวัน จะเริ่มส่งหลังข้อมูลครบรอบ 07:00-07:00 น.")

    last_daily = last_pub = last_test = 0.0
    try:
        while True:
            now = time.time()
            if now - last_daily >= 30:
                if daily_job(client, state, latest):
                    last_pub = 0.0
                last_daily = now
            if now - last_pub >= PUBLISH_INTERVAL_SEC and publish_latest(client, latest):
                last_pub = now
            if TEST_MODE and client.is_connected() and \
                    now - last_test >= TEST_INTERVAL_MIN * 60:
                test_job(client)
                last_test = now
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] หยุดโปรแกรม")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()