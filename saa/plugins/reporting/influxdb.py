from requests.exceptions import ConnectionError
from saa.plugins.plugins import ReportingPluginBase
from influxdb import InfluxDBClient
import saa.utils as utils
import logging

log = logging.getLogger('root')


class InfluxDBPlugin(ReportingPluginBase):
    name = "influxdb"

    def __init__(self, data_queue):
        self.__host = None
        self.__port = 8086
        self.__user = ""
        self.__password = ""
        self.__database_name = None
        self.__ssl_enable = False
        self.__verify_ssl = False
        self.__client = None
        super().__init__(data_queue)

    def main(self):
        log.info(f"[{self.__class__.__name__}] Starting InfluxDB Status Plugin...")
        log.info("\n----------"
                    "\nInfluxDB Config:"
                    f"\nHost: {self.__host}"
                    f"\nPort: {self.__port}"
                    f"\nUser: {self.__user}"
                    f"\nDatabase: {self.__database_name}"
                    f"\nSSL Enable: {self.__ssl_enable}"
                    f"\nVerify SSL: {self.__verify_ssl}"
                    "\n----------")

        self.__client = InfluxDBClient(
            username=self.__user,
            password=self.__password,
            host=self.__host,
            port=self.__port,
            database=self.__database_name,
            ssl=self.__ssl_enable,
            verify_ssl=self.__verify_ssl
        )
        self.__loop()

    def __loop(self):
        """Main loop that handles sending data to influxdb"""
        while True:
            data = self._data_queue.get()
            log.debug(data)
            self.__send_payload(data)

    def __send_payload(self, data):
        if data.get('is_live'):
            fields = {
                    "is_live": int(data.get('is_live')),
                    "chunk_time_elapsed": data.get('chunk_time_elapsed') or 0.0,
                    "stream_time_elapsed": data.get('stream_time_elapsed') or 0.0,
                    "chunks": data.get('chunks') or 0
                }
        else:
            fields = {"is_live": int(data.get('is_live'))}

        payload = [
            {
                "measurement": "streamers",
                "time": data.get('time_utc'),
                "tags": {
                    "streamer": f"{utils.convert_to_basic_string(data.get('streamer'))}"
                },
                "fields": fields
            }
        ]

        try:
            self.__client.write_points(payload, time_precision="s")
        except ConnectionError as e:
            log.critical(f"[{self.__class__.__name__}] Failed to write points to InfluxDB! (Connection Error: {e})")

    def set_config(self, **kwargs):
        self.__host = kwargs.get('host', self.__host)
        self.__port = kwargs.get('port', self.__port)
        self.__user = kwargs.get('user', self.__user)
        self.__password = kwargs.get('password', self.__password)
        self.__database_name = kwargs.get('dbname', self.__database_name)
        self.__ssl_enable = bool(kwargs.get('ssl', self.__ssl_enable))
        self.__verify_ssl = bool(kwargs.get('verify_ssl', self.__verify_ssl))
