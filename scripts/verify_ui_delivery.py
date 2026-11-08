"""Preserve UI hashes and generate an independently tested rollback transaction."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "build" / "evidence-ui"
FILES = {"App.tsx": "frontend/src/App.tsx", "style.css": "frontend/src/style.css", "main.cjs": "desktop/main.cjs"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    baseline = EVIDENCE / "compact-baseline"
    assert all((baseline / name).is_file() for name in FILES)
    hashes = {"baseline": {name: digest(baseline / name) for name in FILES},
              "modified": {name: digest(ROOT / relative) for name, relative in FILES.items()}}
    (EVIDENCE / "HASHES.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    modified = EVIDENCE / "MODIFIED_FILE.tsx"
    diff = EVIDENCE / "DIFF_FILE.patch"
    verification = EVIDENCE / "VERIFICATION.txt"
    rollback = EVIDENCE / "ROLLBACK.sh"
    shutil.copy2(ROOT / "frontend/src/App.tsx", modified)
    diffs = []
    for name, relative in FILES.items():
        diffs.extend(difflib.unified_diff((baseline / name).read_text(encoding="utf-8").splitlines(keepends=True),
            (ROOT / relative).read_text(encoding="utf-8").splitlines(keepends=True),
            fromfile="baseline/" + relative, tofile="modified/" + relative))
    diff.write_text("".join(diffs), encoding="utf-8", newline="\n")
    rollback.write_text('''#!/usr/bin/env bash
set -euo pipefail
here="$(cd -- "$(dirname -- "$0")" && pwd)"
if command -v cygpath >/dev/null 2>&1; then here="$(cygpath -w "$here")"; fi
python - "$here" "${1:?Pass the explicit target copy directory}" <<'PY'
import hashlib,json,shutil,sys
from pathlib import Path
evidence=Path(sys.argv[1]).resolve()
target=Path(sys.argv[2]).resolve()
hashes=json.loads((evidence/'HASHES.json').read_text())
files={'App.tsx':'frontend/src/App.tsx','style.css':'frontend/src/style.css','main.cjs':'desktop/main.cjs'}
for name,relative in files.items():
    source=evidence/'compact-baseline'/name
    destination=target/relative
    assert hashlib.sha256(source.read_bytes()).hexdigest()==hashes['baseline'][name]
    assert destination.is_file(), str(destination)
    assert hashlib.sha256(destination.read_bytes()).hexdigest() in (hashes['modified'][name],hashes['baseline'][name])
for name,relative in files.items():
    destination=target/relative
    shutil.copy2(evidence/'compact-baseline'/name,destination)
    assert hashlib.sha256(destination.read_bytes()).hexdigest()==hashes['baseline'][name]
print('restored=baseline; hashes=3/3')
print('PASS')
PY
''', encoding="utf-8", newline="\n")
    rollback.chmod(0o755)
    bash = Path("C:/Program Files/Git/bin/bash.exe")
    if not bash.exists():
        bash = Path(shutil.which("bash") or "bash")
    subprocess.run([str(bash), "-c", 'chmod +x "$1" && test -x "$1"', "sh", str(rollback)], check=True)
    copy = EVIDENCE / "rollback-copy"
    for _, relative in FILES.items():
        target = copy / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    records = []
    def run(label, command, input_description):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace",
                                env={**os.environ, "PYTHONUTF8": "1"})
        records.append(f"{label}\nCOMMAND: {subprocess.list2cmdline(command)}\nINPUT: {input_description}\n"
                       f"STDOUT:\n{result.stdout}STDERR:\n{result.stderr}EXIT: {result.returncode}\n")
        assert result.returncode == 0, records[-1]
        return result.stdout
    probe = str(ROOT / "scripts/ui_contract_probe.py")
    run("BASELINE", [sys.executable, probe, str(baseline), "baseline"], "preserved pre-review UI source")
    run("MODIFIED", [sys.executable, probe, str(ROOT), "modified"], "delivered UI source")
    run("ROLLBACK", [str(bash), str(rollback), str(copy)], "independent copy of modified UI; live workspace remains changed")
    run("RESTORED_BEHAVIOR", [sys.executable, probe, str(copy), "baseline"], "independently restored copy")
    run("UNIT_TESTS", [sys.executable, "-m", "unittest", "discover", "-q"], "47 backend/worker contracts; no network")
    packaged = json.loads((ROOT / "build/packaged-smoke/REPORT.json").read_text(encoding="utf-8"))
    assert packaged["status"] == "PASS" and packaged["remote_bytes_equal"] is True
    assert digest(modified) == hashes["modified"]["App.tsx"]
    for name, relative in FILES.items():
        assert digest(ROOT / relative) == hashes["modified"][name]
    text = ("CHANGED FIELDS: design badge removed; rail decoration removed; quality badge removed; code-link footer removed; "
            "rail top padding=0 (intermediate placeholder removed); default window 1360x940 -> 1120x820; primary action pinned outside scroll pane.\n"
            + "\n".join(f"{key}: {path}" for key, path in (("MODIFIED_FILE", modified), ("DIFF_FILE", diff),
                ("VERIFICATION", verification), ("ROLLBACK", rollback))) + "\n\nHASHES:\n" + json.dumps(hashes, indent=2)
            + "\n\n" + "\n".join(records) + "\nPACKAGED LIVE DESKTOP:\n" + json.dumps(packaged, ensure_ascii=False, indent=2)
            + "\n\nRESTORED STATUS: baseline restored on independent copy; 3/3 hashes match; baseline behavior PASS; "
              "delivered workspace and MODIFIED_FILE remain modified.\n")
    verification.write_text(text, encoding="utf-8")
    for artifact in (modified, diff, verification, rollback):
        assert artifact.read_bytes(), str(artifact)
        print(f"REOPENED {artifact.name} {digest(artifact)}")
    print("VERIFICATION PASS")


if __name__ == "__main__":
    main()
