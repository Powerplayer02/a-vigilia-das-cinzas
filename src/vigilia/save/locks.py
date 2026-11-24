"""Leases por slot: o SO libera o lock mesmo se o processo morrer."""

import os
from pathlib import Path
import time


class SlotInUseError(ValueError):
    def __init__(self):
        super().__init__("slots.in_use")


class SlotChangedError(ValueError):
    def __init__(self):
        super().__init__("slots.changed")


class SlotLease:
    def __init__(self, database: Path, slot: int):
        database = database.resolve()
        self.path = database.with_name(database.name + f".slot-{slot}.lock")
        self.file = None

    def acquire(self, timeout=0.) -> bool:
        if self.file is not None:
            return True
        deadline = time.monotonic() + timeout
        while True:
            handle = os.fdopen(os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600), "r+b")
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                if os.fstat(handle.fileno()).st_size == 0:
                    handle.write(b"\0")
                    handle.flush()
                self.file = handle
                return True
            except (OSError, BlockingIOError):
                handle.close()
                if time.monotonic() >= deadline:
                    return False
                time.sleep(.01)

    def close(self):
        if self.file is None:
            return
        handle, self.file = self.file, None
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __del__(self):
        self.close()
