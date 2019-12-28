from datetime import datetime
from src.const import TIME_NICE_FORMAT


def get_utc_machine():
    return int((datetime.utcnow() - datetime(1970, 1, 1)).total_seconds()) * 1000


def get_utc_nice():
    return datetime.utcnow().strftime(TIME_NICE_FORMAT)

