import multiprocessing
import logging
import yaml
import utils
import os
import json
from time import sleep
from archiver import StreamArchiver
from exceptions import RequiredValueError
from const import (

    LOG_LEVEL_DEFAULT,
    STREAMLINK_BINARY,
    STREAMERS_REQUIRED_FIELDS

)

STREAMERS_FILE = os.getenv("STREAMERS_CONFIG", "../streamers.yml")
CONFIG_FILE = os.getenv("CONFIG", "../config.yml")


def create_jobs(config_conf:dict, streamers_conf: dict):
    """

    Parses the configs to create a dict that can be sent to archiver.py, and jobs
    :return:
    """
    jobs = {}
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

        jobs[stream] = stream_job

    return jobs


def create_hash(data: dict):
    return hash(frozenset(json.dumps(data, sort_keys=True)))


def streamers_watcher(config_conf: dict, streamers_file: str):

    active = True
    current_proc = {}  # keys are the keys of streamers
    first_run = True
    while active:
        # Load the streams
        with open(streamers_file) as f:
            streamers = yaml.load(f, Loader=yaml.FullLoader)['streamers']

        # create the jobs
        jobs = create_jobs(config_conf, streamers)

        if first_run:
            log.info("Adding streams")
            first_run = False

        for j in jobs:

            j_inner = jobs[j]
            if j in current_proc:
                # TODO: here we could also check if the process is still running
                # check if hash is different
                if current_proc[j]['config_hash'] == create_hash(j_inner):
                    # Skip if stream is already added and no config has changed
                    continue
                else:
                    log.info(f"{j}'s config has changed, recreating process.")
                    current_proc[j]['process'].terminate()
            else:
                if not first_run:
                    log.info(f"Adding new stream: {j_inner['name']}")

            # create a process
            process = multiprocessing.Process(target=StreamArchiver().main, kwargs=j_inner, name=j_inner['name'])
            current_proc[j] = {'process': process, 'config_hash': create_hash(j_inner)}
            process.start()

        sleep(15)


if __name__ == '__main__':

    # Load the config from config.yml
    with open(CONFIG_FILE) as f:
        config = utils.try_get(yaml.load(f, Loader=yaml.FullLoader), lambda x: x['config']) or {}

    # Configure logging
    log = logging.getLogger('root')
    log_level = utils.try_get(config, lambda x: x['log_level'], str) or LOG_LEVEL_DEFAULT
    log.addHandler(utils.LoggingHandler())
    log.setLevel(log_level)
    log.debug(config)

    streamers_watcher(config, STREAMERS_FILE)
