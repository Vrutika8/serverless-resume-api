import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("TABLE_NAME", "test-table")
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import seed  # noqa: E402


class FakeBatch:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def put_item(self, Item):
        self.store[(Item["section"], Item["itemId"])] = Item

    def delete_item(self, Key):
        self.store.pop((Key["section"], Key["itemId"]), None)


class FakeTable:
    def __init__(self, store):
        self.store = store

    def batch_writer(self):
        return FakeBatch(self.store)

    def scan(self, **_):
        return {"Items": [{"section": s, "itemId": i} for s, i in self.store]}


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((SRC / "resume.json").read_text(encoding="utf-8"))

    def test_build_items_uses_expected_keys(self):
        items = seed.build_items(self.data)
        keys = {(item["section"], item["itemId"]) for item in items}
        self.assertIn(("personal", "profile"), keys)
        self.assertIn(("experience", "001"), keys)
        self.assertEqual(len(keys), len(items))

    def test_seed_removes_stale_items(self):
        store = {("experience", "099"): {"section": "experience", "itemId": "099"}}
        seed.seed_table(FakeTable(store), self.data)
        self.assertNotIn(("experience", "099"), store)
        self.assertIn(("personal", "profile"), store)


if __name__ == "__main__":
    unittest.main()
