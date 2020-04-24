import multiprocessing
import logging
import yaml
import utils
import argparse
import rclone
from time import sleep
from archiver import StreamArchiver
from exceptions import RequiredValueError
from const import (

    LOG_LEVEL_DEFAULT,
    STREAMLINK_BINARY,
    STREAMERS_REQUIRED_FIELDS,
    RCLONE_PROCESS_REPEAT_TIME,
    STREAMERS_WATCHER_DEFAULT_SLEEP

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

        if 'enabled' not in stream_job.keys():
            stream_job['enabled'] = True
        stream_job['make_dirs'] = bool(utils.try_get(src=config_conf, getter=lambda x: x['make_dirs'], expected_type=bool)) or True
        stream_job['streamlink_bin'] = utils.try_get(src=config_conf, getter=lambda x: x['streamlink_bin'], expected_type=str) or STREAMLINK_BINARY

        jobs[stream] = stream_job

    return jobs


def streamers_watcher(config_conf: dict, streamers_file: str):
    """
    Main process that watches the streamers config file for changes

    Launches new processes for streams
    Terminates those processes when disabled etc.

    This function currently runs indefinitely.

    :param config_conf: dictionary containing the contents of a config.yml file
    :param streamers_file: path to the streamers.yml file
    :return:
    """
    active = True
    current_proc = {}  # keys are the keys of streamers
    first_run = True
    no_streams = False
    disabled_jobs = []
    while active:
        # Load the streams
        with open(streamers_file) as f:
            streamers = yaml.load(f, Loader=yaml.FullLoader)['streamers'] or {}

        # create the jobs
        jobs = create_jobs(config_conf, streamers)

        # remove any disabled streams
        for j in jobs:
            if jobs[j]['enabled'] is False:
                if j not in disabled_jobs:
                    disabled_jobs.append(j)
                    log.info(f'{j} has been disabled.')
            else:
                if j in disabled_jobs:
                    disabled_jobs.remove(j)
                    log.info(f'{j} has been enabled.')

        for disabled in disabled_jobs:
            jobs.pop(disabled)

        if first_run:
            if len(jobs) > 0:
                log.info(f"Adding {len(jobs)} streams")
            first_run = False

        if len(jobs) == 0 and len(current_proc) == 0:
            if not no_streams: # only want this message to be said once
                log.info("No streams (or enabled streams) in the streamers file - waiting for any to be added.")
                no_streams = True

        # check if we have any removed streams
        removed = set(current_proc.keys()) - set(jobs.keys())

        for remove in removed:
            if remove in disabled_jobs:
                log.info(f"{remove} has been disabled, terminating.")
            else:
                log.info(f"{remove} has been removed from the config file, terminating.")
            current_proc[remove]['process'].terminate()
            current_proc.pop(remove)

        for j in jobs:

            j_inner = jobs[j]
            if j in current_proc:
                # check if hash is different
                if current_proc[j]['config_hash'] == utils.hash_dict(j_inner):
                    # Check if the process is still running
                    if current_proc[j]['process'].is_alive():
                        # Skip if stream is already added and no config has changed, and is alive
                        continue
                    else:
                        log.error(f'Process {j} has crashed, restarting...')

                else:
                    log.info(f"{j}'s config has changed, recreating process.")
                    current_proc[j]['process'].terminate()
            else:
                if not first_run:
                    log.info(f"Adding new stream: {j_inner['name']}")

            # create a process
            process = multiprocessing.Process(target=StreamArchiver().main, kwargs=j_inner, name=j_inner['name'])
            current_proc[j] = {'process': process, 'config_hash': utils.hash_dict(j_inner)}
            process.start()

            if no_streams:
                no_streams = False

        sleep(STREAMERS_WATCHER_DEFAULT_SLEEP)


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
    log.debug(f"general config: {config}")
    log.debug(f"rclone config: {config_rclone}")

    stream_proc = multiprocessing.Process(target=streamers_watcher, args=(config, STREAMERS_FILE), name="StreamWatcher")
    stream_proc.start()

    if not args.disable_rclone:
        # Start the rclone process
        # I originally had the idea to run this through cron, but was easy to implement it into the script
        # Also do we want an is_alive() checker here to restart the rclone process if it ever crashes?
        rclone_delay = utils.try_get(config_rclone, lambda x: x['sleep_interval'], expected_type=int) or RCLONE_PROCESS_REPEAT_TIME
        rclone_proc = multiprocessing.Process(target=rclone.rclone_watcher, args=(config_rclone, STREAMERS_FILE, rclone_delay), name="rcloneWatcher")
        rclone_proc.start()

    stream_proc.join()