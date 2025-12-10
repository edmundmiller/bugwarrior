import unittest
from unittest import mock

from bugwarrior.config import secrets


class TestOracleEval(unittest.TestCase):
    def setUp(self):
        # Clear the cache before each test
        secrets._oracle_cache.clear()

    def test_echo(self):
        self.assertEqual(secrets.oracle_eval("echo fööbår"), "fööbår")

    def test_caching(self):
        """Test that oracle_eval caches results and doesn't re-execute commands."""
        # Use a command that returns a unique value each time if not cached
        command = "echo cached_value"

        # First call should execute the command
        result1 = secrets.oracle_eval(command)
        self.assertEqual(result1, "cached_value")
        self.assertIn(command, secrets._oracle_cache)

        # Second call should return cached result without re-executing
        with mock.patch("subprocess.Popen") as mock_popen:
            result2 = secrets.oracle_eval(command)
            # Popen should not be called because result is cached
            mock_popen.assert_not_called()

        self.assertEqual(result2, "cached_value")

    def test_different_commands_not_cached(self):
        """Test that different commands are cached separately."""
        result1 = secrets.oracle_eval("echo first")
        result2 = secrets.oracle_eval("echo second")

        self.assertEqual(result1, "first")
        self.assertEqual(result2, "second")
        self.assertEqual(len(secrets._oracle_cache), 2)
