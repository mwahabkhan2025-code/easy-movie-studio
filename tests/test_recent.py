import os
import shutil
import tempfile
import unittest

from easy_movie_studio.recent import RecentProjects


class RecentProjectsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.recent = RecentProjects(os.path.join(self.tmp, "cfg", "recent.json"), limit=3)

    def make(self, name):
        path = os.path.join(self.tmp, name)
        with open(path, "w") as handle:
            handle.write("{}")
        return path

    def test_most_recent_first_and_deduplicated(self):
        a, b = self.make("a.mmproj"), self.make("b.mmproj")
        self.recent.add(a)
        self.recent.add(b)
        self.recent.add(a)
        self.assertEqual(self.recent.items(), [a, b])

    def test_limit_is_enforced(self):
        paths = [self.make(f"{i}.mmproj") for i in range(5)]
        for p in paths:
            self.recent.add(p)
        self.assertEqual(self.recent.items(), paths[:1:-1])  # last three, newest first

    def test_missing_files_are_hidden(self):
        a = self.make("a.mmproj")
        self.recent.add(a)
        os.remove(a)
        self.assertEqual(self.recent.items(), [])

    def test_remove_and_clear(self):
        a, b = self.make("a.mmproj"), self.make("b.mmproj")
        self.recent.add(a)
        self.recent.add(b)
        self.recent.remove(a)
        self.assertEqual(self.recent.items(), [b])
        self.recent.clear()
        self.assertEqual(self.recent.items(), [])

    def test_corrupt_store_is_ignored(self):
        os.makedirs(os.path.dirname(self.recent.store_path))
        with open(self.recent.store_path, "w") as handle:
            handle.write("not json")
        self.assertEqual(self.recent.items(), [])
        a = self.make("a.mmproj")
        self.recent.add(a)
        self.assertEqual(self.recent.items(), [a])


if __name__ == "__main__":
    unittest.main()
