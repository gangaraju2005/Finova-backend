"""
Gunicorn configuration for Finovo Backend.
"""
import multiprocessing

# Bind to all interfaces on port 8000
bind = "0.0.0.0:8000"

# Workers = (2 × CPU cores) + 1  (capped at 4 for t3.small)
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)

# Worker class
worker_class = "sync"

# Timeout (seconds) — increase if you have slow endpoints
timeout = 120

# Graceful timeout for worker restart
graceful_timeout = 30

# Keep-alive (seconds) — should be > ALB idle timeout (default 60)
keepalive = 65

# Logging
accesslog = "-"          # stdout
errorlog = "-"           # stderr
loglevel = "info"

# Preload app for faster worker boot (saves memory)
preload_app = True
