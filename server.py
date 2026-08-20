#!/usr/bin/env python3
"""Telemetry Trust Gate: dependency-free, offline browser demo."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import json, math, os, random, threading, time

ROOT = Path(__file__).parent


class Simulator:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with getattr(self, "lock", threading.Lock()):
            self.tick = 0
            self.event_id = 0
            self.score = 97.0
            self.threshold = 72
            self.paused = False
            self.burst = 0
            self.bedrock_up = True
            self.events, self.logs, self.history = [], [], []
            self.counts = {"total": 0, "safe": 0, "anomalous": 0, "rules": 0,
                           "llm": 0, "cache_hits": 0, "cache_misses": 0, "fallbacks": 0}
            self.queue_depth = 0
            self.last_latency = 0
            self.last_justification = "All signals are inside the learned operating envelope."
            self._log("system", "Redis stream robot:telemetry ready; consumer group gate online")

    def _log(self, source, message):
        self.logs.insert(0, {"time": time.strftime("%H:%M:%S"), "source": source, "message": message})
        self.logs = self.logs[:14]

    def step(self):
        with self.lock:
            if self.paused:
                return
            self.tick += 1
            self.event_id += 1
            bad = self.burst > 0
            if bad: self.burst -= 1
            angle = self.tick / 4
            position = round(48 + 12 * math.sin(angle) + random.uniform(-1.5, 1.5), 1)
            torque = round((86 + random.uniform(-5, 8)) if bad else (51 + 6 * math.sin(angle / 2) + random.uniform(-3, 3)), 1)
            temp = round((81 + random.uniform(-2, 4)) if bad else (43 + 3 * math.sin(angle / 3) + random.uniform(-1.5, 1.5)), 1)
            # The review band follows the operator's hard limit. Lowering the
            # limit deliberately sends more near-limit readings for context.
            ambiguous = (self.threshold - 14 <= torque <= self.threshold) or (60 <= temp <= 69)
            critical = torque > self.threshold or temp > 75
            route, verdict, cache = "rules", "safe", None
            latency = random.randint(7, 16)
            reason = "Within torque and thermal thresholds."
            if critical:
                verdict = "anomalous"
                reason = f"Hard rule tripped: {'torque' if torque > self.threshold else 'temperature'} exceeds safe limit."
                self.counts["rules"] += 1
            elif ambiguous:
                route = "llm"
                self.queue_depth = min(8, self.queue_depth + 1)
                self.counts["llm"] += 1
                # Repeated operating envelopes reuse a prior classification.
                cache = "hit" if self.counts["llm"] % 3 == 0 else "miss"
                self.counts["cache_hits" if cache == "hit" else "cache_misses"] += 1
                if not self.bedrock_up:
                    route = "fallback"
                    verdict = "safe" if torque < self.threshold - 3 else "anomalous"
                    latency = random.randint(18, 30)
                    reason = "Bedrock unavailable; conservative local policy evaluated the event."
                    self.counts["fallbacks"] += 1
                else:
                    latency = random.randint(42, 80) if cache == "hit" else random.randint(150, 260)
                    verdict = "safe" if torque < 68 and temp < 66 else "anomalous"
                    reason = ("Pattern is transient and consistent with controlled acceleration."
                              if verdict == "safe" else "Combined load and heat trend indicates unsafe mechanical stress.")
                    self._log("llm", f"{verdict.upper()} · {reason}")
            else:
                self.counts["rules"] += 1
            delta = -22 if verdict == "anomalous" else 2.2
            self.score = max(0, min(100, self.score * .86 + (100 if verdict == "safe" else 0) * .14 + (delta if verdict == "anomalous" else 0)))
            self.last_latency = latency
            self.last_justification = reason
            self.counts["total"] += 1
            self.counts[verdict] += 1
            self.queue_depth = max(0, self.queue_depth - (1 if random.random() < .8 else 0))
            event = {"id": f"evt-{self.event_id:04d}", "position": position, "torque": torque,
                     "temp": temp, "route": route, "verdict": verdict, "latency": latency,
                     "cache": cache, "reason": reason, "at": time.strftime("%H:%M:%S")}
            self.events.insert(0, event); self.events = self.events[:10]
            self.history.append(round(self.score, 1)); self.history = self.history[-40:]
            self._log("gate", f"{event['id']} → {verdict.upper()} via {route} ({latency}ms)")

    def snapshot(self):
        with self.lock:
            return {"score": round(self.score, 1), "threshold": self.threshold, "paused": self.paused,
                    "burst": self.burst, "bedrock_up": self.bedrock_up, "events": self.events,
                    "logs": self.logs, "history": self.history, "counts": self.counts,
                    "queue_depth": self.queue_depth, "last_latency": self.last_latency,
                    "last_justification": self.last_justification,
                    "gate": "SHIP" if self.score >= 70 else "BLOCK"}

SIM = Simulator()

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlparse(self.path).path == "/api/status":
            self.send_json(SIM.snapshot()); return
        self.path = "/index.html" if self.path == "/" else self.path
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            size = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(size) or b"{}")
        except Exception: body = {}
        with SIM.lock:
            if path == "/api/inject":
                SIM.burst += 6; SIM._log("operator", "Injected 6-event bad telemetry burst")
            elif path == "/api/pause":
                SIM.paused = not SIM.paused; SIM._log("operator", "Stream " + ("paused" if SIM.paused else "resumed"))
            elif path == "/api/bedrock":
                SIM.bedrock_up = not SIM.bedrock_up; SIM._log("system", "Bedrock " + ("recovered" if SIM.bedrock_up else "OUTAGE — local fallback armed"))
            elif path == "/api/threshold":
                SIM.threshold = max(60, min(90, int(body.get("value", 72)))); SIM._log("operator", f"Torque threshold set to {SIM.threshold} Nm")
            elif path == "/api/reset":
                pass
            else:
                self.send_error(404); return
        if path == "/api/reset": SIM.reset()
        self.send_json(SIM.snapshot())

    def send_json(self, value):
        data = json.dumps(value).encode(); self.send_response(200)
        self.send_header("Content-Type", "application/json"); self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def log_message(self, *_): pass

def loop():
    while True: SIM.step(); time.sleep(1)

if __name__ == "__main__":
    os.chdir(ROOT); threading.Thread(target=loop, daemon=True).start()
    port = int(os.environ.get("PORT", "8000"))
    print(f"Telemetry Trust Gate → http://localhost:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
