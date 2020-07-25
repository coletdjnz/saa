from saa.plugins.plugins import PluginBase, ReportingPluginBase
from queue import Queue
from time import sleep
import saa.plugins.reporting
import saa.utils as utils
import multiprocessing
import threading
import importlib
import logging
import pkgutil
import inspect

log = logging.getLogger("root")


class PluginHandlerBase:

    def __init__(self, plugin_subclass=None, plugin_pkg=None):
        self.__plugin_subclass = plugin_subclass or PluginBase
        self.__plugin_pkg = plugin_pkg  # Required
        self._plugins = {}

    def find_plugins(self, package):
        """
        Automatically discover plugins for a given package.
        For each class in each module in such package if the class is a subclass of the base plugin and not the base plugin,
        then we found plugin.
        Appends found plugins to self._plugins - format {plugin.name: plugin class}
        """
        for _, plugin_name, ispkg in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
            if ispkg:
                continue
            plugin_module = importlib.import_module(plugin_name)
            for _, class_ in inspect.getmembers(plugin_module, inspect.isclass):
                if issubclass(class_, self.__plugin_subclass) and class_ is not self.__plugin_subclass:
                    log.debug(f"Discovered Plugin: {class_.__module__}.{class_.__name__}")
                    if class_.name not in self._plugins:
                        self._plugins[class_.name] = class_

    def load_plugins(self):
        """
        Finds and loads plugins.
        Clears the current list of plugins if applicable.
        """
        self._plugins.clear()
        log.debug(f"Finding plugins in {self.__plugin_pkg}")
        self.find_plugins(self.__plugin_pkg)


class ReportingPluginHandler(PluginHandlerBase):
    def __init__(self, master_reporting_queue, enabled_plugin_configs: dict):
        self._plugin_threads = {}
        self._plugin_data_queues = []
        self._plugin_configs = enabled_plugin_configs
        self._incoming_data_queue = master_reporting_queue
        self._queue_splitter_thread = None
        super().__init__(plugin_subclass=ReportingPluginBase, plugin_pkg=saa.plugins.reporting)
        self.load_plugins()

    def start(self):
        self._launch_queue_splitter()  # This shouldn't crash...
        while True:
            for plugin_c_name in self._plugin_configs:
                # Check if plugin exists.
                if plugin_c_name not in self._plugins:
                    log.debug(f"Plugin '{plugin_c_name}' does not exist. Ignoring.")
                    continue
                # Launch plugin if not already launched
                if plugin_c_name not in self._plugin_threads:
                    plugin_configured = self.configure_plugin(plugin_c_name, self._plugin_configs[plugin_c_name])
                    self.launch_plugin(plugin_configured)
                    continue

                # Check if plugin is still alive, if not, relaunch
                if not utils.is_alive_safe(self._plugin_threads[plugin_c_name]):
                    log.error(f"[ReportingPluginHandler] {plugin_c_name} thread has crashed! Restarting plugin...")
                    plugin_configured = self.configure_plugin(plugin_c_name, self._plugin_configs[plugin_c_name])
                    self.launch_plugin(plugin_configured)
                    continue
            sleep(2)

    def configure_plugin(self, plugin_name, plugin_config):
        """
        Configure a given plugin with a queue and config.
        Assumes plugin_name represents a valid plugin.
        :return: plugin object
        """
        q = Queue()
        plug_c = self._plugins[plugin_name](q)
        if plugin_config is None:
            plugin_config = {}
        plug_c.set_config(**plugin_config)
        self._plugin_data_queues.append(q)
        return plug_c

    def _launch_queue_splitter(self):
        self._queue_splitter_thread = threading.Thread(target=self._queue_splitter)
        self._queue_splitter_thread.daemon = True
        self._queue_splitter_thread.start()

    def _queue_splitter(self):
        """
        Send data from the master incoming queue to all the plugin queues
        To be launched as a separate thread
        """
        while True:
            next_data = self._incoming_data_queue.get()
            # Push to all queues
            for q in self._plugin_data_queues:
                q.put(next_data)

    def launch_plugin(self, plugin):
        thread = threading.Thread(target=plugin.main)
        thread.daemon = True
        thread.name = plugin.name
        thread.start()
        self._plugin_threads[thread.name] = thread
        return thread


def launch_reporting_plugins(queue: multiprocessing.Queue, plugin_configs: dict):
    """
    Launches the Reporting Plugin Handler which will launch all the enabled reporting plugins.
    """
    status_plugins = ReportingPluginHandler(master_reporting_queue=queue, enabled_plugin_configs=plugin_configs)
    status_plugins_thread = threading.Thread(target=status_plugins.start)
    status_plugins_thread.daemon = True
    status_plugins_thread.start()
