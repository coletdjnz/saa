import multiprocessing
import logging
import yaml
from archiver import StreamArchiver


LOG_LEVEL = "INFO"


class LoggingHandler(logging.StreamHandler):
    def __init__(self):
        logging.StreamHandler.__init__(self)
        fmt = '%(asctime)s %(filename)-18s %(levelname)-8s: [%(processName)s] %(message)s'
        fmt_date = '%Y-%m-%d %T %Z'
        formatter = logging.Formatter(fmt, fmt_date)
        self.setFormatter(formatter)


if __name__ == '__main__':

    log = logging.getLogger('root')
    log.setLevel(LOG_LEVEL)

    log.addHandler(LoggingHandler())

    # Load the streams from config_dev.yml
    with open(r'../config.yml') as f:
        data = yaml.load(f, Loader=yaml.FullLoader)

    jobs = []
    for st in data:

        process = multiprocessing.Process(target=StreamArchiver().main,
                                          kwargs=data[st], name=data[st]['name'])
        jobs.append(process)

    for j in jobs:
        j.start()
