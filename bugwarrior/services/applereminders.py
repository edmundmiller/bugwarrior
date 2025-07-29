import logging
from datetime import datetime
import typing_extensions

from bugwarrior import config
from bugwarrior.services import Service, Issue, Client

log = logging.getLogger(__name__)


class AppleRemindersConfig(config.ServiceConfig):
    """Configuration schema for Apple Reminders service."""
    service: typing_extensions.Literal["applereminders"]
    
    # Optional configuration
    lists: config.ConfigList = config.ConfigList([])
    include_completed: bool = False
    import_labels_as_tags: bool = False
    label_template: str = "{{label}}"
    exclude_lists: config.ConfigList = config.ConfigList([])
    due_only: bool = False


class AppleRemindersClient(Client):
    """Client for interacting with Apple Reminders via apple-reminders library."""
    
    def __init__(self, lists=None, include_completed=False, exclude_lists=None, due_only=False):
        try:
            import apple_reminders
        except ImportError:
            raise ImportError(
                "The 'apple-reminders' library is required for the Apple Reminders service. "
                "Install it with: pip install apple-reminders"
            )
        
        self.apple_reminders = apple_reminders
        self.lists = lists or []
        self.include_completed = include_completed
        self.exclude_lists = exclude_lists or []
        self.due_only = due_only
        
        # Initialize connection to Reminders
        try:
            self.reminders_app = self.apple_reminders.RemindersApp()
        except Exception as e:
            log.error(f"Failed to connect to Apple Reminders: {e}")
            raise OSError(
                "Unable to connect to Apple Reminders. Please ensure:\n"
                "1. You're running on macOS\n"
                "2. The application has permission to access Reminders\n"
                "3. Reminders.app is installed and accessible"
            ) from e

    def get_reminder_lists(self):
        """Get all reminder lists."""
        try:
            return self.reminders_app.lists()
        except Exception as e:
            log.error(f"Failed to get reminder lists: {e}")
            return []

    def get_reminders(self):
        """Get reminders from specified lists."""
        all_lists = self.get_reminder_lists()
        
        # Filter lists based on configuration
        target_lists = []
        for reminder_list in all_lists:
            list_name = reminder_list.name
            
            # Skip excluded lists
            if list_name in self.exclude_lists:
                continue
            
            # If specific lists are configured, only include those
            if self.lists and list_name not in self.lists:
                continue
            
            target_lists.append(reminder_list)
        
        if not target_lists:
            log.warning("No reminder lists found matching configuration")
            return
        
        log.info(f"Processing {len(target_lists)} reminder lists")
        
        for reminder_list in target_lists:
            try:
                reminders = reminder_list.reminders(completed=self.include_completed)
                for reminder in reminders:
                    # Skip completed reminders unless explicitly included
                    if reminder.completed and not self.include_completed:
                        continue
                    
                    # Skip reminders without due dates if due_only is True
                    if self.due_only and not reminder.due_date:
                        continue
                    
                    # Convert reminder to dictionary format
                    reminder_dict = self._reminder_to_dict(reminder, reminder_list.name)
                    yield reminder_dict
                    
            except Exception as e:
                log.error(f"Failed to get reminders from list '{reminder_list.name}': {e}")
                continue

    def _reminder_to_dict(self, reminder, list_name):
        """Convert apple-reminders Reminder object to dictionary."""
        try:
            return {
                'id': reminder.id,
                'title': reminder.title or '',
                'notes': reminder.notes or '',
                'due_date': reminder.due_date,
                'completed': reminder.completed,
                'completion_date': reminder.completion_date,
                'creation_date': reminder.creation_date,
                'modification_date': reminder.modification_date,
                'priority': reminder.priority,  # 0=None, 1=Low, 5=Medium, 9=High
                'list_name': list_name,
                'url': f"x-apple-reminderkit://REMCDReminder/{reminder.id}",
                'flagged': getattr(reminder, 'flagged', False),
                'subtasks': getattr(reminder, 'subtasks', []),
            }
        except Exception as e:
            log.error(f"Failed to convert reminder to dict: {e}")
            return {
                'id': getattr(reminder, 'id', 'unknown'),
                'title': getattr(reminder, 'title', 'Unknown Reminder'),
                'notes': '',
                'due_date': None,
                'completed': False,
                'completion_date': None,
                'creation_date': None,
                'modification_date': None,
                'priority': 0,
                'list_name': list_name,
                'url': f"x-apple-reminderkit://REMCDReminder/{getattr(reminder, 'id', 'unknown')}",
                'flagged': False,
                'subtasks': [],
            }


class AppleRemindersIssue(Issue):
    """Issue class for Apple Reminders."""
    
    # Field constants
    ID = "appleremindersid"
    TITLE = "applereminderstitle"
    NOTES = "appleremindersnotes"
    DUE_DATE = "appleremindersdue"
    COMPLETED = "applereminderscompleted"
    COMPLETION_DATE = "applereminderscompleted_date"
    CREATION_DATE = "applereminderscreated"
    MODIFICATION_DATE = "appleremindersmodified"
    PRIORITY = "appleremindersprioirty"
    LIST_NAME = "applereminderslist"
    URL = "appleremindersurl"
    FLAGGED = "appleremindersflagged"

    # Priority mapping from Apple Reminders to Taskwarrior
    PRIORITY_MAP = {
        0: None,    # No priority
        1: "L",     # Low priority
        5: "M",     # Medium priority  
        9: "H",     # High priority
    }

    UDAS = {
        ID: {
            "type": "string",
            "label": "Apple Reminders ID",
        },
        TITLE: {
            "type": "string", 
            "label": "Apple Reminders Title",
        },
        NOTES: {
            "type": "string",
            "label": "Apple Reminders Notes",
        },
        DUE_DATE: {
            "type": "date",
            "label": "Apple Reminders Due Date",
        },
        COMPLETED: {
            "type": "numeric",
            "label": "Apple Reminders Completed",
        },
        COMPLETION_DATE: {
            "type": "date",
            "label": "Apple Reminders Completion Date",
        },
        CREATION_DATE: {
            "type": "date",
            "label": "Apple Reminders Creation Date",
        },
        MODIFICATION_DATE: {
            "type": "date",
            "label": "Apple Reminders Modification Date",
        },
        PRIORITY: {
            "type": "numeric",
            "label": "Apple Reminders Priority",
        },
        LIST_NAME: {
            "type": "string",
            "label": "Apple Reminders List",
        },
        URL: {
            "type": "string",
            "label": "Apple Reminders URL",
        },
        FLAGGED: {
            "type": "numeric", 
            "label": "Apple Reminders Flagged",
        },
    }

    UNIQUE_KEY = (ID,)

    def to_taskwarrior(self):
        """Convert reminder to taskwarrior task format."""
        
        # Parse dates
        due_date = self.parse_date(self.record['due_date']) if self.record['due_date'] else None
        completion_date = self.parse_date(self.record['completion_date']) if self.record['completion_date'] else None
        creation_date = self.parse_date(self.record['creation_date']) if self.record['creation_date'] else None
        modification_date = self.parse_date(self.record['modification_date']) if self.record['modification_date'] else None

        # Determine task status
        status = "completed" if self.record['completed'] else "pending"

        # Build tags from list name if configured
        tags = []
        if self.config.import_labels_as_tags and self.record['list_name']:
            tags = self.get_tags_from_labels(
                [self.record['list_name']],
                toggle_option='import_labels_as_tags',
                template_option='label_template',
                template_variable='label'
            )

        task = {
            "project": self.extra.get("project", self.record['list_name']),
            "priority": self.get_priority(),
            "annotations": self.extra.get("annotations", []),
            "tags": tags,
            "due": due_date,
            "status": status,
            "entry": creation_date,
            "end": completion_date if status == "completed" else None,
            "modified": modification_date,
            
            # Apple Reminders specific fields
            self.ID: self.record['id'],
            self.TITLE: self.record['title'],
            self.NOTES: self.record['notes'],
            self.DUE_DATE: due_date,
            self.COMPLETED: int(self.record['completed']),
            self.COMPLETION_DATE: completion_date,
            self.CREATION_DATE: creation_date, 
            self.MODIFICATION_DATE: modification_date,
            self.PRIORITY: self.record['priority'],
            self.LIST_NAME: self.record['list_name'],
            self.URL: self.record['url'],
            self.FLAGGED: int(self.record['flagged']),
        }
        
        return task

    def get_default_description(self):
        """Get default description for this reminder."""
        return self.build_default_description(
            title=self.record['title'],
            url=self.record['url'],
            number=self.record['id'],
            cls="task",
        )


class AppleRemindersService(Service):
    """Service class for Apple Reminders integration."""
    
    ISSUE_CLASS = AppleRemindersIssue
    CONFIG_SCHEMA = AppleRemindersConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialize client with configuration
        self.client = AppleRemindersClient(
            lists=list(self.config.lists) if self.config.lists else None,
            include_completed=self.config.include_completed,
            exclude_lists=list(self.config.exclude_lists) if self.config.exclude_lists else None,
            due_only=self.config.due_only,
        )

    @staticmethod
    def get_keyring_service(config):
        """Return keyring service name."""
        return "applereminders://"

    def issues(self):
        """Generator yielding Apple Reminders as Issue instances."""
        log.info("Fetching reminders from Apple Reminders")
        
        try:
            for reminder_record in self.client.get_reminders():
                # Build extra data
                extra = {
                    "project": reminder_record['list_name'],
                    "annotations": [],
                }
                
                # Add notes as annotation if present
                if reminder_record['notes'] and self.main_config.annotation_comments:
                    extra["annotations"].append(f"Notes: {reminder_record['notes']}")
                
                yield self.get_issue_for_record(reminder_record, extra)
                
        except Exception as e:
            log.error(f"Failed to fetch reminders: {e}")
            raise