import threading
import time
from collections import defaultdict

class TaskMetrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.metrics = defaultdict(lambda: {
            "executions": 0,
            "failures": 0,
            "last_success": None,
            "last_failure": None,
            "last_error": None,
            "last_duration": 0.0,
            "total_duration": 0.0,
        })

    def record(self, task_name, success, duration, error=None):
        with self.lock:
            m = self.metrics[task_name]
            m["executions"] = m.get("executions") or 0
            m["failures"] = m.get("failures") or 0
            m["total_duration"] = m.get("total_duration") or 0.0
            m["executions"] += 1
            m["last_duration"] = duration
            m["total_duration"] += duration
            if success:
                m["last_success"] = time.time()
            else:
                m["failures"] += 1
                m["last_failure"] = time.time()
                m["last_error"] = error

    def get_metrics(self):
        with self.lock:
            # Return a copy to avoid race conditions
            return {k: dict(v) for k, v in self.metrics.items()}

metrics_service = TaskMetrics() 