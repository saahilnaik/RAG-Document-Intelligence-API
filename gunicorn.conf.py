import os

bind = "0.0.0.0:8000"
worker_class = "uvicorn.workers.UvicornWorker"
# Each worker loads its own copy of the embedding model (~0.5-1 GB RAM).
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
timeout = 120  # worker heartbeat; async handlers (SSE) are not affected by long streams
graceful_timeout = 30  # let in-flight streams finish on deploy
keepalive = 5
accesslog = None  # structured access log comes from RequestContextMiddleware
errorlog = "-"
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "*")  # behind Caddy on a private network
