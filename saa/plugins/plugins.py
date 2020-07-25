from queue import Queue


class PluginBase:
    name = "PluginBase"

    def __init__(self):
        pass

    def main(self):
        # Code goes here to run plugin
        pass

    def set_config(self, **kwargs):
        # Code goes here to configure the plugin
        pass


class ReportingPluginBase(PluginBase):
    name = "ReportingPluginBase"

    def __init__(self, data_queue: Queue):
        self._data_queue = data_queue
        self._thread = None
        super().__init__()

