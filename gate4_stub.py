"""Gate 4 Sample D stub - a local OpenAI-compatible endpoint.

Serves POST /v1/chat/completions on 127.0.0.1 with a behavior chosen
by the STUB_MODE environment variable, so the PRODUCTION adapter,
parser, guard and runner entrypoint can be fault-tested offline
(design lock v2, Sample D) before any live call:

  valid      a well-formed plan response (stop)
  malformed  content that is not JSON
  empty      empty content (stop)
  truncated  partial JSON with finish_reason "length"
  slow       sleeps past the client timeout before answering
  error500   HTTP 500 with an error body

Every received request appends one line to the file named by
STUB_LOG, so the runner can verify the exact request count. The stub
is a test double: its results are never model evidence.
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

VALID_PLAN = json.dumps({"part_id": "part", "target_zone": "target_zone",
                         "approach_height_m": 0.15, "speed_scale": 0.5})

RESPONSES = {
    "valid": (200, VALID_PLAN, "stop"),
    "malformed": (200, "not json {", "stop"),
    "empty": (200, "", "stop"),
    "truncated": (200, '{"part_id": "par', "length"),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console quiet
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        log = os.environ.get("STUB_LOG")
        if log:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write("request\n")
        mode = os.environ.get("STUB_MODE", "valid")
        if mode == "slow":
            time.sleep(30)
        if mode == "error500":
            body = json.dumps({"error": {"message": "stub failure"}}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        _status, content, finish = RESPONSES.get(mode, RESPONSES["valid"])
        payload = {"id": "stub-response", "model": "stub-model",
                   "choices": [{"message": {"role": "assistant",
                                            "content": content},
                                "finish_reason": finish}]}
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("STUB_PORT", "8399"))
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
