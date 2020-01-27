import multiprocessing
import logging
import yaml
import utils
import os
from archiver import StreamArchiver

from const import (

    LOG_LEVEL_DEFAULT,
    STREAMLINK_BINARY

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


if __name__ == '__main__':

    # Load the config from config.yml
    with open(CONFIG_FILE) as f:
        config = utils.try_get(yaml.load(f, Loader=yaml.FullLoader), lambda x: x['config']) or {}

    # Configure logging
    log = logging.getLogger('root')
    log_level = utils.try_get(config, lambda x: x['log_level'], str) or LOG_LEVEL_DEFAULT
    log.addHandler(LoggingHandler())
    log.setLevel(log_level)

    # Load the streams
    with open(STREAMERS_FILE) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)['streamers']

    log.info(config)

    jobs = []
    for st in data:

        data[st]['make_dirs'] = bool(utils.try_get(src=config, getter=lambda x: x['make_dirs'], expected_type=bool)) or True
        data[st]['streamlink_bin'] = str(
            utils.try_get(src=config, getter=lambda x: x['streamlink_bin'], expected_type=str)) or STREAMLINK_BINARY

        process = multiprocessing.Process(target=StreamArchiver().main,
                                          kwargs=data[st], name=data[st]['name'])
        jobs.append(process)

    for j in jobs:
        j.start()
