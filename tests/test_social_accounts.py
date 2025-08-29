import unittest
from unittest.mock import patch
from plugins import bio_manager as bm


class SocialAccountsTest(unittest.TestCase):
    def test_append_to_bio_list_handles_multiple_accounts(self):
        storage = {}

        def fake_update(user_id, key, update_fn):
            storage[key] = update_fn(storage.get(key))

        with patch.object(bm, "_update_json_field", fake_update):
            bm.append_to_bio_list("u1", "social_accounts.discord", "disc1")
            bm.append_to_bio_list("u1", "social_accounts.discord", "disc2")
            bm.append_to_bio_list("u1", "social_accounts.telegram", "tel1")

        self.assertEqual(
            storage["social_accounts"],
            {"discord": ["disc1", "disc2"], "telegram": ["tel1"]},
        )

    def test_merge_nested_dicts_merges_lists(self):
        original = {"discord": ["a"], "x": ["x1"]}
        updates = {"discord": ["b", "a"], "telegram": ["t1"]}
        merged = bm._merge_nested_dicts(original, updates)
        self.assertEqual(set(merged["discord"]), {"a", "b"})
        self.assertEqual(merged["telegram"], ["t1"])
        self.assertEqual(merged["x"], ["x1"])


if __name__ == "__main__":
    unittest.main()
