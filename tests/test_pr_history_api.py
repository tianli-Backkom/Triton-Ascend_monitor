import unittest
from unittest.mock import patch

from dashboard import GitHub


def page(nodes, more=False, cursor=None):
    return {"data": {"repository": {"pullRequest": {"timelineItems": {
        "nodes": nodes, "pageInfo": {"hasNextPage": more, "endCursor": cursor}
    }}}}}


class ForcePushAPITests(unittest.TestCase):
    def test_every_history_page_is_collected(self):
        api = GitHub()
        with patch.object(api, "get", side_effect=[
            (page([{"createdAt": "first"}], True, "cursor1"), {}),
            (page([{"createdAt": "second"}]), {}),
        ]) as get:
            self.assertEqual(api.force_push_history(2465), [{"createdAt": "first"}, {"createdAt": "second"}])
            self.assertIsNone(get.call_args_list[0].args[1]["variables"]["cursor"])
            self.assertEqual(get.call_args_list[1].args[1]["variables"]["cursor"], "cursor1")

    def test_graphql_errors_are_not_empty_history(self):
        with patch.object(GitHub, "get", return_value=({"errors": [{"message": "permission denied"}]}, {})):
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                GitHub().force_push_history(2465)

    def test_missing_pull_request_is_not_empty_history(self):
        with patch.object(GitHub, "get", return_value=({"data": {"repository": {"pullRequest": None}}}, {})):
            with self.assertRaises(RuntimeError):
                GitHub().force_push_history(2465)

    def test_stuck_cursor_fails_instead_of_looping(self):
        with patch.object(GitHub, "get", return_value=(page([{}], True, "same"), {})):
            with self.assertRaisesRegex(RuntimeError, "pagination"):
                GitHub().force_push_history(2465)


if __name__ == "__main__":
    unittest.main()
