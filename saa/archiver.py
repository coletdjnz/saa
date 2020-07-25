from datetime import datetime
from queue import Queue, Empty
import multiprocessing
import subprocess
import threading
import traceback
import logging
import signal
import saa.utils as utils
import time
import json
import sys
import os

from saa.const import (

    RECHECK_CHANNEL_STATUS_TIME,
    TEMP_FILE_EXT,
    TIME_NICE_FORMAT,
    STREAMLINK_BINARY,
    STREAM_SPLIT_TIME,
    STREAMER_DEFAULT_NAME,
    STREAM_DEFAULT_QUALITY,
    STREAMLINK_ARGS_DEFAULT,
    DEFAULT_DOWNLOAD_DIR,
    STREAMER_UPDATE_COM_STATUS_SLEEP,
    STREAM_WATCHDOG_DEFAULT_SLEEP,
    NEWLINE_CHAR
)

log = logging.getLogger('root')


class StreamArchiver:

    def __init__(self, url,
                 name=STREAMER_DEFAULT_NAME,
                 download_directory=None,
                 split_time=STREAM_SPLIT_TIME,
                 streamlink_args=None,
                 streamlink_bin=STREAMLINK_BINARY,
                 make_dirs=True,
                 quality=STREAM_DEFAULT_QUALITY,
                 com_queue=None, *args, **kwargs):

        self.url = str(url)
        self.split_time = int(split_time)
        self.streamer_name = str(name)

        self.streamlink_args = list(STREAMLINK_ARGS_DEFAULT)
        if streamlink_args is None:
            streamlink_args = []
        self.streamlink_args.extend(streamlink_args)

        if download_directory is None:
            download_directory = os.path.join(DEFAULT_DOWNLOAD_DIR, self.streamer_name)  # TODO: Sanitize this
        self.download_directory = str(download_directory)

        self.streamlink_bin = str(streamlink_bin)
        self.quality = str(quality)
        self.make_dirs = bool(make_dirs)

        self._current_process = None
        self.__stdout_queue = None
        self.__stdout_thread = None
        self.__stderr_queue = None
        self.__stderr_thread = None

        # Variable to hold the start time for the stream watchdog
        self.__chunk_start_time = 0
        self.__split_by_time = True

        # Extra Stats
        self.__current_chunks = 0  # amount of chunks done for the current livestream (resets when stream is down)
        self.__stream_start_time = None

        # External reporting communication (for reporting plugins)
        self.__master_reporting_queue = com_queue
        self.__reporting_thread = None

    @staticmethod
    def _start_streamlink_process(stream_url, file: str, quality=STREAM_DEFAULT_QUALITY, optional_sl_args=None,
                                  streamlink_bin=STREAMLINK_BINARY):
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

        return subprocess.Popen([streamlink_bin, stream_url, quality, "-o", file] + optional_sl_args,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _is_live(self):
        """

        Checks if there is streams available for a given url.

        Uses self.streamlink_args

        :param url:
        :return: True if there is a stream, false if not
        """
        try:
            process_ = subprocess.run([STREAMLINK_BINARY, self.url, '--json'] + self.streamlink_args,
                                      capture_output=True)
            stderr_ = process_.stderr.decode(encoding="UTF-8")
            stdout_ = process_.stdout.decode(encoding="UTF-8")
        except subprocess.CalledProcessError:
            return False
        log.debug(
            f"Output from Streamlink: stderr={stderr_.replace(NEWLINE_CHAR, ' ')}, stdout={stdout_.replace(NEWLINE_CHAR, ' ')}")

        if stderr_ is None or stdout_ is None:
            log.critical("Got None from subprocess")
            return False

        # If there is output in the stderr then Streamlink has failed (e.g invalid arguments)
        if len(stderr_) > 0:
            log.critical(f"Streamlink Error while checking streamer status: {stderr_.replace(NEWLINE_CHAR, ' ')}")
            return False

        # Remove any non-json lines (e.g warnings from plugins)
        filtered = []
        for line in stdout_.split("\n"):
            if "[plugin." in line or line == "":
                continue
            filtered.append(line)

        # if no data after being filtered, then not sure why there isn't any data.
        if len(filtered) == 0:
            log.critical(
                "No valid data returned from stderr or filtered stdout while trying to check if streamer is live"
                " Please report this at https://gitlab.com/colethedj/stream_auto_archiver/-/issues."
                "\nDebug information:"
                f"\nstderr: {stderr_}"
                f"\nstdout: {stdout_}"
                f"\nstdout filtered: {' '.join(filtered)}")
            return False

        # parse as json
        try:
            json_output = json.loads('\n'.join(filtered))
        except json.JSONDecodeError as e:
            log.critical(
                "JSONDecodeError on filtered stdout while trying to check if streamer is live"
                " Please report this at https://gitlab.com/colethedj/stream_auto_archiver/-/issues."
                "\nDebug information:"
                f"\nstderr: {stderr_}"
                f"\nstdout: {stdout_}")
            return False

        # if there is no error key in the json output, assume good.
        if "error" not in json_output:
            return True

        else:
            log.debug(f"Streamlink said: {json_output['error']}")
            return False

    def _stream_download_handler(self, stream_url):

        """
        Loop that handles downloading the stream, splitting it every X amount of time
        """

        errors = 0
        while True:

            # One loop = one split
            # Get start times
            start_time_p, start_time_m = utils.get_utc_nice(), utils.get_utc_machine()

            # Create a filename for this loop
            # Start with identifier (in this case "D") so we can always check if download has failed
            filename = start_time_p + "_" + self.streamer_name + ".ts" + TEMP_FILE_EXT

            log.info(f"Starting download of stream {filename}.")

            # Start the download process
            self._current_process = self._start_streamlink_process(stream_url,
                                                                   os.path.join(self.download_directory, filename),
                                                                   optional_sl_args=self.streamlink_args,
                                                                   quality=self.quality,
                                                                   streamlink_bin=self.streamlink_bin)

            # Start the stream watchdog, which will sleep and watch until we next split the stream
            status = self._stream_watchdog()
            self.__current_chunks += 1
            if status == 0:
                log.info(f"Cutting stream")
                if self._current_process.poll() is None:
                    self._current_process.kill()
                self._current_process = None
                # Set both Queues to None.
                # This should trigger the thread to stop
                self.__stderr_queue = None
                self.__stdout_queue = None

                # Wait until the stdout/stderr watcher threads stop. Hopefully this should not lock up the script.
                said_m = False
                before_t = time.time()
                while utils.is_alive_safe(self.__stdout_thread) or utils.is_alive_safe(self.__stderr_thread):
                    if said_m is False:
                        log.debug("Waiting for stdout and stderr watcher threads to stop.")
                        said_m = True
                else:
                    log.debug(f"stdout and stderr watcher threads have stopped (took {time.time() - before_t}s).")
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
                os.rename(os.path.join(self.download_directory, filename), os.path.join(self.download_directory,
                                                                                        start_time_p + "_to_" + end_time_p + "_" + self.streamer_name + ".ts"))

            # Run some checks based on the return code
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
        self.__stdout_thread, self.__stdout_queue = self.__read_std(queue=self.__stdout_queue,
                                                                    thread=self.__stdout_thread,
                                                                    data=data,
                                                                    std=self._current_process.stdout,
                                                                    lines=lines)
        return data

    def _read_stderr(self, lines=10):
        data = []
        self.__stderr_thread, self.__stderr_queue = self.__read_std(queue=self.__stderr_queue,
                                                                    thread=self.__stderr_thread,
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

    def __s_wd_keep_running(self):
        """

        (I couldn't think of a better function name)
        Helper function for self._stream_watchdog
        Checks if the watchdog should keep running or not.

        :return: True if keep running, False if stop
        """

        if self.__split_by_time:
            return (time.time() - self.__chunk_start_time) <= self.split_time

        # TODO: Add check by filesize

        return False

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

        self.__chunk_start_time = time.time()

        while self.__s_wd_keep_running():

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

    def _streamer_watchdog(self):

        """

        Checks if streamer is streaming, and if so, triggers the download handler.

        """
        run = True
        not_live_runs = 0

        while run:
            stream_status = self._is_live()

            if not stream_status:
                if not_live_runs == 0:
                    log.info(f"{self.streamer_name} is not currently live.")
                    not_live_runs += 1
                else:
                    log.debug(f"{self.streamer_name} is not currently live.")
            else:
                log.info(f"{self.streamer_name} is live, archiving started.")
                not_live_runs = 0
                self.__current_chunks = 0
                self.__stream_start_time = time.time()
                return_code = self._stream_download_handler(self.url)
                self.__current_chunks = 0
                self.__stream_start_time = None

            time.sleep(RECHECK_CHANNEL_STATUS_TIME)

    def _display_config(self):

        log.info(f"\n----------\n"
                 f"Configuration:\n"
                 f"Stream Name: {self.streamer_name}\n"
                 f"URL: {self.url}\n"
                 f"Download Directory: {self.download_directory}\n"
                 f"Stream Split Length: {self.split_time}s\n"
                 f"Quality: {self.quality}\n"
                 f"Make Directories: {self.make_dirs}\n"
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
            if file[16:-len(".ts" + TEMP_FILE_EXT)].lower() != self.streamer_name.lower():
                continue
            last_mod = datetime.utcfromtimestamp(
                os.path.getmtime(os.path.join(self.download_directory, file))).strftime(TIME_NICE_FORMAT)
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
        """
        log.debug(f"Received sig code {sig}")
        if multiprocessing.current_process().name == self.streamer_name:
            log.debug("Shutting down gracefully")

            if self._current_process is not None:
                if self._current_process.poll() is None:
                    log.debug("Killing Streamlink process")
                    self._current_process.kill()

            said = False
            while utils.is_alive_safe(self.__stdout_thread) or utils.is_alive_safe(self.__stderr_thread):
                if not said:
                    self.__stdout_queue = None
                    self.__stderr_queue = None
                    log.debug("Waiting for stdout and stderr watcher threads to stop...")
                    said = True

            log.debug("Cleaning up...")
            self.cleanup()
            log.debug("All finished now, exiting. Bye!")
            sys.exit(0)
        sys.exit(0)

    def set_reporting_queue(self, queue: multiprocessing.Queue):
        self.__master_reporting_queue = queue

    def __start_ext_com_thread(self):
        if self.__master_reporting_queue is not None:
            self.__reporting_thread = threading.Thread(target=self.__enqueue_communicate)
            self.__reporting_thread.daemon = True
            self.__reporting_thread.start()
            return True
        return False

    def __enqueue_communicate(self):
        """
        Separate thread that pushes information about the streamer state to the master reporting queue.
        """
        while True:
            payload = {'streamer': self.streamer_name,
                       'pid': multiprocessing.current_process().pid,
                       'time_utc': int(datetime.now().strftime('%s')),
                       "is_live": False,
                       }
            if self._current_process is not None:
                if self._current_process.poll() is None:
                    try:
                        chunk_time_elapsed = time.time() - self.__chunk_start_time
                    except TypeError:
                        chunk_time_elapsed = 0
                    try:
                        stream_time_elapsed = time.time() - self.__stream_start_time
                    except TypeError:
                        stream_time_elapsed = 0

                    payload = {**payload, **{"is_live": True,
                                             "chunk_time_elapsed": chunk_time_elapsed,
                                             'streamlink_pid': self._current_process.pid,
                                             'stream_time_elapsed': stream_time_elapsed,
                                             'chunks': self.__current_chunks}}
            self.__master_reporting_queue.put(payload)
            time.sleep(STREAMER_UPDATE_COM_STATUS_SLEEP)

    def run(self):
        """
        Main entry function to start the archiver
        """
        log.info("Launching Archiver")
        # Create download directory
        if not os.path.exists(self.download_directory) and self.make_dirs:
            try:
                os.makedirs(self.download_directory, exist_ok=True)
            except (PermissionError,) as er:
                log.critical("Permission Error was raised while trying to create download directory. "
                             "Please check the permissions of the location. "
                             "Maybe try manually creating the folder? Exiting.")
                log.debug(f"Error:: {er}")
                sys.exit(1)
            except OSError as er:
                log.critical("OS Error was raised while trying to create download directory. ")
                log.debug(f"Error:: {er}")
                sys.exit(1)

        # setup signals
        signal.signal(signal.SIGTERM, self.kill_handler)
        signal.signal(signal.SIGINT, self.kill_handler)

        self.cleanup()
        self._display_config()
        try:
            sqs = self.__start_ext_com_thread()
            if sqs:
                log.debug("Started external reporting thread")
            else:
                log.debug("No master reporting queue present, not starting external reporting thread.")
            self._streamer_watchdog()
        except Exception:
            """
            Catch all exception here so we can be sure we gracefully shut down and kill Streamlink process etc.
            We'll capture the traceback here and log it for debugging purposes.
            This only works if the error is not in the kill handler.
            """
            tb = traceback.format_exc()
            log.critical(f"Stream Archiver Crashed: {tb}")
            self.kill_handler(1, None)


def worker(master_reporting_queue=None, *args, **kwargs):
    a = StreamArchiver(*args, **kwargs)
    if master_reporting_queue is not None:
        a.set_reporting_queue(master_reporting_queue)
    a.run()
