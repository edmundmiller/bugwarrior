import datetime
import sys
from unittest.mock import Mock, patch

import pytz

from bugwarrior.collect import TaskConstructor

from .base import AbstractServiceTest, ServiceTest

# Mock EventKit and Foundation before importing our service
mock_eventkit = Mock()
mock_foundation = Mock()
sys.modules["EventKit"] = mock_eventkit
sys.modules["Foundation"] = mock_foundation

from bugwarrior.services.applereminders import (  # noqa: E402
    AppleRemindersClient,
    AppleRemindersConfig,
    AppleRemindersService,
)


class MockNSDate:
    """Mock NSDate object for date handling."""

    def __init__(self, datetime_obj):
        self._datetime = datetime_obj

    def timeIntervalSince1970(self):
        """Return timestamp like NSDate."""
        return self._datetime.timestamp()


class MockNSDateComponents:
    """Mock NSDateComponents object for date components."""

    def __init__(self, datetime_obj):
        self._datetime = datetime_obj
        self.year = datetime_obj.year
        self.month = datetime_obj.month
        self.day = datetime_obj.day
        self.hour = datetime_obj.hour
        self.minute = datetime_obj.minute
        self.second = datetime_obj.second


class MockEKReminder:
    """Mock EventKit EKReminder object."""

    def __init__(self, **kwargs):
        self._id = kwargs.get("id", "test-reminder-id")
        self._title = kwargs.get("title", "Test Reminder")
        self._notes = kwargs.get("notes", "Test notes")
        self._due_date = kwargs.get("due_date")
        self._completed = kwargs.get("completed", False)
        self._completion_date = kwargs.get("completion_date")
        self._creation_date = kwargs.get("creation_date")
        self._modification_date = kwargs.get("modification_date")
        self._priority = kwargs.get("priority", 0)  # EventKit priority mapping
        self._flagged = kwargs.get("flagged", False)
        self._due_components = None
        if self._due_date:
            # Create mock NSDateComponents
            self._due_components = MockNSDateComponents(self._due_date)

    def calendarItemIdentifier(self):
        return self._id

    def title(self):
        return self._title

    def notes(self):
        return self._notes

    def isCompleted(self):
        return self._completed

    def completionDate(self):
        return MockNSDate(self._completion_date) if self._completion_date else None

    def creationDate(self):
        return MockNSDate(self._creation_date) if self._creation_date else None

    def lastModifiedDate(self):
        return MockNSDate(self._modification_date) if self._modification_date else None

    def priority(self):
        return self._priority

    def dueDateComponents(self):
        return self._due_components


class MockEKCalendar:
    """Mock EventKit EKCalendar object."""

    def __init__(self, name, reminders_data=None):
        self._name = name
        self._reminders_data = reminders_data or []

    def title(self):
        return self._name


class MockEKEventStore:
    """Mock EventKit EKEventStore object."""

    def __init__(self, lists_data=None):
        self._lists_data = lists_data or {}
        self._calendars = []
        for list_name, reminders_data in self._lists_data.items():
            self._calendars.append(MockEKCalendar(list_name, reminders_data))

    @classmethod
    def alloc(cls):
        return cls()

    def init(self):
        return self

    def calendarsForEntityType_(self, entity_type):
        return self._calendars

    def predicateForRemindersInCalendars_(self, calendars):
        # Return a mock predicate
        return Mock()

    def fetchRemindersMatchingPredicate_completion_(
        self, predicate, completion_handler
    ):
        # Return reminders for all calendars
        reminders = []
        for calendar in self._calendars:
            for reminder_data in calendar._reminders_data:
                reminders.append(MockEKReminder(**reminder_data))
        completion_handler(reminders)

    def accessGrantedForEntityType_(self, entity_type):
        return True  # Mock that we have access


# Test data constants
ARBITRARY_CREATED = datetime.datetime(2023, 1, 15, 10, 0, 0, tzinfo=pytz.UTC)
ARBITRARY_MODIFIED = datetime.datetime(2023, 1, 16, 11, 30, 0, tzinfo=pytz.UTC)
ARBITRARY_DUE = datetime.datetime(2023, 1, 20, 15, 0, 0, tzinfo=pytz.UTC)
ARBITRARY_COMPLETED = datetime.datetime(2023, 1, 18, 14, 0, 0, tzinfo=pytz.UTC)

ARBITRARY_REMINDER = {
    "id": "test-reminder-123",
    "title": "Buy groceries",
    "notes": "Milk, bread, eggs",
    "due_date": ARBITRARY_DUE,
    "completed": False,
    "completion_date": None,
    "creation_date": ARBITRARY_CREATED,
    "modification_date": ARBITRARY_MODIFIED,
    "priority": 5,  # Medium priority
    "list_name": "Shopping",
    "url": "x-apple-reminderkit://REMCDReminder/test-reminder-123",
    "flagged": True,
    "subtasks": [],
}

COMPLETED_REMINDER = {
    "id": "test-reminder-456",
    "title": "Completed task",
    "notes": "This was finished",
    "due_date": ARBITRARY_DUE,
    "completed": True,
    "completion_date": ARBITRARY_COMPLETED,
    "creation_date": ARBITRARY_CREATED,
    "modification_date": ARBITRARY_MODIFIED,
    "priority": 9,  # Internal high priority
    "list_name": "Work",
    "url": "x-apple-reminderkit://REMCDReminder/test-reminder-456",
    "flagged": False,
    "subtasks": [],
}

HIGH_PRIORITY_REMINDER = {
    "id": "test-reminder-789",
    "title": "Urgent task",
    "notes": "",
    "due_date": None,
    "completed": False,
    "completion_date": None,
    "creation_date": ARBITRARY_CREATED,
    "modification_date": ARBITRARY_MODIFIED,
    "priority": 9,  # Internal high priority
    "list_name": "Work",
    "url": "x-apple-reminderkit://REMCDReminder/test-reminder-789",
    "flagged": False,
    "subtasks": [],
}

LOW_PRIORITY_REMINDER = {
    "id": "test-reminder-low",
    "title": "Low priority task",
    "notes": "Can wait",
    "due_date": None,
    "completed": False,
    "completion_date": None,
    "creation_date": ARBITRARY_CREATED,
    "modification_date": ARBITRARY_MODIFIED,
    "priority": 1,  # Internal low priority
    "list_name": "Personal",
    "url": "x-apple-reminderkit://REMCDReminder/test-reminder-low",
    "flagged": False,
    "subtasks": [],
}

NO_PRIORITY_REMINDER = {
    "id": "test-reminder-none",
    "title": "No priority task",
    "notes": "",
    "due_date": None,
    "completed": False,
    "completion_date": None,
    "creation_date": ARBITRARY_CREATED,
    "modification_date": ARBITRARY_MODIFIED,
    "priority": 0,  # No priority
    "list_name": "Personal",
    "url": "x-apple-reminderkit://REMCDReminder/test-reminder-none",
    "flagged": False,
    "subtasks": [],
}

ARBITRARY_EXTRA = {"project": "Shopping", "annotations": []}


class TestAppleRemindersIssue(AbstractServiceTest, ServiceTest):
    """Test cases for AppleRemindersIssue class."""

    maxDiff = None
    SERVICE_CONFIG = {"service": "applereminders"}

    def test_to_taskwarrior(self):
        """Test conversion of reminder to taskwarrior format."""
        service = self.get_mock_service(AppleRemindersService)
        issue = service.get_issue_for_record(ARBITRARY_REMINDER, ARBITRARY_EXTRA)

        # Mock the date formatting to simulate proper NSDate handling
        with patch.object(issue, "_get_formatted_date") as mock_format_date:

            def format_date_side_effect(date_value):
                if date_value is None:
                    return None
                if hasattr(date_value, "strftime"):
                    return date_value.strftime("%Y%m%dT%H%M%SZ")
                return None

            mock_format_date.side_effect = format_date_side_effect
            actual_output = issue.to_taskwarrior()

        # Basic taskwarrior fields
        self.assertEqual(actual_output["project"], ARBITRARY_REMINDER["list_name"])
        self.assertEqual(actual_output["priority"], "M")  # Medium priority (5 -> M)
        self.assertEqual(actual_output["annotations"], [])
        self.assertEqual(actual_output["tags"], [])
        self.assertEqual(actual_output["status"], "pending")

        # Should have dates formatted for taskwarrior
        self.assertIn("due", actual_output)
        self.assertIn("entry", actual_output)

        # Apple Reminders specific fields
        self.assertEqual(actual_output[issue.ID], ARBITRARY_REMINDER["id"])
        self.assertEqual(actual_output[issue.TITLE], ARBITRARY_REMINDER["title"])
        self.assertEqual(actual_output[issue.NOTES], ARBITRARY_REMINDER["notes"])
        self.assertEqual(actual_output[issue.LIST], ARBITRARY_REMINDER["list_name"])
        self.assertEqual(actual_output[issue.URL], ARBITRARY_REMINDER["url"])
        self.assertEqual(actual_output[issue.FLAGGED], "true")

        # Check date fields are present
        self.assertIn(issue.DUE_DATE, actual_output)
        self.assertIn(issue.CREATION_DATE, actual_output)
        self.assertIn(issue.MODIFICATION_DATE, actual_output)
        # Completion date is only added if the reminder has one (not None)
        # Not completed, so no completion date field
        self.assertNotIn(issue.COMPLETION_DATE, actual_output)

    def test_to_taskwarrior_completed(self):
        """Test conversion of completed reminder to taskwarrior format."""
        service = self.get_mock_service(AppleRemindersService)
        issue = service.get_issue_for_record(
            COMPLETED_REMINDER, {"project": "Work", "annotations": []}
        )

        # Mock the date formatting to simulate proper NSDate handling
        with patch.object(issue, "_get_formatted_date") as mock_format_date:

            def format_date_side_effect(date_value):
                if date_value is None:
                    return None
                if hasattr(date_value, "strftime"):
                    return date_value.strftime("%Y%m%dT%H%M%SZ")
                return None

            mock_format_date.side_effect = format_date_side_effect
            actual_output = issue.to_taskwarrior()

        # Basic taskwarrior fields
        self.assertEqual(actual_output["project"], COMPLETED_REMINDER["list_name"])
        self.assertEqual(actual_output["priority"], "H")  # High priority (9 -> H)
        self.assertEqual(actual_output["annotations"], [])
        self.assertEqual(actual_output["tags"], [])
        self.assertEqual(actual_output["status"], "completed")

        # Apple Reminders specific fields
        self.assertEqual(actual_output[issue.ID], COMPLETED_REMINDER["id"])
        self.assertEqual(actual_output[issue.TITLE], COMPLETED_REMINDER["title"])
        self.assertEqual(actual_output[issue.NOTES], COMPLETED_REMINDER["notes"])
        self.assertEqual(actual_output[issue.LIST], COMPLETED_REMINDER["list_name"])
        self.assertEqual(actual_output[issue.URL], COMPLETED_REMINDER["url"])
        # Flagged field is only added if the reminder is flagged
        self.assertNotIn(
            issue.FLAGGED, actual_output
        )  # Not flagged, so no flagged field

        # Check completion date is set
        self.assertIn(issue.COMPLETION_DATE, actual_output)
        self.assertIsNotNone(actual_output[issue.COMPLETION_DATE])

    def test_to_taskwarrior_with_tags(self):
        """Test conversion with import_labels_as_tags enabled."""
        service = self.get_mock_service(
            AppleRemindersService, config_overrides={"import_labels_as_tags": True}
        )
        issue = service.get_issue_for_record(ARBITRARY_REMINDER, ARBITRARY_EXTRA)

        actual_output = issue.to_taskwarrior()

        # Should include list name as tag
        self.assertEqual(actual_output["tags"], ["Shopping"])

    def test_to_taskwarrior_priority_mapping(self):
        """Test priority mapping from Apple Reminders to Taskwarrior."""
        service = self.get_mock_service(AppleRemindersService)

        # Test high priority (9 -> H)
        issue = service.get_issue_for_record(
            HIGH_PRIORITY_REMINDER, {"project": "Work", "annotations": []}
        )
        self.assertEqual(issue.to_taskwarrior()["priority"], "H")

        # Test medium priority (5 -> M)
        issue = service.get_issue_for_record(ARBITRARY_REMINDER, ARBITRARY_EXTRA)
        self.assertEqual(issue.to_taskwarrior()["priority"], "M")

        # Test low priority (1 -> L)
        issue = service.get_issue_for_record(
            LOW_PRIORITY_REMINDER, {"project": "Personal", "annotations": []}
        )
        self.assertEqual(issue.to_taskwarrior()["priority"], "L")

        # Test no priority (0 -> None, falls back to service default)
        issue = service.get_issue_for_record(
            NO_PRIORITY_REMINDER, {"project": "Personal", "annotations": []}
        )
        self.assertEqual(
            issue.to_taskwarrior()["priority"], service.config.default_priority
        )

    def test_issues(self):
        """Test basic issues() method functionality."""
        # This will be implemented in the service test
        pass


class TestAppleRemindersClient(ServiceTest):
    """Test cases for AppleRemindersClient class."""

    SERVICE_CONFIG = {"service": "applereminders"}

    def setUp(self):
        super().setUp()
        # Set up EventKit mocks
        mock_eventkit.EKAuthorizationStatusAuthorized = 3
        mock_eventkit.EKAuthorizationStatusNotDetermined = 0
        mock_eventkit.EKAuthorizationStatusDenied = 2
        mock_eventkit.EKEntityTypeReminder = 1

        # Mock the store creation
        self.mock_store = Mock()
        self.mock_store.accessGrantedForEntityType_.return_value = True
        mock_eventkit.EKEventStore.alloc.return_value.init.return_value = (
            self.mock_store
        )

    def create_client_with_mocks(self, config):
        """Helper to create client with mocked EventKit imports."""
        with patch("builtins.__import__") as mock_import:

            def import_side_effect(name, *args, **kwargs):
                if name == "EventKit":
                    return mock_eventkit
                elif name == "Foundation":
                    return mock_foundation
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = import_side_effect
            return AppleRemindersClient(config)

    def test_init_success(self):
        """Test successful client initialization."""
        config = AppleRemindersConfig(service="applereminders")

        client = self.create_client_with_mocks(config)

        self.assertEqual(client.lists, [])
        self.assertEqual(client.include_completed, False)
        self.assertEqual(client.exclude_lists, [])
        self.assertEqual(client.due_only, False)

    def test_init_with_config(self):
        """Test client initialization with configuration."""
        config = AppleRemindersConfig(
            service="applereminders",
            lists=["Work", "Personal"],
            include_completed=True,
            exclude_lists=["Archive"],
            due_only=True,
        )

        client = self.create_client_with_mocks(config)

        self.assertEqual(client.lists, ["Work", "Personal"])
        self.assertEqual(client.include_completed, True)
        self.assertEqual(client.exclude_lists, ["Archive"])
        self.assertEqual(client.due_only, True)

    def test_init_missing_library(self):
        """Test client initialization when EventKit library is missing."""
        config = AppleRemindersConfig(service="applereminders")

        with patch(
            "builtins.__import__", side_effect=ImportError("No module named 'EventKit'")
        ):
            with self.assertRaises(ImportError) as cm:
                AppleRemindersClient(config)

            self.assertIn("EventKit framework not available", str(cm.exception))
            self.assertIn("pyobjc-framework-EventKit", str(cm.exception))

    def test_init_connection_error(self):
        """Test client initialization when EventKit access is denied."""
        config = AppleRemindersConfig(service="applereminders")

        # Mock denied access
        self.mock_store.accessGrantedForEntityType_.return_value = False

        with patch("builtins.__import__") as mock_import:

            def import_side_effect(name, *args, **kwargs):
                if name == "EventKit":
                    return mock_eventkit
                elif name == "Foundation":
                    return mock_foundation
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = import_side_effect

            with self.assertRaises(PermissionError) as cm:
                AppleRemindersClient(config)

            self.assertIn("Access to Apple Reminders is required", str(cm.exception))

        # Reset for other tests
        self.mock_store.accessGrantedForEntityType_.return_value = True

    def test_get_reminder_lists_success(self):
        """Test successful retrieval of reminder lists."""
        config = AppleRemindersConfig(service="applereminders")
        mock_calendars = [Mock(), Mock()]
        mock_calendars[0].title.return_value = "Work"
        mock_calendars[1].title.return_value = "Personal"

        self.mock_store.calendarsForEntityType_.return_value = mock_calendars

        client = self.create_client_with_mocks(config)
        lists = client.get_reminder_lists()

        self.assertEqual(lists, mock_calendars)

    def test_get_reminder_lists_error(self):
        """Test error handling when getting reminder lists fails."""
        config = AppleRemindersConfig(service="applereminders")
        self.mock_store.calendarsForEntityType_.side_effect = Exception("Access denied")

        client = self.create_client_with_mocks(config)

        with self.assertRaises(Exception) as cm:
            client.get_reminder_lists()

            self.assertIn("Access denied", str(cm.exception))

        # Reset for other tests
        self.mock_store.calendarsForEntityType_.side_effect = None

    def test_get_reminders_no_lists_configured(self):
        """Test getting reminders when no specific lists are configured."""
        config = AppleRemindersConfig(service="applereminders")

        # Set up mock calendars and reminders
        mock_calendar1 = Mock()
        mock_calendar1.title.return_value = "Work"
        mock_calendar2 = Mock()
        mock_calendar2.title.return_value = "Personal"

        self.mock_store.calendarsForEntityType_.return_value = [
            mock_calendar1,
            mock_calendar2,
        ]

        # Set up mock reminders
        mock_reminder1 = MockEKReminder(**ARBITRARY_REMINDER)
        mock_reminder2 = MockEKReminder(**LOW_PRIORITY_REMINDER)

        def mock_fetch(predicate, completion_handler):
            completion_handler([mock_reminder1, mock_reminder2])

        self.mock_store.fetchRemindersMatchingPredicate_completion_.side_effect = (
            mock_fetch
        )

        client = self.create_client_with_mocks(config)
        reminders = list(client.get_reminders())

        self.assertEqual(len(reminders), 4)  # 2 calendars * 2 reminders each
        # Check that reminders have expected titles
        titles = [r["title"] for r in reminders]
        self.assertIn("Buy groceries", titles)
        self.assertIn("Low priority task", titles)

    def test_get_reminders_specific_lists(self):
        """Test getting reminders from specific lists."""
        config = AppleRemindersConfig(
            service="applereminders", lists=["Work", "Personal"]
        )

        # Set up mock calendars
        mock_work = Mock()
        mock_work.title.return_value = "Work"
        mock_personal = Mock()
        mock_personal.title.return_value = "Personal"
        mock_archive = Mock()
        mock_archive.title.return_value = "Archive"

        self.mock_store.calendarsForEntityType_.return_value = [
            mock_work,
            mock_personal,
            mock_archive,
        ]

        # Set up mock reminders for each call
        def mock_fetch_reminders(predicate, completion_handler):
            # Return different reminders based on which calendar is being queried
            reminders = [
                MockEKReminder(**HIGH_PRIORITY_REMINDER),
                MockEKReminder(**LOW_PRIORITY_REMINDER),
            ]
            completion_handler(reminders)

        self.mock_store.fetchRemindersMatchingPredicate_completion_.side_effect = (
            mock_fetch_reminders
        )

        client = self.create_client_with_mocks(config)
        reminders = list(client.get_reminders())

        # Should only get reminders from Work and Personal lists (2 calendars * 2 reminders each)
        self.assertEqual(len(reminders), 4)
        list_names = [r["list_name"] for r in reminders]
        self.assertIn("Work", list_names)
        self.assertIn("Personal", list_names)
        self.assertNotIn("Archive", list_names)

    def test_get_reminders_exclude_lists(self):
        """Test getting reminders while excluding specific lists."""
        config = AppleRemindersConfig(
            service="applereminders", exclude_lists=["Archive"]
        )

        # Set up mock calendars
        mock_work = Mock()
        mock_work.title.return_value = "Work"
        mock_personal = Mock()
        mock_personal.title.return_value = "Personal"
        mock_archive = Mock()
        mock_archive.title.return_value = "Archive"

        self.mock_store.calendarsForEntityType_.return_value = [
            mock_work,
            mock_personal,
            mock_archive,
        ]

        def mock_fetch_reminders(predicate, completion_handler):
            completion_handler([MockEKReminder(**HIGH_PRIORITY_REMINDER)])

        self.mock_store.fetchRemindersMatchingPredicate_completion_.side_effect = (
            mock_fetch_reminders
        )

        client = self.create_client_with_mocks(config)
        reminders = list(client.get_reminders())

        # Should only get reminders from Work and Personal (not Archive)
        self.assertEqual(len(reminders), 2)
        list_names = [r["list_name"] for r in reminders]
        self.assertNotIn("Archive", list_names)

    def test_get_reminders_include_completed(self):
        """Test getting reminders including completed ones."""
        config = AppleRemindersConfig(service="applereminders", include_completed=True)

        mock_calendar = Mock()
        mock_calendar.title.return_value = "Work"
        self.mock_store.calendarsForEntityType_.return_value = [mock_calendar]

        # Set up completed and non-completed reminders
        mock_reminder1 = MockEKReminder(**HIGH_PRIORITY_REMINDER)
        mock_reminder2 = MockEKReminder(**COMPLETED_REMINDER)

        def mock_fetch_reminders(predicate, completion_handler):
            completion_handler([mock_reminder1, mock_reminder2])

        self.mock_store.fetchRemindersMatchingPredicate_completion_.side_effect = (
            mock_fetch_reminders
        )

        client = self.create_client_with_mocks(config)
        reminders = list(client.get_reminders())

        self.assertEqual(len(reminders), 2)
        completed_statuses = [r["completed"] for r in reminders]
        self.assertIn(True, completed_statuses)
        self.assertIn(False, completed_statuses)

    def test_get_reminders_exclude_completed(self):
        """Test getting reminders excluding completed ones (default behavior)."""
        config = AppleRemindersConfig(service="applereminders")

        mock_calendar = Mock()
        mock_calendar.title.return_value = "Work"
        self.mock_store.calendarsForEntityType_.return_value = [mock_calendar]

        # Set up completed and non-completed reminders
        mock_reminder1 = MockEKReminder(**HIGH_PRIORITY_REMINDER)
        mock_reminder2 = MockEKReminder(**COMPLETED_REMINDER)

        def mock_fetch_reminders(predicate, completion_handler):
            completion_handler([mock_reminder1, mock_reminder2])

        self.mock_store.fetchRemindersMatchingPredicate_completion_.side_effect = (
            mock_fetch_reminders
        )

        client = self.create_client_with_mocks(config)
        reminders = list(client.get_reminders())

        # Should only get non-completed reminder
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["completed"], False)

    def test_get_reminders_due_only(self):
        """Test getting reminders with due dates only."""
        config = AppleRemindersConfig(service="applereminders", due_only=True)

        mock_calendar = Mock()
        mock_calendar.title.return_value = "Work"
        self.mock_store.calendarsForEntityType_.return_value = [mock_calendar]

        # Set up reminders - one with due date, one without
        mock_reminder1 = MockEKReminder(**ARBITRARY_REMINDER)
        mock_reminder2 = MockEKReminder(**NO_PRIORITY_REMINDER)
        mock_reminder2._due_components = None  # No due date

        def mock_fetch_reminders(predicate, completion_handler):
            completion_handler([mock_reminder1, mock_reminder2])

        self.mock_store.fetchRemindersMatchingPredicate_completion_.side_effect = (
            mock_fetch_reminders
        )

        # Mock Foundation calendar for date components conversion
        mock_calendar_obj = Mock()
        mock_foundation.NSCalendar.currentCalendar.return_value = mock_calendar_obj
        mock_calendar_obj.dateFromComponents_.return_value = MockNSDate(ARBITRARY_DUE)

        client = self.create_client_with_mocks(config)
        reminders = list(client.get_reminders())

        # Should only get reminder with due date
        self.assertEqual(len(reminders), 1)
        self.assertIsNotNone(reminders[0]["due_date"])

    def test_get_reminders_no_matching_lists(self):
        """Test getting reminders when no lists match configuration."""
        config = AppleRemindersConfig(service="applereminders", lists=["NonExistent"])

        mock_calendar = Mock()
        mock_calendar.title.return_value = "Work"
        self.mock_store.calendarsForEntityType_.return_value = [mock_calendar]

        client = self.create_client_with_mocks(config)
        reminders = list(client.get_reminders())

        # Should get no reminders since 'Work' is not in the configured lists
        self.assertEqual(len(reminders), 0)

    def test_reminder_to_dict_success(self):
        """Test successful conversion of reminder to dictionary."""
        config = AppleRemindersConfig(service="applereminders")

        client = self.create_client_with_mocks(config)

        # Mock the date components conversion
        client._components_to_datetime = Mock(return_value=ARBITRARY_DUE.isoformat())

        mock_reminder = MockEKReminder(**ARBITRARY_REMINDER)
        result = client._reminder_to_dict(mock_reminder, "Shopping")

        # Check non-date fields
        self.assertEqual(result["id"], "test-reminder-123")
        self.assertEqual(result["title"], "Buy groceries")
        self.assertEqual(result["notes"], "Milk, bread, eggs")
        self.assertEqual(result["due_date"], ARBITRARY_DUE.isoformat())
        self.assertEqual(result["completed"], False)
        self.assertEqual(result["completion_date"], None)
        self.assertEqual(result["priority"], 5)
        self.assertEqual(result["list_name"], "Shopping")
        self.assertEqual(
            result["url"], "x-apple-reminderkit://REMCDReminder/test-reminder-123"
        )
        self.assertEqual(result["flagged"], False)

        # Check date fields are ISO strings (since our _format_nsdate converts them)
        self.assertEqual(result["creation_date"], ARBITRARY_CREATED.isoformat())
        self.assertEqual(result["modification_date"], ARBITRARY_MODIFIED.isoformat())

    def test_reminder_to_dict_error_handling(self):
        """Test error handling in reminder to dictionary conversion."""
        config = AppleRemindersConfig(service="applereminders")

        client = self.create_client_with_mocks(config)

        # Create a mock reminder that raises an exception when accessing title
        mock_reminder = Mock()
        mock_reminder.calendarItemIdentifier.return_value = "test-id"
        # Make accessing title raise an exception
        mock_reminder.title.side_effect = Exception("Access error")

        result = client._reminder_to_dict(mock_reminder, "TestList")

        # Should return a fallback dictionary
        self.assertEqual(
            result["id"], "test-id"
        )  # This works since calendarItemIdentifier doesn't fail
        self.assertEqual(
            result["title"], "Error"
        )  # Falls back to 'Error' when title fails
        self.assertEqual(result["list_name"], "TestList")


class TestAppleRemindersService(AbstractServiceTest, ServiceTest):
    """Test cases for AppleRemindersService class."""

    maxDiff = None
    SERVICE_CONFIG = {"service": "applereminders"}

    def test_to_taskwarrior(self):
        """Test the to_taskwarrior method through the service."""
        service = self.get_mock_service(AppleRemindersService)
        issue = service.get_issue_for_record(ARBITRARY_REMINDER, ARBITRARY_EXTRA)

        # Mock the date formatting to return actual strings
        with patch.object(issue, "_get_formatted_date") as mock_format_date:
            mock_format_date.side_effect = lambda date_value: (
                date_value.strftime("%Y%m%dT%H%M%SZ")
                if date_value and hasattr(date_value, "strftime")
                else None
            )

            result = TaskConstructor(issue).get_taskwarrior_record()

        expected_subset = {
            "annotations": [],
            "description": ("(bw)Is# - Buy groceries"),
            "due": ARBITRARY_DUE.strftime("%Y%m%dT%H%M%SZ"),
            "entry": ARBITRARY_CREATED.strftime("%Y%m%dT%H%M%SZ"),
            "priority": "M",
            "project": "Shopping",
            "status": "pending",
            "tags": [],
            # Apple Reminders specific UDAs
            "appleremindersid": "test-reminder-123",
            "applereminderstitle": "Buy groceries",
            "applereminderssubnotes": "Milk, bread, eggs",
            "appleremindersduedate": ARBITRARY_DUE.strftime("%Y%m%dT%H%M%SZ"),
            "applereminderscreationdate": ARBITRARY_CREATED.strftime("%Y%m%dT%H%M%SZ"),
            "appleremindersmodificationdate": ARBITRARY_MODIFIED.strftime(
                "%Y%m%dT%H%M%SZ"
            ),
            "applereminderslist": "Shopping",
            "appleremindersurl": "x-apple-reminderkit://REMCDReminder/test-reminder-123",
            "appleremindersflagged": "true",
        }

        # Check that all expected fields are present and correct
        for key, expected_value in expected_subset.items():
            self.assertIn(key, result, f"Missing key: {key}")
            self.assertEqual(result[key], expected_value, f"Wrong value for key {key}")

    @patch("bugwarrior.services.applereminders.AppleRemindersClient")
    def test_issues(self, mock_client_class):
        """Test the issues() generator method."""
        # Mock the client and its methods
        mock_client = Mock()
        mock_client.get_reminders.return_value = [
            ARBITRARY_REMINDER,
            HIGH_PRIORITY_REMINDER,
        ]
        mock_client_class.return_value = mock_client

        service = self.get_mock_service(AppleRemindersService)
        issues = list(service.issues())

        self.assertEqual(len(issues), 2)

        # Check first issue
        first_issue = issues[0]
        self.assertEqual(first_issue.record["id"], "test-reminder-123")
        self.assertEqual(first_issue.record["title"], "Buy groceries")
        self.assertEqual(first_issue.record["list_name"], "Shopping")

        # Check second issue
        second_issue = issues[1]
        self.assertEqual(second_issue.record["id"], "test-reminder-789")
        self.assertEqual(second_issue.record["title"], "Urgent task")
        self.assertEqual(second_issue.record["list_name"], "Work")

    @patch("bugwarrior.services.applereminders.AppleRemindersClient")
    def test_issues_with_notes_annotation(self, mock_client_class):
        """Test issues generation with notes as annotations."""
        mock_client = Mock()
        mock_client.get_reminders.return_value = [ARBITRARY_REMINDER]
        mock_client_class.return_value = mock_client

        service = self.get_mock_service(
            AppleRemindersService, config_overrides={"add_notes_as_annotation": True}
        )
        issues = list(service.issues())

        self.assertEqual(len(issues), 1)
        issue = issues[0]
        # Notes should be added as annotation through the Issue's to_taskwarrior method
        task = issue.to_taskwarrior()
        self.assertIn("Milk, bread, eggs", task["annotations"])

    @patch("bugwarrior.services.applereminders.AppleRemindersClient")
    def test_issues_client_error(self, mock_client_class):
        """Test error handling when client fails to get reminders."""
        mock_client = Mock()
        mock_client.get_reminders.side_effect = Exception("Connection failed")
        mock_client_class.return_value = mock_client

        service = self.get_mock_service(AppleRemindersService)

        with self.assertRaises(Exception) as cm:
            list(service.issues())

        self.assertIn("Connection failed", str(cm.exception))

    def test_keyring_service(self):
        """Test keyring service name generation."""
        service = self.get_mock_service(AppleRemindersService)
        keyring_service = service.get_keyring_service(service.config)
        self.assertEqual(keyring_service, "bugwarrior://applereminders")

    @patch("bugwarrior.services.applereminders.AppleRemindersClient")
    def test_service_initialization_with_config(self, mock_client_class):
        """Test service initialization with various configurations."""
        mock_client = Mock()
        # Mock get_reminders to return a list so len() works
        mock_client.get_reminders.return_value = [
            ARBITRARY_REMINDER,
            HIGH_PRIORITY_REMINDER,
        ]
        mock_client_class.return_value = mock_client

        service = self.get_mock_service(
            AppleRemindersService,
            config_overrides={
                "lists": ["Work", "Personal"],
                "include_completed": True,
                "exclude_lists": ["Archive"],
                "due_only": True,
            },
        )

        # Trigger client creation by calling issues()
        list(service.issues())

        # Verify client is initialized with correct config
        mock_client_class.assert_called_once()
        call_args = mock_client_class.call_args[0][
            0
        ]  # First positional argument (config)
        self.assertEqual(call_args.lists, ["Work", "Personal"])
        self.assertEqual(call_args.include_completed, True)
        self.assertEqual(call_args.exclude_lists, ["Archive"])
        self.assertEqual(call_args.due_only, True)
        self.assertIsNotNone(service.client)


class TestAppleRemindersConfig(ServiceTest):
    """Test cases for AppleRemindersConfig schema validation."""

    SERVICE_CONFIG = {"service": "applereminders"}

    def test_minimal_config(self):
        """Test minimal valid configuration."""
        config = {"service": "applereminders"}

        # Should not raise validation error
        service_config = AppleRemindersConfig(**config)
        self.assertEqual(service_config.service, "applereminders")
        self.assertEqual(list(service_config.lists), [])
        self.assertEqual(service_config.include_completed, False)
        self.assertEqual(service_config.import_labels_as_tags, False)
        self.assertEqual(list(service_config.exclude_lists), [])
        self.assertEqual(service_config.due_only, False)

    def test_full_config(self):
        """Test configuration with all options."""
        config = {
            "service": "applereminders",
            "lists": ["Work", "Personal"],
            "include_completed": True,
            "import_labels_as_tags": True,
            "label_template": "{{label}}-tag",
            "exclude_lists": ["Archive", "Old"],
            "due_only": True,
        }

        service_config = AppleRemindersConfig(**config)
        self.assertEqual(service_config.lists, ["Work", "Personal"])
        self.assertEqual(service_config.include_completed, True)
        self.assertEqual(service_config.import_labels_as_tags, True)
        self.assertEqual(service_config.label_template, "{{label}}-tag")
        self.assertEqual(service_config.exclude_lists, ["Archive", "Old"])
        self.assertEqual(service_config.due_only, True)

    def test_invalid_service_name(self):
        """Test configuration with invalid service name."""
        config = {"service": "invalid_service"}

        with self.assertRaises(Exception):
            AppleRemindersConfig(**config)


class TestAppleRemindersIntegration(ServiceTest):
    """Integration tests combining multiple components."""

    SERVICE_CONFIG = {
        "service": "applereminders",
        "lists": ["Work"],
        "import_labels_as_tags": True,
    }

    @patch("bugwarrior.services.applereminders.AppleRemindersClient")
    def test_end_to_end_workflow(self, mock_client_class):
        """Test complete workflow from service to task construction."""
        # Set up mock client
        mock_client = Mock()
        mock_client.get_reminders.return_value = [
            HIGH_PRIORITY_REMINDER,
            ARBITRARY_REMINDER,
        ]
        mock_client_class.return_value = mock_client

        service = self.get_mock_service(AppleRemindersService)
        issues = list(service.issues())

        # Should get both reminders
        self.assertEqual(len(issues), 2)

        # Convert to taskwarrior format
        tasks = []
        for issue in issues:
            task = TaskConstructor(issue).get_taskwarrior_record()
            tasks.append(task)

        # Verify task properties
        self.assertEqual(len(tasks), 2)

        # Check that all tasks have the expected structure
        for task in tasks:
            self.assertIn("appleremindersid", task)
            self.assertIn("applereminderstitle", task)
            self.assertIn("priority", task)
            self.assertIn("tags", task)

            # Should have list name as tag due to import_labels_as_tags
            # Tags are based on the list_name from the reminder data
            task_list_name = None
            for reminder in [HIGH_PRIORITY_REMINDER, ARBITRARY_REMINDER]:
                if task["appleremindersid"] == reminder["id"]:
                    task_list_name = reminder["list_name"]
                    break
            if task_list_name:
                self.assertIn(task_list_name, task["tags"])

    @patch("bugwarrior.services.applereminders.AppleRemindersClient")
    def test_priority_mapping_integration(self, mock_client_class):
        """Test priority mapping in complete workflow."""
        mock_client = Mock()
        mock_client.get_reminders.return_value = [
            HIGH_PRIORITY_REMINDER,  # priority 9 -> H
            ARBITRARY_REMINDER,  # priority 5 -> M
            LOW_PRIORITY_REMINDER,  # priority 1 -> L
            NO_PRIORITY_REMINDER,  # priority 0 -> default
        ]
        mock_client_class.return_value = mock_client

        service = self.get_mock_service(AppleRemindersService)
        issues = list(service.issues())

        priorities = []
        for issue in issues:
            task = TaskConstructor(issue).get_taskwarrior_record()
            priorities.append(task["priority"])

        # Should have all different priority levels
        self.assertIn("H", priorities)  # High
        self.assertIn("M", priorities)  # Medium
        self.assertIn("L", priorities)  # Low
        # Default for no priority
        self.assertIn(service.config.default_priority, priorities)
