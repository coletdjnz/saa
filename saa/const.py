STREAMLINK_BINARY = "streamlink"

# recheck every 30 seconds
RECHECK_CHANNEL_STATUS_TIME = 30

TIME_NICE_FORMAT = "%Y%m%d_%H%M%S"

TEMP_FILE_EXT = ".sapart"

LOG_LEVEL_DEFAULT = "INFO"

# Stream archiver defaults
STREAM_SPLIT_TIME = 86400
STREAM_DEFAULT_NAME = "unknown_stream"
STREAM_DEFAULT_QUALITY = "best"
STREAM_WATCHDOG_DEFAULT_SLEEP = 1
STREAMERS_WATCHER_DEFAULT_SLEEP = 5

# rclone defaults
RCLONE_BIN_LOCATION = "rclone"
RCLONE_CONFIG_LOCATION = ""
RCLONE_DEFAULT_TRANSFERS = 4
RCLONE_DEFAULT_OPERATION = "move"
RCLONE_PROCESS_REPEAT_TIME = 9000  # every 2.5 hours by default

STREAMERS_REQUIRED_FIELDS = {

    'url': str,

}

DEFAULT_DOWNLOAD_DIR = "."
NEWLINE_CHAR = "\n"
