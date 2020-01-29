import multiprocessing
import logging
import yaml
import utils
import json
import argparse
import rclone
from time import sleep
from archiver import StreamArchiver
from exceptions import RequiredValueError
from const import (

    LOG_LEVEL_DEFAULT,
    STREAMLINK_BINARY,
    STREAMERS_REQUIRED_FIELDS,
    RCLONE_PROCESS_REPEAT_TIME

)


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
        stream_job['streamlink_bin'] = utils.try_get(src=config_conf, getter=lambda x: x['streamlink_bin'], expected_type=str) or STREAMLINK_BINARY

        jobs[stream] = stream_job

    return jobs


def create_hash(data: dict):
    return hash(frozenset(json.dumps(data, sort_keys=True)))


def streamers_watcher(config_conf: dict, streamers_file: str):

    active = True
    current_proc = {}  # keys are the keys of streamers
    first_run = True
    no_streams = False
    while active:
        # Load the streams
        with open(streamers_file) as f:
            streamers = yaml.load(f, Loader=yaml.FullLoader)['streamers'] or {}

        # create the jobs
        jobs = create_jobs(config_conf, streamers)

        if first_run:
            if len(streamers) > 0:
                log.info(f"Adding {len(streamers)} streams")
            first_run = False

        if len(streamers) == 0 and len(current_proc) == 0:
            if not no_streams: # only want this message to be said once
                log.info("No streams in streamers file - waiting for any to be added.")
                no_streams = True

        # check if we have any removed streams
        removed = set(current_proc.keys()) - set(jobs.keys())

        for remove in removed:
            log.info(f"{remove} as been removed from the config file, terminating.")
            current_proc[remove]['process'].terminate()
            current_proc.pop(remove)

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

            if no_streams:
                no_streams = False

        sleep(15)


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("--config-file", help="path to config.yml", required=True)
    parser.add_argument("--streamers-file", help="path to streamers.yml", required=True)
    parser.add_argument("--disable-rclone", help="enable the rclone auto upload feature", action="store_true")
    args = parser.parse_args()

    CONFIG_FILE = args.config_file
    STREAMERS_FILE = args.streamers_file

    # Load the config from config.yml
    with open(CONFIG_FILE) as f:
        d = yaml.load(f, Loader=yaml.FullLoader)
        config = utils.try_get(d, lambda x: x['config']) or {}
        config_rclone = utils.try_get(d, lambda x: x['rclone']) or {}
    # Configure logging
    log = logging.getLogger('root')
    log_level = utils.try_get(config, lambda x: x['log_level'], str) or LOG_LEVEL_DEFAULT
    log.addHandler(utils.LoggingHandler())
    log.setLevel(log_level)
    log.debug(config)
    log.debug(config_rclone)

    stream_proc = multiprocessing.Process(target=streamers_watcher, args=(config, STREAMERS_FILE), name="StreamWatcher")
    stream_proc.start()

    if not args.disable_rclone:
        rclone_delay = utils.try_get(config_rclone, lambda x: x['sleep_interval'], expected_type=int) or RCLONE_PROCESS_REPEAT_TIME
        rclone_proc = multiprocessing.Process(target=rclone.rclone_watcher, args=(config_rclone, STREAMERS_FILE, rclone_delay), name="rcloneWatcher")
        rclone_proc.start()

    stream_proc.join()