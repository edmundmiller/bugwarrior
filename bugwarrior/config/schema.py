import logging
import os
import pathlib
import re
import sys
import typing

import pydantic
from pydantic import (
    AnyUrl,
    field_validator,
    model_validator,
    Field,
    BaseModel,
    ValidationError,
    create_model,
    ConfigDict,
)
from pydantic_settings import BaseSettings
from pydantic._internal._model_construction import complete_model_class
from pydantic.functional_validators import BeforeValidator
from pydantic_core import PydanticCustomError
from typing_extensions import Annotated
import taskw_ng

from bugwarrior.collect import get_service

from .data import BugwarriorData, get_data_path

log = logging.getLogger(__name__)


class StrippedTrailingSlashUrl(AnyUrl):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema

        return core_schema.with_info_before_validator_function(
            cls._validate,
            core_schema.url_schema(),
        )

    @classmethod
    def _validate(cls, value, info):
        if isinstance(value, str):
            value = value.rstrip("/")
        return value


class OracleUrl(str):
    """URL type that supports @oracle:eval: prefixed values.

    Evaluates oracle strings before URL validation, allowing URLs
    to be fetched from external commands (e.g., password managers).
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema

        return core_schema.with_info_before_validator_function(
            cls._validate,
            core_schema.url_schema(),
        )

    @classmethod
    def _validate(cls, value, info):
        if isinstance(value, str):
            if value.startswith("@oracle:eval:"):
                from .secrets import oracle_eval

                command = value[13:]  # len("@oracle:eval:") == 13
                value = oracle_eval(command)
            value = value.rstrip("/")
        return value


class NoSchemeUrl(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema

        return core_schema.with_info_before_validator_function(
            cls._validate,
            core_schema.str_schema(),
        )

    @classmethod
    def _validate(cls, value, info):
        if isinstance(value, str):
            value = value.rstrip("/")
            # Check for scheme
            if "://" in value:
                scheme = value.split("://", 1)[0]
                raise ValueError(f"URL should not include scheme ('{scheme}')")
        return value


# Pydantic complicates the use of sets or lists as default values.
class ConfigList(frozenset):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema

        return core_schema.with_info_before_validator_function(
            cls._validate,
            core_schema.list_schema(core_schema.str_schema()),
        )

    @classmethod
    def _validate(cls, value, info):
        """Cast ini string to a list of strings"""
        if isinstance(value, str):
            return [
                item.strip()
                for item in re.split(",(?![^{]*})", value.strip())
                if item != ""
            ]
        return value


# HACK https://stackoverflow.com/a/34116756
class ExpandedPath(type(pathlib.Path())):  # type: ignore
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema

        return core_schema.with_info_before_validator_function(
            cls._validate,
            core_schema.str_schema(),
        )

    @classmethod
    def _validate(cls, path, info):
        return os.path.expanduser(os.path.expandvars(path))


class LoggingPath(ExpandedPath):
    @classmethod
    def _validate(cls, path, info):
        expanded = super()._validate(path, info)
        return os.path.relpath(expanded)


class TaskrcPath(ExpandedPath):
    @classmethod
    def _validate(cls, path, info):
        expanded_path = super()._validate(os.path.normpath(path), info)
        if not os.path.isfile(expanded_path):
            raise OSError(f"Unable to find taskrc file at {expanded_path}.")
        return expanded_path

    @classmethod
    def default_factory(cls):
        """Mimic taskwarrior's logic (comments copied from taskwarrior)."""

        # Allow $TASKRC override.
        env_taskrc = os.getenv("TASKRC")
        if env_taskrc:
            return cls(env_taskrc)

        # Default to ~/.taskrc (ctor).
        taskrc = os.path.expanduser("~/.taskrc")
        if os.path.isfile(taskrc):
            return cls(taskrc)

        # If no ~/.taskrc, use $XDG_CONFIG_HOME/task/taskrc if exists, or
        # ~/.config/task/taskrc if $XDG_CONFIG_HOME is unset
        xdg_config_home = os.getenv("XDG_CONFIG_HOME")
        if xdg_config_home:
            xdg_config_taskrc = os.path.join(xdg_config_home, "task/taskrc")
            if os.path.isfile(xdg_config_taskrc):
                return cls(xdg_config_taskrc)
        else:
            dotconfig_taskrc = os.path.expanduser("~/.config/task/taskrc")
            if os.path.isfile(dotconfig_taskrc):
                return cls(dotconfig_taskrc)

        raise OSError("Unable to find taskrc file. (Try running `task`.)")


T = typing.TypeVar("T")


class UnsupportedOption(typing.Generic[T]):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema

        # Get the generic argument type
        if hasattr(source_type, "__args__") and source_type.__args__:
            inner_type = source_type.__args__[0]
        else:
            inner_type = typing.Any

        return core_schema.with_info_before_validator_function(
            cls._validate,
            handler.generate_schema(inner_type),
        )

    @classmethod
    def _validate(cls, v: T, info):
        if v:
            raise ValueError("Option is unsupported by service.")
        return v


class MainSectionConfig(BaseModel):
    """The :ref:`common_configuration:Main Section` configuration, plus computed attributes:"""

    model_config = pydantic.ConfigDict(
        frozen=True,  # config is faux-immutable
        extra="forbid",  # do not allow undeclared fields
        validate_default=True,  # validate default fields
        arbitrary_types_allowed=True,
    )

    # required
    targets: ConfigList

    # added during configuration loading
    #: Interactive status.
    interactive: bool

    # added during validation (computed field support will land in pydantic-2)
    #: Local data storage.
    data: typing.Optional[BugwarriorData] = None

    @model_validator(mode="before")
    @classmethod
    def compute_data(cls, values):
        if isinstance(values, dict) and "taskrc" in values:
            values["data"] = BugwarriorData(get_data_path(values["taskrc"]))
        return values

    # optional
    taskrc: TaskrcPath = Field(default_factory=TaskrcPath.default_factory)
    shorten: bool = False
    inline_links: bool = True
    annotation_links: bool = False
    annotation_comments: bool = True
    annotation_newlines: bool = False
    annotation_length: typing.Optional[int] = 45
    description_length: typing.Optional[int] = 35
    merge_annotations: bool = True
    merge_tags: bool = True
    replace_tags: bool = False
    static_tags: ConfigList = ConfigList([])
    static_fields: ConfigList = ConfigList(["priority"])
    reopen_completed_tasks: bool = True

    log_level: typing.Literal[
        "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "DISABLED"
    ] = "INFO"
    log_file: typing.Optional[LoggingPath] = None


class Hooks(BaseModel):
    pre_import: ConfigList = ConfigList([])


class Notifications(BaseModel):
    notifications: bool = False
    # Although upstream supports it, pydantic has problems with Literal[None].
    backend: typing.Optional[
        typing.Literal["gobject", "growlnotify", "applescript"]
    ] = None
    finished_querying_sticky: bool = True
    task_crud_sticky: bool = True
    only_on_new_tasks: bool = False


class SchemaBase(BaseSettings):
    model_config = pydantic.ConfigDict(
        extra="ignore"  # Allow extra top-level sections so all targets don't have to be selected.
    )

    hooks: Hooks = Hooks()
    notifications: Notifications = Notifications()


class ValidationErrorEnhancedMessages(list):
    """Methods adapted for pydantic v2."""

    def __init__(self, error: ValidationError):
        super().__init__(self.flatten(error))

    def __str__(self):
        return "\n".join(self)

    @staticmethod
    def display_error_loc(e):
        loc = e.get("loc", ())
        loc_len = len(loc)
        if loc_len == 1 or (loc_len > 1 and loc[1] == "__root__"):
            return f"[{loc[0]}]"
        elif loc_len == 2:
            return f"[{loc[0]}]\n{loc[1]}"
        raise ValueError(
            "Configuration should not be nested more than two layers deep."
        )

    def display_error(self, e):
        if e.get("type") == "extra_forbidden":
            e["msg"] = "unrecognized option"
        return f"{self.display_error_loc(e)}  <- {e.get('msg', 'Unknown error')}\n"

    def flatten(self, err):
        for error in err.errors():
            yield self.display_error(error)


def raise_validation_error(msg, config_path, no_errors=1):
    log.error(
        ("Validation error" if no_errors == 1 else f"{no_errors} validation errors")
        + f" found in {config_path}\n"
        f"See https://bugwarrior.readthedocs.io\n\n{msg}"
    )
    sys.exit(1)


def get_target_validator(targets):
    @model_validator(mode="before")
    @classmethod
    def compute_target(cls, values):
        if isinstance(values, dict):
            for target in targets:
                if target in values and isinstance(values[target], dict):
                    values[target]["target"] = target
        return values

    return compute_target


def validate_config(config: dict, main_section: str, config_path: str) -> dict:
    # Pre-validate the minimum requirements to build our pydantic models.
    try:
        main = config[main_section]
    except KeyError:
        raise_validation_error(f"No section: '{main_section}'", config_path)
    try:
        targets = ConfigList._validate(main["targets"], None)
    except KeyError:
        raise_validation_error(
            f"No option 'targets' in section: '{main_section}'", config_path
        )
    try:
        configmap = {target: config[target] for target in targets}
    except KeyError as e:
        raise_validation_error(f"No section: '{e.args[0]}'", config_path)
    servicemap = {}
    for target, serviceconfig in configmap.items():
        try:
            servicemap[target] = serviceconfig["service"]
        except KeyError:
            raise_validation_error(
                f"No option 'service' in section: '{target}'", config_path
            )

    # Construct Service Models
    target_schemas = {
        target: (get_service(service).CONFIG_SCHEMA, ...)
        for target, service in servicemap.items()
    }

    # Construct Validation Model
    fields = {
        "general": (MainSectionConfig, ...),
        **{
            flavor: (MainSectionConfig, ...)
            for flavor in config.get("flavor", {}).values()
        },
        **target_schemas,
    }

    # Create dynamic model with target validator
    # Use create_model to properly create the dynamic model with all fields
    model_fields = {}
    for name, field_info in fields.items():
        annotation, default = field_info
        model_fields[name] = (annotation, default)

    # Create a base class with the target validator logic
    class BugwarriorConfigModelBase(SchemaBase):
        model_config = pydantic.ConfigDict(**SchemaBase.model_config)

        # Apply the target validator logic directly
        @model_validator(mode="before")
        @classmethod
        def apply_target_validator(cls, values):
            if isinstance(values, dict):
                for target in targets:
                    if target in values and isinstance(values[target], dict):
                        values[target]["target"] = target
            return values

    # Create the dynamic model with all fields
    bugwarrior_config_model = create_model(
        "BugwarriorConfigModel", __base__=BugwarriorConfigModelBase, **model_fields
    )

    # Validate
    try:
        # Convert top-level model to dict since target names are dynamic and
        # a bunch of calls to getattr(config, target) inhibits readability.
        return dict(bugwarrior_config_model(**config))
    except ValidationError as e:
        errors = ValidationErrorEnhancedMessages(e)
        raise_validation_error(str(errors), config_path, no_errors=len(errors))


# Dynamically add template fields to model.
# Include standard taskwarrior fields plus common UDAs
_TEMPLATE_FIELDS = set(taskw_ng.task.Task.FIELDS.keys()) | {"area"}

# Use pydantic's create_model for dynamic fields
_ServiceConfig = create_model(
    "_ServiceConfig",
    **{
        f"{key}_template": (typing.Optional[str], Field(default=None))
        for key in _TEMPLATE_FIELDS
    },
)


class ServiceConfig(_ServiceConfig):  # type: ignore  # (dynamic base class)
    """Pydantic_ base class for service configurations.

    .. _Pydantic: https://docs.pydantic.dev/latest/
    """

    model_config = ConfigDict(
        frozen=True,  # config is faux-immutable
        extra="forbid",  # do not allow undeclared fields
        validate_default=True,  # validate default fields
    )

    # Added during validation (computed field support will land in pydantic-2)
    templates: dict = {}
    target: typing.Optional[str] = None

    # Optional fields shared by all services.
    only_if_assigned: str = ""
    also_unassigned: bool = False
    default_priority: typing.Literal["", "L", "M", "H"] = "M"
    add_tags: ConfigList = ConfigList([])
    static_fields: ConfigList = ConfigList([])

    @model_validator(mode="before")
    @classmethod
    def compute_templates(cls, values):
        """Get any defined templates for configuration values.

        Users can override the value of any Taskwarrior field using
        this feature on a per-key basis.  The key should be the name of
        the field to you would like to configure the value of, followed
        by '_template', and the value should be a Jinja template
        generating the field's value.  As context variables, all fields
        on the taskwarrior record are available.

        For example, to prefix the returned
        project name for tickets returned by a service with 'workproject_',
        you could add an entry reading:

            project_template = workproject_{{project}}

        Or, if you'd simply like to override the returned project name
        for all tickets incoming from a specific service, you could add
        an entry like:

            project_template = myprojectname

        The above would cause all issues to receive a project name
        of 'myprojectname', regardless of what the project name of the
        generated issue was.

        """
        if isinstance(values, dict):
            if "templates" not in values:
                values["templates"] = {}
            for key in _TEMPLATE_FIELDS:
                template = values.get(f"{key}_template")
                if template is not None:
                    values["templates"][key] = template
        return values

    @model_validator(mode="before")
    @classmethod
    def deprecate_filter_merge_requests(cls, values):
        if isinstance(values, dict) and hasattr(
            cls, "_DEPRECATE_FILTER_MERGE_REQUESTS"
        ):
            if values.get("filter_merge_requests") != "Undefined":
                if values.get("include_merge_requests") != "Undefined":
                    raise ValueError(
                        "filter_merge_requests and include_merge_requests are incompatible."
                    )
                values["include_merge_requests"] = not values["filter_merge_requests"]
                log.warning(
                    "filter_merge_requests is deprecated in favor of include_merge_requests"
                )
            elif values.get("include_merge_requests") == "Undefined":
                values["include_merge_requests"] = True
        return values

    @model_validator(mode="before")
    @classmethod
    def deprecate_project_name(cls, values):
        if isinstance(values, dict) and hasattr(cls, "_DEPRECATE_PROJECT_NAME"):
            if values.get("project_name", "") != "":
                log.warning("project_name is deprecated in favor of project_template")
        return values
