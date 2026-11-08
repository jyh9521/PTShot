"""Observe baseline / delivered / restored behavior without network access."""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("probe_target", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
url = "https://img1.pixhost.to/images/1/1_sample.png"
code = module.bbcode_for_urls([url])
compress = module.compression_required(10_000_001)
state = "modified" if code == f"[img]{url}[/img]" and compress else "baseline"
print(f"bbcode={code!r}; compression(10000001)={compress}; state={state}")
assert state == sys.argv[2], (state, sys.argv[2])
print("PASS")
