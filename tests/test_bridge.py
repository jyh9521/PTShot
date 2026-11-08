import json
import os
import subprocess
import sys
import unittest


class BridgeTests(unittest.TestCase):
    def worker(self, request):
        return subprocess.run([sys.executable, "-u", "-m", "ptshot.bridge"], input=json.dumps(request) + "\n",
                              capture_output=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, timeout=15)

    def test_inspect_json_lines(self):
        result = self.worker({"action": "inspect"})
        self.assertEqual(result.returncode, 0, result.stderr)
        messages = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(messages[0]["type"], "result")
        self.assertIn("tools", messages[0])
        self.assertEqual(messages[-1], {"type": "finished", "ok": True})

    def test_bad_action_reported_with_failed_exit(self):
        result = self.worker({"action": "unknown"})
        self.assertEqual(result.returncode, 1)
        messages = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(messages[0]["type"], "error")
        self.assertFalse(messages[-1]["ok"])

    def test_worker_exits_with_stdin_still_open(self):
        child = subprocess.Popen([sys.executable, "-u", "-m", "ptshot.bridge"], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            child.stdin.write('{"action":"inspect"}\n')
            child.stdin.flush()
            child.wait(timeout=10)
            self.assertEqual(child.returncode, 0, child.stderr.read())
        finally:
            child.stdin.close()
            child.stdout.close()
            child.stderr.close()
            if child.poll() is None:
                child.kill()
