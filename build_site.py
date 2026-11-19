#!/usr/bin/env python3
"""Turn index.html into a standalone website in site/.

index.html is written as a page fragment (title, styles, markup, script) with
no <html>/<head>/<body> of its own. This wraps it in a full document and copies
the data files, the home-screen icon and the offline helper next to it, ready
for any static host.

    python3 -I build_site.py
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex">
<meta name="description" content="Find City of Toronto drop-in swims, skates, sports and more near you, today and through the week. Unofficial.">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#E2F5F4">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0F1634">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Drop-Ins">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icons/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="icons/icon-180.png">
<style>:root{color-scheme:light;padding:env(safe-area-inset-top,0px) 0 env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
"""

# Registers sw.js, which keeps a copy of the page and schedule so the home-screen app opens offline.
TAIL = """<script>if('serviceWorker' in navigator)addEventListener('load',function(){navigator.serviceWorker.register('sw.js').catch(function(){});});</script>
"""

# Files copied next to the page as they are.
EXTRAS = ["manifest.webmanifest", "sw.js", "icons/icon.svg", "icons/icon-180.png", "icons/icon-192.png", "icons/icon-512.png"]


def main():
    with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
        page = f.read()
    cut = page.index('<div class="page">')
    doc = HEAD + page[:cut].strip() + "\n</head>\n<body>\n" + page[cut:].strip() + "\n" + TAIL + "</body>\n</html>\n"

    os.makedirs(os.path.join(SITE, "data"), exist_ok=True)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    for name in ("schedule.json", "places.json"):
        shutil.copyfile(os.path.join(HERE, "data", name), os.path.join(SITE, "data", name))
    os.makedirs(os.path.join(SITE, "icons"), exist_ok=True)
    for name in EXTRAS:
        shutil.copyfile(os.path.join(HERE, name), os.path.join(SITE, name))
    print("wrote %s (%.0f KB page)" % (SITE, len(doc) / 1024))


if __name__ == "__main__":
    main()
