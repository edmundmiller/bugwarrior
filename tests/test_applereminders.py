import datetime
import sys
from unittest.mock import Mock, patch

import pytz

from bugwarrior.collect import TaskConstructor
from .base import ServiceTest, AbstractServiceTest

# Mock apple_reminders before importing our service
mock_apple_reminders = Mock()
sys.modules['apple_reminders'] = mock_apple_reminders

from bugwarrior.services.applereminders import (  # noqa: E402
    AppleRemindersConfig, AppleRemindersService, AppleRemindersClient
)


class MockReminder:
    """Mock Apple Reminders reminder object."""

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 'test-reminder-id')
        self.title = kwargs.get('title', 'Test Reminder')
        self.notes = kwargs.get('notes', 'Test notes')
        self.due_date = kwargs.get('due_date')
        self.completed = kwargs.get('completed', False)
        self.completion_date = kwargs.get('completion_date')
        self.creation_date = kwargs.get('creation_date')
        self.modification_date = kwargs.get('modification_date')
        self.priority = kwargs.get('priority', 0)  # 0=None, 1=Low, 5=Medium, 9=High
        self.flagged = kwargs.get('flagged', False)
        self.subtasks = kwargs.get('subtasks', [])


class MockRemindersList:
    """Mock Apple Reminders list object."""

    def __init__(self, name, reminders_data=None):
        self.name = name
        self._reminders_data = reminders_data or []

    def reminders(self, completed=False):
        """Return mock reminders based on completed filter."""
        for reminder_data in self._reminders_data:
            if not completed and reminder_data.get('completed', False):
                continue
            yield MockReminder(**reminder_data)


class MockRemindersApp:
    """Mock Apple Reminders app object."""

    def __init__(self, lists_data=None):
        self._lists_data = lists_data or {}

    def lists(self):
        """Return mock reminder lists."""
        result = []
        for list_name, reminders_data in self._lists_data.items():
            result.append(MockRemindersList(list_name, reminders_data))
        return result


# Test data constants
ARBITRARY_CREATED = datetime.datetime(2023, 1, 15, 10, 0, 0, tzinfo=pytz.UTC)
ARBITRARY_MODIFIED = datetime.datetime(2023, 1, 16, 11, 30, 0, tzinfo=pytz.UTC)
ARBITRARY_DUE = datetime.datetime(2023, 1, 20, 15, 0, 0, tzinfo=pytz.UTC)
ARBITRARY_COMPLETED = datetime.datetime(2023, 1, 18, 14, 0, 0, tzinfo=pytz.UTC)

ARBITRARY_REMINDER = {
    'id': 'test-reminder-123',
    'title': 'Buy groceries',
    'notes': 'Milk, bread, eggs',
    'due_date': ARBITRARY_DUE,
    'completed': False,
    'completion_date': None,
    'creation_date': ARBITRARY_CREATED,
    'modification_date': ARBITRARY_MODIFIED,
    'priority': 5,  # Medium priority
    'list_name': 'Shopping',
    'url': 'x-apple-reminderkit://REMCDReminder/test-reminder-123',
    'flagged': True,
    'subtasks': [],
}

COMPLETED_REMINDER = {
    'id': 'test-reminder-456',
    'title': 'Completed task',
    'notes': 'This was finished',
    'due_date': ARBITRARY_DUE,
    'completed': True,
    'completion_date': ARBITRARY_COMPLETED,
    'creation_date': ARBITRARY_CREATED,
    'modification_date': ARBITRARY_MODIFIED,
    'priority': 9,  # High priority
    'list_name': 'Work',
    'url': 'x-apple-reminderkit://REMCDReminder/test-reminder-456',
    'flagged': False,
    'subtasks': [],
}

HIGH_PRIORITY_REMINDER = {
    'id': 'test-reminder-789',
    'title': 'Urgent task',
    'notes': '',
    'due_date': None,
    'completed': False,
    'completion_date': None,
    'creation_date': ARBITRARY_CREATED,
    'modification_date': ARBITRARY_MODIFIED,
    'priority': 9,  # High priority
    'list_name': 'Work',
    'url': 'x-apple-reminderkit://REMCDReminder/test-reminder-789',
    'flagged': False,
    'subtasks': [],
}

LOW_PRIORITY_REMINDER = {
    'id': 'test-reminder-low',
    'title': 'Low priority task',
    'notes': 'Can wait',
    'due_date': None,
    'completed': False,
    'completion_date': None,
    'creation_date': ARBITRARY_CREATED,
    'modification_date': ARBITRARY_MODIFIED,
    'priority': 1,  # Low priority
    'list_name': 'Personal',
    'url': 'x-apple-reminderkit://REMCDReminder/test-reminder-low',
    'flagged': False,
    'subtasks': [],
}

NO_PRIORITY_REMINDER = {
    'id': 'test-reminder-none',
    'title': 'No priority task',
    'notes': '',
    'due_date': None,
    'completed': False,
    'completion_date': None,
    'creation_date': ARBITRARY_CREATED,
    'modification_date': ARBITRARY_MODIFIED,
    'priority': 0,  # No priority
    'list_name': 'Personal',
    'url': 'x-apple-reminderkit://REMCDReminder/test-reminder-none',
    'flagged': False,
    'subtasks': [],
}

ARBITRARY_EXTRA = {
    'project': 'Shopping',
    'annotations': [],
}


class TestAppleRemindersIssue(AbstractServiceTest, ServiceTest):
    """Test cases for AppleRemindersIssue class."""

    maxDiff = None
    SERVICE_CONFIG = {
        'service': 'applereminders',
    }

    def test_to_taskwarrior(self):
        """Test conversion of reminder to taskwarrior format."""
        service = self.get_mock_service(AppleRemindersService)
        issue = service.get_issue_for_record(ARBITRARY_REMINDER, ARBITRARY_EXTRA)

        expected_output = {
            'project': ARBITRARY_EXTRA['project'],
            'priority': 'M',  # Medium priority (5 -> M)
            'annotations': [],
            'tags': [],
            'due': ARBITRARY_DUE,
            'status': 'pending',
            'entry': ARBITRARY_CREATED,
            'end': None,  # Not completed
            'modified': ARBITRARY_MODIFIED,

            # Apple Reminders specific fields
            issue.ID: ARBITRARY_REMINDER['id'],
            issue.TITLE: ARBITRARY_REMINDER['title'],
            issue.NOTES: ARBITRARY_REMINDER['notes'],
            issue.DUE_DATE: ARBITRARY_DUE,
            issue.COMPLETED: 0,  # False -> 0
            issue.COMPLETION_DATE: None,
            issue.CREATION_DATE: ARBITRARY_CREATED,
            issue.MODIFICATION_DATE: ARBITRARY_MODIFIED,
            issue.PRIORITY: ARBITRARY_REMINDER['priority'],
            issue.LIST_NAME: ARBITRARY_REMINDER['list_name'],
            issue.URL: ARBITRARY_REMINDER['url'],
            issue.FLAGGED: 1,  # True -> 1
        }

        actual_output = issue.to_taskwarrior()
        self.assertEqual(actual_output, expected_output)

    def test_to_taskwarrior_completed(self):
        """Test conversion of completed reminder to taskwarrior format."""
        service = self.get_mock_service(AppleRemindersService)
        issue = service.get_issue_for_record(
            COMPLETED_REMINDER, {'project': 'Work', 'annotations': []}
        )

        expected_output = {
            'project': 'Work',
            'priority': 'H',  # High priority (9 -> H)
            'annotations': [],
            'tags': [],
            'due': ARBITRARY_DUE,
            'status': 'completed',
            'entry': ARBITRARY_CREATED,
            'end': ARBITRARY_COMPLETED,
            'modified': ARBITRARY_MODIFIED,

            # Apple Reminders specific fields
            issue.ID: COMPLETED_REMINDER['id'],
            issue.TITLE: COMPLETED_REMINDER['title'],
            issue.NOTES: COMPLETED_REMINDER['notes'],
            issue.DUE_DATE: ARBITRARY_DUE,
            issue.COMPLETED: 1,  # True -> 1
            issue.COMPLETION_DATE: ARBITRARY_COMPLETED,
            issue.CREATION_DATE: ARBITRARY_CREATED,
            issue.MODIFICATION_DATE: ARBITRARY_MODIFIED,
            issue.PRIORITY: COMPLETED_REMINDER['priority'],
            issue.LIST_NAME: COMPLETED_REMINDER['list_name'],
            issue.URL: COMPLETED_REMINDER['url'],
            issue.FLAGGED: 0,  # False -> 0
        }

        actual_output = issue.to_taskwarrior()
        self.assertEqual(actual_output, expected_output)

    def test_to_taskwarrior_with_tags(self):
        """Test conversion with import_labels_as_tags enabled."""
        service = self.get_mock_service(AppleRemindersService, config_overrides={
            'import_labels_as_tags': True
        })
        issue = service.get_issue_for_record(ARBITRARY_REMINDER, ARBITRARY_EXTRA)

        actual_output = issue.to_taskwarrior()

        # Should include list name as tag
        self.assertEqual(actual_output['tags'], ['Shopping'])

    def test_to_taskwarrior_priority_mapping(self):
        """Test priority mapping from Apple Reminders to Taskwarrior."""
        service = self.get_mock_service(AppleRemindersService)

        # Test high priority (9 -> H)
        issue = service.get_issue_for_record(
            HIGH_PRIORITY_REMINDER, {'project': 'Work', 'annotations': []}
        )
        self.assertEqual(issue.to_taskwarrior()['priority'], 'H')

        # Test medium priority (5 -> M)
        issue = service.get_issue_for_record(ARBITRARY_REMINDER, ARBITRARY_EXTRA)
        self.assertEqual(issue.to_taskwarrior()['priority'], 'M')

        # Test low priority (1 -> L)
        issue = service.get_issue_for_record(
            LOW_PRIORITY_REMINDER, {'project': 'Personal', 'annotations': []}
        )
        self.assertEqual(issue.to_taskwarrior()['priority'], 'L')

        # Test no priority (0 -> None, falls back to service default)
        issue = service.get_issue_for_record(
            NO_PRIORITY_REMINDER, {'project': 'Personal', 'annotations': []}
        )
        self.assertEqual(issue.to_taskwarrior()['priority'], service.config.default_priority)

    def test_issues(self):
        """Test basic issues() method functionality."""
        # This will be implemented in the service test
        pass


class TestAppleRemindersClient(ServiceTest):
    """Test cases for AppleRemindersClient class."""

    SERVICE_CONFIG = {
        'service': 'applereminders',
    }

    def test_init_success(self):
        """Test successful client initialization."""
        mock_reminders_app = Mock()
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient()

        self.assertEqual(client.apple_reminders, mock_apple_reminders)
        self.assertEqual(client.reminders_app, mock_reminders_app)
        self.assertEqual(client.lists, [])
        self.assertEqual(client.include_completed, False)
        self.assertEqual(client.exclude_lists, [])
        self.assertEqual(client.due_only, False)

    def test_init_with_config(self):
        """Test client initialization with configuration."""
        mock_reminders_app = Mock()
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient(
            lists=['Work', 'Personal'],
            include_completed=True,
            exclude_lists=['Archive'],
            due_only=True
        )

        self.assertEqual(client.lists, ['Work', 'Personal'])
        self.assertEqual(client.include_completed, True)
        self.assertEqual(client.exclude_lists, ['Archive'])
        self.assertEqual(client.due_only, True)

    def test_init_missing_library(self):
        """Test client initialization when apple-reminders library is missing."""
        # Temporarily remove the mock to test import error handling
        original_module = sys.modules.get('apple_reminders')
        if 'apple_reminders' in sys.modules:
            del sys.modules['apple_reminders']

        try:
            with patch(
                'builtins.__import__',
                side_effect=ImportError("No module named 'apple_reminders'")
            ):
                with self.assertRaises(ImportError) as cm:
                    AppleRemindersClient()

                self.assertIn("apple-reminders", str(cm.exception))
                self.assertIn("pip install apple-reminders", str(cm.exception))
        finally:
            # Restore the mock
            if original_module:
                sys.modules['apple_reminders'] = original_module

    def test_init_connection_error(self):
        """Test client initialization when connection to Reminders fails."""
        mock_apple_reminders.RemindersApp.side_effect = Exception("Permission denied")

        with self.assertRaises(OSError) as cm:
            AppleRemindersClient()

        self.assertIn("Unable to connect to Apple Reminders", str(cm.exception))
        self.assertIn("permission to access Reminders", str(cm.exception))

        # Reset the mock for other tests
        mock_apple_reminders.RemindersApp.side_effect = None

    def test_get_reminder_lists_success(self):
        """Test successful retrieval of reminder lists."""
        mock_lists = [Mock(name='Work'), Mock(name='Personal')]
        mock_reminders_app = Mock()
        mock_reminders_app.lists.return_value = mock_lists
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient()
        lists = client.get_reminder_lists()

        self.assertEqual(lists, mock_lists)

    def test_get_reminder_lists_error(self):
        """Test error handling when getting reminder lists fails."""
        mock_reminders_app = Mock()
        mock_reminders_app.lists.side_effect = Exception("Access denied")
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient()
        lists = client.get_reminder_lists()

        self.assertEqual(lists, [])

        # Reset for other tests
        mock_reminders_app.lists.side_effect = None

    def test_get_reminders_no_lists_configured(self):
        """Test getting reminders when no specific lists are configured."""
        mock_reminders_app = MockRemindersApp({
            'Work': [ARBITRARY_REMINDER],
            'Personal': [LOW_PRIORITY_REMINDER],
        })
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient()
        reminders = list(client.get_reminders())

        self.assertEqual(len(reminders), 2)
        self.assertEqual(reminders[0]['title'], 'Buy groceries')
        self.assertEqual(reminders[1]['title'], 'Low priority task')

    def test_get_reminders_specific_lists(self):
        """Test getting reminders from specific lists."""
        mock_reminders_app = MockRemindersApp({
            'Work': [HIGH_PRIORITY_REMINDER],
            'Personal': [LOW_PRIORITY_REMINDER],
            'Archive': [COMPLETED_REMINDER],
        })
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient(lists=['Work', 'Personal'])
        reminders = list(client.get_reminders())

        self.assertEqual(len(reminders), 2)
        # Should only get reminders from Work and Personal lists
        list_names = [r['list_name'] for r in reminders]
        self.assertIn('Work', list_names)
        self.assertIn('Personal', list_names)
        self.assertNotIn('Archive', list_names)

    def test_get_reminders_exclude_lists(self):
        """Test getting reminders while excluding specific lists."""
        mock_reminders_app = MockRemindersApp({
            'Work': [HIGH_PRIORITY_REMINDER],
            'Personal': [LOW_PRIORITY_REMINDER],
            'Archive': [COMPLETED_REMINDER],
        })
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient(exclude_lists=['Archive'])
        reminders = list(client.get_reminders())

        self.assertEqual(len(reminders), 2)
        # Should not get reminders from Archive list
        list_names = [r['list_name'] for r in reminders]
        self.assertNotIn('Archive', list_names)

    def test_get_reminders_include_completed(self):
        """Test getting reminders including completed ones."""
        mock_reminders_app = MockRemindersApp({
            'Work': [HIGH_PRIORITY_REMINDER, COMPLETED_REMINDER],
        })
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient(include_completed=True)
        reminders = list(client.get_reminders())

        self.assertEqual(len(reminders), 2)
        completed_statuses = [r['completed'] for r in reminders]
        self.assertIn(True, completed_statuses)
        self.assertIn(False, completed_statuses)

    def test_get_reminders_exclude_completed(self):
        """Test getting reminders excluding completed ones (default behavior)."""
        mock_reminders_app = MockRemindersApp({
            'Work': [HIGH_PRIORITY_REMINDER, COMPLETED_REMINDER],
        })
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient()
        reminders = list(client.get_reminders())

        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]['completed'], False)

    def test_get_reminders_due_only(self):
        """Test getting reminders with due dates only."""
        no_due_reminder = NO_PRIORITY_REMINDER.copy()
        no_due_reminder['due_date'] = None

        mock_reminders_app = MockRemindersApp({
            'Work': [ARBITRARY_REMINDER, no_due_reminder],
        })
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient(due_only=True)
        reminders = list(client.get_reminders())

        self.assertEqual(len(reminders), 1)
        self.assertIsNotNone(reminders[0]['due_date'])

    def test_get_reminders_no_matching_lists(self):
        """Test getting reminders when no lists match configuration."""
        mock_reminders_app = MockRemindersApp({
            'Work': [HIGH_PRIORITY_REMINDER],
        })
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient(lists=['NonExistent'])
        reminders = list(client.get_reminders())

        self.assertEqual(len(reminders), 0)

    def test_reminder_to_dict_success(self):
        """Test successful conversion of reminder to dictionary."""
        mock_reminders_app = Mock()
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient()

        mock_reminder = MockReminder(**ARBITRARY_REMINDER)
        result = client._reminder_to_dict(mock_reminder, 'Shopping')

        expected = {
            'id': 'test-reminder-123',
            'title': 'Buy groceries',
            'notes': 'Milk, bread, eggs',
            'due_date': ARBITRARY_DUE,
            'completed': False,
            'completion_date': None,
            'creation_date': ARBITRARY_CREATED,
            'modification_date': ARBITRARY_MODIFIED,
            'priority': 5,
            'list_name': 'Shopping',
            'url': 'x-apple-reminderkit://REMCDReminder/test-reminder-123',
            'flagged': True,
            'subtasks': [],
        }

        self.assertEqual(result, expected)

    def test_reminder_to_dict_error_handling(self):
        """Test error handling in reminder to dictionary conversion."""
        mock_reminders_app = Mock()
        mock_apple_reminders.RemindersApp.return_value = mock_reminders_app

        client = AppleRemindersClient()

        # Create a mock reminder that raises an exception when accessing title
        mock_reminder = Mock()
        mock_reminder.id = 'test-id'
        # Make accessing title raise an exception
        type(mock_reminder).title = property(
            lambda self: (_ for _ in ()).throw(Exception("Access error"))
        )

        result = client._reminder_to_dict(mock_reminder, 'TestList')

        # Should return a fallback dictionary
        self.assertEqual(result['id'], 'test-id')
        self.assertEqual(result['title'], 'Unknown Reminder')
        self.assertEqual(result['list_name'], 'TestList')


class TestAppleRemindersService(AbstractServiceTest, ServiceTest):
    """Test cases for AppleRemindersService class."""

    maxDiff = None
    SERVICE_CONFIG = {
        'service': 'applereminders',
    }

    def test_to_taskwarrior(self):
        """Test the to_taskwarrior method through the service."""
        service = self.get_mock_service(AppleRemindersService)
        issue = service.get_issue_for_record(ARBITRARY_REMINDER, ARBITRARY_EXTRA)

        expected = {
            'annotations': [],
            'description': ('(bw)#test-reminder-123 - Buy groceries .. '
                            'x-apple-reminderkit://REMCDReminder/test-reminder-123'),
            'due': ARBITRARY_DUE,
            'entry': ARBITRARY_CREATED,
            'end': None,
            'modified': ARBITRARY_MODIFIED,
            'priority': 'M',
            'project': 'Shopping',
            'status': 'pending',
            'tags': [],

            # Apple Reminders specific UDAs
            'appleremindersid': 'test-reminder-123',
            'applereminderstitle': 'Buy groceries',
            'appleremindersnotes': 'Milk, bread, eggs',
            'appleremindersdue': ARBITRARY_DUE,
            'applereminderscompleted': 0,
            'applereminderscompleted_date': None,
            'applereminderscreated': ARBITRARY_CREATED,
            'appleremindersmodified': ARBITRARY_MODIFIED,
            'appleremindersprioirty': 5,
            'applereminderslist': 'Shopping',
            'appleremindersurl': 'x-apple-reminderkit://REMCDReminder/test-reminder-123',
            'appleremindersflagged': 1,
        }

        self.assertEqual(TaskConstructor(issue).get_taskwarrior_record(), expected)

    @patch('bugwarrior.services.applereminders.AppleRemindersClient')
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
        self.assertEqual(first_issue.record['id'], 'test-reminder-123')
        self.assertEqual(first_issue.record['title'], 'Buy groceries')
        self.assertEqual(first_issue.extra['project'], 'Shopping')

        # Check second issue
        second_issue = issues[1]
        self.assertEqual(second_issue.record['id'], 'test-reminder-789')
        self.assertEqual(second_issue.record['title'], 'Urgent task')
        self.assertEqual(second_issue.extra['project'], 'Work')

    @patch('bugwarrior.services.applereminders.AppleRemindersClient')
    def test_issues_with_notes_annotation(self, mock_client_class):
        """Test issues generation with notes as annotations."""
        mock_client = Mock()
        mock_client.get_reminders.return_value = [ARBITRARY_REMINDER]
        mock_client_class.return_value = mock_client

        service = self.get_mock_service(AppleRemindersService, general_overrides={
            'annotation_comments': True
        })
        issues = list(service.issues())

        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue.extra['annotations'], ['Notes: Milk, bread, eggs'])

    @patch('bugwarrior.services.applereminders.AppleRemindersClient')
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
        service_config = AppleRemindersConfig(service='applereminders')
        keyring_service = AppleRemindersService.get_keyring_service(service_config)
        self.assertEqual(keyring_service, "applereminders://")

    @patch('bugwarrior.services.applereminders.AppleRemindersClient')
    def test_service_initialization_with_config(self, mock_client_class):
        """Test service initialization with various configurations."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        service = self.get_mock_service(AppleRemindersService, config_overrides={
            'lists': ['Work', 'Personal'],
            'include_completed': True,
            'exclude_lists': ['Archive'],
            'due_only': True,
        })

        # Verify client is initialized with correct parameters
        mock_client_class.assert_called_once_with(
            lists=['Work', 'Personal'],
            include_completed=True,
            exclude_lists=['Archive'],
            due_only=True,
        )
        self.assertIsNotNone(service.client)


class TestAppleRemindersConfig(ServiceTest):
    """Test cases for AppleRemindersConfig schema validation."""

    SERVICE_CONFIG = {
        'service': 'applereminders',
    }

    def test_minimal_config(self):
        """Test minimal valid configuration."""
        config = {
            'service': 'applereminders',
        }

        # Should not raise validation error
        service_config = AppleRemindersConfig(**config)
        self.assertEqual(service_config.service, 'applereminders')
        self.assertEqual(list(service_config.lists), [])
        self.assertEqual(service_config.include_completed, False)
        self.assertEqual(service_config.import_labels_as_tags, False)
        self.assertEqual(list(service_config.exclude_lists), [])
        self.assertEqual(service_config.due_only, False)

    def test_full_config(self):
        """Test configuration with all options."""
        config = {
            'service': 'applereminders',
            'lists': ['Work', 'Personal'],
            'include_completed': True,
            'import_labels_as_tags': True,
            'label_template': '{{label}}-tag',
            'exclude_lists': ['Archive', 'Old'],
            'due_only': True,
        }

        service_config = AppleRemindersConfig(**config)
        self.assertEqual(service_config.lists, ['Work', 'Personal'])
        self.assertEqual(service_config.include_completed, True)
        self.assertEqual(service_config.import_labels_as_tags, True)
        self.assertEqual(service_config.label_template, '{{label}}-tag')
        self.assertEqual(service_config.exclude_lists, ['Archive', 'Old'])
        self.assertEqual(service_config.due_only, True)

    def test_invalid_service_name(self):
        """Test configuration with invalid service name."""
        config = {
            'service': 'invalid_service',
        }

        with self.assertRaises(Exception):
            AppleRemindersConfig(**config)


class TestAppleRemindersIntegration(ServiceTest):
    """Integration tests combining multiple components."""

    SERVICE_CONFIG = {
        'service': 'applereminders',
        'lists': ['Work'],
        'import_labels_as_tags': True,
    }

    @patch('bugwarrior.services.applereminders.AppleRemindersClient')
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
            self.assertIn('appleremindersid', task)
            self.assertIn('applereminderstitle', task)
            self.assertIn('priority', task)
            self.assertIn('tags', task)

            # Should have list name as tag due to import_labels_as_tags
            # Tags are based on the list_name from the reminder data
            task_list_name = None
            for reminder in [HIGH_PRIORITY_REMINDER, ARBITRARY_REMINDER]:
                if task['appleremindersid'] == reminder['id']:
                    task_list_name = reminder['list_name']
                    break
            if task_list_name:
                self.assertIn(task_list_name, task['tags'])

    @patch('bugwarrior.services.applereminders.AppleRemindersClient')
    def test_priority_mapping_integration(self, mock_client_class):
        """Test priority mapping in complete workflow."""
        mock_client = Mock()
        mock_client.get_reminders.return_value = [
            HIGH_PRIORITY_REMINDER,    # priority 9 -> H
            ARBITRARY_REMINDER,        # priority 5 -> M
            LOW_PRIORITY_REMINDER,     # priority 1 -> L
            NO_PRIORITY_REMINDER,      # priority 0 -> default
        ]
        mock_client_class.return_value = mock_client

        service = self.get_mock_service(AppleRemindersService)
        issues = list(service.issues())

        priorities = []
        for issue in issues:
            task = TaskConstructor(issue).get_taskwarrior_record()
            priorities.append(task['priority'])

        # Should have all different priority levels
        self.assertIn('H', priorities)  # High
        self.assertIn('M', priorities)  # Medium
        self.assertIn('L', priorities)  # Low
        # Default for no priority
        self.assertIn(service.config.default_priority, priorities)
