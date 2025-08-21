# Azure Function (Python) - HTTP trigger
import logging, re
from datetime import datetime, timezone
import azure.functions as func
import xml.etree.ElementTree as ET

def parse_utcdatetime(s: str):
    if s is None: return None
    m = re.search(r"\{utcdatetime:U([0-9\-:T\.]+)\}", s)
    if not m:
        return datetime.fromisoformat(s.replace("Z","")).replace(tzinfo=timezone.utc)
    iso = m.group(1)
    if iso.endswith(".000"): iso = iso[:-4]
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)

def dt_to_ics(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")

def ics_escape(s: str) -> str:
    if not s: return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,")
    return s.replace("\r\n", "\\n").replace("\n", "\\n")

def build_rrule(el):
    if el is None: return None
    rtype = (el.attrib.get("type") or "").capitalize()
    if rtype != "Weekly": return None
    interval = el.attrib.get("repeat_every", "1")
    until_raw = el.attrib.get("until_date") or el.attrib.get("unitil_date")
    rep = el.attrib.get("repeat_on")
    byday = None
    if rep and len(rep) == 7:
        map_dow = ["SU","MO","TU","WE","TH","FR","SA"]
        byday = ",".join(map_dow[i] for i,c in enumerate(rep) if c=="1") or None
    parts = [f"FREQ=WEEKLY", f"INTERVAL={interval}"]
    if until_raw:
        u_dt = parse_utcdatetime(until_raw)
        parts.append(f"UNTIL={u_dt.strftime('%Y%m%dT%H%M%SZ')}")
    if byday: parts.append(f"BYDAY={byday}")
    return ";".join(parts)

def convert(xml_text: str) -> str:
    root = ET.fromstring(xml_text)
    lines = ["BEGIN:VCALENDAR","PRODID:-//mxl-to-ics//saskpolytech//EN","VERSION:2.0",
             "CALSCALE:GREGORIAN","METHOD:PUBLISH"]
    now = dt_to_ics(datetime.now(timezone.utc))
    for ev in root.findall("event"):
        title = (ev.findtext("title") or "").strip()
        desc = ev.findtext("description") or ""
        start_raw = ev.findtext("start_date")
        end_raw = ev.findtext("end_date")
        loc = (ev.findtext("location") or "").strip()
        recur = ev.find("recurrence")
        all_day = (ev.attrib.get("is_allday_event","False").lower()=="true")
        sdt = parse_utcdatetime(start_raw) if start_raw else None
        edt = parse_utcdatetime(end_raw) if end_raw else None

        lines.append("BEGIN:VEVENT")
        if sdt:
            lines.append(f"DTSTART;VALUE=DATE:{sdt.strftime('%Y%m%d')}" if all_day else f"DTSTART:{dt_to_ics(sdt)}")
        if edt:
            lines.append(f"DTEND;VALUE=DATE:{edt.strftime('%Y%m%d')}" if all_day else f"DTEND:{dt_to_ics(edt)}")
        uid = f"{ev.attrib.get('id','x')}-{dt_to_ics(sdt or datetime.now(timezone.utc))}@mxl2ics"
        lines.append(f"UID:{uid}")
        lines.append(f"SUMMARY:{ics_escape(title)}")
        if desc: lines.append(f"DESCRIPTION:{ics_escape(desc)}")
        if loc: lines.append(f"LOCATION:{ics_escape(loc)}")
        rrule = build_rrule(recur)
        if rrule: lines.append(f"RRULE:{rrule}")
        lines.append(f"DTSTAMP:{now}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        xml_text = req.get_body().decode("utf-8", errors="ignore")
        ics = convert(xml_text)
        return func.HttpResponse(ics, status_code=200, mimetype="text/calendar")
    except Exception as e:
        logging.exception("Conversion failed")
        return func.HttpResponse(f"Error: {e}", status_code=400)
