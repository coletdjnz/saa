from datetime import datetime
from const import TIME_NICE_FORMAT
import logging
import json
from time import time
import hashlib


class LoggingHandler(logging.StreamHandler):
    def __init__(self):
        logging.StreamHandler.__init__(self)
        fmt = '%(asctime)s %(filename)-18s %(levelname)-8s: [%(processName)s] %(message)s'
        fmt_date = '%Y-%m-%d %T %Z'
        formatter = logging.Formatter(fmt, fmt_date)
        self.setFormatter(formatter)


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

def is_alive_safe(proc):

    try:
        return proc.is_alive()
    except AttributeError:
        return False


def time_test(func):
    """
    Decorator to time a function
    """
    def inner(*args, **kwargs):
        s = time()
        o = func(*args, **kwargs)
        e = time()
        print(f"{func.__name__} took {e-s}.")
        return o
    return inner


def hash_dict(data: dict):
    """

    Hashes a dictionary

    Note: Keys need to be strings.
    :param data: dictionary to be hashed
    :return: md5 hash
    """
    return hashlib.md5(repr(json.dumps(data, sort_keys=True, ensure_ascii=True)).encode('utf-8')).hexdigest()