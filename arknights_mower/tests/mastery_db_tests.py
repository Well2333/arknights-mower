import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils import mastery_db


class TestMasteryDatabaseLifecycle(unittest.TestCase):
    def test_expired_in_progress_remains_visible_until_terminal_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_tmp = Path(temp_dir)

            with patch.object(
                mastery_db,
                "get_path",
                side_effect=lambda value: (
                    app_tmp if value == "@app/tmp" else app_tmp / "data.db"
                ),
            ):
                mastery_db.insert_plan(
                    "char_test",
                    1,
                    "pending",
                    level=1,
                )
                mastery_db.set_plan_status(
                    "char_test",
                    1,
                    "in_progress",
                    level=1,
                    expires_at="2020-01-01 00:00:00",
                )

                self.assertTrue(mastery_db.has_in_progress_plan())
                current = mastery_db.get_in_progress_plan()
                self.assertEqual(current["status"], "in_progress")
                self.assertEqual(current["expires_at"], "2020-01-01 00:00:00")

                mastery_db.set_plan_status(
                    "char_test",
                    1,
                    "completed",
                    level=1,
                )

                self.assertFalse(mastery_db.has_in_progress_plan())
                self.assertIsNone(mastery_db.get_in_progress_plan())


if __name__ == "__main__":
    unittest.main()
