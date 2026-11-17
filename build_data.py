#!/usr/bin/env python3
"""Fetch the City of Toronto drop-in schedule and write data/schedule.json.

Run weekly (the city refreshes the feed weekly):

    python3 -I build_data.py

Sources (City of Toronto Open Data, Open Government Licence - Toronto):
  - Registered Programs and Drop In Courses Offering: Drop-in + Locations
  - Parks and Recreation Facilities (coordinates, phone)
  - EarlyON Child and Family Centres (regular weekly drop-in hours)

Downloads are treated as untrusted data: each goes into its own folder under
.cache/, and this script only ever parses them as JSON.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
OUT = os.path.join(HERE, "data", "schedule.json")
CKAN = "https://ckan0.cf.opendata.inter.prod-toronto.ca"

RESOURCES = {
    # name: (resource id, cache subfolder, filename)
    "dropin": ("067b41e7-ac8a-4d3f-ad08-089f8cd70316", "dropin", "drop-in.json"),
    "locations": ("87f95a5a-184f-4df5-ad37-84bcc1ea99a9", "locations", "locations.json"),
    "facilities": ("f6cdcd50-da7b-4ede-8e60-c3cdba70b559", "facilities", "facilities.geojson"),
    "earlyon": ("c02ccbd4-000f-49e3-a133-3f23c9bfa418", "earlyon", "earlyon.geojson"),
}

# EarlyON centres: free drop-in for children from birth to six with a parent
# or caregiver. The city lists each centre's regular weekly drop-in hours, not
# dated sessions and not which program runs in each slot.
EARLYON_CAT = "Early Years"
EARLYON_TYPE = "EarlyON"
EARLYON_TITLE = "EarlyON drop-in"
EARLYON_AGE_MAX = 6
EARLYON_AGE_NOTE = "Ages 0–6 + caregiver"   # kept short: the tag does not wrap on a phone
EARLYON_PAGE = ("https://www.toronto.ca/community-people/children-parenting/children-programs-activities/"
                "child-family-programs-and-groups/child-family-programs/")
EARLYON_MIN_CENTRES = 50   # fewer than this with readable hours means the file changed shape
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Top-level activity groups, in display order. Each section name in the feed
# maps to one of these by prefix.
CATEGORIES = ["Swim", "Skate", "Sports", "Fitness", "Arts & Hobbies", "Youth Spaces", "Early Years"]
SECTION_PREFIXES = [
    ("Swim", "Swim"),
    ("Reserve a Spot - Aquatic", "Swim"),
    ("Skate", "Skate"),
    ("Sports", "Sports"),
    ("EYS - Sports", "Sports"),
    ("Reserve a Spot - Sports", "Sports"),
    ("FitnessTO", "Fitness"),
    ("EYS", "Youth Spaces"),
    ("Early Years", "Early Years"),
    ("Arts", "Arts & Hobbies"),
    ("Hobbies", "Arts & Hobbies"),
]
# Titles that belong somewhere other than their section suggests.
TITLE_OVERRIDES = {"Indoor Playground with Caregiver": "Early Years"}


def fetch(name):
    rid, sub, fname = RESOURCES[name]
    meta_url = "%s/api/3/action/resource_show?id=%s" % (CKAN, rid)
    with urllib.request.urlopen(meta_url, timeout=60) as r:
        meta = json.load(r)["result"]
    folder = os.path.join(CACHE, sub)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, fname)
    with urllib.request.urlopen(meta["url"], timeout=300) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    with open(path, encoding="utf-8") as f:
        return json.load(f), (meta.get("last_modified") or "")[:10]


def category_for(section, title):
    if title in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[title]
    for prefix, cat in SECTION_PREFIXES:
        if section.startswith(prefix):
            return cat
    return "Arts & Hobbies"


def base_type(title):
    """Collapse variants into one pickable type: 'Lane Swim: Older Adult' -> 'Lane Swim'."""
    t = title.replace("®", "").strip()
    t = re.sub(r"\s*\([^)]*\)", "", t)
    t = t.split(":")[0]
    t = re.split(r"\s+with\s+", t, flags=re.I)[0]
    t = re.sub(r"\s+-\s+.*$", "", t)
    t = re.sub(r"^(Adapted|Outdoor)\s+", "", t)
    if t.startswith("Cardio"):
        t = "Cardio"
    if t.startswith("Zumba"):
        t = "Zumba"
    return t.strip() or title


def none(v):
    return None if v in (None, "", "None") else v


def to_int(v):
    v = none(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def clean_addr(loc, fac_props):
    parts = [none(loc.get(k)) for k in ("Street No", "Street No Suffix", "Street Name", "Street Type", "Street Direction")]
    if parts[0] and parts[1]:
        parts[0] = "%s%s" % (parts[0], parts[1])
    parts[1] = None
    addr = " ".join(str(p).strip().rstrip(".") for p in parts if p)
    if not addr and fac_props:
        addr = (none(fac_props.get("ADDRESS")) or "").title()
    return addr


def load_streets():
    path = os.path.join(HERE, "data", "places.json")  # written by build_places.py
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def geocode(streets, number, street_name):
    """Tiny mirror of the page's address lookup, used for locations the
    facilities file has no point for."""
    if not streets or number is None:
        return None
    key = re.sub(r"[^a-z0-9 ]", "", street_name.lower()).strip()
    for s in streets["streets"]:
        if s[0].lower() == key or re.sub(r"[^a-z0-9 ]", "", s[0].lower()) == key:
            nums, lats, lngs = [], [], []
            n = la = lo = 0
            for i in range(0, len(s[2]), 3):
                n += s[2][i]; la += s[2][i + 1]; lo += s[2][i + 2]
                nums.append(n); lats.append(la); lngs.append(lo)
            best = min(range(len(nums)), key=lambda i: abs(nums[i] - number))
            sc = streets["scale"]
            return [round(lats[best] / sc, 5), round(lngs[best] / sc, 5)]
    return None


def parse_clock(text, is_end):
    t = text.strip().lower()
    if t == "noon":
        return 720
    if t == "midnight":
        return 1440 if is_end else 0
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?$", t)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if not 1 <= hour <= 12 or minute > 59:
        return None
    return (hour % 12 + (12 if m.group(3) == "p" else 0)) * 60 + minute


def parse_hours(text):
    """'Monday: 9:00 a.m. - noon ; 1:00 p.m. - 3:00 p.m. | Tuesday: ...'
    -> ({weekday index: sorted [(start, end)]}, number of pieces not understood)"""
    out, bad = {}, 0
    for part in (text or "").split("|"):
        day, sep, rest = part.partition(":")
        if not sep:
            bad += 1 if part.strip() else 0
            continue
        if day.strip() not in WEEKDAYS:
            bad += 1
            continue
        spans = out.setdefault(WEEKDAYS.index(day.strip()), set())
        for piece in rest.split(";"):
            if not piece.strip():
                continue
            m = re.match(r"^(.+?)\s+-\s+(.+)$", piece.strip())
            a = parse_clock(m.group(1), False) if m else None
            b = parse_clock(m.group(2), True) if m else None
            if a is None or b is None or not a < b:
                bad += 1
                continue
            spans.add((a, b))
    return {d: sorted(s) for d, s in out.items() if s}, bad


def easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    j, k = c // 4, c % 4
    m = (a + 11 * h) // 319
    r = (2 * e + 2 * j - k - h + m + 32) % 7
    month = (h - m + r + 90) // 25
    return dt.date(year, month, (h - m + r + month + 19) % 32)


def nth_monday(year, month, n):
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(7 - first.weekday()) % 7 + 7 * (n - 1))


def holidays(year):
    """Ontario public holidays plus the August civic holiday, with the weekday
    a weekend holiday is observed on. Centres keep regular hours otherwise."""
    days = {
        nth_monday(year, 2, 3),                                   # Family Day
        easter(year) - dt.timedelta(days=2),                      # Good Friday
        dt.date(year, 5, 24) - dt.timedelta(days=dt.date(year, 5, 24).weekday()),  # Victoria Day
        nth_monday(year, 8, 1),                                   # Civic Holiday
        nth_monday(year, 9, 1),                                   # Labour Day
        nth_monday(year, 10, 2),                                  # Thanksgiving
    }
    for fixed in (dt.date(year, 1, 1), dt.date(year, 7, 1), dt.date(year, 12, 25), dt.date(year, 12, 26)):
        days.add(fixed)
        if fixed.weekday() >= 5:
            d = fixed
            while d.weekday() >= 5 or d in days:
                d += dt.timedelta(days=1)
            days.add(d)
    return days


def earlyon_name(name):
    n = re.sub(r"\s+Child\s+(and|&)\s+Family\s+(Centre|Center|Ctr)\b\.?", "", name.strip(), flags=re.I)
    n = re.sub(r"earlyon", "EarlyON", n, flags=re.I)
    n = re.sub(r"\s+", " ", n).strip()
    if "earlyon" not in n.lower() and "on y va" not in n.lower():
        n += " EarlyON"
    return n


def web_link(url):
    """The operator's website as a safe http(s) link, or '' if there is none."""
    u = (none(url) or "").strip()
    if not u or " " in u:
        return ""
    if not re.match(r"^https?://", u, flags=re.I):
        u = "http://" + u
    return u if re.match(r"^https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/\S*)?$", u) else ""


def earlyon_notes(p, name):
    notes = []
    building = (none(p.get("buildingName")) or "").strip()
    if p.get("located_in_school") == "Yes":
        notes.append("In a school, may close on school holidays")
    elif building and not building[0].isdigit():
        b = building.lower()
        generic = ("earlyon" in b or "child and family" in b or b == "commercial storefront")
        if not generic and b not in name.lower() and name.lower().replace(" earlyon", "") not in b:
            notes.append("In " + building)
    if p.get("indigenous_program") == "Yes":
        notes.append("Indigenous program")
    if p.get("french_language_program") == "Yes":
        notes.append("French-language program")
    langs = []
    for l in re.split(r"[;,]", none(p.get("languages")) or ""):
        l = re.sub(r"\s*\([^)]*\)", "", l).split(" - ")[0].strip()
        if l and l not in langs and l != "English":
            langs.append(l)
    if langs and not (langs == ["French"] and "French-language program" in notes):
        notes.append("Also in " + ", ".join(langs[:4]))
    return notes


def add_earlyon(feed, start, last_offset, courses, loc_list, rows):
    """Append EarlyON centres and their regular weekly drop-in hours, expanded
    over the same dates the recreation feed covers."""
    closed = set()
    for y in range(start.year, (start + dt.timedelta(days=last_offset)).year + 1):
        closed |= holidays(y)
    by_weekday = collections.defaultdict(list)
    for off in range(last_offset + 1):
        d = start + dt.timedelta(days=off)
        if d not in closed:
            by_weekday[d.weekday()].append(off)

    course = len(courses)
    courses.append([EARLYON_TITLE, CATEGORIES.index(EARLYON_CAT), EARLYON_TYPE, 0, EARLYON_AGE_NOTE])
    centres = unread = 0
    for f in feed["features"]:
        p = f["properties"]
        hours, bad = parse_hours(none(p.get("dropinHours")))
        unread += bad
        try:
            lat, lng = round(float(p["lat"]), 5), round(float(p["lng"]), 5)
        except (KeyError, TypeError, ValueError):
            continue
        if not hours or not (43.4 < lat < 44.0 and -79.8 < lng < -79.0):
            continue
        name = earlyon_name(none(p.get("program_name")) or "EarlyON")
        phone = re.sub(r"\s+X\s+", " ext. ", (none(p.get("phone")) or "").strip())
        loc = len(loc_list)
        loc_list.append([to_int(p.get("loc_id")) or 0, name, lat, lng, (none(p.get("address")) or "").strip(),
                         "", 0, phone, web_link(p.get("website")), earlyon_notes(p, name)])
        centres += 1
        for wd, spans in hours.items():
            if by_weekday[wd]:
                for a, b in spans:
                    rows.append([loc, course, a, b, None, EARLYON_AGE_MAX, by_weekday[wd]])
    if centres < EARLYON_MIN_CENTRES:
        sys.exit("Only %d EarlyON centres had readable drop-in hours; refusing to publish without them" % centres)
    return centres, unread


def main():
    drop, drop_updated = fetch("dropin")
    locs, _ = fetch("locations")
    fac, _ = fetch("facilities")
    earlyon, earlyon_updated = fetch("earlyon")
    streets = load_streets()

    loc_by_id = {to_int(r["Location ID"]): r for r in locs}
    fac_by_id = {}
    for f in fac["features"]:
        lid = to_int(f["properties"].get("LOCATIONID"))
        g = f.get("geometry") or {}
        c = g.get("coordinates")
        if lid is None or not c:
            continue
        pt = c[0] if g.get("type") == "MultiPoint" else c
        fac_by_id[lid] = (f["properties"], [round(pt[1], 5), round(pt[0], 5)])

    dates = sorted(none(r.get("First Date")) for r in drop if none(r.get("First Date")))
    if not dates:
        sys.exit("Feed has no dated sessions; refusing to overwrite %s" % OUT)
    start = dt.date.fromisoformat(dates[0])

    courses, course_idx = [], {}
    loc_list, loc_idx = [], {}
    unplaced = []
    groups = collections.OrderedDict()

    for r in drop:
        lid = to_int(r.get("Location ID"))
        title = (none(r.get("Course Title")) or "").strip()
        section = (none(r.get("Section")) or "").strip()
        first, last = none(r.get("First Date")), none(r.get("Last Date")) or none(r.get("First Date"))
        sh, sm, eh, em = (to_int(r.get(k)) for k in ("Start Hour", "Start Minute", "End Hour", "End Min"))
        if lid is None or not title or not first or sh is None or eh is None:
            continue

        if lid not in loc_idx:
            loc = loc_by_id.get(lid, {})
            props, pt = fac_by_id.get(lid, (None, None))
            addr = clean_addr(loc, props)
            if pt is None:
                pt = geocode(streets, to_int(loc.get("Street No")), " ".join(
                    str(none(loc.get(k))).rstrip(".") for k in ("Street Name", "Street Type", "Street Direction") if none(loc.get(k))))
                if pt is None:
                    unplaced.append("%s (%s)" % (loc.get("Location Name"), addr))
            acc = {"Fully Accessible": 2, "Partially Accessible": 1}.get(loc.get("Accessibility"), 0)
            name = none(loc.get("Location Name")) or (props or {}).get("ASSET_NAME", "Location %d" % lid).title()
            phone = none((props or {}).get("PHONE")) or ""
            loc_idx[lid] = len(loc_list)
            loc_list.append([lid, name, pt[0] if pt else None, pt[1] if pt else None, addr,
                             none(loc.get("District")) or "", acc, phone])

        reserve = 1 if section.startswith("Reserve a Spot") else 0
        cat = category_for(section, title)
        ck = (title, cat, reserve)
        if ck not in course_idx:
            course_idx[ck] = len(courses)
            courses.append([title, CATEGORIES.index(cat), base_type(title), reserve])

        amin, amax = to_int(r.get("Age Min")), to_int(r.get("Age Max"))
        if amin == 0:
            amin = None
        if amax is not None and amax >= 98:
            amax = None

        d0, d1 = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
        days = []
        if d0 == d1:
            days.append((d0 - start).days)
        else:  # a range row: one session on each matching weekday
            want = none(r.get("DayOftheWeek"))
            d = d0
            while d <= d1:
                if not want or d.strftime("%A") == want:
                    days.append((d - start).days)
                d += dt.timedelta(days=1)

        key = (loc_idx[lid], course_idx[ck], sh * 60 + (sm or 0), eh * 60 + (em or 0), amin, amax)
        groups.setdefault(key, set()).update(days)

    rows = [list(k) + [sorted(v)] for k, v in groups.items()]
    last_offset = max(d for r in rows for d in r[6])
    end = start + dt.timedelta(days=last_offset)
    rec_rows = len(rows)
    centres, unread = add_earlyon(earlyon, start, last_offset, courses, loc_list, rows)
    all_days = [d for r in rows for d in r[6]]

    out = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "sourceUpdated": drop_updated,
        "earlyonUpdated": earlyon_updated,
        "earlyonPage": EARLYON_PAGE,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "cats": CATEGORIES,
        "courses": courses,
        "locs": loc_list,
        "rows": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)

    print("sessions: %d in %d rows | locations: %d | activities: %d" % (len(all_days), len(rows), len(loc_list), len(courses)))
    print("covers %s to %s | city feed updated %s" % (out["start"], out["end"], drop_updated))
    print("EarlyON: %d centres with drop-in hours, %d weekly time slots, %d pieces of text not understood | list updated %s"
          % (centres, len(rows) - rec_rows, unread, earlyon_updated))
    print("wrote %s (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024))
    if unplaced:
        print("no map point for: " + "; ".join(unplaced))


if __name__ == "__main__":
    main()
