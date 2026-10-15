bind = "0.0.0.0:15000"
workers = 4
worker_class = "sync" # 默认sync；IO密集型可换 gevent/eventlet
timeout = 120
keepalive = 5
log_level = "info"
accesslog = "./access.log"
errorlog = "./error.log"
pidfile = "./gunicorn.pid"

