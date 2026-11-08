"""Observe the exact UI fields changed during review, including a restored copy."""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
flat = (root / "App.tsx").exists()
app = (root / "App.tsx" if flat else root / "frontend/src/App.tsx").read_text(encoding="utf-8")
css = (root / "style.css" if flat else root / "frontend/src/style.css").read_text(encoding="utf-8")
main = (root / "main.cjs" if flat else root / "desktop/main.cjs").read_text(encoding="utf-8")
badge = 'className="design-badge"' in app
decoration = 'className="rail-header"' in app
quality = 'className="quality-note"' in app
code_link = 'className="rail-footer"' in app
padding_match = re.search(r'\.rail-container\s*\{[^}]*padding:\s*(\d+)', css)
padding = int(padding_match[1]) if padding_match else 0
width, height = re.search(r'new BrowserWindow\(\{ width:\s*(\d+), height:\s*(\d+)', main).groups()
pinned = 'className="persistent-dock"' in app
state = "modified" if (not any((badge, decoration, quality, code_link)) and padding == 0
                         and (width, height) == ("1120", "820") and pinned) else "baseline"
print(f"state={state}; badge={int(badge)}; decoration={int(decoration)}; quality={int(quality)}; "
      f"code_link={int(code_link)}; rail_padding={padding}; window={width}x{height}; pinned_action={int(pinned)}")
assert state == sys.argv[2]
if state == "baseline":
    assert all((badge, decoration, quality, code_link)) and (width, height) == ("1360", "940") and not pinned
print("PASS")
