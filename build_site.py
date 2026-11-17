#!/usr/bin/env python3
"""Turn index.html into a standalone website in site/.

index.html is written as a page fragment (title, styles, markup, script) with
no <html>/<head>/<body> of its own. This wraps it in a full document and copies
the data files next to it, ready for any static host.

    python3 -I build_site.py
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")

ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
        "%3Ccircle cx='16' cy='17' r='14' fill='%23A3ABBB'/%3E"
        "%3Cellipse cx='10.5' cy='16' rx='5.5' ry='4' fill='%233A4157'/%3E"
        "%3Cellipse cx='21.5' cy='16' rx='5.5' ry='4' fill='%233A4157'/%3E"
        "%3Ccircle cx='11' cy='16' r='1.8' fill='%23fff'/%3E%3Ccircle cx='21' cy='16' r='1.8' fill='%23fff'/%3E"
        "%3Cellipse cx='16' cy='22' rx='5' ry='3.6' fill='%23F4F6FA'/%3E"
        "%3Ccircle cx='16' cy='20.5' r='1.6' fill='%2316213E'/%3E"
        "%3Cpath d='M3 12 Q16 2 29 12 L29 8 Q16 -2 3 8 Z' fill='%233CCBDD'/%3E%3C/svg%3E")

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex">
<meta name="description" content="Find City of Toronto drop-in swims, skates, sports and more near you, today and through the week. Unofficial.">
<link rel="icon" href="%s">
<style>:root{color-scheme:light;padding:env(safe-area-inset-top,0px) 0 env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%%}[hidden]{display:none!important}</style>
""" % ICON


def main():
    with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
        page = f.read()
    cut = page.index('<div class="page">')
    doc = HEAD + page[:cut].strip() + "\n</head>\n<body>\n" + page[cut:].strip() + "\n</body>\n</html>\n"

    os.makedirs(os.path.join(SITE, "data"), exist_ok=True)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    for name in ("schedule.json", "places.json"):
        shutil.copyfile(os.path.join(HERE, "data", name), os.path.join(SITE, "data", name))
    print("wrote %s (%.0f KB page)" % (SITE, len(doc) / 1024))


if __name__ == "__main__":
    main()
