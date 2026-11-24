"""Configuração do log do executável."""

import logging
import atexit
from logging.handlers import QueueHandler, QueueListener
from queue import SimpleQueue


class AsyncLog:
    """O produtor só enfileira; o destino de I/O roda numa thread dedicada."""

    def __init__(self, sink: logging.Handler):
        queue = SimpleQueue()
        self.handler = QueueHandler(queue)
        self.listener = QueueListener(queue, sink, respect_handler_level=True)
        self.listener.start()
        self.closed = False

    def close(self):
        if not self.closed:
            self.closed = True
            self.listener.stop()
            self.handler.close()


_owned: AsyncLog | None = None


def configure_logging() -> None:
    """Preserva handlers externos; o executável próprio usa I/O assíncrono."""
    global _owned
    root = logging.getLogger()
    if root.handlers:
        return
    sink = logging.StreamHandler()
    sink.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    _owned = AsyncLog(sink)
    root.setLevel(logging.INFO)
    root.addHandler(_owned.handler)


def shutdown_logging():
    """Drena mensagens no encerramento, depois da simulação."""
    global _owned
    if _owned is not None:
        owned, _owned = _owned, None
        logging.getLogger().removeHandler(owned.handler)
        owned.close()


atexit.register(shutdown_logging)
