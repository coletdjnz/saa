from datetime import datetime
from const import TIME_NICE_FORMAT


def get_utc_machine():
    return int((datetime.utcnow() - datetime(1970, 1, 1)).total_seconds()) * 1000


def get_utc_nice():
    return datetime.utcnow().strftime(TIME_NICE_FORMAT)


def try_get(src, getter, expected_type=None):
    # From youtube-dl codebase:
    # https://github.com/ytdl-org/youtube-dl/blob/941e359e9512c1c75d42cb5b4b248816e16edb82/youtube_dl/utils.py#L3901
    if not isinstance(getter, (list, tuple)):
        getter = [getter]
    for get in getter:
        try:
            v = get(src)
        except (AttributeError, KeyError, TypeError, IndexError):
            pass
        else:
            if expected_type is None or isinstance(v, expected_type):
                return v

