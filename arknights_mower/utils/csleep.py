import time
from datetime import datetime, timedelta

from arknights_mower.utils import config


class MowerExit(Exception):
    pass


def csleep(interval: float = 1, wake_event=None):
    """check and sleep"""
    stop_time = datetime.now() + timedelta(seconds=interval)
    while True:
        if config.stop_mower.is_set():
            raise MowerExit
        if wake_event is not None and wake_event.is_set():
            return
        remaining = stop_time - datetime.now()
        if remaining > timedelta(seconds=1):
            if wake_event is None:
                time.sleep(1)
            else:
                wake_event.wait(1)
        elif remaining > timedelta():
            if wake_event is None:
                time.sleep(remaining.total_seconds())
            else:
                wake_event.wait(remaining.total_seconds())
        else:
            return
