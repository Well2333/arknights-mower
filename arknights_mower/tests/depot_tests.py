import unittest
from unittest.mock import patch

from arknights_mower.utils import depot


class TestDepotUnknownItems(unittest.TestCase):
    def test_unknown_activity_item_is_skipped_without_losing_known_items(self):
        mapping = {
            "known_id": ("known_key", "known_label", "Known Material"),
        }
        items = [
            {"id": "known_id", "count": "12"},
            {"id": "ark_odc_act53side_spitem_1", "count": "3"},
            {"id": "zero_item", "count": "0"},
        ]

        with (
            patch.object(depot, "key_mapping", mapping),
            patch.object(depot.logger, "warning") as warning,
        ):
            result = depot.inventory_items_by_name(items)

        self.assertEqual(result, {"Known Material": 12})
        warning.assert_called_once()
        self.assertIn(
            "ark_odc_act53side_spitem_1",
            warning.call_args.args[0],
        )


if __name__ == "__main__":
    unittest.main()
