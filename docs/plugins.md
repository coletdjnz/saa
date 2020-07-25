# Table of Contents
1. [Configuring Plugins](#configuring-plugins)
2. [Creating Plugins](#creating-plugins)

# Configuring Plugins

## InfluxDB Plugin

```yaml
# config.yml
plugins:
    influxdb:
      host: localhost
      port: 8086
      user: "foo"
      password: "supersecretpassword"
      dbname: "saa"
      ssl: False
      verify_ssl: False
```


# Creating Plugins

Currently SAA only supports "Reporting Plugins". 


## Reporting Plugins

These are plugins that receive data from each streamer process about their state - is live, how long been live for etc. 

Reporting plugins are to be put in `saa/plugins/reporting`. 

This works by each streamer process putting data in a "master data queue", which is shared between all streamer processes. 
The `ReportingPluginHandler` dequeues this data, and sends it to all the individual plugin queues. 

Each Reporting plugin runs in its own thread and has its own incoming data queue. It should continuously dequeue and process any data that comes in.

#### Incoming data queue

Each streamer process puts a dictionary of data into the master data queue in `__enqueue_communicate` function in [archiver.py](../saa/archiver.py).

Data is sent every 10 seconds per streamer. 

Keys:
- `streamer` - streamer name as defined in `streamers.yml`
- `pid` - process id of streamer process (**not** the streamlink process)
- `time_utc` - epoch time in UTC of when this payload was created
- `is_live` - bool value representing if a streamer is live or not

When the streamer is live, there are additional keys:
- `chunk_time_elapsed` - how much time as elapsed for the current recording chunk
- `stream_time_elapsed` - total time the stream as been running for
- `streamlink_pid` - process id of streamlink process
- `chunks` - how many recording chunks there have been for current stream recording. 

#### Building a reporting plugin
A reporting plugin must inherit `ReportingPluginBase`. 

As well as include these 3 methods:
- a public `name` variable, which gets used as the plugin name in `config.yml`
- `__init__(self, data_queue)` method taking `data_queue` parameter, and includes `super().__init__(data_queue)`
 - `set_config(self, **kwargs)` - the config in `config.yml` for this plugin gets passed to this function
 - `main(self)` - the function that gets called by threading.Thread() to launch the plugin
 
 
 
 Here is a quick example:
 
 ```python
from saa.plugins.plugins import ReportingPluginBase
import logging

log = logging.getLogger('root')

class TestPlugin(ReportingPluginBase):
    name = "test"
    def __init__(self, data_queue):
        self.__some_variable = None
        super().__init__(data_queue)
    
    def main(self):
        log.info(f"[{self.__class__.__name__}] Starting test reporting plugin...")
        while True:
            print(self._data_queue.get())
    
    def set_config(self, **kwargs):
        self.__some_variable = kwargs.get("foo", self.__some_variable)
```

And in `config.yml` you would add:

```yaml
plugins:
    test:
      foo: "my value"
```

(This is a working example. Drop this code into a python file in `saa/plugins/reporting/`, edit `config.yml` and run to see how it works!)

For a more detailed example, [view the influxdb.py reporting plugin.](../saa/plugins/reporting/influxdb.py)