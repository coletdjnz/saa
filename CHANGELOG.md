# Changelog

##### 2020.07.25
- Basic plugin implementation. For now there are only Reporting Plugins. 
- Reporting plugins: 
    - Each streamer process reports back basic status data.
    - This data is fed to each enabled reporting plugin.
    - Currently have InfluxDB reporting plugin to send such data to influxdb.
    - Reporting plugins are located in plugins/reporting. See docs/plugins.md on how to implement your own plugin.
- Add setup.py (you can now install by going `pip install .` and run with `saa <args>`)
##### 2020.07.18

- More detailed logging when errors occur during is live checks.