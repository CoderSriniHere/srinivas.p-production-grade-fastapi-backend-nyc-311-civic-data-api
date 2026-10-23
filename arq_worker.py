from arq.connections import RedisSettings

from app.config import get_settings
from app.services.report_service import generate_agency_report

settings = get_settings()


class WorkerSettings:
    functions = [generate_agency_report]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 120