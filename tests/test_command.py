import logging
import os
import pathlib
from unittest import TestCase, mock

from typer.testing import CliRunner

from bugwarrior import command
from bugwarrior.config.load import BugwarriorConfigParser

from .base import ConfigTest
from .test_github import ARBITRARY_EXTRA, ARBITRARY_ISSUE


def fake_github_issues(self):
    yield from [self.get_issue_for_record(ARBITRARY_ISSUE, ARBITRARY_EXTRA)]


def fake_bz_issues(self):
    yield from [
        self.get_issue_for_record(
            {
                "id": 1234567,
                "status": "NEW",
                "summary": "This is the issue summary",
                "product": "Product",
                "component": "Something",
                "description": "(bw)Is#1234567 - This is the issue summary .. https://http://one.com//show_bug.cgi?id=1234567",  # noqa: E501
                "priority": "H",
                "project": "Something",
                "tags": [],
            },
            {"url": "https://http://one.com//show_bug.cgi?id=1234567"},
        )
    ]


class TestPull(ConfigTest):
    def setUp(self):
        super().setUp()

        self.runner = CliRunner()
        self.config = BugwarriorConfigParser()

        self.config["general"] = {
            "targets": "my_service",
            "static_fields": "project, priority",
            "taskrc": self.taskrc,
        }
        self.config["my_service"] = {
            "service": "github",
            "github.login": "ralphbean",
            "github.token": "abc123",
            "github.username": "ralphbean",
        }

        self.write_rc(self.config)

    def write_rc(self, conf):
        """
        Write configparser object to temporary bugwarriorrc path.
        """
        rcfile = os.path.join(self.tempdir, ".config/bugwarrior/bugwarriorrc")
        if not os.path.exists(os.path.dirname(rcfile)):
            os.makedirs(os.path.dirname(rcfile))
        with open(rcfile, "w") as configfile:
            conf.write(configfile)
        return rcfile

    @mock.patch("bugwarrior.services.github.GithubService.issues", fake_github_issues)
    def test_success(self):
        """
        A normal `bugwarrior pull` invocation.
        """
        result = self.runner.invoke(command.app, args=["pull", "--debug"])

        # Console output goes to stderr, which CliRunner captures in output
        output = result.output
        self.assertIn("Adding 1 tasks", output)
        self.assertIn("Sync complete:", output)

    @mock.patch(
        "bugwarrior.services.github.GithubService.issues",
        lambda self: (_ for _ in ()).throw(Exception("message")),
    )
    def test_failure(self):
        """
        A broken `bugwarrior pull` invocation.
        """
        result = self.runner.invoke(command.app, args=["pull"])

        # Error messages go to console (stderr captured in output)
        self.assertIn("Aborted [my_service] due to critical error", result.output)

    @mock.patch("bugwarrior.services.github.GithubService.issues", lambda self: [])
    @mock.patch(
        "bugwarrior.services.bz.BugzillaService.issues",
        lambda self: (_ for _ in ()).throw(Exception("message")),
    )
    def test_partial_failure_survival(self):
        """
        One service is broken but the other succeeds.

        Synchronization should work for succeeding services even if one service
        fails.  See https://github.com/ralphbean/bugwarrior/issues/279.
        """
        self.config["general"]["targets"] = "my_service,my_broken_service"
        self.config["my_broken_service"] = {
            "service": "bugzilla",
            "bugzilla.base_uri": "bugzilla.redhat.com",
            "bugzilla.username": "rbean@redhat.com",
        }

        self.write_rc(self.config)

        # Use --debug to disable multiprocessing so mocks work
        result = self.runner.invoke(command.app, args=["pull", "--debug"])

        self.assertIn(
            "Aborted [my_broken_service] due to critical error", result.output
        )
        self.assertIn("Sync complete:", result.output)

    @mock.patch("bugwarrior.services.github.GithubService.issues", fake_github_issues)
    @mock.patch("bugzilla.Bugzilla")
    def test_partial_failure_database_integrity(self, bugzillalib):
        """
        When a service fails and is terminated, don't close existing tasks.

        See https://github.com/ralphbean/bugwarrior/issues/821.
        """
        # Add the broken service to the configuration.
        self.config["general"]["targets"] = "my_service,my_broken_service"
        self.config["my_broken_service"] = {
            "service": "bugzilla",
            "bugzilla.base_uri": "bugzilla.redhat.com",
            "bugzilla.username": "rbean@redhat.com",
        }
        self.write_rc(self.config)

        # Add a task to each service.
        # Use --debug to disable multiprocessing so mocks work
        with mock.patch(
            "bugwarrior.services.bz.BugzillaService.issues", fake_bz_issues
        ):
            result = self.runner.invoke(command.app, args=["pull", "--debug"])
        self.assertIn("Adding 2 tasks", result.output)

        # Break the service and run pull again.
        with mock.patch(
            "bugwarrior.services.bz.BugzillaService.issues",
            lambda self: (_ for _ in ()).throw(Exception("message")),
        ):
            result = self.runner.invoke(command.app, args=["pull", "--debug"])

        # Make sure my_broken_service failed while my_service succeeded.
        self.assertIn(
            "Aborted [my_broken_service] due to critical error", result.output
        )
        self.assertNotIn("Aborted my_service due to critical error", result.output)

        # Assert that issues weren't closed (Closing X tasks not shown)
        self.assertNotIn("Closing", result.output)

    @mock.patch("bugwarrior.services.github.GithubService.issues", fake_github_issues)
    def test_legacy_cli(self):
        """
        Test that invoking the app directly with 'pull' command works.
        """
        result = self.runner.invoke(command.app, args=["pull", "--debug"])

        output = result.output
        self.assertIn("Adding 1 tasks", output)
        self.assertIn("Sync complete:", output)


class TestIni2Toml(TestCase):
    def setUp(self):
        super().setUp()
        self.runner = CliRunner()

    def test_bugwarriorrc(self):
        basedir = pathlib.Path(__file__).parent
        result = self.runner.invoke(
            command.app, args=["ini2toml", str(basedir / "config/example-bugwarriorrc")]
        )

        self.assertEqual(result.exit_code, 0)

        self.maxDiff = None
        with open(basedir / "config/example-bugwarrior.toml", "r") as f:
            self.assertEqual(result.stdout, f.read())
