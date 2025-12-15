import copy
import logging
import multiprocessing
import time

from importlib_metadata import entry_points
from jinja2 import Template
from rich.progress import Progress, SpinnerColumn, TextColumn
from taskw_ng.task import Task

from bugwarrior.console import error as console_error

log = logging.getLogger(__name__)

# Sentinels for process completion status
SERVICE_FINISHED_OK = 0
SERVICE_FINISHED_ERROR = 1


def get_service(service_name: str):
    try:
        (service,) = entry_points(group="bugwarrior.service", name=service_name)
    except ValueError as e:
        if service_name in [
            "activecollab",
            "activecollab2",
            "megaplan",
            "teamlab",
            "versionone",
        ]:
            log.warning(f"The {service_name} service has been removed.")
        raise ValueError(
            f"Configured service '{service_name}' not found. "
            "Is it installed? Or misspelled?"
        ) from e
    return service.load()


def _aggregate_issues(conf, main_section, target, queue):
    """This worker function is separated out from the main
    :func:`aggregate_issues` func only so that we can use multiprocessing
    on it for speed reasons.
    """

    start = time.time()

    try:
        service = get_service(conf[target].service)(conf[target], conf[main_section])
        issue_count = 0
        for issue in service.issues():
            queue.put(issue)
            issue_count += 1
    except SystemExit as e:
        log.critical(f"Worker for [{target}] exited: {e}")
        queue.put((SERVICE_FINISHED_ERROR, target, 0))
    except BaseException as e:
        if hasattr(e, "request") and e.request:
            # Exceptions raised by requests library have the HTTP request
            # object stored as attribute. The request can have hooks attached
            # to it, and we need to remove them, as there can be unpickleable
            # methods. There is no one left to call these hooks anyway.
            e.request.hooks = {}
        log.exception(f"Worker for [{target}] failed: {e}")
        queue.put((SERVICE_FINISHED_ERROR, target, 0))
    else:
        log.debug(f"Worker for [{target}] finished ok.")
        queue.put((SERVICE_FINISHED_OK, target, issue_count))
    finally:
        duration = time.time() - start
        log.debug(f"Done with [{target}] in {duration:.1f}s.")


def aggregate_issues(conf, main_section, debug, quiet=False, verbose=False):
    """Return all issues from every target."""
    log.debug("Starting to aggregate remote issues.")

    # Create and call service objects for every target in the config
    targets = conf[main_section].targets

    queue = multiprocessing.Queue()

    log.debug("Spawning %i workers." % len(targets))

    # Set up progress display (unless quiet mode)
    use_progress = not quiet
    progress_ctx = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=not verbose,
        disable=not use_progress,
    )

    with progress_ctx as progress:
        # Create a progress task for each target
        progress_tasks = {}
        for target in targets:
            progress_tasks[target] = progress.add_task(
                f"[cyan]{target}[/cyan]", total=1
            )

        if debug:
            for target in targets:
                _aggregate_issues(conf, main_section, target, queue)
        else:
            for target in targets:
                proc = multiprocessing.Process(
                    target=_aggregate_issues, args=(conf, main_section, target, queue)
                )
                proc.start()

                # Sleep for 1 second here to try and avoid a race condition where
                # all N workers start up and ask the gpg-agent process for
                # information at the same time.  This causes gpg-agent to fumble
                # and tell some of our workers some incomplete things.
                time.sleep(1)

        currently_running = len(targets)
        issue_counts = {target: 0 for target in targets}

        while currently_running > 0:
            issue = queue.get(True)
            try:
                record = TaskConstructor(issue).get_taskwarrior_record()
                record["target"] = issue.config.target
                # Track issue count per target
                target = record["target"]
                issue_counts[target] = issue_counts.get(target, 0) + 1
                yield record
            except AttributeError:
                if isinstance(issue, tuple):
                    currently_running -= 1
                    completion_type, target, count = issue
                    if completion_type == SERVICE_FINISHED_ERROR:
                        console_error(f"Aborted \\[{target}] due to critical error.")
                        progress.update(
                            progress_tasks[target],
                            description=f"[red]✗ {target}[/red]",
                            completed=1,
                        )
                        yield ("SERVICE FAILED", target)
                    else:
                        final_count = issue_counts.get(target, count)
                        progress.update(
                            progress_tasks[target],
                            description=f"[green]✓ {target}[/green] ({final_count} issues)",
                            completed=1,
                        )
                    continue
                raise

    log.debug("Done aggregating remote issues.")


class TaskConstructor:
    """Construct a taskwarrior task from a foreign record."""

    def __init__(self, issue):
        self.issue = issue

    def get_added_tags(self):
        added_tags = []
        for tag in self.issue.config.add_tags:
            tag = Template(tag).render(self.get_template_context())
            if tag:
                added_tags.append(tag)

        return added_tags

    def get_taskwarrior_record(self, refined=True) -> dict:
        if not getattr(self, "_taskwarrior_record", None):
            self._taskwarrior_record = self.issue.to_taskwarrior()
        record = copy.deepcopy(self._taskwarrior_record)
        if refined:
            record = self.refine_record(record)
        if "tags" not in record:
            record["tags"] = []
        if refined:
            record["tags"].extend(self.get_added_tags())
        return record

    def get_template_context(self):
        context = self.get_taskwarrior_record(refined=False).copy()
        context.update(self.issue.extra)
        context.update({"description": self.issue.get_default_description()})
        return context

    def refine_record(self, record):
        for field in Task.FIELDS.keys():
            if field in self.issue.config.templates:
                template = Template(self.issue.config.templates[field])
                record[field] = template.render(self.get_template_context())
            elif field == "description":
                record["description"] = self.issue.get_default_description()
        # Also apply UDA templates (fields not in Task.FIELDS)
        for field, template_str in self.issue.config.templates.items():
            if field not in Task.FIELDS:
                template = Template(template_str)
                record[field] = template.render(self.get_template_context())
        return record
