from __future__ import annotations
import logging

from app.scheduler.instance import scheduler
from app.scheduler.meter_reader import scheduled_task_of_fetching_kwh_data_from_mbus

log = logging.getLogger("mbusreader.scheduler")




def start_scheduler() -> None:
    if scheduler.running:
        return

    scheduler.add_job(
        scheduled_task_of_fetching_kwh_data_from_mbus,
        trigger="cron",
        minute="0,15,30,45",
        second=0,
        id="mbus_read",
        replace_existing=True,
        max_instances=1,
        coalesce=True,          # missed-runs policy: do NOT run 3 times after downtime; run once
        misfire_grace_time=600  # only run a missed tick if we're not too late (e.g., <= 10 minutes late)
    )

    scheduler.start()
    log.info("Scheduler started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")

