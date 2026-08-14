import io
import logging
import sys
import unittest
from queue import Queue
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.solvers.shop import _template_sqdiff_score
from arknights_mower.utils import config
from arknights_mower.utils.digit_reader import DigitReader
from arknights_mower.utils.log import EncodingSafeStream, Handler


class AsciiStream(io.StringIO):
    encoding = "ascii"


class TestRuntimeRegressions(unittest.TestCase):
    def test_web_log_handler_formats_plain_record(self):
        output = Queue()
        record = logging.LogRecord(
            "test", logging.INFO, __file__, 1, "plain %s", ("message",), None
        )

        with patch.object(config, "log_queue", output):
            Handler().handle(record)

        message = output.get_nowait()
        self.assertIn(" INFO plain message", message)
        self.assertRegex(message, r"^\d{4}-\d{2}-\d{2} ")

    def test_web_log_handler_preserves_exception_traceback(self):
        output = Queue()
        try:
            raise ValueError("web-log-probe")
        except ValueError:
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            "request failed",
            (),
            exc_info,
        )

        with patch.object(config, "log_queue", output):
            Handler().handle(record)

        message = output.get_nowait()
        self.assertIn(" ERROR request failed", message)
        self.assertIn("Traceback (most recent call last)", message)
        self.assertIn("ValueError: web-log-probe", message)

    def test_digit_reader_uses_image_dimensions_when_not_provided(self):
        reader = DigitReader.__new__(DigitReader)
        reader.time_template = [np.zeros((1, 1), dtype=np.uint8) for _ in range(10)]
        matches = []
        for digit in range(10):
            result = np.zeros((1, 200), dtype=np.float32)
            if digit < 6:
                result[0, digit * 10 + 5] = 1
            matches.append(result)

        image = np.zeros((720, 1280), dtype=np.uint8)
        with (
            patch.object(cv2, "resize", return_value=np.zeros((33, 1421))),
            patch.object(cv2, "matchTemplate", side_effect=matches),
        ):
            result = reader.get_time(image)

        self.assertEqual(result, "01:23:45")

    def test_failed_order_time_read_is_not_reported_as_zero_seconds(self):
        solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
        solver.recog = MagicMock(w=1920, h=1080)
        solver.find = MagicMock(return_value=(1, 1))
        solver.read_time = MagicMock(return_value=None)

        with self.assertRaisesRegex(Exception, "订单倒计时识别失败"):
            solver.get_order_remaining_time()

    def test_shop_template_match_pads_small_fragment(self):
        fragment = np.zeros((3, 3), dtype=np.uint8)
        template = np.zeros((31, 20), dtype=np.uint8)

        score = _template_sqdiff_score(fragment, template)

        self.assertTrue(np.isfinite(score))

    def test_console_stream_escapes_unsupported_characters(self):
        target = AsciiStream()
        stream = EncodingSafeStream(target)

        stream.write("GALLUS²")

        self.assertEqual(target.getvalue(), r"GALLUS\xb2")


if __name__ == "__main__":
    unittest.main()
