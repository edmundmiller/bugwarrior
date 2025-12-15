import getpass
import logging
import os
import sys
from typing import Optional

import typer
from lockfile import LockTimeout
from lockfile.pidlockfile import PIDLockFile
from typing_extensions import Annotated

from bugwarrior.collect import aggregate_issues, get_service
from bugwarrior.config import get_config_path, get_keyring, load_config
from bugwarrior.console import console, error, set_verbosity, warn
from bugwarrior.db import get_defined_udas_as_strings, synchronize

log = logging.getLogger(__name__)

# We overwrite 'list' further down.
lst = list

# Main CLI app
app = typer.Typer(
    help="Sync issues from forges to taskwarrior.",
    no_args_is_help=True,
)

# Vault subcommand group
vault_app = typer.Typer(
    help="Password/keyring management for bugwarrior.",
    no_args_is_help=True,
)
app.add_typer(vault_app, name="vault")


def _get_section_name(flavor: Optional[str]) -> str:
    if flavor:
        return "flavor." + flavor
    return "general"


def _try_load_config(main_section, interactive=False, quiet=False):
    try:
        return load_config(main_section, interactive, quiet)
    except OSError as e:
        error(f"Could not load configuration: {e}")
        console.print("[dim]Maybe you have not created a configuration file.[/dim]")
        sys.exit(1)


@app.command()
def pull(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Don't modify taskwarrior.")
    ] = False,
    flavor: Annotated[Optional[str], typer.Option(help="The flavor to use.")] = None,
    interactive: Annotated[
        bool, typer.Option(help="Prompt for missing credentials.")
    ] = False,
    debug: Annotated[
        bool, typer.Option(help="Disable multiprocessing (for debugging with pdb).")
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("-q", "--quiet", help="Suppress output except warnings/errors."),
    ] = False,
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Show per-task details.")
    ] = False,
):
    """Pull down tasks from forges and add them to your taskwarrior tasks."""
    # Set console verbosity before any output
    set_verbosity(quiet=quiet, verbose=verbose)

    main_section = _get_section_name(flavor)
    config = _try_load_config(main_section, interactive, quiet)

    lockfile_path = os.path.join(config[main_section].data.path, "bugwarrior.lockfile")
    try:
        lockfile = PIDLockFile(lockfile_path)
        lockfile.acquire(timeout=10)
        try:
            # Get all the issues. This can take a while.
            issue_generator = aggregate_issues(
                config, main_section, debug, quiet=quiet, verbose=verbose
            )

            # Stuff them in the taskwarrior db as necessary
            synchronize(
                issue_generator,
                config,
                main_section,
                dry_run,
                verbose=verbose or dry_run,
            )
        finally:
            lockfile.release()
    except LockTimeout:
        error(
            f"Your taskrc repository is currently locked. "
            f"Remove the file at {lockfile_path} if you are sure no other "
            f"bugwarrior processes are currently running."
        )
        sys.exit(1)
    except RuntimeError as e:
        error(f"Aborted: {e}")
        sys.exit(1)


def _get_keyring_targets():
    """Get targets that use keyring for passwords."""
    config = _try_load_config("general")
    for target in config["general"].targets:
        service_class = get_service(config[target].service)
        for value in [v for v in dict(config[target]).values() if isinstance(v, str)]:
            if "@oracle:use_keyring" in value:
                yield service_class.get_keyring_service(config[target])


@vault_app.command("list")
def vault_list():
    """List configured keyring targets."""
    pws = lst(_get_keyring_targets())
    print("%i @oracle:use_keyring passwords in bugwarriorrc" % len(pws))
    for section in pws:
        print("-", section)


@vault_app.command("clear")
def vault_clear(
    target: Annotated[str, typer.Argument(help="The target service name.")],
    username: Annotated[str, typer.Argument(help="The username.")],
):
    """Clear a password from the keyring."""
    target_list = lst(_get_keyring_targets())
    if target not in target_list:
        raise typer.BadParameter(f"{target} must be one of {target_list!r}")

    keyring = get_keyring()
    if keyring.get_password(target, username):
        keyring.delete_password(target, username)
        print(f"Password cleared for {target}, {username}")
    else:
        print(f"No password found for {target}, {username}")


@vault_app.command("set")
def vault_set(
    target: Annotated[str, typer.Argument(help="The target service name.")],
    username: Annotated[str, typer.Argument(help="The username.")],
):
    """Set a password in the keyring."""
    target_list = lst(_get_keyring_targets())
    if target not in target_list:
        warn(
            "You must configure the password to '@oracle:use_keyring' "
            "prior to setting the value."
        )
        raise typer.BadParameter(f"{target} must be one of {target_list!r}")

    keyring = get_keyring()
    keyring.set_password(target, username, getpass.getpass())
    print(f"Password set for {target}, {username}")


@app.command()
def uda(
    flavor: Annotated[Optional[str], typer.Option(help="The flavor to use.")] = None,
):
    """List bugwarrior-managed UDAs.

    Most services define a set of UDAs in which bugwarrior stores extra
    information about the incoming ticket. Usually, this includes things
    like the title of the ticket and its URL, but some services provide
    an extensive amount of metadata.

    For using this data in reports, it is recommended that you add these
    UDA definitions to your taskrc file.
    """
    main_section = _get_section_name(flavor)
    conf = _try_load_config(main_section)
    print("# Bugwarrior UDAs")
    for uda_line in get_defined_udas_as_strings(conf, main_section):
        print(uda_line)
    print("# END Bugwarrior UDAs")


@app.command()
def ini2toml(
    rcfile: Annotated[
        Optional[str], typer.Argument(help="Path to bugwarriorrc file to convert.")
    ] = None,
):
    """Convert ini bugwarriorrc to toml and print result to stdout."""
    if rcfile is None:
        rcfile = get_config_path()

    if not os.path.exists(rcfile):
        raise typer.BadParameter(f"File not found: {rcfile}")

    try:
        from ini2toml.api import Translator
    except ImportError:
        raise SystemExit(
            "Install extra dependencies to use this command:\n"
            "    pip install bugwarrior[ini2toml]"
        )
    if os.path.splitext(rcfile)[-1] == ".toml":
        raise SystemExit(f"{rcfile} is already toml!")
    with open(rcfile, "r") as f:
        bugwarriorrc = f.read()
    print(Translator().translate(bugwarriorrc, "bugwarriorrc"))


# For backward compatibility with legacy entry points (bugwarrior-pull, etc.)
# These are referenced in pyproject.toml [project.scripts]
# We need to expose these as module-level callables.


def _legacy_pull():
    """Legacy entry point for bugwarrior-pull."""
    import sys

    # Insert 'pull' as the command if not already specified
    if len(sys.argv) == 1 or sys.argv[1].startswith("-"):
        sys.argv.insert(1, "pull")
    app()


def _legacy_vault():
    """Legacy entry point for bugwarrior-vault."""
    vault_app()


def _legacy_uda():
    """Legacy entry point for bugwarrior-uda."""
    import sys

    # Insert 'uda' as the command if not already specified
    if len(sys.argv) == 1 or sys.argv[1].startswith("-"):
        sys.argv.insert(1, "uda")
    app()


# Create the main CLI function
def cli():
    """Main entry point."""
    app()
