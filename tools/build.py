"""Build data.js: Confederate symbols and lynching victims, by year.

Inputs (in data/, git-ignored):
  splc_whose_heritage.xlsx   SPLC "Whose Heritage?" master sheet, from
      https://docs.google.com/spreadsheets/d/1W4H2qa2THM1ni53QYZftGob_k_Bf9HreFAtCERfjCIU/export?format=xlsx
  seguin_rigby_2019.csv      Seguin & Rigby (2019) national lynching data,
      38 states outside the Tolnay-Beck South, https://osf.io/kr8yc
  tolnay_beck.csv            optional; full Tolnay-Beck inventory (10
      Southern states), requested via https://sites.uw.edu/lynching/
  duslr_subset.csv           stand-in until then: Tolnay-Beck rows from
      Matthew Kollmer's DUSLR (github.com/MatthewKollmer/DUSLR,
      subset_cleaned_combined_lynch_inventories.csv): named Black and
      white victims, 1865-1921, geocoded to town. No license stated.
  2023_Gaz_counties_national.txt   Census county centroids, from
      https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/
  states.geojson, labels.geojson   state outlines and label points, from
      Census cb_2023_us_state_20m (GENZ2023):
        ogr2ogr -f GeoJSON -lco COORDINATE_PRECISION=3 -simplify 0.01 \
          states.geojson cb_2023_us_state_20m.shp -select STUSPS,NAME
        ogr2ogr -f GeoJSON -lco COORDINATE_PRECISION=3 -dialect SQLite \
          -sql "SELECT STUSPS, NAME, ST_PointOnSurface(geometry) AS geometry
                FROM cb_2023_us_state_20m" labels.geojson cb_2023_us_state_20m.shp

Usage:
  python3 tools/build.py

Output: data.js with MON (symbols), LYN (victims) and META (counts,
sources present). Victims are placed near their county's centroid with a
fixed per-case offset: the sources give the county, not the spot.
"""

import csv
import hashlib
import json
import math
import os
import sys

import openpyxl

DATA = 'data'
SPLC = os.path.join(DATA, 'splc_whose_heritage.xlsx')
SR = os.path.join(DATA, 'seguin_rigby_2019.csv')
TB = os.path.join(DATA, 'tolnay_beck.csv')
DUSLR = os.path.join(DATA, 'duslr_subset.csv')
GAZ = os.path.join(DATA, '2023_Gaz_counties_national.txt')
STATES = os.path.join(DATA, 'states.geojson')
LABELS = os.path.join(DATA, 'labels.geojson')

# Label points that read better than the computed point on surface.
LABEL_AT = {'FL': (28.3, -81.7), 'LA': (31.0, -92.3), 'MI': (43.4, -84.6),
            'KY': (37.6, -85.0), 'VA': (37.5, -78.6), 'MD': (39.1, -76.9)}

# Offset victims up to this far from the county centroid (km), so cases
# in one county don't stack on one dot.
SPREAD_KM = 12

# Town-geocoded victims (DUSLR) get a small offset so cases in one town
# stay apart.
TOWN_KM = 2

STATE_ABBR = {'alabama': 'AL', 'arkansas': 'AR', 'florida': 'FL', 'georgia': 'GA',
              'kentucky': 'KY', 'louisiana': 'LA', 'mississippi': 'MS',
              'north carolina': 'NC', 'south carolina': 'SC', 'tennessee': 'TN'}

# Counties the sources spell differently or that no longer exist, mapped
# to today's county or city. CT dropped counties in 2022; its old county
# centroid is given directly.
COUNTY_FIX = {
    ('VA', 'PRINCESS ANNE'): '51810',     # now Virginia Beach
    ('VA', 'WARWICK'): '51700',           # now Newport News
    ('VA', 'NANESEMOND'): '51800',        # Nansemond, now Suffolk
    ('VA', 'SURREY'): '51181',            # Surry
    ('VA', 'ACCOMAC'): '51001',           # Accomack
    ('VA', 'NOTTAWAY'): '51135',          # Nottoway
    ('VA', 'NORTHUMBERLAND T'): '51133',  # Northumberland
    ('VA', 'CULPEPPER'): '51047',         # Culpeper
    ('WV', 'WATZEL'): '54103',            # Wetzel
}
FIXED_POINT = {('CT', 'LITCHFIELD'): (41.79, -73.24)}

TB_STATES = ['AL', 'AR', 'FL', 'GA', 'KY', 'LA', 'MS', 'NC', 'SC', 'TN']

# Short codes keep data.js small; the page maps them back.
TYPE = {'Monument': 'M', 'Roadway': 'R', 'School': 'S', 'Building': 'B',
        'County/Municipality': 'C', 'Other': 'O'}
STATUS = {'Live': 'L', 'Renamed': 'N', 'Removed': 'X', 'Relocated': 'V',
          'Pending': 'P', 'Live (statue removed; pedestal remains)': 'D',
          'Reconciliation': 'R'}


def year(v):
    """Leading 4-digit year of a cell, or None."""
    s = str(v or '').strip()[:4]
    return int(s) if s.isdigit() else None


def clean(v):
    return ' '.join(str(v or '').split())


def symbols():
    ws = openpyxl.load_workbook(SPLC, read_only=True)['Whose Heritage Master']
    rows = list(ws.iter_rows(values_only=True))
    head = rows[0]
    out = []
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        d = dict(zip(head, r))
        try:
            lat, lon = [float(x) for x in str(d['Coordinates']).split(',')]
        except ValueError:
            continue

        out.append([round(lat, 5), round(lon, 5), year(d['Year Dedicated']),
                    TYPE.get(d['Symbol Type'], 'O'), STATUS.get(d['Tracking Status'], ''),
                    clean(d['feature_name']), clean(d['Honorees']), clean(d['City']),
                    clean(d['State']), clean(d['Sponsors']), year(d['Year Removed'])])
    return out


def centroids():
    res = {}
    with open(GAZ, encoding='utf-8') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            r = {k.strip(): v.strip() for k, v in r.items()}
            res[r['GEOID']] = (float(r['INTPTLAT']), float(r['INTPTLONG']))
    return res


def jitter(key, lat, lon, km=SPREAD_KM):
    """Fixed pseudo-random offset within km, seeded by the case id."""
    h = hashlib.sha1(key.encode()).digest()
    a = h[0] / 255 * 2 * math.pi
    r = math.sqrt(h[1] / 255) * km
    dlat = r * math.sin(a) / 110.57
    dlon = r * math.cos(a) / (111.32 * math.cos(math.radians(lat)))
    return round(lat + dlat, 4), round(lon + dlon, 4)


def victim(src, key, fips, cent, y, m, d, rest):
    """One victim row, or None when the county has no centroid."""
    c = cent.get(fips)
    if c is None or y is None:
        return None
    lat, lon = jitter(src + key, *c)
    return [lat, lon, y, m, d] + rest + [src]


def seguin_rigby(cent, missing):
    out = []
    with open(SR, encoding='utf-8-sig', errors='replace') as f:
        for r in csv.DictReader(f):
            key = (r['state'], clean(r['county']).upper())
            fips = COUNTY_FIX.get(key, r['full_fips'].zfill(5))
            if key in FIXED_POINT:
                fips = 'pt:' + key[1]
                cent.setdefault(fips, FIXED_POINT[key])
            v = victim('S', r['caseid'], fips, cent, year(r['year']),
                       int(r['month'] or 0), int(r['day'] or 0),
                       [clean(r['victim']), clean(r['race']), clean(r['alleged_offense']),
                        clean(r['lynch_method']), clean(r['county']).title(), r['state'],
                        clean(r['city'])])
            if v is None:
                missing.append(('S', r['state'], r['county'], fips))
                continue
            out.append(v)
    return out


def tolnay_beck(cent, missing):
    """Tolnay-Beck rows; column names checked when the file arrives."""
    if not os.path.exists(TB):
        return []
    sys.exit('tolnay_beck.csv found: map its columns in tolnay_beck() first')


def month_day(s):
    """Month and day from '1890-07-20' or '7/20/90'; 0 when unknown.
    DUSLR sets unknown days to the 1st, so day 1 is treated as unknown."""
    if '-' in s:
        _, m, d = (s + '--').split('-')[:3]
    elif '/' in s:
        m, d = s.split('/')[:2]
    else:
        return 0, 0
    m, d = int(m or 0), int(d or 0)
    return m, (0 if d == 1 else d)


def county_index(path):
    """{(state, 'chatham county'): GEOID} from the Gazetteer."""
    res = {}
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            r = {k.strip(): v.strip() for k, v in r.items()}
            res[(r['USPS'], r['NAME'].lower())] = r['GEOID']
    return res


def duslr(cent, missing):
    """DUSLR's Tolnay-Beck rows in the 10 core states only (Seguin-Rigby
    covers the rest, so this avoids counting a victim twice)."""
    if not os.path.exists(DUSLR):
        return []
    counties = county_index(GAZ)
    box = state_boxes(counties, cent)
    out, moved = [], 0
    with open(DUSLR, encoding='utf-8', errors='replace') as f:
        for i, r in enumerate(csv.DictReader(f)):
            if r['source'] != 'tolnay-beck':
                continue
            parts = [p.strip() for p in r['lynch_location'].split(',')]
            st = STATE_ABBR.get(parts[-1])
            if st is None:
                continue

            county = parts[-2].title() if len(parts) > 1 else ''
            m, d = month_day(r['lynch_date'])
            key = 'D%d' % i
            pt = (float(r['latitude']), float(r['longitude'])) if r['latitude'] else None
            if pt and not inside(box[st], pt):
                moved += 1
                pt = None
            if pt:
                lat, lon = jitter(key, pt[0], pt[1], TOWN_KM)
            else:
                g = counties.get((st, county.lower()))
                if g is None:
                    missing.append(('D', st, county, ''))
                    continue
                lat, lon = jitter(key, *cent[g])

            # DUSLR sets unknown days to the 1st; keep year and month only then.
            out.append([lat, lon, year(r['year']), m, d,
                        r['victim_name'].title(), r['victim_race'].title(), '', '',
                        county.replace(' County', '').replace(' Parish', ''), st,
                        parts[0].title() if len(parts) > 2 else '', 'T'])
    print('DUSLR: %d town points outside their state, moved to county centroid' % moved)
    return out


# Slack around a state's county centroids, in degrees: a town point
# outside this box was geocoded to the wrong place.
BOX_PAD = 0.6


def state_boxes(counties, cent):
    box = {}
    for (st, _), g in counties.items():
        lat, lon = cent[g]
        b = box.setdefault(st, [lat, lon, lat, lon])
        box[st] = [min(b[0], lat), min(b[1], lon), max(b[2], lat), max(b[3], lon)]
    return {k: [b[0] - BOX_PAD, b[1] - BOX_PAD, b[2] + BOX_PAD, b[3] + BOX_PAD] for k, b in box.items()}


def inside(b, pt):
    return b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3]


def states():
    """State outlines and [abbr, name, lat, lon] labels."""
    geo = json.load(open(STATES))
    for f in geo['features']:
        f['properties'] = {'s': f['properties']['STUSPS']}
    labels = []
    for f in json.load(open(LABELS))['features']:
        p = f['properties']
        lon, lat = f['geometry']['coordinates']
        lat, lon = LABEL_AT.get(p['STUSPS'], (lat, lon))
        labels.append([p['STUSPS'], p['NAME'], round(lat, 2), round(lon, 2)])
    return geo, labels


def main():
    mon = symbols()
    cent = centroids()
    missing = []
    lyn = seguin_rigby(cent, missing) + (tolnay_beck(cent, missing) or duslr(cent, missing))

    meta = {'mon': len(mon), 'lyn': len(lyn),
            'tb': 'full' if os.path.exists(TB) else 'duslr' if os.path.exists(DUSLR) else '',
            'tbStates': TB_STATES,
            'unplaced': len(missing)}
    sep = (',', ':')
    with open('data.js', 'w') as out:
        out.write('// Generated by tools/build.py. Do not edit.\n')
        out.write('var MON=' + json.dumps(mon, separators=sep) + ';\n')
        out.write('var LYN=' + json.dumps(lyn, separators=sep) + ';\n')
        out.write('var META=' + json.dumps(meta, separators=sep) + ';\n')
        geo, labels = states()
        out.write('var STATES=' + json.dumps(geo, separators=sep) + ';\n')
        out.write('var STATE_LABELS=' + json.dumps(labels, separators=sep) + ';\n')

    print(meta)
    for m in missing[:20]:
        print('unplaced', m)


if __name__ == '__main__':
    main()
