import os
import socket
import time

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))


def connect(retries: int = 3, timeout: float = 5.0):
    last = None
    for attempt in range(1, retries + 1):
        try:
            return socket.create_connection((DB_HOST, DB_PORT), timeout=timeout)
        except OSError as e:
            last = e
            print(f"connect attempt {attempt}/{retries} to {DB_HOST}:{DB_PORT} failed: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError(f"DB unreachable: {DB_HOST}:{DB_PORT}") from last
