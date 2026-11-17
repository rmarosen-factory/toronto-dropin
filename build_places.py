#!/usr/bin/env python3
"""Build data/places.json: everything the page needs to turn typed text into
a point on the map without calling an outside service.

    python3 -I build_places.py            # reuse files already in .cache/
    python3 -I build_places.py --refresh  # download fresh copies first

Streets change slowly; rerun this a couple of times a year at most.

Sources (City of Toronto Open Data, Open Government Licence - Toronto):
  - Address Points (Municipal) - Toronto One Address Repository  (183 MB)
  - Neighbourhoods (158 social planning neighbourhoods)
  - Parks and Recreation Facilities + drop-in Locations (place names)
  - Licensed Child Care Centres (only used to place postal-code areas)

Downloads are untrusted data: each sits in its own folder under .cache/ and
is only ever parsed as CSV/JSON.
"""
import collections
import csv
import json
import math
import os
import statistics
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
OUT = os.path.join(HERE, "data", "places.json")
CKAN = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
SCALE = 10000        # coordinates stored as round(deg * SCALE): about 11 m
SPACING_M = 150      # keep one address roughly every 150 m along a street

FILES = {
    "addresses": ("64d4e54b-738f-4cd9-a9e7-8050fac8a52f", "addresses", "address-points.csv"),
    "neighbourhoods": ("0719053b-28b7-48ea-b863-068823a93aaa", "neighbourhoods", "neighbourhoods.geojson"),
    "childcare": ("4f5ef49d-15ee-4d73-8b66-90303c5ef746", "childcare", "childcare.geojson"),
    "locations": ("87f95a5a-184f-4df5-ad37-84bcc1ea99a9", "locations", "locations.json"),
    "facilities": ("f6cdcd50-da7b-4ede-8e60-c3cdba70b559", "facilities", "facilities.geojson"),
}


def path_for(name, refresh):
    rid, sub, fname = FILES[name]
    folder = os.path.join(CACHE, sub)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, fname)
    if refresh or not os.path.exists(path):
        with urllib.request.urlopen("%s/api/3/action/resource_show?id=%s" % (CKAN, rid), timeout=60) as r:
            url = json.load(r)["result"]["url"]
        print("downloading", name)
        with urllib.request.urlopen(url, timeout=600) as r, open(path, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    return path


def metres(a, b):
    dlat = (a[0] - b[0]) * 111320.0
    dlng = (a[1] - b[1]) * 111320.0 * math.cos(math.radians(43.7))
    return math.hypot(dlat, dlng)


def first_point(geom):
    c = geom["coordinates"]
    while isinstance(c[0], list):
        c = c[0]
    return (c[1], c[0])


def build_streets(path):
    csv.field_size_limit(10 ** 7)
    by_id = collections.defaultdict(list)
    names, munis = {}, collections.defaultdict(collections.Counter)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                num = int(row["LO_NUM"])
                pt = first_point(json.loads(row["geometry"]))
            except (ValueError, KeyError, IndexError, TypeError):
                continue
            sid = row["LINEAR_NAME_ID"]
            by_id[sid].append((num, pt[0], pt[1]))
            names[sid] = row["LINEAR_NAME_FULL"].strip()
            munis[sid][row["MUNICIPALITY_NAME"].replace("former ", "")] += 1

    name_count = collections.Counter(names.values())
    muni_list = sorted({m for c in munis.values() for m in c})
    streets, kept_total = [], 0
    for sid, pts in by_id.items():
        # one point per house number (mean of duplicates), in number order
        per_num = collections.defaultdict(list)
        for num, la, lo in pts:
            per_num[num].append((la, lo))
        ordered = [(n, statistics.fmean(p[0] for p in v), statistics.fmean(p[1] for p in v))
                   for n, v in sorted(per_num.items())]
        lats, lngs = [p[1] for p in ordered], [p[2] for p in ordered]
        if metres((min(lats), min(lngs)), (max(lats), max(lngs))) < SPACING_M:
            kept = [ordered[len(ordered) // 2]]          # short street: one point is enough
        else:
            # Odd and even sides are numbered independently and drift apart on
            # long streets, so thin each side on its own.
            kept = []
            for parity in (0, 1):
                side = [p for p in ordered if p[0] % 2 == parity]
                if not side:
                    continue
                run = [side[0]]
                for p in side[1:]:
                    if metres(p[1:], run[-1][1:]) >= SPACING_M:
                        run.append(p)
                if metres(side[-1][1:], run[-1][1:]) >= 40:
                    run.append(side[-1])
                kept += run
            kept.sort()
        deltas, pn, pla, plo = [], 0, 0, 0
        for n, la, lo in kept:
            ila, ilo = round(la * SCALE), round(lo * SCALE)
            deltas += [n - pn, ila - pla, ilo - plo]
            pn, pla, plo = n, ila, ilo
        kept_total += len(kept)
        name = names[sid]
        # -1 = name is unique city-wide; otherwise which former municipality
        muni = muni_list.index(munis[sid].most_common(1)[0][0]) if name_count[name] > 1 else -1
        streets.append([name, muni, deltas])
    streets.sort(key=lambda s: s[0])
    print("streets: %d, sample points kept: %d" % (len(streets), kept_total))
    return streets, muni_list


def ring_centroid(ring):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-12:
        return (statistics.fmean(p[1] for p in ring), statistics.fmean(p[0] for p in ring), 0.0)
    return (cy / (3 * a), cx / (3 * a), abs(a) / 2)


def build_neighbourhoods(path):
    with open(path, encoding="utf-8") as f:
        feats = json.load(f)["features"]
    out = []
    for ft in feats:
        g = ft["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        best = max((ring_centroid(p[0]) for p in polys), key=lambda c: c[2])
        out.append([ft["properties"]["AREA_NAME"], round(best[0], 4), round(best[1], 4), "n"])
    return out


def build_facilities(loc_path, fac_path):
    with open(loc_path, encoding="utf-8") as f:
        names = {int(r["Location ID"]): r["Location Name"] for r in json.load(f)}
    with open(fac_path, encoding="utf-8") as f:
        feats = json.load(f)["features"]
    out, seen = [], set()
    for ft in feats:
        p = ft["properties"]
        try:
            lid = int(p["LOCATIONID"])
            la, lo = first_point(ft["geometry"])
        except (ValueError, KeyError, TypeError, IndexError):
            continue
        name = names.get(lid) or p["ASSET_NAME"].title()
        if name in seen:
            continue
        seen.add(name)
        out.append([name, round(la, 4), round(lo, 4), "p" if p.get("TYPE") == "Park" else "c"])
    return out


def build_fsa(childcare_path):
    with open(childcare_path, encoding="utf-8") as f:
        feats = json.load(f)["features"]
    pts = collections.defaultdict(list)
    for ft in feats:
        code = (ft["properties"].get("PCODE") or "").replace(" ", "").upper()[:3]
        if len(code) == 3 and code[0] == "M":
            pts[code].append(first_point(ft["geometry"]))
    return [[code, round(statistics.median(p[0] for p in v), 4), round(statistics.median(p[1] for p in v), 4)]
            for code, v in sorted(pts.items())]


def main():
    refresh = "--refresh" in sys.argv
    streets, munis = build_streets(path_for("addresses", refresh))
    places = build_neighbourhoods(path_for("neighbourhoods", refresh))
    places += build_facilities(path_for("locations", refresh), path_for("facilities", refresh))
    fsa = build_fsa(path_for("childcare", refresh))
    out = {"scale": SCALE, "munis": munis, "streets": streets, "places": places, "fsa": fsa}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
    print("places: %d | postal areas: %d" % (len(places), len(fsa)))
    print("wrote %s (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
