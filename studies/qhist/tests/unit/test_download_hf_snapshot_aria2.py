import tempfile
import unittest
from pathlib import Path

from download_hf_snapshot_aria2 import transport_complete


class Aria2CompletionTests(unittest.TestCase):
    def test_matching_size_without_control_file_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "shard"
            target.write_bytes(b"1234")
            self.assertTrue(transport_complete(target, 4))

    def test_sparse_or_partial_transfer_with_control_file_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "shard"
            target.write_bytes(b"1234")
            target.with_name("shard.aria2").write_bytes(b"control")
            self.assertFalse(transport_complete(target, 4))

    def test_wrong_or_unknown_size_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "shard"
            target.write_bytes(b"1234")
            self.assertFalse(transport_complete(target, 3))
            self.assertFalse(transport_complete(target, None))


if __name__ == "__main__":
    unittest.main()
