from datetime import datetime
from zoneinfo import ZoneInfo


def india_today():return datetime.now(ZoneInfo('Asia/Kolkata')).date()
