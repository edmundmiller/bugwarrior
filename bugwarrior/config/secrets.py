import logging
import subprocess
import sys

log = logging.getLogger(__name__)

# Cache for oracle_eval results to avoid redundant command executions
# (e.g., calling 1password CLI 10 times for the same secret)
_oracle_cache: dict[str, str] = {}


def get_keyring():
    """Try to import and return optional keyring dependency."""
    try:
        import keyring
    except ImportError:
        raise ImportError(
            "Extra dependencies must be installed to use the keyring feature. "
            "Install them with `pip install bugwarrior[keyring]`."
        )
    return keyring


def get_service_password(service, username, oracle=None, interactive=False):
    """
    Retrieve the sensitive password for a service by:

      * retrieving password from a secure store (@oracle:use_keyring, default)
      * asking the password from the user (@oracle:ask_password, interactive)
      * executing a command and use the output as password
        (@oracle:eval:<command>)

    Note that the keyring may or may not be locked
    which requires that the user provides a password (interactive mode).

    :param service:     Service name, may be key into secure store (as string).
    :param username:    Username for the service (as string).
    :param oracle:      Hint which password oracle strategy to use.
    :return: Retrieved password (as string)

    .. seealso::
        https://bitbucket.org/kang/python-keyring-lib
    """
    import getpass

    password = None
    if not oracle or oracle == "@oracle:use_keyring":
        keyring = get_keyring()
        password = keyring.get_password(service, username)
        if interactive and password is None:
            # -- LEARNING MODE: Password is not stored in keyring yet.
            oracle = "@oracle:ask_password"
            password = get_service_password(service, username, oracle, interactive=True)
            if password:
                keyring.set_password(service, username, password)
        elif not interactive and password is None:
            log.error(
                "Unable to retrieve password from keyring. "
                "Re-run in interactive mode to set a password"
            )
    elif interactive and oracle == "@oracle:ask_password":
        prompt = "%s password: " % service
        password = getpass.getpass(prompt)
    elif oracle.startswith("@oracle:eval:"):
        command = oracle[13:]
        return oracle_eval(command)

    if password is None:
        log.critical(
            "MISSING PASSWORD: oracle='%s', interactive=%s for service=%s"
            % (oracle, interactive, service)
        )
        sys.exit(1)
    return password


def oracle_eval(command):
    """Retrieve password from the given command (cached).

    Results are cached by command string to avoid redundant executions.
    This is especially important for external password managers like
    1password CLI which can be slow and may prompt for authentication.
    """
    # Return cached result if available
    if command in _oracle_cache:
        log.debug(f"Using cached oracle result for command: {command[:20]}...")
        return _oracle_cache[command]

    p = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    p.wait()
    if p.returncode == 0:
        result = p.stdout.readline().strip().decode("utf-8")
        _oracle_cache[command] = result
        return result
    else:
        log.critical(
            "Error retrieving password: `{command}` returned '{error}'".format(
                command=command, error=p.stderr.read().strip()
            )
        )
        sys.exit(1)
