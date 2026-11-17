#!/usr/bin/env python3
"""Fetch the City of Toronto drop-in schedule and write data/schedule.json.

Run weekly (the city refreshes the feed weekly):

    python3 -I build_data.py

Sources (City of Toronto Open Data, Open Government Licence - Toronto):
  - Registered Programs and Drop In Courses Offering: Drop-in + Locations
  - Parks and Recreation Facilities (coordinates, phone)

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
}

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


def main():
    drop, drop_updated = fetch("dropin")
    locs, _ = fetch("locations")
    fac, _ = fetch("facilities")
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
    all_days = [d for r in rows for d in r[6]]
    end = start + dt.timedelta(days=max(all_days))

    out = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "sourceUpdated": drop_updated,
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
    print("wrote %s (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024))
    if unplaced:
        print("no map point for: " + "; ".join(unplaced))


if __name__ == "__main__":
    main()
