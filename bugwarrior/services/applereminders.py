import logging
from datetime import datetime
import typing_extensions

from bugwarrior import config
from bugwarrior.services import Service, Issue, Client

log = logging.getLogger(__name__)


class AppleRemindersConfig(config.ServiceConfig):
    """Configuration for Apple Reminders integration."""
    service: typing_extensions.Literal['applereminders']
    lists: list[str] = []
    exclude_lists: list[str] = []
    include_completed: bool = False
    due_only: bool = False
    import_labels_as_tags: bool = False
    label_template: str = '{{label}}'
    add_notes_as_annotation: bool = False


class AppleRemindersClient(Client):
    """Client for Apple Reminders using EventKit framework."""

    def __init__(self, config: AppleRemindersConfig):
        self.config = config
        self.lists = config.lists
        self.exclude_lists = config.exclude_lists
        self.include_completed = config.include_completed
        self.due_only = config.due_only

        try:
            import EventKit
            import Foundation
            self.EventKit = EventKit
            self.Foundation = Foundation

            # Create event store and request access
            self.store = EventKit.EKEventStore.alloc().init()
            self._request_access()

        except ImportError as e:
            log.error("Failed to import EventKit framework. This service only works on macOS.")
            raise ImportError(
                "EventKit framework not available. "
                "Make sure you're on macOS and have pyobjc-framework-EventKit installed."
            ) from e
        except Exception as e:
            log.error("Failed to initialize Apple Reminders connection: %s", e)
            raise

    def _request_access(self):
        """Request access to reminders."""
        # Check if we already have access
        status = self.EventKit.EKEventStore.authorizationStatusForEntityType_(
            self.EventKit.EKEntityTypeReminder
        )

        if status == self.EventKit.EKAuthorizationStatusAuthorized:
            log.debug("Already have access to reminders")
            return

        # Request access if needed
        if status == self.EventKit.EKAuthorizationStatusNotDetermined:
            log.info("Requesting access to reminders...")
            granted = [None]
            error = [None]

            def completion_handler(granted_val, error_val):
                granted[0] = granted_val
                error[0] = error_val

            self.store.requestAccessToEntityType_completion_(
                self.EventKit.EKEntityTypeReminder,
                completion_handler
            )

            # Wait for completion
            import time
            for _ in range(50):  # 5 seconds timeout
                if granted[0] is not None:
                    break
                time.sleep(0.1)

            if not granted[0]:
                raise PermissionError(
                    "Access to reminders was denied. "
                    "Please grant access in System Settings > Privacy & Security > Reminders"
                )
        elif status == self.EventKit.EKAuthorizationStatusDenied:
            raise PermissionError(
                "Access to reminders was denied. "
                "Please grant access in System Settings > Privacy & Security > Reminders"
            )

    def get_reminder_lists(self):
        """Get all reminder lists."""
        try:
            calendars = self.store.calendarsForEntityType_(
                self.EventKit.EKEntityTypeReminder
            )
            return [cal for cal in calendars if cal is not None]
        except Exception as e:
            log.error("Failed to get reminder lists: %s", e)
            raise

    def _should_include_list(self, list_name):
        """Check if a list should be included based on configuration."""
        if self.exclude_lists and list_name in self.exclude_lists:
            return False
        if self.lists and list_name not in self.lists:
            return False
        return True

    def get_reminders(self):
        """Get all reminders based on configuration."""
        reminders = []

        lists = self.get_reminder_lists()
        for calendar in lists:
            list_name = str(calendar.title())
            if not self._should_include_list(list_name):
                log.debug("Skipping list: %s", list_name)
                continue

            # Create predicate for this calendar
            predicate = self.store.predicateForRemindersInCalendars_([calendar])

            # Fetch reminders synchronously
            fetched_reminders = self.store.remindersMatchingPredicate_(predicate)

            for reminder in fetched_reminders:
                if not self.include_completed and reminder.isCompleted():
                    continue

                if self.due_only and not reminder.dueDateComponents():
                    continue

                reminders.append(self._reminder_to_dict(reminder, list_name))

        return reminders

    def _reminder_to_dict(self, reminder, list_name):
        """Convert an EKReminder object to a dictionary."""
        try:
            # Get basic fields
            data = {
                'id': str(reminder.calendarItemExternalIdentifier()),
                'title': str(reminder.title()) if reminder.title() else '',
                'notes': str(reminder.notes()) if reminder.notes() else '',
                'completed': bool(reminder.isCompleted()),
                'list_name': list_name,
                'url': (
                    f"x-apple-reminderkit://REMCDReminder/"
                    f"{str(reminder.calendarItemExternalIdentifier())}"
                ),
                'flagged': False,  # EventKit doesn't expose flagged status directly
            }

            # Handle dates
            if reminder.dueDateComponents():
                due_components = reminder.dueDateComponents()
                # Create date from components
                data['due_date'] = self._components_to_datetime(due_components)
            else:
                data['due_date'] = None

            if reminder.completionDate():
                data['completion_date'] = reminder.completionDate()
            else:
                data['completion_date'] = None

            if reminder.creationDate():
                data['creation_date'] = reminder.creationDate()
            else:
                data['creation_date'] = None

            if reminder.lastModifiedDate():
                data['modification_date'] = reminder.lastModifiedDate()
            else:
                data['modification_date'] = None

            # Map priority (EventKit uses 0=none, 1-4=high, 5=medium, 6-9=low)
            priority = reminder.priority()
            if priority == 0:
                data['priority'] = 0
            elif 1 <= priority <= 4:
                data['priority'] = 9  # High
            elif priority == 5:
                data['priority'] = 5  # Medium
            else:
                data['priority'] = 1  # Low

            return data

        except Exception as e:
            log.error("Failed to convert reminder to dict: %s", e)
            # Return minimal data on error
            try:
                fallback_title = str(reminder.title()) if reminder.title() else 'Error'
            except Exception:
                fallback_title = 'Error'
            return {
                'id': 'error',
                'title': fallback_title,
                'notes': '',
                'completed': False,
                'list_name': list_name,
                'priority': 0,
            }

    def _components_to_datetime(self, components):
        """Convert NSDateComponents to datetime string."""
        try:
            # Get calendar and create date
            calendar = self.Foundation.NSCalendar.currentCalendar()
            date = calendar.dateFromComponents_(components)
            if date:
                # Convert to Python datetime
                timestamp = date.timeIntervalSince1970()
                dt = datetime.fromtimestamp(timestamp)
                return dt.isoformat()
        except Exception as e:
            log.error("Failed to convert date components: %s", e)
        return None


class AppleRemindersIssue(Issue):
    TITLE = 'applereminderstitle'
    NOTES = 'applereminderssubnotes'
    DUE_DATE = 'appleremindersduedate'
    COMPLETION_DATE = 'applereminderscompletiondate'
    CREATION_DATE = 'applereminderscreationdate'
    MODIFICATION_DATE = 'appleremindersmodificationdate'
    LIST = 'applereminderslist'
    URL = 'appleremindersurl'
    FLAGGED = 'appleremindersflagged'
    UNIQUE_KEY = 'appleremindersid'

    UDAS = {
        TITLE: {'type': 'string', 'label': 'Apple Reminders Title'},
        NOTES: {'type': 'string', 'label': 'Apple Reminders Notes'},
        DUE_DATE: {'type': 'date', 'label': 'Apple Reminders Due Date'},
        COMPLETION_DATE: {'type': 'date', 'label': 'Apple Reminders Completion Date'},
        CREATION_DATE: {'type': 'date', 'label': 'Apple Reminders Creation Date'},
        MODIFICATION_DATE: {'type': 'date', 'label': 'Apple Reminders Modification Date'},
        LIST: {'type': 'string', 'label': 'Apple Reminders List'},
        URL: {'type': 'string', 'label': 'Apple Reminders URL'},
        FLAGGED: {'type': 'string', 'label': 'Apple Reminders Flagged'},
        UNIQUE_KEY: {'type': 'string', 'label': 'Apple Reminders ID'},
    }

    def _get_formatted_date(self, date_value):
        """Format date for taskwarrior."""
        if not date_value:
            return None

        # If it's already a string (ISO format), parse it
        if isinstance(date_value, str):
            try:
                dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                return dt.strftime('%Y%m%dT%H%M%SZ')
            except Exception:
                return None

        # If it's an NSDate object, convert to timestamp
        try:
            timestamp = date_value.timeIntervalSince1970()
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y%m%dT%H%M%SZ')
        except Exception:
            return None

    def to_taskwarrior(self):
        task = {
            'project': self.record['list_name'],
            'priority': self.get_priority(),
            'annotations': [],
            self.UNIQUE_KEY: self.record['id'],
            self.TITLE: self.record['title'],
            self.LIST: self.record['list_name'],
        }

        # Add optional fields
        if self.record.get('notes'):
            task[self.NOTES] = self.record['notes']
            # Optionally add notes as annotation
            if hasattr(self, 'config') and getattr(self.config, 'add_notes_as_annotation', False):
                task['annotations'].append(self.record['notes'])

        if self.record.get('url'):
            task[self.URL] = self.record['url']

        if self.record.get('flagged'):
            task[self.FLAGGED] = 'true' if self.record['flagged'] else 'false'

        # Handle dates
        due_date = self._get_formatted_date(self.record.get('due_date'))
        if due_date:
            task['due'] = due_date
            task[self.DUE_DATE] = due_date

        completion_date = self._get_formatted_date(self.record.get('completion_date'))
        if completion_date:
            task[self.COMPLETION_DATE] = completion_date

        creation_date = self._get_formatted_date(self.record.get('creation_date'))
        if creation_date:
            task['entry'] = creation_date
            task[self.CREATION_DATE] = creation_date

        modification_date = self._get_formatted_date(self.record.get('modification_date'))
        if modification_date:
            task[self.MODIFICATION_DATE] = modification_date

        # Handle completion status
        if self.record.get('completed'):
            task['status'] = 'completed'
        else:
            task['status'] = 'pending'

        # Add tags from list name if configured
        task['tags'] = self.get_tags()

        return task

    def get_tags(self):
        tags = []

        if self.config.import_labels_as_tags and self.record['list_name']:
            template = self.config.label_template
            label = template.replace('{{label}}', self.record['list_name'])
            tags.append(label)

        return tags

    def get_priority(self):
        """Convert Apple priority (0/1/5/9) to taskwarrior priority (H/M/L)."""
        apple_priority = self.record.get('priority', 0)
        if apple_priority == 9:
            return 'H'
        elif apple_priority == 5:
            return 'M'
        elif apple_priority == 1:
            return 'L'
        else:
            return self.config.default_priority

    def get_default_description(self):
        return self.build_default_description(title=self.record['title'])


class AppleRemindersService(Service):
    ISSUE_CLASS = AppleRemindersIssue
    CONFIG_SCHEMA = AppleRemindersConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = None

    def get_keyring_service(self, config):
        """Apple Reminders doesn't use API keys."""
        return "bugwarrior://applereminders"

    def issues(self):
        """Yield issues from Apple Reminders."""
        if not self.client:
            self.client = AppleRemindersClient(self.config)

        try:
            reminders = self.client.get_reminders()
            log.info("Found %d reminders in Apple Reminders", len(reminders))

            for reminder in reminders:
                issue = self.get_issue_for_record(reminder)
                issue.config = self.config
                yield issue

        except Exception as e:
            log.error("Error retrieving reminders: %s", e)
            raise
