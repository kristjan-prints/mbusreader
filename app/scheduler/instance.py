from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler

# Keep one scheduler instance
scheduler = BackgroundScheduler(timezone=ZoneInfo("UTC"))