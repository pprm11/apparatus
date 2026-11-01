"""Write diagrams.json (every mermaid block of the given Markdown files) next to measure.html.

Usage: python extract.py FILE.md ...
Then serve this folder (python -m http.server) and open measure.html; in the console run
  await measure({tight: true})      -> [id, width, height] per block
  await best(1000, 1300)             -> best direction per flowchart for a 1000 px column
"""
import json
import os
import re
import sys

out = []
for f in sys.argv[1:]:
    t = open(f, encoding="utf-8").read().replace("\r\n", "\n")
    for i, m in enumerate(re.finditer(r"```mermaid\n(.*?)```", t, re.S)):
        out.append({"f": os.path.basename(f)[:-3], "i": i + 1, "src": m.group(1)})
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagrams.json"), "w", encoding="utf-8"))
print(len(out), "blocks")
