Linear
======

You can import tasks from Linear.app using the ``linear`` service name.


Example Service
---------------

Here's an example of a Linear target:

.. config::

    [my_issues]
    service = linear
    linear.api_token = <your API token>

The above example is the minimum required to import issues from Linear.  You
can also feel free to use any of the configuration options described in
:ref:`common_configuration_options`.

Options
----------

.. describe:: api_token

    Linear offers API keys at Settings -> Security & Access -> Personal API
    Keys. You will need to provide ``api_token`` to allow bugwarrior to read
    issues. The token needs only Read access.

.. describe:: import_labels_as_tags

    A boolean that indicates whether the Linear labels should be imported as
    tags in taskwarrior. (Defaults to false.)

.. describe:: label_template

   Template used to convert Linear labels to taskwarrior tags.
   See :ref:`field_templates` for more details regarding how templates
   are processed.
   The default value is ``{{label|replace(' ', '_')}}``.

Provided UDA Fields
-------------------

.. udas:: bugwarrior.services.linear.LinearIssue

