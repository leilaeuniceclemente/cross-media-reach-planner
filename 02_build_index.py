#!/usr/bin/env python3
"""
02_build_index.py
-----------------
Builds index.html by injecting data.json into index_template.html.
Run 01_generate_data.py first. Re-run order is always 01 then 02.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

with open(os.path.join(ROOT, "index_template.html")) as f:
    template = f.read()
with open(os.path.join(ROOT, "data.json")) as f:
    data = f.read()

if "__DATA__" not in template:
    raise SystemExit("Template is missing the __DATA__ placeholder.")

html = template.replace("__DATA__", data)

out = os.path.join(ROOT, "index.html")
with open(out, "w") as f:
    f.write(html)

print(f"Built {out}  ({len(html)/1024:.1f} KB)")
