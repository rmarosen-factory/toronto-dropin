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

Three pages share the one screen:

- **Find** lists what is on near you for a chosen activity and day.
- **Favourites** keeps places (tap the heart on a place) and single activities
  at a place (tap the round + beside a time). Places show everything on that
  day; activities show the next seven days.
- **My plan** collects the sessions you pick, day by day, and flags ones that
  overlap or have dropped out of the city schedule. Any session, or the whole
  plan, can go to a calendar: a calendar file for Apple Calendar and Outlook,
  or a link for Google Calendar.

Your starting point, filters, favourites and plan are saved only in your own
browser, so they do not follow you to another phone or computer.

## Run it locally

    python3 -I build_data.py     # fetch the latest schedule
    python3 -I build_site.py     # write site/
    python3 -m http.server --directory site 8000

## Data

Schedules are a weekly snapshot, so same-day closures and cancellations do not
appear. Check the centre's city page before heading out.

EarlyON Child and Family Centres appear under Early Years. They are free, for
children from birth to six with a parent or caregiver. The city publishes each
centre's regular weekly drop-in hours, not dated sessions, so the app repeats
those hours each week and skips Ontario public holidays. It cannot tell which
program runs in a given time slot (the city's own page says to contact centres
for that, so baby-only or toddler times are not shown) or when a centre closes
for a school break.

Contains information licensed under the
[Open Government Licence – Toronto](https://open.toronto.ca/open-data-license/),
from these City of Toronto Open Data sets: Registered Programs and Drop In
Courses Offering, Parks and Recreation Facilities, EarlyON Child and Family
Centres, Address Points (Municipal),
Neighbourhoods, and Licensed Child Care Centres (used only to place postal
code areas).
