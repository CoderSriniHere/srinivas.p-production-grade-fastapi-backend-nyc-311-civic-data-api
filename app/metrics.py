from prometheus_client import Counter, Gauge
from prometheus_fastapi_instrumentator import Instrumentator

cache_hits_total = Counter("cache_hits_total", "Cache hits", ["endpoint"])
cache_misses_total = Counter("cache_misses_total", "Cache misses", ["endpoint"])
active_ws_connections = Gauge("active_ws_connections", "Currently open WebSocket connections")
report_jobs_total = Counter("report_jobs_total", "Report jobs submitted", ["status"])


def setup_instrumentator(app):
    instrumentator = Instrumentator()
    instrumentator.instrument(app)
    return instrumentator