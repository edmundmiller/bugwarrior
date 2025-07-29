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
    """Client for Apple Reminders using PyObjC EventKit framework."""

    def __init__(self, config: AppleRemindersConfig):
        self.config = config
        self.lists = config.lists
        self.exclude_lists = config.exclude_lists
        self.include_completed = config.include_completed
        self.due_only = config.due_only

        try:
            from EventKit import EKEventStore, EKEntityTypeReminder
            from Foundation import NSDate
            
            self.EKEventStore = EKEventStore
            self.EKEntityTypeReminder = EKEntityTypeReminder
            self.NSDate = NSDate
            
            # Create event store
            self.event_store = EKEventStore.alloc().init()
            
            # Request access to reminders
            self._request_access()
            
            log.info("Successfully connected to Apple Reminders via EventKit")

        except ImportError as e:
            log.error("Failed to import EventKit/Foundation from PyObjC. This service only works on macOS with PyObjC installed.")
            raise ImportError(
                "EventKit framework not available. "
                "Make sure you're on macOS and have PyObjC installed (pip install pyobjc-framework-EventKit)."
            ) from e
        except Exception as e:
            log.error("Failed to initialize Apple Reminders connection: %s", e)
            raise

    def _request_access(self):
        """Request access to reminders and wait for permission."""
        import time
        
        # Check if we already have access
        has_access = self.event_store.accessGrantedForEntityType_(self.EKEntityTypeReminder)
        if has_access:
            log.debug("Already have access to reminders")
            return
        
        # For modern macOS, we should try the newer access request methods first
        try:
            # Try requesting full access to reminders (macOS 14+)
            if hasattr(self.event_store, 'requestFullAccessToRemindersWithCompletion_'):
                log.info("Requesting full access to reminders...")
                access_granted = [False]
                request_complete = [False]
                
                def full_access_completion_handler(granted, error):
                    access_granted[0] = granted
                    request_complete[0] = True
                    if error:
                        log.error("Error requesting full access: %s", error)
                
                self.event_store.requestFullAccessToRemindersWithCompletion_(full_access_completion_handler)
                
                # Wait for response (up to 10 seconds)
                for _ in range(100):  # 10 seconds with 0.1s intervals
                    if request_complete[0]:
                        if access_granted[0]:
                            log.info("Full access to reminders granted")
                            return
                        else:
                            log.warning("Full access to reminders denied, trying standard access...")
                        break
                    time.sleep(0.1)
        
        except Exception as e:
            log.debug("Full access request not available or failed: %s", e)
        
        # Fallback to standard access request
        log.info("Requesting standard access to reminders...")
        access_granted = [False]
        request_complete = [False]
        
        def completion_handler(granted, error):
            access_granted[0] = granted
            request_complete[0] = True
            if error:
                log.error("Error requesting access: %s", error)
        
        try:
            self.event_store.requestAccessToEntityType_completion_(
                self.EKEntityTypeReminder, 
                completion_handler
            )
            
            # Wait for response (up to 10 seconds)
            for _ in range(100):  # 10 seconds with 0.1s intervals
                if request_complete[0]:
                    if access_granted[0]:
                        log.info("Access to reminders granted")
                        return
                    break
                time.sleep(0.1)
        
        except Exception as e:
            log.error("Failed to request access: %s", e)
        
        # Final check to see if we have access now
        has_access = self.event_store.accessGrantedForEntityType_(self.EKEntityTypeReminder)
        if has_access:
            log.info("Access to reminders verified")
            return
        
        # If we still don't have access, provide helpful error message
        raise PermissionError(
            "Access to Apple Reminders is required but not granted. Please:\n"
            "1. Grant access when prompted by macOS\n"
            "2. Or go to System Settings > Privacy & Security > Reminders\n"
            "3. Ensure your terminal or application has access to Reminders"
        )

    def get_reminder_lists(self):
        """Get all reminder calendars."""
        try:
            calendars = self.event_store.calendarsForEntityType_(self.EKEntityTypeReminder)
            log.debug("Found %d reminder calendars", len(calendars))
            return calendars
        except Exception as e:
            log.error("Failed to get reminder calendars: %s", e)
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

        try:
            # Get all reminder calendars
            calendars = self.get_reminder_lists()
            
            for calendar in calendars:
                calendar_name = str(calendar.title())
                
                # Check if this calendar should be included
                if not self._should_include_list(calendar_name):
                    log.debug("Skipping calendar: %s", calendar_name)
                    continue
                
                # Get reminders from this calendar
                calendar_reminders = self._get_reminders_from_calendar(calendar)
                
                for reminder in calendar_reminders:
                    # Apply completion filter
                    if not self.include_completed and reminder.isCompleted():
                        continue

                    # Apply due_only filter
                    if self.due_only and not reminder.dueDateComponents():
                        continue

                    reminders.append(self._reminder_to_dict(reminder, calendar_name))

            log.debug("Filtered to %d reminders", len(reminders))
            return reminders

        except Exception as e:
            log.error("Failed to get reminders: %s", e)
            raise

    def _get_reminders_from_calendar(self, calendar):
        """Get all reminders from a specific calendar."""
        from Foundation import NSPredicate, NSDate
        
        # Create predicate to fetch all reminders from this calendar
        # We'll get both completed and incomplete reminders, then filter later
        predicate = self.event_store.predicateForRemindersInCalendars_([calendar])
        
        # Fetch reminders synchronously
        reminders = []
        fetch_complete = [False]
        
        def completion_handler(reminder_list):
            reminders.extend(reminder_list or [])
            fetch_complete[0] = True
        
        self.event_store.fetchRemindersMatchingPredicate_completion_(
            predicate,
            completion_handler
        )
        
        # Wait for fetch to complete (up to 5 seconds)
        import time
        for _ in range(50):  # 5 seconds with 0.1s intervals
            if fetch_complete[0]:
                break
            time.sleep(0.1)
        
        return reminders

    def _reminder_to_dict(self, reminder, list_name):
        """Convert an EventKit reminder object to a dictionary."""
        try:
            # Get basic fields
            data = {
                'id': str(reminder.calendarItemIdentifier()),
                'title': str(reminder.title() or ''),
                'notes': str(reminder.notes() or ''),
                'completed': bool(reminder.isCompleted()),
                'list_name': list_name,
                'url': f"x-apple-reminderkit://REMCDReminder/{reminder.calendarItemIdentifier()}",
                'flagged': bool(getattr(reminder, 'isFlagged', lambda: False)()),
            }

            # Handle dates
            data['due_date'] = self._format_date_components(reminder.dueDateComponents())
            data['creation_date'] = self._format_nsdate(reminder.creationDate())
            data['modification_date'] = self._format_nsdate(reminder.lastModifiedDate())
            data['completion_date'] = self._format_nsdate(reminder.completionDate())

            # Map priority (EventKit uses 0=none, 1-4=low, 5=medium, 6-9=high)
            priority = reminder.priority()
            if priority == 0:
                data['priority'] = 0  # none
            elif 1 <= priority <= 4:
                data['priority'] = 1  # low
            elif priority == 5:
                data['priority'] = 5  # medium
            elif 6 <= priority <= 9:
                data['priority'] = 9  # high
            else:
                data['priority'] = 0

            return data

        except Exception as e:
            log.error("Failed to convert reminder to dict: %s", e)
            # Return minimal data on error
            return {
                'id': str(getattr(reminder, 'calendarItemIdentifier', lambda: 'error')()),
                'title': str(getattr(reminder, 'title', lambda: 'Error')() or 'Error'),
                'notes': '',
                'completed': False,
                'list_name': list_name,
                'priority': 0,
                'due_date': None,
                'creation_date': None,
                'modification_date': None,
                'completion_date': None,
                'url': '',
                'flagged': False,
            }

    def _format_nsdate(self, nsdate):
        """Format NSDate object to ISO string."""
        if not nsdate:
            return None
        
        try:
            # Convert NSDate to timestamp and then to datetime
            timestamp = nsdate.timeIntervalSince1970()
            dt = datetime.fromtimestamp(timestamp)
            return dt.isoformat()
        except Exception as e:
            log.error("Failed to format NSDate: %s", e)
            return None

    def _format_date_components(self, date_components):
        """Format NSDateComponents object to ISO string."""
        if not date_components:
            return None
        
        try:
            # Extract date components
            year = date_components.year()
            month = date_components.month()
            day = date_components.day()
            hour = getattr(date_components, 'hour', lambda: 0)()
            minute = getattr(date_components, 'minute', lambda: 0)()
            second = getattr(date_components, 'second', lambda: 0)()
            
            # Check for invalid values (NSDateComponents uses NSIntegerMax for unset values)
            # NSIntegerMax is typically 9223372036854775807 on 64-bit systems
            max_val = 2147483647  # Use a reasonable max value
            if any(val > max_val for val in [year, month, day, hour, minute, second] if val != -1):
                return None
                
            # Validate ranges
            if year == -1 or year < 1 or year > 9999:
                return None
            if month == -1 or month < 1 or month > 12:
                month = 1
            if day == -1 or day < 1 or day > 31:
                day = 1
            if hour == -1 or hour < 0 or hour > 23:
                hour = 0
            if minute == -1 or minute < 0 or minute > 59:
                minute = 0
            if second == -1 or second < 0 or second > 59:
                second = 0
            
            # Create datetime object
            dt = datetime(year, month, day, hour, minute, second)
            return dt.isoformat()
        except Exception as e:
            log.error("Failed to format date components: %s", e)
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
    UNIQUE_KEY = ('appleremindersid',)

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
                # Handle both with and without timezone
                if 'T' in date_value:
                    dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                else:
                    dt = datetime.fromisoformat(date_value)
                return dt.strftime('%Y%m%dT%H%M%SZ')
            except Exception as e:
                log.error("Failed to parse ISO date string: %s", e)
                return None

        # If it's an NSDate object, convert to timestamp
        try:
            timestamp = date_value.timeIntervalSince1970()
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y%m%dT%H%M%SZ')
        except Exception as e:
            log.error("Failed to convert NSDate: %s", e)
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
