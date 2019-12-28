- Better way of handling specific errors/warnings printed in stdout

- Use a thread pool, and from that, be able to check for new streams added to config.yml on the fly
and start a new thread. 

- Separate Rclone script to transfer completed stream chunks to a remote, to be run with cron or similar programs. 

- Stream metadata retrieval (initial, continuous, final)