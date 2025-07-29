Apple Reminders
===============

You can import tasks from Apple Reminders using the ``applereminders`` service name.
This service integrates with Apple's native Reminders application on macOS through the
EventKit framework.

.. note::
   This service is only available on macOS and requires permission to access the Reminders app.

Installation
------------

Install Bugwarrior's Apple Reminders support with the ``applereminders`` extra:

::

    pip install bugwarrior[applereminders]

This will install the required ``apple-reminders`` library dependency.

Example Service
---------------

Here is an example of a minimal configuration for the ``applereminders`` service:

.. config::

    [applereminders]
    service = applereminders

The above example is the minimum required to import reminders from Apple Reminders.
You can also use any of the configuration options described in 
:ref:`common_configuration_options` or described in `Service Features`_ below.

macOS Permissions
-----------------

Before using this service, you must grant permission for your terminal application
(and by extension, Bugwarrior) to access Apple Reminders:

1. Run Bugwarrior for the first time - you'll be prompted for permission
2. If the permission dialog doesn't appear, go to **System Preferences > Security & Privacy > Privacy**
3. Select **Reminders** from the left sidebar
4. Add your terminal application (Terminal.app, iTerm2, etc.) to the list of allowed applications
5. If Bugwarrior is running in a different context (cron, automation), you may need to add additional applications

.. warning::
   Without proper EventKit permissions, the service will fail to connect to Apple Reminders
   and throw an ``OSError`` with permission details.

Service Features
----------------

List Filtering
++++++++++++++

By default, reminders from all lists are imported. You can control which lists to include
or exclude using the ``lists`` and ``exclude_lists`` options.

To import reminders from specific lists only:

.. config::
    :fragment: applereminders

    applereminders.lists = Shopping, Work, Personal

To exclude specific lists while importing from all others:

.. config::
    :fragment: applereminders

    applereminders.exclude_lists = Archive, Completed

If both ``lists`` and ``exclude_lists`` are specified, ``exclude_lists`` takes precedence
for any lists that appear in both.

Completion Status Handling
++++++++++++++++++++++++++

By default, only pending (incomplete) reminders are imported. To also import completed
reminders, use the ``include_completed`` option:

.. config::
    :fragment: applereminders

    applereminders.include_completed = True

When ``include_completed`` is enabled, completed reminders will have their status set to
"completed" in Taskwarrior and will include completion dates if available.

Due Date Filtering
++++++++++++++++++

To import only reminders that have due dates set, use the ``due_only`` option:

.. config::
    :fragment: applereminders

    applereminders.due_only = True

This is useful if you want to focus on time-sensitive tasks and ignore general reminders
without specific deadlines.

Import Labels as Tags
+++++++++++++++++++++

Apple Reminders organizes tasks into lists. You can import the list name as a Taskwarrior
tag using the ``import_labels_as_tags`` option:

.. config::
    :fragment: applereminders

    applereminders.import_labels_as_tags = True

By default, the list name is used directly as the tag. You can customize this behavior
using a template with the ``label_template`` option:

.. config::
    :fragment: applereminders

    applereminders.label_template = apple_{{label}}

This would prefix all list-based tags with "apple_", so a reminder from the "Shopping"
list would get the tag "apple_Shopping".

.. note::
   See :ref:`field_templates` for more details regarding how templates are processed.

Priority Mapping
++++++++++++++++

Apple Reminders uses a numeric priority system (0=None, 1=Low, 5=Medium, 9=High).
These are mapped to Taskwarrior priorities as follows:

- Apple Reminders priority 0 (None) → No Taskwarrior priority (uses ``default_priority`` if set)
- Apple Reminders priority 1 (Low) → Taskwarrior priority "L"
- Apple Reminders priority 5 (Medium) → Taskwarrior priority "M"  
- Apple Reminders priority 9 (High) → Taskwarrior priority "H"

Date Handling
+++++++++++++

The service handles several types of dates from Apple Reminders:

- **Due dates**: Mapped to Taskwarrior's ``due`` field
- **Creation dates**: Mapped to Taskwarrior's ``entry`` field
- **Completion dates**: Mapped to Taskwarrior's ``end`` field (for completed tasks)
- **Modification dates**: Mapped to Taskwarrior's ``modified`` field

All dates are preserved in their original timezone and format.

Configuration Options
---------------------

.. config:: bugwarrior.services.applereminders.AppleRemindersConfig

Provided UDA Fields
-------------------

.. udas:: bugwarrior.services.applereminders.AppleRemindersIssue

Examples
--------

Basic Configuration
+++++++++++++++++++

Import all pending reminders from all lists:

.. config::

    [applereminders]
    service = applereminders

Work-Focused Configuration
++++++++++++++++++++++++++

Import only work-related reminders with due dates:

.. config::

    [work_reminders]
    service = applereminders
    applereminders.lists = Work, Projects
    applereminders.due_only = True
    applereminders.import_labels_as_tags = True
    applereminders.label_template = work_{{label}}

Complete Task Archive
+++++++++++++++++++++

Import all reminders including completed ones for archival purposes:

.. config::

    [complete_archive]
    service = applereminders
    applereminders.include_completed = True
    applereminders.exclude_lists = Spam, Archive

Personal Task Management
++++++++++++++++++++++++

Import personal reminders with list-based tagging:

.. config::

    [personal_tasks]
    service = applereminders
    applereminders.lists = Personal, Home, Shopping
    applereminders.import_labels_as_tags = True
    applereminders.label_template = {{label|lower}}
    # Set low default priority for personal tasks
    default_priority = L