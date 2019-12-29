import multiprocessing
import logging
import yaml
import utils
from archiver import StreamArchiver

from const import (

    LOG_LEVEL_DEFAULT,
    STREAMLINK_BINARY

)
class LoggingHandler(logging.StreamHandler):
    def __init__(self):
        logging.StreamHandler.__init__(self)
        fmt = '%(asctime)s %(filename)-18s %(levelname)-8s: [%(processName)s] %(message)s'
        fmt_date = '%Y-%m-%d %T %Z'
        formatter = logging.Formatter(fmt, fmt_date)
        self.setFormatter(formatter)


if __name__ == '__main__':


    # Load up the config

    # Load the streams from config_dev.yml
    with open(r'../config.yml') as f:
        config = utils.try_get(yaml.load(f, Loader=yaml.FullLoader), lambda x: x['config']) or {}

    # Configure logging
    log = logging.getLogger('root')
    log_level = utils.try_get(config, lambda x: x['log_level'], str) or LOG_LEVEL_DEFAULT
    log.addHandler(LoggingHandler())
    log.setLevel(log_level)

    # Load the streams from config_dev.yml
    with open(r'../streamers.yml') as f:
        data = yaml.load(f, Loader=yaml.FullLoader)['streamers']

    jobs = []
    for st in data:

        process = multiprocessing.Process(target=StreamArchiver().main,
                                          kwargs=data[st], name=data[st]['name'])
        jobs.append(process)

    for j in jobs:
        j.start()
