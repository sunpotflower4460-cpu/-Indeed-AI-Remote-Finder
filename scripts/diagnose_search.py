#!/usr/bin/env python3
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import fetch_jobs as finder

OUT = Path(__file__).resolve().parents[1] / "data" / "diagnostics.json"
rows = []
for category, query in finder.QUERIES:
    try:
        root = ET.fromstring(finder.fetch(query))
    except Exception as exc:
        rows.append({"category": category, "error": str(exc)})
        continue
    items = []
    for item in root.findall('.//item')[:5]:
        items.append({
            "title": finder.clean(item.findtext('title')),
            "link": finder.clean(item.findtext('link')),
            "description": finder.clean(item.findtext('description'))[:400],
            "pubDate": finder.clean(item.findtext('pubDate')),
        })
    rows.append({"category": category, "query": query, "items": items})
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote diagnostics to {OUT}")
