# Toronto Drop-In Finder

Pick an activity and a starting point to see City of Toronto drop-in programs
nearby (swim, skate, sports, fitness and more) for today and the next six days.

An unofficial personal project. It is not a City of Toronto service.

## How it works

- `index.html` is the whole app: one page, no framework, no server.
- `data/schedule.json` holds the drop-in sessions. `build_data.py` rebuilds it
  from the city's open data feed. A scheduled GitHub Action runs it twice a
  week and republishes the site.
- `data/places.json` lets the page turn a typed address, postal code,
  neighbourhood or centre name into a point on the map without calling any
  outside service. `build_places.py` rebuilds it (rarely needed; it downloads
  183 MB of address points).
- `build_site.py` wraps the page into a standalone website in `site/`.

Your starting point and filters are saved only in your own browser.

## Run it locally

    python3 -I build_data.py     # fetch the latest schedule
    python3 -I build_site.py     # write site/
    python3 -m http.server --directory site 8000

## Data

Schedules are a weekly snapshot, so same-day closures and cancellations do not
appear. Check the centre's city page before heading out.

Contains information licensed under the
[Open Government Licence – Toronto](https://open.toronto.ca/open-data-license/),
from these City of Toronto Open Data sets: Registered Programs and Drop In
Courses Offering, Parks and Recreation Facilities, Address Points (Municipal),
Neighbourhoods, and Licensed Child Care Centres (used only to place postal
code areas).
