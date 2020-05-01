from datetime import datetime
from queue import Queue, Empty
import multiprocessing
import subprocess
import streamlink
import threading
import traceback
import logging
import signal
import utils
import time
import json
import sys
import os

from const import (

    RECHECK_CHANNEL_STATUS_TIME,
    TEMP_FILE_EXT,
    TIME_NICE_FORMAT,
    STREAMLINK_BINARY,
    STREAM_SPLIT_TIME,
    STREAM_DEFAULT_NAME,
    STREAM_DEFAULT_QUALITY,
    STREAM_WATCHDOG_DEFAULT_SLEEP

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
        self.streamlink_bin = STREAMLINK_BINARY
        self.make_dirs = True
        self.quality = STREAM_DEFAULT_QUALITY
        self._stdout_queue = None
        self._stdout_thread = None
        self._stderr_queue = None
        self._stderr_thread = None

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

        if a is None:
            log.error("Got None from subprocess")
            return False
        filtered = []

        for line in a.split("\n"):
            if "[plugin." in line:
                continue

            if line == "":
                continue

            filtered.append(line)

        if len(filtered) == 0:
            log.warning("No valid lines returned from subprocess (issue with Streamlink?)")
            return False

        try:
            json_output = json.loads('\n'.join(filtered))
        except json.JSONDecodeError as e:
            log.error(f"JSONDecodeError while trying to check if stream is live or not (probably an issue with Streamlink): {e}")
            log.debug(f"filtered: {filtered}")
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
                if self._current_process.poll() is None:
                    self._current_process.kill()
                self._current_process = None
                # Set both Queues to None.
                # This should trigger the thread to stop
                self._stderr_queue = None
                self._stdout_queue = None

                # Wait until the stdout/stderr watcher threads stop. Hopefully this should not lock up the script.
                said_m = False
                before_t = time.time()
                while utils.is_alive_safe(self._stdout_thread) or utils.is_alive_safe(self._stderr_thread):
                    if said_m is False:
                        log.debug("Waiting for stdout and stderr watcher threads to stop.")
                        said_m = True
                else:
                    log.debug(f"stdout and stderr watcher threads have stopped (took {time.time()-before_t}s).")
            else:
                if self._current_process.poll() is None:
                    # If the process is still running, terminate it.
                    # This shouldn't ever be reached.
                    # So if it does then something has gone wrong and we should terminate it.
                    self._current_process.terminate()

            log.debug(f"Finalizing files...")
            end_time_p, end_time_m = utils.get_utc_nice(), utils.get_utc_machine()

            # Rename the file as a completed split
            if os.path.exists(os.path.join(self.download_directory, filename)):
                os.rename(os.path.join(self.download_directory, filename), os.path.join(self.download_directory, start_time_p + "_to_" + end_time_p + "_" + self.stream_name + ".ts"))

            # Run some checks based on the return code
            # TODO: use -1 error code
            if status > 0:
                # Stream has ended
                if status == 1:
                    log.info(f"Stream has ended.")
                    return 1

                # Stream has crashed, after 3 errors abort (TODO)
                if status == 2 or status == -1:
                    errors += 1

                    if errors > 3:
                        log.warning("Finished due to error with stream (-1)")
                        return -1

    def __start_std_watcher(self, std):
        queue = Queue()
        thread = threading.Thread(target=self.__enqueue_std, args=(std, queue))
        thread.daemon = True
        thread.start()
        return thread, queue

    def _read_stdout(self, lines=10):
        """
        Trigger lines to be read from the standard output into a list

        :param lines: number of lines to read
        :return: list containing lines from stdout
        """
        data = []
        self._stdout_thread, self._stdout_queue = self.__read_std(queue=self._stdout_queue,
                                                                  thread=self._stdout_thread,
                                                                  data=data,
                                                                  std=self._current_process.stdout,
                                                                  lines=lines)
        return data

    def _read_stderr(self, lines=10):
        data = []
        self._stderr_thread, self._stderr_queue = self.__read_std(queue=self._stderr_queue,
                                                                  thread=self._stderr_thread,
                                                                  data=data,
                                                                  std=self._current_process.stderr,
                                                                  lines=lines)
        return data

    def __read_std(self, queue: Queue, thread: threading.Thread, data: list, std, lines=10):
        """
        General function to handle reading from stderr/stdout etc
        :param queue: Queue object
        :param thread: Thread object
        :param data: list to append lines to
        :param std: stdout/stderr/file obj
        :param lines: number of lines in the queue to check
        :return: thread, queue (same as input if not changed)
        """
        if queue is None and thread is None:
            thread, queue = self.__start_std_watcher(std)

        if not thread.is_alive():
            thread, queue = self.__start_std_watcher(std)

        data.clear()
        if queue is None:
            return thread, queue
        for x in range(lines):
            try:
                line = queue.get_nowait()
                data.append(line)
            except Empty:
                return thread, queue

        return thread, queue

    @staticmethod
    def __enqueue_std(std, queue):
        """
        Read output of stdout/stderr and add to a given queue.

        This is to be run in another thread.
        :param std:
        :param queue:
        :return:
        """
        try:
            for line in iter(std.readline, b''):
                if queue is None:
                    return
                queue.put(line.decode('utf-8'))
            std.close()
        except ValueError:  # If the file is closed
            return

    def _stream_watchdog(self):

        """

        Checks if the stream is still downloading

        Will run for self.split_time amount of time

        Relies on self.current_process

        0 - success, still running
        1 - Stream has finished
        2 - Streamlink exit code > 0 (crashed etc)

        """

        if not isinstance(self._current_process, subprocess.Popen):
            return -1

        start_time = time.time()

        while (time.time() - start_time) <= self.split_time:

            stdout_data = self._read_stdout(lines=20)
            stderr_data = self._read_stderr(lines=20)

            current_proc_state = self._current_process.poll()
            if current_proc_state is not None:
                log.debug(f"Return code of process is {current_proc_state}")
                return current_proc_state

            for line in stderr_data:
                # Not sure if Streamlink outputs to stderr, but just in case...
                log.error(f"[Streamlink][stderr]: {line}")

            for line in stdout_data:
                # TODO: Process logs from stdout
                if "error" not in line.lower():
                    log.debug("[Streamlink]: " + str(line).strip())
                    continue

                # TODO: Streamlink will eventually quit with this error.
                # Do we want to override this?
                if "failed to reload playlist: unable to open url" in line.lower() or "failed to open segment" in line.lower():
                    log.debug(f"Stream has probably ended - Streamlink said: {line}")
                    break

                log.error(f"[Streamlink][stdout]:{line}")

            time.sleep(STREAM_WATCHDOG_DEFAULT_SLEEP)

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
        log.debug(f"Received sig code {sig}")
        if multiprocessing.current_process().name == self.stream_name:
            log.debug("Shutting down gracefully")

            if self._current_process is not None:
                if self._current_process.poll() is None:
                    log.debug("Killing Streamlink process")
                    self._current_process.kill()

            said = False
            while utils.is_alive_safe(self._stdout_thread) or utils.is_alive_safe(self._stderr_thread):
                if not said:
                    self._stdout_queue = None
                    self._stderr_queue = None
                    log.debug("Waiting for stdout and stderr watcher threads to stop...")
                    said = True

            log.debug("Cleaning up...")
            self.cleanup()
            log.debug("All finished now, exiting. Bye!")
            sys.exit(0)
        sys.exit(0)

    def main(self, **kwargs):
        log.info("Launching Archiver")
        self.url = kwargs.get('url', self.url)
        self.stream_name = kwargs.get('name', self.stream_name)
        self.download_directory = kwargs.get('download_directory', self.download_directory)
        self.split_time = int(kwargs.get('split_time', self.split_time))
        self.streamlink_args.extend(list(kwargs.get('streamlink_args', self.streamlink_args)))
        self.streamlink_bin = kwargs.get('streamlink_bin', self.streamlink_bin)
        self.make_dirs = bool(kwargs.get('make_dirs', self.make_dirs))
        self.quality = str(kwargs.get('quality', self.quality))
        # Create download directory
        if not os.path.exists(self.download_directory) and self.make_dirs:
            try:
                os.makedirs(self.download_directory, exist_ok=True)
            except (PermissionError, ) as er:
                log.critical("Permission Error was raised while trying to create download directory. "
                             "Please check the permissions of the location. "
                             "Maybe try manually creating the folder? Exiting.")
                log.debug(f"Error:: {er}")
                sys.exit(1)

        # setup signals
        signal.signal(signal.SIGTERM, self.kill_handler)
        signal.signal(signal.SIGINT, self.kill_handler)

        self.cleanup()
        self._display_config()
        try:
            self._site_watchdog()
        except Exception:
            """
            Catch all exception here so we can be sure we gracefully shut down and kill Streamlink process etc.
            We'll capture the traceback here and log it for debugging purposes.
            This only works if the error is not in the kill handler.
            """
            tb = traceback.format_exc()
            log.critical(f"Stream Archiver Crashed: {tb}")
            self.kill_handler(1, None)
