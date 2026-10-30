"""Download a bounded, attributed OSM context layer for the FRA airfield map.

Usage: python scripts/fetch_fra_context.py
Only public OSM map API responses are used; no imagery or inferred taxiways.
Coordinates are simplified to a 3 m tolerance and rounded to six decimals.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import math
from pathlib import Path
import time
import urllib.request

BBOX = [8.485, 49.993, 8.610, 50.061]
COPYRIGHT = "https://www.openstreetmap.org/copyright"
HEADERS = {"User-Agent": "FRA-WindLab-hackathon/1.0 (public airport map context)"}


def fetch(bounds):
    url = "https://api.openstreetmap.org/api/0.6/map.json?bbox=" + ",".join(f"{v:.6f}" for v in bounds)
    for attempt in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as response:
                data = json.load(response)
            print(f"Fetched {len(data['elements'])} elements: {url}", flush=True)
            return url, data["elements"]
        except Exception:
            if attempt:
                raise
            time.sleep(2)


def simplify(coords, tolerance=3):
    """Ramer-Douglas-Peucker in a local metre approximation at 50 degrees N."""
    if len(coords) < 3:
        return coords
    xscale, yscale = 111320 * math.cos(math.radians(50.03)), 111320
    a, b = coords[0], coords[-1]
    dx, dy = (b[0] - a[0]) * xscale, (b[1] - a[1]) * yscale
    den = dx * dx + dy * dy
    max_distance, index = 0, 0
    for i, point in enumerate(coords[1:-1], 1):
        px, py = (point[0] - a[0]) * xscale, (point[1] - a[1]) * yscale
        t = max(0, min(1, (px * dx + py * dy) / den)) if den else 0
        distance = math.hypot(px - t * dx, py - t * dy)
        if distance > max_distance:
            max_distance, index = distance, i
    if max_distance > tolerance:
        return simplify(coords[:index + 1], tolerance)[:-1] + simplify(coords[index:], tolerance)
    return [a, b]


def kind_for(tags):
    if tags.get("aeroway") == "aerodrome" and (tags.get("icao") == "EDDF" or "Frankfurt" in tags.get("name", "")):
        return "airport-boundary"
    if tags.get("aeroway") in {"taxiway", "apron"}:
        return tags["aeroway"]
    if tags.get("highway") in {"motorway", "motorway_link", "trunk", "trunk_link"}:
        return "motorway"
    if tags.get("landuse") == "forest" or tags.get("natural") == "wood":
        return "forest"
    if tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
        return "water"
    if tags.get("aeroway") == "hangar" or tags.get("building") in {"hangar", "warehouse"}:
        return "airport-building"
    if tags.get("name", "").lower() in {"cargo city süd", "cargo city nord", "cargocity süd", "cargocity nord"}:
        return "cargo"
    return None


def feature(osm_type, osm_id, tags, kind, geometry):
    # Collection-level ODbL attribution applies to every feature; keep unique
    # OSM object links here without repeating the same license text 1,000+ times.
    props = {"kind": kind, "osmType": osm_type, "osmID": osm_id,
             "sourceURL": f"https://www.openstreetmap.org/{osm_type}/{osm_id}"}
    for tag in ("name", "ref", "aeroway", "highway", "building", "landuse", "natural", "surface", "width"):
        if tag in tags:
            props[tag] = tags[tag]
    return {"type": "Feature", "id": f"osm-{osm_type}-{osm_id}", "properties": props, "geometry": geometry}


def join_rings(segments):
    """Join complete OSM member ways, retaining only actually closed rings."""
    pending = [list(s) for s in segments if s]
    rings = []
    while pending:
        ring = pending.pop()
        while ring[0] != ring[-1]:
            for i, seg in enumerate(pending):
                if ring[-1] == seg[0]:
                    ring.extend(seg[1:]); pending.pop(i); break
                if ring[-1] == seg[-1]:
                    ring.extend(seg[-2::-1]); pending.pop(i); break
                if ring[0] == seg[-1]:
                    ring = seg[:-1] + ring; pending.pop(i); break
                if ring[0] == seg[0]:
                    ring = seg[:0:-1] + ring; pending.pop(i); break
            else:
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


def inside(point, ring):
    x, y = point
    result = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            result = not result
        j = i
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "dist/data/fra-context.json")
    args = parser.parse_args()
    west, south, east, north = BBOX
    boxes = [[west + (east-west)*x/4, south + (north-south)*y/2,
              west + (east-west)*(x+1)/4, south + (north-south)*(y+1)/2]
             for y in range(2) for x in range(4)]
    elements, source_urls = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        for url, items in executor.map(fetch, boxes):
            source_urls.append(url)
            for item in items:
                elements[(item["type"], item["id"])] = item
    nodes = {key[1]: [round(value["lon"], 6), round(value["lat"], 6)]
             for key, value in elements.items() if key[0] == "node"}
    ways = {key[1]: value for key, value in elements.items() if key[0] == "way"}
    features, skipped = [], 0

    def coords_for(ids, polygon=False):
        if any(node not in nodes for node in ids):
            return None
        coords = [nodes[node] for node in ids]
        reduced = simplify(coords)
        return reduced if len(reduced) >= (4 if polygon else 2) else coords

    for (osm_type, osm_id), item in sorted(elements.items()):
        tags = item.get("tags", {})
        kind = kind_for(tags)
        if not kind:
            continue
        geometry = None
        if osm_type == "way":
            ids = item["nodes"]
            polygon = ids[0] == ids[-1] and kind not in {"taxiway", "motorway"}
            coords = coords_for(ids, polygon)
            if coords:
                geometry = {"type": "Polygon" if polygon else "LineString",
                            "coordinates": [coords] if polygon else coords}
        elif osm_type == "node" and kind == "cargo":
            geometry = {"type": "Point", "coordinates": nodes[osm_id]}
        elif osm_type == "relation" and tags.get("type") == "multipolygon":
            members = [m for m in item.get("members", []) if m["type"] == "way"]
            if any(m["ref"] not in ways for m in members):
                skipped += 1
                continue
            outers = join_rings([ways[m["ref"]]["nodes"] for m in members if m.get("role", "") in {"outer", ""}])
            inners = join_rings([ways[m["ref"]]["nodes"] for m in members if m.get("role") == "inner"])
            outer_coords = [coords_for(ids, True) for ids in outers]
            inner_coords = [coords_for(ids, True) for ids in inners]
            if outer_coords and all(outer_coords) and all(inner_coords):
                polygons = [[outer] + [inner for inner in inner_coords if inside(inner[0], outer)] for outer in outer_coords]
                geometry = {"type": "MultiPolygon", "coordinates": polygons}
        if geometry:
            features.append(feature(osm_type, osm_id, tags, kind, geometry))
    counts = {}
    for item in features:
        key = item["properties"]["kind"]
        counts[key] = counts.get(key, 0) + 1
    result = {"type": "FeatureCollection", "name": "Frankfurt Airport OSM airfield context",
              "retrievedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "bbox": BBOX,
              "coordinateSystem": "WGS84 longitude,latitude", "attribution": "© OpenStreetMap contributors",
              "license": "ODbL-1.0", "licenseURL": COPYRIGHT, "sourceURLs": source_urls,
              "simplificationToleranceM": 3, "featureCounts": counts,
              "coverageNote": "Eight bounded OSM map API queries; complete returned ways and complete multipolygon relations only. Features can extend beyond the query bounding box. Not for navigation.",
              "incompleteRelationsSkipped": skipped, "features": features}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(args.output), "bytes": args.output.stat().st_size, "counts": counts, "incompleteRelationsSkipped": skipped}))


if __name__ == "__main__":
    main()
