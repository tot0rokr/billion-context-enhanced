import gzip
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        data = self.rfile.read(int(self.headers.get("content-length", "0")))
        if self.headers.get("content-encoding") == "gzip":
            data = gzip.decompress(data)
        try:
            payload = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {"unparsed_bytes": len(data), "content_type": self.headers.get("content-type")}
        with Path("/audit/otel.jsonl").open("a") as output:
            output.write(json.dumps({"at": time.time(), "path": self.path, "payload": payload}) + "\n")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 4318), Handler).serve_forever()
