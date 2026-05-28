from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QThreadPool, QTimer

    from gui import FunctionWorker
except ImportError as exc:  # pragma: no cover - depends on optional GUI deps in test env.
    raise unittest.SkipTest(f"PySide6 is not installed: {exc}")


class FunctionWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def run_worker(self, worker: FunctionWorker) -> None:
        loop = QEventLoop()
        worker.signals.finished.connect(loop.quit)
        QThreadPool.globalInstance().start(worker)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()

    def test_worker_emits_result(self) -> None:
        results: list[object] = []
        errors: list[str] = []
        worker = FunctionWorker(lambda: "ok")
        worker.signals.result.connect(results.append)
        worker.signals.error.connect(errors.append)

        self.run_worker(worker)

        self.assertEqual(results, ["ok"])
        self.assertEqual(errors, [])

    def test_worker_emits_error(self) -> None:
        results: list[object] = []
        errors: list[str] = []

        def fail() -> None:
            raise RuntimeError("boom")

        worker = FunctionWorker(fail)
        worker.signals.result.connect(results.append)
        worker.signals.error.connect(errors.append)

        self.run_worker(worker)

        self.assertEqual(results, [])
        self.assertEqual(errors, ["boom"])


if __name__ == "__main__":
    unittest.main()
