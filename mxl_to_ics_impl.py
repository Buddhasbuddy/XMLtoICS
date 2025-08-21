def parse_utcdatetime(s: str) -> datetime:
    """
    Input looks like: {utcdatetime:U2022-07-14T19:00:00.000}
    Return aware datetime in UTC.
    """
    if s is None:
        return None
    m = re.search(r"\{utcdatetime:U([0-9\-:T\.]+)\}", s)
    if not m:
        # Try plain ISO
        try:
            dt = datetime.fromisoformat(s.replace("Z","")).replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            raise ValueError(f"Unrecognized datetime format: {s}")
    iso = m.group(1)
    # Trim milliseconds if present
    if iso.endswith(".000"):
        iso = iso[:-4]
    dt = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
    return dt

def ics_escape(s: str) -> str:
    """Escape text per RFC 5545."""
    if s is None:
        return ""
    s = re.sub(r"<[^>]+>", "", s)  # strip HTML tags if present
    s = s.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,")
    # Normalize newlines
    s = s.replace("\r\n", "\\n").replace("\n", "\\n")
    return s

def fold_ics_line(line: str) -> str:
    """
    Fold a single ICS line at 75 octets (approx with len) with CRLF and a space on continuation.
    For simplicity, we fold based on character count which is OK for ASCII content used here.
    """
    max_len = 75
    if len(line) <= max_len:
        return line
    parts = []
    while len(line) > max_len:
        parts.append(line[:max_len])
        line = " " + line[max_len:]
    parts.append(line)
    return "\r\n".join(parts)

def build_rrule(recur_el: ET.Element) -> str | None:
    if recur_el is None:
        return None
    rtype = recur_el.attrib.get("type")
    if rtype is None:
        return None
    rtype = rtype.capitalize()
    if rtype != "Weekly":
        # Only Weekly is present in sample; extend easily if needed.
        return None
    interval = recur_el.attrib.get("repeat_every", "1")
    until_raw = recur_el.attrib.get("until_date") or recur_el.attrib.get("unitil_date")
    byday = None
    repeat_on = recur_el.attrib.get("repeat_on")  # e.g., "0010010"
    # Map indices 0..6 to BYDAY (Sun..Sat)
    dow_map = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"]
    if repeat_on and len(repeat_on) == 7:
        days = [dow_map[i] for i, ch in enumerate(repeat_on) if ch == "1"]
        if days:
            byday = ",".join(days)
    parts = [f"FREQ=WEEKLY", f"INTERVAL={interval}"]
    if until_raw:
        u_dt = parse_utcdatetime(until_raw)
        # RFC 5545 requires UTC in basic format YYYYMMDDTHHMMSSZ
        until_str = u_dt.strftime("%Y%m%dT%H%M%SZ")
        parts.append(f"UNTIL={until_str}")
    if byday:
        parts.append(f"BYDAY={byday}")
    return ";".join(parts)

def dt_to_ics(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")

def make_uid(event_id: str, start_dt: datetime) -> str:
    # Stable-ish UID using id + start + random suffix to avoid collisions across calendars
    base = f"{event_id}-{dt_to_ics(start_dt)}@mxl2ics"
    # Keep simple: deterministic without random
    return base

def mxl_to_ics(xml_path: Path, ics_out: Path) -> None:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    lines = []
    lines.append("BEGIN:VCALENDAR")
    lines.append("PRODID:-//mxl-to-ics//saskpolytech//EN")
    lines.append("VERSION:2.0")
    lines.append("CALSCALE:GREGORIAN")
    lines.append("METHOD:PUBLISH")
    # Iterate events
    for ev in root.findall("event", XML_NS):
        title = (ev.findtext("title") or "").strip()
        desc = ev.findtext("description") or ""
        start_raw = ev.findtext("start_date")
        end_raw = ev.findtext("end_date")
        loc = (ev.findtext("location") or "").strip()
        recur_el = ev.find("recurrence")
        is_all_day = (ev.attrib.get("is_allday_event","False").lower() == "true")
        start_dt = parse_utcdatetime(start_raw) if start_raw else None
        end_dt = parse_utcdatetime(end_raw) if end_raw else None

        lines.append("BEGIN:VEVENT")
        if start_dt:
            if is_all_day:
                lines.append(f"DTSTART;VALUE=DATE:{start_dt.strftime('%Y%m%d')}")
            else:
                lines.append(f"DTSTART:{dt_to_ics(start_dt)}")
        if end_dt:
            if is_all_day:
                # For all-day, DTEND is non-inclusive, so add a day. Here we assume already correct.
                lines.append(f"DTEND;VALUE=DATE:{end_dt.strftime('%Y%m%d')}")
            else:
                lines.append(f"DTEND:{dt_to_ics(end_dt)}")

        uid = make_uid(ev.attrib.get("id","x"), start_dt or datetime.now(timezone.utc))
        lines.append(f"UID:{uid}")
        lines.append(fold_ics_line(f"SUMMARY:{ics_escape(title)}"))
        if desc:
            lines.append(fold_ics_line(f"DESCRIPTION:{ics_escape(desc)}"))
        if loc:
            lines.append(fold_ics_line(f"LOCATION:{ics_escape(loc)}"))
        rrule = build_rrule(recur_el)
        if rrule:
            lines.append(f"RRULE:{rrule}")
        # DTSTAMP now
        lines.append(f"DTSTAMP:{dt_to_ics(datetime.now(timezone.utc))}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    # Fold all lines and ensure CRLF
    final = "\r\n".join([fold_ics_line(line) for line in lines]) + "\r\n"
    ics_out.write_text(final, encoding="utf-8")
