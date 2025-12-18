import itertools
import json
import logging
import re
import subprocess

from rich.panel import Panel
from rich.table import Table
from taskw_ng import TaskWarrior
from taskw_ng.exceptions import TaskwarriorError

from bugwarrior.collect import get_service
from bugwarrior.console import console, hint, warn, detail
from bugwarrior.notifications import send_notification

log = logging.getLogger(__name__)


class NotFound(Exception):
    pass


class MultipleMatches(Exception):
    pass


def get_normalized_annotation(annotation):
    return re.sub(r"[\W_]", "", str(annotation))


def get_annotation_hamming_distance(left, right):
    left = get_normalized_annotation(left)
    right = get_normalized_annotation(right)
    if len(left) > len(right):
        left = left[0 : len(right)]
    elif len(right) > len(left):
        right = right[0 : len(left)]
    return hamdist(left, right)


def hamdist(str1, str2):
    """Count the # of differences between equal length strings str1 and str2"""
    diffs = 0
    for ch1, ch2 in zip(str1, str2):
        if ch1 != ch2:
            diffs += 1
    return diffs


def get_managed_task_uuids(tw, key_list):
    expected_task_ids = set()
    for keys in key_list.values():
        tasks = tw.filter_tasks(
            {
                "and": [("%s.any" % key, None) for key in keys],
                "or": [("status", "pending"), ("status", "waiting")],
            }
        )
        expected_task_ids = expected_task_ids | set([task["uuid"] for task in tasks])

    return expected_task_ids


def make_unique_identifier(keys: dict, issue: dict) -> str:
    """For a given issue, make an identifier from its unique keys.

    This is not the same as the taskwarrior uuid, which is assigned
    only once the task is created.
    """
    for service, key_list in keys.items():
        if all([key in issue for key in key_list]):
            subset = {key: issue[key] for key in key_list}
            return json.dumps(subset, sort_keys=True)
    raise RuntimeError("Could not determine unique identifier for %s" % issue)


def find_taskwarrior_uuid(tw, keys, issue):
    """For a given issue issue, find its local taskwarrior UUID.

    Assembles a list of task IDs existing in taskwarrior
    matching the supplied issue (`issue`) on the combination of any
    set of supplied unique identifiers (`keys`).

    :params:
    * `tw`: An instance of `taskw_ng.TaskWarrior`
    * `keys`: A list of lists of keys to use for uniquely identifying
      an issue.  To clarify the "list of lists" behavior, assume that
      there are two services, one having a single primary key field
      -- 'serviceAid' -- and another having a pair of fields composing
      its primary key -- 'serviceBproject' and 'serviceBnumber' --, the
      incoming data for this field would be::

        [
            ['serviceAid'],
            ['serviceBproject', 'serviceBnumber'],
        ]

    * `issue`: An instance of a subclass of `bugwarrior.services.Issue`.

    :returns:
    * A single string UUID.

    :raises:
    * `bugwarrior.db.MultipleMatches`: if multiple matches were found.
    * `bugwarrior.db.NotFound`: if an issue was not found.

    """
    if not issue["description"]:
        raise ValueError("Issue %s has no description." % issue)

    possibilities = set()

    for service, key_list in keys.items():
        if any([key in issue for key in key_list]):
            results = tw.filter_tasks(
                {
                    "and": [("%s.is" % key, issue[key]) for key in key_list],
                    "or": [
                        ("status", "pending"),
                        ("status", "waiting"),
                        ("status", "completed"),
                    ],
                }
            )
            new_possibilities = set([task["uuid"] for task in results])
            # Previous versions of bugwarrior did not allow for reopening
            # completed tasks, so there could be multiple completed tasks
            # for the same issue if it was closed and reopened before that.
            if len(new_possibilities) > 1 and all(
                r["status"] == "completed" for r in results
            ):
                for r in results[1:]:
                    for k in key_list:
                        if r[k] != results[0][k]:
                            break
                else:
                    # All results are completed duplicates.
                    new_possibilities = set([new_possibilities.pop()])
            possibilities = possibilities | new_possibilities

    if len(possibilities) == 1:
        return possibilities.pop()

    if len(possibilities) > 1:
        raise MultipleMatches(
            "Issue %s matched multiple IDs: %s" % (issue["description"], possibilities)
        )

    raise NotFound("No issue was found matching %s" % issue)


def replace_left(field, local_task, remote_issue, keep_items=[]):
    """Replace array field from the remote_issue to the local_task

    * Local 'left' entries are suppressed, unless those listed in keep_items.
    * Remote 'left' are appended to task, if not present in local.

    :param `field`: Task field to merge.
    :param `local_task`: `taskw.task.Task` object into which to replace
        remote changes.
    :param `remote_issue`: `dict` instance from which to add into
        local task.
    :param `keep_items`: list of items to keep into local_task even if not
        present in remote_issue
    """

    # Ensure that empty default are present
    local_field = local_task.get(field, []).copy()
    remote_field = remote_issue.get(field, [])

    # We need to make sure an array exists for this field because
    # we will be appending to it in a moment.
    if field not in local_task:
        local_task[field] = []

    # Delete all items in local_task, unless they are in keep_items or in remote_issue
    # This ensure that the task is not being updated if there is no changes
    for item in local_field:
        if keep_items.count(item) == 0 and remote_field.count(item) == 0:
            log.debug("found %s to remove" % (item))
            local_task[field].remove(item)
        elif remote_field.count(item) > 0:
            remote_field.remove(item)

    if len(remote_field) > 0:
        local_task[field] += remote_field


def merge_left(field, local_task, remote_issue, hamming=False):
    """Merge array field from the remote_issue into local_task

    * Local 'left' entries are preserved without modification
    * Remote 'left' are appended to task if not present in local.

    :param `field`: Task field to merge.
    :param `local_task`: `taskw.task.Task` object into which to merge
        remote changes.
    :param `remote_issue`: `dict` instance from which to merge into
        local task.
    :param `hamming`: (default `False`) If `True`, compare entries by
        truncating to maximum length, and comparing hamming distances.
        Useful generally only for annotations.

    """

    # Ensure that empty defaults are present
    local_field = local_task.get(field, [])
    remote_field = remote_issue.get(field, [])

    # We need to make sure an array exists for this field because
    # we will be appending to it in a moment.
    if field not in local_task:
        local_task[field] = []

    # If a remote does not appear in local, add it to the local task
    new_count = 0
    for remote in remote_field:
        for local in local_field:
            if (
                # For annotations, they don't have to match *exactly*.
                (hamming and get_annotation_hamming_distance(remote, local) == 0)
                # But for everything else, they should.
                or (remote == local)
            ):
                break
        else:
            log.debug("%s not found in %r" % (remote, local_field))
            local_task[field].append(remote)
            new_count += 1
    if new_count > 0:
        log.debug(
            "Added %s new values to %s (total: %s)"
            % (new_count, field, len(local_task[field]))
        )


def run_hooks(pre_import):
    for hook in pre_import:
        exit_code = subprocess.call(hook, shell=True)
        if exit_code != 0:
            msg = "Non-zero exit code %d on hook %s" % exit_code, hook
            log.error(msg)
            raise RuntimeError(msg)


def synchronize(issue_generator, conf, main_section, dry_run=False, verbose=False):
    """Synchronize issues from services to taskwarrior.

    Args:
        issue_generator: Generator yielding issues from services.
        conf: Configuration dict.
        main_section: Name of the main config section.
        dry_run: If True, don't actually modify taskwarrior.
        verbose: If True, log per-task details at INFO level.
    """
    main_config = conf[main_section]

    targets = main_config.targets.copy()
    services = set([conf[target].service for target in targets])
    key_list = build_key_list(services)
    uda_list = build_uda_config_overrides(services)

    if uda_list:
        hint(
            "Service-defined UDAs exist: run 'bugwarrior uda' "
            "to export UDA definitions for your taskrc."
        )

    # Before running CRUD operations, call the pre_import hook(s).
    run_hooks(conf["hooks"].pre_import)

    notify = conf["notifications"].notifications and not dry_run

    tw = TaskWarrior(
        config_filename=main_config.taskrc, config_overrides=uda_list, marshal=True
    )

    issue_updates = {
        "new": [],
        "existing": [],
        "changed": [],
        "closed": [],
        "diverged": [],
    }

    issue_map = {}  # unique identifier -> issue
    for issue in issue_generator:
        if isinstance(issue, tuple) and issue[0] == "SERVICE FAILED":
            targets.remove(issue[1])
            continue

        # De-duplicate issues coming in
        unique_identifier = make_unique_identifier(key_list, issue)
        if unique_identifier in issue_map:
            log.debug(f"Merging tags and skipping. Seen {unique_identifier} of {issue}")
            # Merge and deduplicate tags.
            issue_map[unique_identifier]["tags"] += issue["tags"]
            issue_map[unique_identifier]["tags"] = list(
                set(issue_map[unique_identifier]["tags"])
            )
        else:
            issue_map[unique_identifier] = issue

    seen_uuids = set()
    for issue in issue_map.values():
        # We received this issue from The Internet, but we're not sure what
        # kind of encoding the service providers may have handed us. Let's try
        # and decode all byte strings from UTF8 off the bat.  If we encounter
        # other encodings in the wild in the future, we can revise the handling
        # here. https://github.com/ralphbean/bugwarrior/issues/350
        for key in issue.keys():
            if isinstance(issue[key], bytes):
                try:
                    issue[key] = issue[key].decode("utf-8")
                except UnicodeDecodeError:
                    log.warn("Failed to interpret %r as utf-8" % key)

        # Blank priority should mean *no* priority
        if issue["priority"] == "":
            issue["priority"] = None

        # Target was only tacked on to pass configuration to this function.
        service_config = conf[issue.pop("target")]

        try:
            existing_taskwarrior_uuid = find_taskwarrior_uuid(tw, key_list, issue)
        except MultipleMatches as e:
            log.exception("Multiple matches: %s", str(e))
        except NotFound:  # Create new task
            issue_updates["new"].append(issue)
        else:  # Update existing task.
            seen_uuids.add(existing_taskwarrior_uuid)
            _, task = tw.get_task(uuid=existing_taskwarrior_uuid)

            if task["status"] == "completed":
                # Task is completed locally but issue is still open upstream
                if main_config.reopen_completed_tasks:
                    # Reopen the task (original behavior)
                    detail(
                        f"Reopening completed task {existing_taskwarrior_uuid} "
                        f"for issue {issue.get('description', '')}"
                    )
                    task["status"] = "pending"
                    task["end"] = None
                else:
                    # Don't reopen it - track as diverged
                    # (warning displayed later in summary)
                    issue_updates["diverged"].append(
                        {
                            "uuid": existing_taskwarrior_uuid,
                            "task": task,
                            "issue": issue,
                            "service": service_config.service,
                        }
                    )
                    # Skip further processing of this task - leave it completed
                    continue

            # Drop static fields from the upstream issue.  We don't want to
            # overwrite local changes to fields we declare static.
            for field in itertools.chain(
                main_config.static_fields, service_config.static_fields
            ):
                if field in issue:
                    del issue[field]

            # Merge annotations & tags from online into our task object
            if main_config.merge_annotations:
                merge_left("annotations", task, issue, hamming=True)

            if main_config.merge_tags:
                if main_config.replace_tags:
                    replace_left("tags", task, issue, list(main_config.static_tags))
                else:
                    merge_left("tags", task, issue)

            issue.pop("annotations", None)
            issue.pop("tags", None)

            task.update(issue)

            if task.get_changes(keep=True):
                issue_updates["changed"].append(task)
            else:
                issue_updates["existing"].append(task)

    notreally = " [dim](dry run)[/dim]" if dry_run else ""

    # Add new issues
    if issue_updates["new"]:
        console.print(
            f"Adding [green]{len(issue_updates['new'])}[/green] tasks{notreally}"
        )
    for issue in issue_updates["new"]:
        detail(f"+ {issue['description']}")

        if dry_run:
            continue
        if notify:
            send_notification(issue, "Created", conf["notifications"])

        try:
            new_task = tw.task_add(**issue)
            if "end" in issue and issue["end"]:
                tw.task_done(uuid=new_task["uuid"])
        except TaskwarriorError as e:
            log.exception("Unable to add task: %s" % e.stderr)
        else:
            seen_uuids.add(new_task["uuid"])

    if issue_updates["changed"]:
        console.print(
            f"Updating [blue]{len(issue_updates['changed'])}[/blue] tasks{notreally}"
        )
    for issue in issue_updates["changed"]:
        changes = "; ".join(
            [
                "{field}: {f} -> {t}".format(field=field, f=repr(ch[0]), t=repr(ch[1]))
                for field, ch in issue.get_changes(keep=True).items()
            ]
        )
        detail(f"~ {issue['description']}: {changes}")
        if dry_run:
            continue

        try:
            _, updated_task = tw.task_update(issue)
            if "end" in issue and issue["end"]:
                tw.task_done(uuid=updated_task["uuid"])
        except TaskwarriorError as e:
            log.exception("Unable to modify task: %s" % e.stderr)

    log.debug(f"Closing tasks for succeeding services: {targets}.")
    succeeded_service_task_uuids = get_managed_task_uuids(
        tw, build_key_list(set([conf[target].service for target in targets]))
    )
    issue_updates["closed"] = succeeded_service_task_uuids - seen_uuids
    if issue_updates["closed"]:
        console.print(
            f"Closing [red]{len(issue_updates['closed'])}[/red] tasks{notreally}"
        )
    for issue in issue_updates["closed"]:
        _, task_info = tw.get_task(uuid=issue)
        detail(f"- {task_info.get('description', '')}")
        if dry_run:
            continue

        if notify:
            send_notification(task_info, "Completed", conf["notifications"])

        try:
            tw.task_done(uuid=issue)
        except TaskwarriorError as e:
            log.exception("Unable to close task: %s" % e.stderr)

    # Warn about diverged tasks (completed locally but still open upstream)
    if issue_updates["diverged"]:
        # Group diverged tasks by service for cleaner output
        by_service = {}
        for diverged in issue_updates["diverged"]:
            service = diverged["service"]
            if service not in by_service:
                by_service[service] = []
            by_service[service].append(diverged)

        # Build Rich table for diverged tasks
        table = Table(
            title="Diverged Tasks",
            title_style="bold yellow",
            show_header=True,
            header_style="bold",
        )
        table.add_column("Service", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("ID", style="dim")
        table.add_column("URL", style="blue")

        for service, diverged_tasks in by_service.items():
            for diverged in diverged_tasks:
                task = diverged["task"]
                issue = diverged["issue"]
                description = task.get("description", "Unknown")

                # Try to extract URL from task - services store URLs in UDAs
                url = (
                    task.get(f"{service}url")
                    or task.get("url")
                    or issue.get(f"{service}url")
                    or issue.get("url")
                    or f"(close in {service})"
                )

                # Try to get issue identifier for display
                issue_id = ""
                if service == "github" and "githubnumber" in task:
                    number = task["githubnumber"]
                    # Convert to int if it's a numeric with .0 suffix
                    if isinstance(number, (int, float)):
                        issue_id = f"#{int(number)}"
                    else:
                        issue_id = f"#{number}"
                elif service == "jira" and "jiraid" in task:
                    issue_id = task["jiraid"]
                elif service == "gitlab" and "gitlabnumber" in task:
                    number = task["gitlabnumber"]
                    # Convert to int if it's a numeric with .0 suffix
                    if isinstance(number, (int, float)):
                        issue_id = f"#{int(number)}"
                    else:
                        issue_id = f"#{number}"
                elif service == "linear" and "linearidentifier" in task:
                    issue_id = task["linearidentifier"]

                # Make URLs clickable if they are actual URLs
                if url.startswith(("http://", "https://")):
                    # Use Rich hyperlink markup for terminal emulators that support it
                    # Rich automatically handles terminal detection and fallback
                    clickable_url = f"[link={url}]{url}[/link]"
                else:
                    clickable_url = url  # For "(close in service)" messages

                table.add_row(service.upper(), description, issue_id, clickable_url)

        console.print()
        console.print(
            Panel(
                table,
                title="[bold yellow]⚠️  Completed Locally, Still Open Upstream[/]",
                subtitle="[dim]Close these issues upstream to dismiss this warning[/]",
                border_style="yellow",
            )
        )
        console.print()

    # Print final summary with Rich
    summary_parts = []
    if issue_updates["new"]:
        summary_parts.append(f"[green]+{len(issue_updates['new'])} new[/]")
    if issue_updates["changed"]:
        summary_parts.append(f"[blue]~{len(issue_updates['changed'])} updated[/]")
    if issue_updates["closed"]:
        summary_parts.append(f"[red]-{len(issue_updates['closed'])} closed[/]")
    if issue_updates["diverged"]:
        summary_parts.append(f"[yellow]⚠ {len(issue_updates['diverged'])} diverged[/]")

    if summary_parts:
        console.print(f"[bold]Sync complete:[/] {', '.join(summary_parts)}")
    else:
        console.print("[dim]Sync complete: no changes[/]")

    # Send notifications
    if notify:
        updates = (
            len(issue_updates["new"])
            + len(issue_updates["changed"])
            + len(issue_updates["closed"])
        )
        if not conf["notifications"].only_on_new_tasks or updates > 0:
            description = "New: %d, Changed: %d, Completed: %d" % (
                len(issue_updates["new"]),
                len(issue_updates["changed"]),
                len(issue_updates["closed"]),
            )
            if issue_updates["diverged"]:
                description += ", Diverged: %d" % len(issue_updates["diverged"])
            send_notification(
                dict(description=description),
                "bw_finished",
                conf["notifications"],
            )


def build_key_list(targets):
    keys = {}
    for target in targets:
        keys[target] = get_service(target).ISSUE_CLASS.UNIQUE_KEY
    return keys


def get_defined_udas_as_strings(conf, main_section):
    targets = conf[main_section].targets
    services = set([conf[target].service for target in targets])
    uda_list = build_uda_config_overrides(services)

    yield from convert_override_args_to_taskrc_settings(uda_list)


def build_uda_config_overrides(targets):
    """Returns a list of UDAs defined by given targets

    For all targets in `targets`, build a dictionary of configuration overrides
    representing the UDAs defined by the passed-in services (`targets`).

    Given a hypothetical situation in which you have two services, the first
    of which defining a UDA named 'serviceAid' ("Service A ID", string) and
    a second service defining two UDAs named 'serviceBproject'
    ("Service B Project", string) and 'serviceBnumber'
    ("Service B Number", numeric), this would return the following structure::

        {
            'uda': {
                'serviceAid': {
                    'label': 'Service A ID',
                    'type': 'string',
                },
                'serviceBproject': {
                    'label': 'Service B Project',
                    'type': 'string',
                },
                'serviceBnumber': {
                    'label': 'Service B Number',
                    'type': 'numeric',
                }
            }
        }

    """
    targets_udas = {}
    for target in targets:
        targets_udas.update(get_service(target).ISSUE_CLASS.UDAS)
    return {"uda": targets_udas}


def convert_override_args_to_taskrc_settings(config, prefix=""):
    args = []
    for k, v in config.items():
        if isinstance(v, dict):
            args.extend(
                convert_override_args_to_taskrc_settings(
                    v, prefix=".".join([prefix, k]) if prefix else k
                )
            )
        else:
            v = str(v)
            left = (prefix + "." if prefix else "") + k
            args.append("=".join([left, v]))
    return args
