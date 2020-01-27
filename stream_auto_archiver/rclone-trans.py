"""

Separate Script to be run from cron to automatically move/copy files

"""

import os
import logging
import yaml
import utils
import subprocess
import tempfile

from run import LoggingHandler

from const import (

    TEMP_FILE_EXT,
    RCLONE_BIN_LOCATION,
    RCLONE_CONFIG_LOCATION,
    RCLONE_DEFAULT_TRANSFERS,
    RCLONE_DEFAULT_OPERATION,
    LOG_LEVEL_DEFAULT


)


STREAMERS_FILE = os.getenv("STREAMERS_CONFIG", "streamers.yml")
CONFIG_FILE = os.getenv("CONFIG", "config.yml")


class Rclone:

    def __init__(self, binary: str, config: str):
        self.BINARY = binary
        self.CONFIG = config
        self.BASE_COMMAND = [self.BINARY] + (["--config", self.CONFIG] if self.CONFIG != ""  else []) + (['--verbose'] if log.level <= logging.DEBUG else [])

    def operation_from(self, operation: str, files: list, dest: str, common_path: str, extra_args=[]):

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
                                  str(common_path), str(dest)] + extra_args)

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
        #log.debug(f"RcloneTrans Arguments: {kwargs}")
        self.download_directory = kwargs.get('download_directory')
        self.download_directory_basename = os.path.basename(self.download_directory)

        self.rclone_config = kwargs.get('rclone_config', RCLONE_CONFIG_LOCATION)
        self.rclone_bin = kwargs.get('rclone_bin', RCLONE_BIN_LOCATION)
        self.remote_dir = kwargs.get('remote_dir')
        self.operation = kwargs.get('operation', RCLONE_DEFAULT_OPERATION)
        self.rclone_args = list(kwargs.get('rclone_args', []))
        self.run()

    def _get_recordings_filtered(self):
        return [a for a in os.listdir(self.download_directory) if not a.endswith(TEMP_FILE_EXT)]

    def run(self):

        log.debug("Getting list of recordings")
        # Get a list of all the recordings in the download directory

        recordings_unfiltered = self._get_recordings_filtered()

        # Transferring to remote using Rclone
        t = Rclone(binary=self.rclone_bin, config=self.rclone_config)
        t.operation_from(self.operation, files=recordings_unfiltered, dest=self.remote_dir, common_path=self.download_directory, extra_args=self.rclone_args)
        log.debug("Completed Transfer")

if __name__ == "__main__":
    # Load the config from config.yml
    with open(CONFIG_FILE) as f:
        d = yaml.load(f, Loader=yaml.FullLoader)
        config_gen = utils.try_get(d, lambda x: x['config']) or {}
        config_rclone = utils.try_get(d, lambda x: x['rclone']) or {}

    # Configure logging
    log = logging.getLogger('root')
    log_level = utils.try_get(config_gen, lambda x: x['log_level'], str) or LOG_LEVEL_DEFAULT
    log.addHandler(LoggingHandler())
    log.setLevel(log_level)

    # Load the streams from config_dev.yml
    with open(STREAMERS_FILE) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)['streamers']


    for stream in data:
        log.info(f"Running rclone transfer task for {data[stream]['name']}")
        # get seperate properties for rclone out of stream rclone

        rclone_stream = utils.try_get(data[stream], lambda x: x['rclone'], expected_type=dict) or {}

        if rclone_stream == {}:
            log.info("Skipping")
            continue

        operation = utils.try_get(rclone_stream, lambda x:x['operation'], expected_type=str) or utils.try_get(config_gen, lambda x:x['default_operation'], expected_type=str) or RCLONE_DEFAULT_OPERATION
        remote_dir = utils.try_get(rclone_stream, lambda x:x['remote_dir'], expected_type=str) or utils.try_get(config_gen, lambda x:x['default_remote_dir'], expected_type=str)
        rclone_args = utils.try_get(rclone_stream, lambda x:x['rclone_args'], expected_type=list) or []
        if remote_dir is None:
            log.critical(f"There is no remote/dest directory to {operation} files to. Skipping.")
            continue

        j = RcloneTrans(**{**config_gen, **config_rclone, **data[stream], **{'operation': operation, 'remote_dir': remote_dir, 'rclone_args': rclone_args}})
