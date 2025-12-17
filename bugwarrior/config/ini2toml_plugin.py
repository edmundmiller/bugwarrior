import importlib
import inspect
import logging
import re
import typing

from ini2toml.types import IntermediateRepr, Translator
import pydantic
from pydantic import BaseModel, ValidationError

from .schema import ConfigList, Hooks, MainSectionConfig, Notifications, ServiceConfig

log = logging.getLogger(__name__)


def to_type(section: IntermediateRepr, key: str, converter: typing.Callable):
    try:
        val = section[key]
    except KeyError:
        pass
    else:
        section[key] = converter(val)


class BooleanModel(BaseModel):
    """
    Use Pydantic to convert various strings to booleans.

    "True", "False", "yes", "no", etc.
    Adapted from https://docs.pydantic.dev/usage/types/#booleans
    """

    bool_value: bool


def to_bool(section: IntermediateRepr, key: str):
    to_type(section, key, lambda val: BooleanModel(bool_value=val).bool_value)


def to_int(section: IntermediateRepr, key: str):
    to_type(section, key, int)


def to_list(section: IntermediateRepr, key: str):
    # For v2, use a lambda that calls the validator correctly
    to_type(section, key, lambda val: ConfigList._validate(val, None))


def convert_section(section: IntermediateRepr, schema_class: type[BaseModel]):
    # For v2, use model_fields to introspect field types
    for prop, field_info in schema_class.model_fields.items():
        attrs = {"type": "string"}  # default fallback
        # Try to determine type from annotation
        if hasattr(field_info, "annotation"):
            annotation = field_info.annotation
            if annotation == bool:
                attrs = {"type": "boolean"}
            elif annotation == int:
                attrs = {"type": "integer"}
            elif (
                hasattr(annotation, "__origin__")
                and getattr(annotation, "__origin__", None) == list
            ):
                attrs = {"type": "array"}
        try:
            t = attrs["type"]
        except KeyError:
            pass  # optional
        else:
            if t == "boolean":
                to_bool(section, prop)
            elif t == "integer":
                to_int(section, prop)
            elif t == "array":
                to_list(section, prop)


def process_values(doc: IntermediateRepr) -> IntermediateRepr:
    for name, section in doc.items():
        if isinstance(name, str):
            if name == "general" or re.match(r"^flavor\.", name):
                convert_section(section, MainSectionConfig)
                for k in ["log.level", "log.file"]:
                    if k in section:
                        section.rename(k, k.replace(".", "_"))
            elif name == "hooks":
                convert_section(section, Hooks)
            elif name == "notifications":
                convert_section(section, Notifications)
            else:  # services
                service = section["service"]

                # Validate and strip prefixes.
                for key in section.keys():
                    if isinstance(key, str) and key != "service":
                        prefix = "ado" if service == "azuredevops" else service
                        newkey, subs = re.subn(f"^{prefix}\\.", "", key)
                        if subs != 1:
                            option = key.split(".").pop()
                            log.warning(
                                f"[{name}]\n{key} <-expected prefix "
                                f"'{prefix}': did you mean "
                                f"'{prefix}.{option}'?"
                            )
                        section.rename(key, newkey)

                # Get Config
                module_name = {"bugzilla": "bz", "phabricator": "phab"}.get(
                    service, service
                )
                service_module = importlib.import_module(
                    f"bugwarrior.services.{module_name}"
                )
                for name, obj in inspect.getmembers(
                    service_module, predicate=inspect.isclass
                ):
                    if issubclass(obj, ServiceConfig):
                        schema = obj
                        break
                else:
                    raise ValueError(
                        f"ServiceConfig class not found in {service} module."
                    )

                # Convert Types
                convert_section(section, schema)
                if service == "gitlab" and "verify_ssl" in section.keys():
                    try:
                        to_bool(section, "verify_ssl")
                    except ValidationError:
                        # verify_ssl is allowed to be a path
                        pass

    return doc


def activate(translator: Translator):
    profile = translator["bugwarriorrc"]
    profile.description = "Convert 'bugwarriorrc' files to 'bugwarrior.toml'"
    profile.intermediate_processors.append(process_values)
