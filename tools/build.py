"""Build data.js: Confederate symbols and lynching victims, by year.

Inputs (in data/, git-ignored):
  splc_whose_heritage.xlsx   SPLC "Whose Heritage?" master sheet, from
      https://docs.google.com/spreadsheets/d/1W4H2qa2THM1ni53QYZftGob_k_Bf9HreFAtCERfjCIU/export?format=xlsx
  seguin_rigby_2019.csv      Seguin & Rigby (2019) national lynching data,
      38 states outside the Tolnay-Beck South, https://osf.io/kr8yc
  tolnay_beck.csv            optional; Tolnay-Beck inventory (10 Southern
      states), requested via the contact form at https://sites.uw.edu/lynching/
  2023_Gaz_counties_national.txt   Census county centroids, from
      https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/

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
GAZ = os.path.join(DATA, '2023_Gaz_counties_national.txt')

# Offset victims up to this far from the county centroid (km), so cases
# in one county don't stack on one dot.
SPREAD_KM = 12

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


def jitter(key, lat, lon):
    """Fixed pseudo-random offset within SPREAD_KM, seeded by the case id."""
    h = hashlib.sha1(key.encode()).digest()
    a = h[0] / 255 * 2 * math.pi
    r = math.sqrt(h[1] / 255) * SPREAD_KM
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


def main():
    mon = symbols()
    cent = centroids()
    missing = []
    lyn = seguin_rigby(cent, missing) + tolnay_beck(cent, missing)

    meta = {'mon': len(mon), 'lyn': len(lyn),
            'tb': os.path.exists(TB), 'tbStates': TB_STATES,
            'unplaced': len(missing)}
    sep = (',', ':')
    with open('data.js', 'w') as out:
        out.write('// Generated by tools/build.py. Do not edit.\n')
        out.write('var MON=' + json.dumps(mon, separators=sep) + ';\n')
        out.write('var LYN=' + json.dumps(lyn, separators=sep) + ';\n')
        out.write('var META=' + json.dumps(meta, separators=sep) + ';\n')

    print(meta)
    for m in missing[:20]:
        print('unplaced', m)


if __name__ == '__main__':
    main()
