"""Um destino bloqueado não impede o produtor de continuar a simulação."""

import logging
from threading import Event, Thread, get_ident

from vigilia.core.log import AsyncLog


def test_slow_sink_does_not_block_producer_and_shutdown_drains_in_order():
    entered, release, producer_done = Event(), Event(), Event()
    received, threads = [], []

    class SlowSink(logging.Handler):
        def emit(self, record):
            threads.append(get_ident())
            entered.set()
            assert release.wait(3)
            received.append(record.getMessage())

    pipe = AsyncLog(SlowSink())
    logger = logging.Logger("test-async-log", logging.INFO)
    logger.addHandler(pipe.handler)
    def producer():
        logger.info("dano %s", 42)
        logger.info("vitória")
        producer_done.set()
    worker = Thread(target=producer)
    try:
        worker.start()
        assert entered.wait(2)
        assert producer_done.wait(1), "I/O lento reteve o produtor"
        assert received == []
        assert all(identity != worker.ident for identity in threads)
    finally:
        release.set()
        worker.join(3)
        pipe.close()
        pipe.close()
    assert received == ["dano 42", "vitória"]
