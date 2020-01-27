import multiprocessing
import logging
import yaml
import utils
import os
from archiver import StreamArchiver
from exceptions import RequiredValueError
from const import (

    LOG_LEVEL_DEFAULT,
    STREAMLINK_BINARY,
    STREAMERS_REQUIRED_FIELDS

)

STREAMERS_FILE = os.getenv("STREAMERS_CONFIG", "../streamers.yml")
CONFIG_FILE = os.getenv("CONFIG", "../config.yml")


class LoggingHandler(logging.StreamHandler):
    def __init__(self):
        logging.StreamHandler.__init__(self)
        fmt = '%(asctime)s %(filename)-18s %(levelname)-8s: [%(processName)s] %(message)s'
        fmt_date = '%Y-%m-%d %T %Z'
        formatter = logging.Formatter(fmt, fmt_date)
        self.setFormatter(formatter)


def create_jobs(config_conf:dict, streamers_conf: dict):
    """

    Parses the configs to create a dict that can be sent to archiver.py, and jobs
    :return:
    """
    jobs = []
    for stream in streamers_conf:
        # create a copy, we are just editing a few values
        stream_job = streamers_conf[stream].copy()

        # check required fields

        for r in STREAMERS_REQUIRED_FIELDS:
            if r not in stream_job.keys():
                raise RequiredValueError(f"[{stream}] {r} is a required value.")
            else:
                if not isinstance(stream_job[r], STREAMERS_REQUIRED_FIELDS[r]):
                    raise TypeError(f"[{stream}] {r} needs to be a {STREAMERS_REQUIRED_FIELDS[r].__name__}, currently it is {type(stream_job[r]).__name__}.")
        if 'name' not in stream_job.keys():
            stream_job['name'] = stream
        stream_job['make_dirs'] = bool(utils.try_get(src=config_conf, getter=lambda x: x['make_dirs'], expected_type=bool)) or True
        stream_job['streamlink_bin'] = str(
            utils.try_get(src=config_conf, getter=lambda x: x['streamlink_bin'], expected_type=str)) or STREAMLINK_BINARY

        jobs.append(stream_job)

    return jobs


if __name__ == '__main__':

    # Load the config from config.yml
    with open(CONFIG_FILE) as f:
        config = utils.try_get(yaml.load(f, Loader=yaml.FullLoader), lambda x: x['config']) or {}

    # Configure logging
    log = logging.getLogger('root')
    log_level = utils.try_get(config, lambda x: x['log_level'], str) or LOG_LEVEL_DEFAULT
    log.addHandler(LoggingHandler())
    log.setLevel(log_level)
    log.debug(config)

    # Load the streams
    with open(STREAMERS_FILE) as f:
        streamers = yaml.load(f, Loader=yaml.FullLoader)['streamers']

    # create the jobs
    jobs = create_jobs(config, streamers)

    processes = []
    for j in jobs:
        process = multiprocessing.Process(target=StreamArchiver().main, kwargs=j, name=j['name'])
        processes.append(process)

    for p in processes:
        p.start()
