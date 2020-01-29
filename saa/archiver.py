from datetime import datetime
import multiprocessing
import subprocess
import streamlink
import logging
import time
import os
import utils
import json
import sys
import signal

from const import (

    RECHECK_CHANNEL_STATUS_TIME,
    TEMP_FILE_EXT,
    TIME_NICE_FORMAT,
    STDOUT_READ_NEXT_LINE_TIMEOUT,
    STREAMLINK_BINARY,
    STREAM_SPLIT_TIME,
    STREAM_DEFAULT_NAME,
    STREAM_DEFAULT_QUALITY

)

log = logging.getLogger('root')


class StreamArchiver:

    def __init__(self):
        self.url = ""
        self.split_time = STREAM_SPLIT_TIME
        self.stream_name = STREAM_DEFAULT_NAME
        self.download_directory = "."
        self._current_process = None
        self.streamlink_args = []
        self._stdout_data = []
        self.stdout_line_read_timeout = STDOUT_READ_NEXT_LINE_TIMEOUT
        self.streamlink_bin = STREAMLINK_BINARY
        self.make_dirs = True
        self.quality = STREAM_DEFAULT_QUALITY

    @staticmethod
    def _start_streamlink_process(stream_url, file: str, quality=STREAM_DEFAULT_QUALITY, optional_sl_args=None, streamlink_bin=STREAMLINK_BINARY):
        """

        Start Streamlink, downloading the given stream to the given file.

        :param url: url of stream
        :param file: file to download to
        :param quality: quality of the stream
        :return: the process object
        """
        if optional_sl_args is None:
            optional_sl_args = []

        optional_sl_args = optional_sl_args.copy()

        if log.level > logging.DEBUG:

            optional_sl_args.append("--quiet")
        else:
            optional_sl_args.extend(['-l', 'debug'])

        return subprocess.Popen([streamlink_bin, stream_url, quality, "-o", file] + optional_sl_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    @staticmethod
    def _init_download_fallback():
        # Try use youtube-dl to download unsupported streams
        pass

    def _is_live(self):
        """

        Checks if there is streams available for a given url.

        Uses self.streamlink_args

        :param url:
        :return: True if there is a stream, false if not
        """
        try:
            a = subprocess.run([STREAMLINK_BINARY, self.url, '--json'] + self.streamlink_args, capture_output=True).stdout.decode(encoding="UTF-8")
        except subprocess.CalledProcessError:
            return False

        filtered = []
        for line in a.split("\n"):
            if "[plugin." not in line:
                filtered.append(line)

        try:
            json_output = json.loads('\n'.join(filtered))
        except json.JSONDecodeError as e:
            log.error(f"JSONDecodeError while trying to check if stream is live or not (probably an issue with Streamlink): {e}")
            return False

        if "error" not in json_output:
            return True

        else:
            log.debug(f"Streamlink said: {json_output['error']}")
            return False

    @staticmethod
    def get_streams(url: str):

        streams = dict(streamlink.streams(url))
        return streams

    def _download_handler(self, stream_url):

        """

        Loop that handles downloading the stream, splitting it every X amount of time


        :param stream:
        :return:
        """

        errors = 0

        while True:
            # One loop = one split
            # Get start times
            start_time_p, start_time_m = utils.get_utc_nice(), utils.get_utc_machine()

            # Create a filename for this loop
            # Start with identifier (in this case "D") so we can always check if download has failed
            filename =  start_time_p + "_" + self.stream_name + ".ts" + TEMP_FILE_EXT

            log.info(f"Beginning Stream Download of {filename}")

            # Start the download process
            self._current_process = self._start_streamlink_process(stream_url, os.path.join(self.download_directory, filename), optional_sl_args=self.streamlink_args, quality=self.quality, streamlink_bin=self.streamlink_bin)

            # Start the stream watchdog, which will sleep and watch until we next split the stream
            status = self._stream_watchdog()

            if status == 0:
                log.info(f"Cutting stream")
                self._current_process.kill()

            log.debug(f"Finalizing files...")
            end_time_p, end_time_m = utils.get_utc_nice(), utils.get_utc_machine()

            # Rename the file as a completed split
            if os.path.exists(os.path.join(self.download_directory, filename)):
                os.rename(os.path.join(self.download_directory, filename), os.path.join(self.download_directory, start_time_p + "_to_" + end_time_p + "_" + self.stream_name + ".ts"))

            # Run some checks based on the return code
            if status > 0:
                # Stream has ended
                if status == 1:
                    log.info(f"Stream has ended.")
                    return 1

                # Stream has crashed, after 3 errors abort (TODO)
                if status == 2:
                    errors += 1

                    if errors > 3:
                        return 2

    def _stdout_gen(self):
        for line in self._current_process.stdout:
            yield line

    def _stdout_next(self, line):
        for t in range(1000):
            try:
                a = next(self._stdout_gen())
                line.append(a)
            except StopIteration:
                return

    def _timeout_read_next_stdout(self):
        manager = multiprocessing.Manager()
        line = manager.list()
        process = multiprocessing.Process(target=self._stdout_next, args=(line,))
        process.start()
        process.join(timeout=STDOUT_READ_NEXT_LINE_TIMEOUT)
        process.terminate()

        self._stdout_data.extend([l.decode(encoding='UTF-8') for l in line])

    def _stream_watchdog(self):

        """

        Checks if the stream is still downloading

        Will run for self.split_time amount of time

        Relies on self.current_process

        :return:

        0 - success, still running
        1 - Stream has finished
        2 - Streamlink exit code > 0 (crashed etc)

        """

        if not isinstance(self._current_process, subprocess.Popen):
            return 2

        start_time = time.time()

        while (time.time() - start_time) <= self.split_time:

            prev_output = len(self._stdout_data)
            self._timeout_read_next_stdout()
            s = self._current_process.poll()
            if s is not None:

                if s > 1:
                    log.debug(f"Return code of process is {s}")
                    return s
                else:
                    log.info(f"Stream is down/finished")
                    return 1

            for line in self._stdout_data[prev_output:]:
                log.debug("[STREAMLINK]: " + str(line).strip())
                # TODO: Process logs from stdout
                if "error" not in line.lower():
                    continue

                if "failed to reload playlist: unable to open url" in line.lower():
                    log.debug(f"Stream has probably ended - Streamlink said: {line}")
                    break

                log.error(f"{line}")

            time.sleep(self.split_time / (self.split_time / 2))

        return 0

    def _site_watchdog(self):

        """

        Checks if stream is alive, and if so, triggers the download handler.

        :return:
        """

        run = True

        not_live_runs = 0

        while run:
            stream_status = self._is_live()

            if not stream_status:
                if not_live_runs == 0:
                    log.info(f"{self.stream_name} is not currently live.")
                    not_live_runs += 1
                else:
                    log.debug(f"{self.stream_name} is not currently live.")
            else:
                log.info(f"{self.stream_name} is live, archiving started.")
                not_live_runs = 0
                return_code = self._download_handler(self.url)

            time.sleep(RECHECK_CHANNEL_STATUS_TIME)

    def _display_config(self):

        log.info(f"\n----------\n"
                 f"Configuration:\n"
                 f"Stream Name: {self.stream_name}\n"
                 f"URL: {self.url}\n"
                 f"Download Directory: {self.download_directory}\n"
                 f"Stream Split Length: {self.split_time}s\n"
                 f"Quality: {self.quality}\n"
                 f"Extra Streamlink args {self.streamlink_args}"
                 f"\n----------\n"
                 "")

    def cleanup(self):

        # Cleanup any files in the download directory that have failed (assuming this is the only instance)

        # Does so by renaming based on last mod time and removes the temp file ext
        total_cleaned = 0
        for file in os.listdir(self.download_directory):
            if not file.endswith(TEMP_FILE_EXT):
                continue

            if file[16:-len(".ts" + TEMP_FILE_EXT)].lower() != self.stream_name.lower():
                continue

            last_mod = datetime.utcfromtimestamp(os.path.getmtime(os.path.join(self.download_directory, file))).strftime(TIME_NICE_FORMAT)

            # Assuming filename is in the format <start_time>_<stream_name>.<ext>.<TEMP_FILE_EXT>

            new_name = file[:15] + "_to_" + last_mod + "_" + file[16:-len(".ts" + TEMP_FILE_EXT)] + ".ts"

            os.rename(os.path.join(self.download_directory, file), os.path.join(self.download_directory, new_name))

            total_cleaned += 1

        log.debug(f"Cleaned up {total_cleaned} unfinished streams.")

    def kill_handler(self, sig, frame):
        """

        This will kill the streamlink subprocess before killing the main process
        Before this the streamlink process would continue even if the main process had been killed.

        Here we also have to check if the current process is equal to the stream name as this gets called
         e.g when the stdout read times out.


        :param sig:
        :param frame:
        :return:
        """
        if multiprocessing.current_process().name == self.stream_name:
            log.debug("Shutting down gracefully")

            if self._current_process is not None:
                if self._current_process.poll() is None:
                    log.debug("Killing Streamlink process")
                    self._current_process.kill()
            log.debug("Cleaning up...")
            self.cleanup()
            log.debug("All finished now, exiting. Bye!")
            sys.exit(0)
        sys.exit(0)

    def main(self, **kwargs):

        self.url = kwargs.get('url', self.url)
        self.stream_name = kwargs.get('name', self.stream_name)
        self.download_directory = kwargs.get('download_directory', self.download_directory)
        self.split_time = int(kwargs.get('split_time', self.split_time))
        self.streamlink_args.extend(list(kwargs.get('steamlink_args', self.streamlink_args)))
        self.streamlink_bin = kwargs.get('streamlink_bin', self.streamlink_bin)
        self.make_dirs = bool(kwargs.get('make_dirs', self.make_dirs))
        self.quality = str(kwargs.get('quality', self.quality))
        # Create download directory
        if not os.path.exists(self.download_directory) and self.make_dirs:
            os.makedirs(self.download_directory, exist_ok=True)

        # setup signals
        signal.signal(signal.SIGTERM, self.kill_handler)
        signal.signal(signal.SIGINT, self.kill_handler)

        self.cleanup()
        self._display_config()
        self._site_watchdog()
