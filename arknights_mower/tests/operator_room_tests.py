import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from arknights_mower.solvers.base_mixin import (
    OP_ROOM,
    OP_ROOM_WIDTH,
    BaseMixin,
    _foreground_width,
    _resolve_operator_room_prefix,
)


class TestOperatorRoomRecognition(unittest.TestCase):
    def test_blank_name_crop_returns_empty_result(self):
        solver = BaseMixin()

        self.assertEqual(
            solver.read_operator_in_room(np.zeros((58, 344), dtype=np.uint8)), ""
        )

    def test_enter_room_verifies_success_after_tap(self):
        solver = BaseMixin()
        solver.recog = SimpleNamespace(img=np.zeros((1080, 1920, 3), dtype=np.uint8))
        solver.find = Mock(side_effect=[((100, 100), (200, 200)), None])
        solver.detect_room = Mock(return_value="dormitory_1")
        solver.adjust_room = Mock(return_value=((100, 100), (200, 200)))
        solver.tap = Mock()
        solver.back_to_index = Mock()
        solver.back_to_infrastructure = Mock()

        with patch(
            "arknights_mower.solvers.base_mixin.segment.base",
            return_value={"dormitory_1": ((100, 100), (200, 200))},
        ):
            solver.enter_room("dormitory_1")

        solver.tap.assert_called_once()
        solver.detect_room.assert_called_once()
        solver.back_to_index.assert_not_called()

    def test_enter_room_resets_view_between_failed_batches(self):
        solver = BaseMixin()
        solver.recog = SimpleNamespace(img=np.zeros((1080, 1920, 3), dtype=np.uint8))
        solver.find = Mock(return_value=((100, 100), (200, 200)))
        solver.detect_room = Mock()
        solver.adjust_room = Mock(return_value=((100, 100), (200, 200)))
        solver.tap = Mock()
        solver.back_to_index = Mock()
        solver.back_to_infrastructure = Mock()

        with (
            patch(
                "arknights_mower.solvers.base_mixin.segment.base",
                return_value={"dormitory_1": ((100, 100), (200, 200))},
            ),
            self.assertRaisesRegex(Exception, "未成功进入房间"),
        ):
            solver.enter_room("dormitory_1")

        self.assertEqual(solver.tap.call_count, 15)
        self.assertEqual(solver.back_to_index.call_count, 2)
        self.assertEqual(solver.back_to_infrastructure.call_count, 2)

    def test_prefix_operator_uses_long_name_when_extra_text_is_visible(self):
        result = _resolve_operator_room_prefix(
            "凯尔希",
            0.57,
            {"凯尔希": 0.57, "凯尔希·思衡托": 0.54},
            sample_width=237,
            template_widths={"凯尔希": 106, "凯尔希·思衡托": 254},
        )

        self.assertEqual(result, "凯尔希·思衡托")

    def test_prefix_operator_keeps_short_name_without_extra_text(self):
        result = _resolve_operator_room_prefix(
            "凯尔希",
            1.0,
            {"凯尔希": 1.0, "凯尔希·思衡托": 0.64},
            sample_width=106,
            template_widths={"凯尔希": 106, "凯尔希·思衡托": 254},
        )

        self.assertEqual(result, "凯尔希")

    def test_current_templates_keep_old_and_new_kaltsit_distinct(self):
        solver = BaseMixin()
        self.assertEqual(solver.read_operator_in_room(OP_ROOM["凯尔希"]), "凯尔希")
        self.assertEqual(
            solver.read_operator_in_room(OP_ROOM["凯尔希·思衡托"]), "凯尔希·思衡托"
        )

        old_score = cv2.minMaxLoc(
            cv2.matchTemplate(OP_ROOM["凯尔希"], OP_ROOM["凯尔希"], cv2.TM_CCORR_NORMED)
        )[1]
        new_score = cv2.minMaxLoc(
            cv2.matchTemplate(
                OP_ROOM["凯尔希"], OP_ROOM["凯尔希·思衡托"], cv2.TM_CCORR_NORMED
            )
        )[1]
        self.assertEqual(
            _resolve_operator_room_prefix(
                "凯尔希",
                old_score,
                {"凯尔希": old_score, "凯尔希·思衡托": new_score},
                _foreground_width(OP_ROOM["凯尔希"]),
                OP_ROOM_WIDTH,
            ),
            "凯尔希",
        )


if __name__ == "__main__":
    unittest.main()
