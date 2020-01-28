"""

Separate Script to be run from cron to automatically move/copy files

"""

import os
import logging
import yaml
import utils
import subprocess
import tempfile
from exceptions import RequiredValueError
from const import (

    TEMP_FILE_EXT,
    RCLONE_BIN_LOCATION,
    RCLONE_CONFIG_LOCATION,
    RCLONE_DEFAULT_TRANSFERS,
    RCLONE_DEFAULT_OPERATION,
    LOG_LEVEL_DEFAULT,
    DEFAULT_DOWNLOAD_DIR

)


STREAMERS_FILE = os.getenv("STREAMERS_CONFIG", "../streamers.yml")
CONFIG_FILE = os.getenv("CONFIG", "../config.yml")


class Rclone:

    def __init__(self, binary: str, config: str):
        self.BINARY = binary
        self.CONFIG = config
        self.BASE_COMMAND = [self.BINARY] + (["--config", self.CONFIG] if self.CONFIG != ""  else []) + (['--verbose'] if log.level <= logging.DEBUG else [])

    def operation_from(self, operation: str, files: list, dest: str, common_path: str, extra_args=[], transfers=RCLONE_DEFAULT_TRANSFERS):

        print(operation, files, dest, common_path)
        operation = operation.lower()
        if operation != "copy" and operation != "move":
            log.critical(f"Invalid operation! Valid operations are move and copy, not {operation}")
            return

        file_name = ""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            file_name = f.name

            for line in files:
                f.write(f"{line}\n")

            f.close()

        d = self._run_command([operation, '--files-from', str(file_name),
                                  str(common_path), str(dest), '--transfers', str(transfers)] + extra_args)

        os.unlink(f.name)
        return d

    def _run_command(self, command_args: list):
        """

        Run Rclone comand.


        :param command_args: List of rclone arguments, EXCLUDING the config and binary declaration
        :return: If fails, None. else the Output of command.
        """
        # print(command_args)

        log.debug(self.BASE_COMMAND + command_args)
        try:
            output = subprocess.run(self.BASE_COMMAND + command_args, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            log.critical(f"Failed to run rclone command: {e}. Debug info: "
                             f"\nreturncode: {e.returncode}"
                             f"\nstderr: {e.stdout.decode(encoding='UTF-8')}"
                             f"\nstderr: {e.stderr.decode(encoding='UTF-8')}"
                             )
            return None
        else:
            if isinstance(output, subprocess.CompletedProcess):
                log.debug(f"Success: "
                              f"\nreturncode: {output.returncode}"
                              f"\nstdout: {output.stdout.decode(encoding='UTF-8')}"
                              f"\nstderr: {output.stderr.decode(encoding='UTF-8')}"
                              )
                return output


class RcloneTrans:

    def __init__(self, **kwargs):

        self.source_dir = kwargs.get('source_dir')
        self.source_dir_basename = os.path.basename(self.source_dir)
        self.rclone_config = kwargs.get('rclone_config', RCLONE_CONFIG_LOCATION)
        self.rclone_bin = kwargs.get('rclone_bin', RCLONE_BIN_LOCATION)
        self.remote_dir = kwargs.get('remote_dir')
        self.operation = kwargs.get('operation', RCLONE_DEFAULT_OPERATION)
        self.rclone_args = list(kwargs.get('rclone_args', []))
        self.transfers = kwargs.get('transfers', RCLONE_DEFAULT_TRANSFERS)
        self.run()

    def _get_recordings_filtered(self):
        return [a for a in os.listdir(self.source_dir) if not a.endswith(TEMP_FILE_EXT)]

    def run(self):

        log.debug("Getting list of recordings")
        # Get a list of all the recordings in the download directory

        recordings_unfiltered = self._get_recordings_filtered()

        # Transferring to remote using Rclone
        t = Rclone(binary=self.rclone_bin, config=self.rclone_config)
        t.operation_from(self.operation, files=recordings_unfiltered, dest=self.remote_dir, common_path=self.source_dir, extra_args=self.rclone_args, transfers=self.transfers)
        log.debug("Completed Transfer")


def create_tasks(streamers_conf: dict, rclone_conf: dict):

    tasks = []

    for stream in streamers_conf:

        # Check if the stream has rclone arguments to start with

        rclone_stream = utils.try_get(streamers_conf[stream], lambda x: x['rclone'], expected_type=dict) or None

        if rclone_stream is None:
            log.debug(f"No rclone entry for {stream}, skipping.")
            continue

        task = {}
        task['operation'] = utils.try_get(rclone_stream, lambda x: x['operation'], expected_type=str) or utils.try_get(rclone_conf, lambda x:x['default_operation'], expected_type=str) or RCLONE_DEFAULT_OPERATION
        task['remote_dir'] = utils.try_get(rclone_stream, lambda x: x['remote_dir'], expected_type=str) or None

        if task['remote_dir'] is None:
            raise RequiredValueError(f"[{stream}] remote_dir is a required argument")

        task['rclone_args'] = utils.try_get(rclone_stream, lambda x: x['rclone_args'], expected_type=list) or []
        task['rclone_bin'] = utils.try_get(rclone_stream, lambda x: x['rclone_bin'], expected_type=str) or utils.try_get(
            rclone_conf, lambda x: x['rclone_bin'], expected_type=str) or RCLONE_BIN_LOCATION

        task['source_dir'] = utils.try_get(streamers_conf[stream], lambda x: x['download_directory'], expected_type=str) or DEFAULT_DOWNLOAD_DIR

        task['rclone_config'] = utils.try_get(rclone_stream, lambda x: x['config'], expected_type=str) or utils.try_get(
            rclone_conf, lambda x: x['config'], expected_type=str) or RCLONE_CONFIG_LOCATION

        task['transfers'] = utils.try_get(rclone_stream, lambda x: x['transfers'], expected_type=int) or utils.try_get(
            rclone_conf, lambda x: x['transfers'], expected_type=int) or RCLONE_DEFAULT_TRANSFERS
        tasks.append(task)

    return tasks


if __name__ == "__main__":
    # Load the config from config.yml
    with open(CONFIG_FILE) as f:
        d = yaml.load(f, Loader=yaml.FullLoader)
        config_gen = utils.try_get(d, lambda x: x['config']) or {}
        config_rclone = utils.try_get(d, lambda x: x['rclone']) or {}

    # Configure logging
    log = logging.getLogger('root')
    log_level = utils.try_get(config_gen, lambda x: x['log_level'], str) or LOG_LEVEL_DEFAULT
    log.addHandler(utils.LoggingHandler())
    log.setLevel(log_level)

    # Load the streams from config_dev.yml
    with open(STREAMERS_FILE) as f:
        streamers = yaml.load(f, Loader=yaml.FullLoader)['streamers']

    tasks = create_tasks(streamers, config_rclone)

    for task in tasks:
        RcloneTrans(**task)
