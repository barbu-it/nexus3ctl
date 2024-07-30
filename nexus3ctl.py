#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# pylint: disable=logging-fstring-interpolation
# pylint: disable=too-many-lines
# pylint: disable=too-many-public-methods
# pylint: disable=too-many-arguments
# pylint: disable=too-few-public-methods
# pylint: disable=too-many-instance-attributes

"""Nexus3Ctl CLI interface

This CLI provides a similar experience as the git CLI, but in Python with Typer.

Example:
``` py title="test.py"
from my_app.cli import cli_app

app = cli_app()
app.info()
app.apply()
```

This is a quite complete CLI template for your App, you will probably want
to remove 80% of this file.

To start, you need to replace the following strings:
* `Nexus3Ctl`
* `app`

When used with poetry:
```
[tool.poetry.scripts]
my_app = "my_app.cli:cli_run"
```

Author: Robin Cordier
License: GPLv3
"""

import glob
import json
import logging
import os
import re
import shutil
import sys
import traceback
from enum import Enum
from pathlib import Path
from pprint import pprint
from typing import Optional

# App libraries
import requests
import typer
import yaml
from requests.auth import HTTPBasicAuth

# Base Application example
# ===============================

logging.basicConfig(format="%(levelname)8s: %(message)s")
logger = logging.getLogger()
__version__ = "0.1.0"


# Base library
# ===============================


def write_to_file(filename, content, fmt=None, append_ext=True, dry=False):
    """
    Write content to a file.

    Args:
        filename: The name of the file to write to.
        content: The content to be written to the file.

    """

    # Manage file format
    if fmt is None:
        content = str(content)
    elif fmt == OutputFormat.JSON:
        content = json.dumps(content, indent=2)
        filename = f"{filename}.json" if append_ext else filename
    elif fmt == OutputFormat.YAML:
        content = yaml.dump(content)
        filename = f"{filename}.yaml" if append_ext else filename
    else:
        raise Nexus3CtlException(f"Unsupported format: {fmt}")

    # Save file content
    if not dry:
        # Create dest dir
        dest_dir = os.path.dirname(filename)
        if not os.path.isdir(dest_dir):
            os.makedirs(dest_dir)

        with open(filename, "w", encoding="utf-8") as file:
            file.write(content)

    return filename


def read_from_file(filename):
    """
    Read content from a file.

    Args:
        filename: The name of the file to read from.

    Returns:
        The content of the file as a string if successful, None otherwise.
    """
    with open(filename, "r", encoding="utf-8") as file:
        content = file.read()
    return content


class FakeResponse:
    "Object that mock a valid HTTP response"

    def __init__(self, status_code=200):
        "Instanciate response"

        self.status_code = status_code


class ExtendedEnum(Enum):
    "Extended Enum class that provide a list method"

    @classmethod
    def list(cls):
        "List all values"
        return list(map(lambda c: c.value, cls))


# Nexus3Ctl library
# ===============================


def limit_reduce(config, key="name", limits=None, sep=",", select=None):
    "Reduce a list of only allowed items"

    # Process args
    select = select or LimitSelect.EXACT
    limits = limits.split(sep) if isinstance(limits, str) else limits
    assert isinstance(config, list)

    # Return everything
    if not limits:
        return config

    # Return only requested items
    out = []
    for limit in limits:

        if select == LimitSelect.EXACT:
            matched = [item for item in config if item.get(key) == limit]
        elif select == LimitSelect.CONTAINS:
            matched = [item for item in config if limit in item.get(key)]
        elif select == LimitSelect.STARTSWITH:
            matched = [item for item in config if item.get(key).startswith(limit)]
        elif select == LimitSelect.ENDSWITH:
            matched = [item for item in config if item.get(key).endswith(limit)]
        elif select == LimitSelect.REGEX:
            matched = [item for item in config if re.match(limit, item.get(key))]
        else:
            choices = ",".join(LimitSelect.list())
            raise Nexus3CtlException(
                f"Unsupported mode '{select}', please choose one of: {choices}"
            )

        for match in matched:
            ident = match.get(key)
            existing = [item for item in out if item.get(key) == ident]
            if not existing:
                out.append(match)

    return out


def control_list(config, defaults=None, delim=",", default="ALL"):
    "Allow to add or remove elements in a given set. Support ALL and NONE keywords"

    # Prepare args
    defaults = defaults or []
    if isinstance(config, str):
        config = config.split(delim)
    assert isinstance(config, list), f"Expected a list, got: {config}"

    # Prepapre defaults
    if default is not None and default not in config:
        config.insert(0, default)

    # Build config
    out = []
    for conf in config:
        if not conf:
            continue
        name = conf
        action = "add"

        # Detect requested action
        if conf.startswith("-"):
            name = conf[1:]
            action = "remove"
        elif conf.startswith("+"):
            name = conf[1:]

        # Process action
        if conf == "ALL":
            out = defaults
        elif conf == "NONE":
            out = []
        elif action == "add":
            if name not in out:
                out.append(name)
        else:
            if name in out:
                out.remove(name)

    return list(set(out))


# Nexus3Ctl Classes
# ===============================


class Nexus3CtlException(Exception):
    """Generic Nexus3Ctl exception"""

    rc = 1


class ResourceTypes(str, ExtendedEnum):
    "Available resources types"

    REPOS = "repos"
    ROLES = "roles"
    LDAP = "ldap"
    REALMS = "realms"
    # USERS = "users"
    # PRIVILEGES = "privileges"
    # CONFIG = "config"


class Nexus3Ctl:
    "This is Nexus3Ctl Class"

    version = __version__
    name = "My Super App"

    # targets = ["repos", "ldap", "roles"]
    targets = ResourceTypes.list()

    def __init__(
        self,
        path,
        output_format="json",
        dry_mode=False,
        target_dir=None,
        nexus_url=None,
        nexus_user=None,
        nexus_pass=None,
    ):
        # Prepare object
        self.path = path
        self.target_dir = target_dir or os.path.join(path, "out")
        self.api_host = nexus_url
        self.api_url = f"{self.api_host}/service/rest/v1/"
        self.output_format = output_format
        self.dry_mode = dry_mode

        self.api_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        logger.debug(f"Nexus url: {self.api_url}")
        logger.debug(f"Nexus credentials: {nexus_user}, {nexus_pass}")
        self.api_auth = HTTPBasicAuth(nexus_user, nexus_pass)

        # Manage dry mode
        self.dry_mode_str = ""
        if self.dry_mode:
            logger.info("Dry mode enabled")
            self.dry_mode_str = " (dry-mode)"

    def clean_target_dir(self):
        "Remove and delete all files in target directory"

        if os.path.isdir(self.target_dir):
            if not self.dry_mode:
                shutil.rmtree(self.target_dir)

            logger.info(f"Cleaned target dir: {self.target_dir}{self.dry_mode_str}")

    # API Client
    # =======================

    def api_client(self, url_path, method="GET", data=None, dry=None):
        "Nexus client API helper"

        dry = dry if isinstance(dry, bool) else self.dry_mode
        common_kwargs = {
            "headers": self.api_headers,
            "auth": self.api_auth,
        }

        data = data if isinstance(data, str) else json.dumps(data)
        url = self.api_url + url_path
        tmout = 10

        logger.debug(f"API call: {method} {url}")

        out = None
        if dry:
            if method == "GET":
                out = requests.get(url, **common_kwargs, timeout=tmout)
            else:
                out = FakeResponse(status_code=200)
        else:

            if method == "PUT":
                out = requests.put(url, data=data, **common_kwargs, timeout=tmout)

            elif method == "POST":
                out = requests.post(url, data=data, **common_kwargs, timeout=tmout)

            elif method == "DELETE":
                out = requests.delete(url, **common_kwargs, timeout=tmout)

            elif method == "GET":
                out = requests.get(url, **common_kwargs, timeout=tmout)
            else:
                raise Nexus3CtlException(f"Unsupported HTTP method: {method}")

        if out.status_code == 401:
            pprint(common_kwargs)
            pprint(out.__dict__)
            msg = "Could not authenticate against API, got 401"
            raise Nexus3CtlException(msg)

        return out

    # Assets management
    # =======================

    nexus_default_roles = ["nx-admin", "nx-anonymous"]

    def nexus_remap_format(self, name):
        "Remap Nexus repos format to api name"
        if name == "maven2":
            return "maven"
        return name

    @staticmethod
    def nexus_sort_repos(file_name):
        "Sort helper to sort repository by dependencies: hosted>proxy>groups"
        ret = 3
        if "hosted" in file_name:
            ret =  1
        elif "proxy" in file_name:
            ret =  2
        return ret

    @staticmethod
    def nexus_sort_roles(item):
        "Sort helper to sort roles"
        roles = item.get("roles", [])
        privileges = item.get("privileges", [])
        return len(roles) * 3 + len(privileges)

    # Repos management
    # =======================

    def api_get_repos(self, limits=None, select=None):
        "List all repos"

        response = self.api_client("repositories")
        if response.status_code == 200:
            out = response.json()
            if limits:
                out = limit_reduce(out, key="name", limits=limits, select=select)
            return out
        return {}

    def api_get_repo(self, name, repo_format=None, repo_type=None):
        "Show one repo"

        # Automagic helper
        if not repo_format or not repo_type:
            response = self.api_client(f"repositories/{name}")
            if response.status_code == 200:
                payload = response.json()
                repo_format = payload["format"]
                repo_type = payload["type"]
            else:
                logger.debug(f"Repo does not exists: {name}")
                return {}

        # Remap format to API
        repo_format = self.nexus_remap_format(repo_format)

        # Return response
        response = self.api_client(f"repositories/{repo_format}/{repo_type}/{name}")
        if response.status_code == 200:
            return response.json()

        logger.debug(f"MISSING REPO: {name}")
        # pprint(response.__dict__)
        return {}

    def api_set_repo(self, config):
        "Set a repo from a dict config"

        config = dict(config)
        name = config["name"]
        current = self.api_get_repo(name)

        # Remap format to API
        config["format"] = self.nexus_remap_format(config["format"])
        if "url" in config:
            del config["url"]

        # Prepare payload
        _format = config["format"]
        _type = config["type"]

        if self.dry_mode:
            ret = (
                FakeResponse(status_code=204)
                if current
                else FakeResponse(status_code=201)
            )
        else:
            if current:
                # Update item
                ret = self.api_client(
                    f"repositories/{_format}/{_type}/{name}", method="PUT", data=config
                )
            else:
                # Create item
                ret = self.api_client(
                    f"repositories/{_format}/{_type}", method="POST", data=config
                )

        # Report status
        if ret.status_code == 201:
            logger.info(f"Repository created: {name}{self.dry_mode_str}")
        elif ret.status_code == 204:
            logger.info(f"Repository updated: {name}{self.dry_mode_str}")
        else:
            logger.warning(f"Failed to create repo: {name}")
            pprint(config)
            pprint(ret.__dict__)
            print("=" * 20)

    # Roles management
    # =======================
    def api_get_roles(
        self, exclude_ldap=False, exclude_default=False, limits=None, select=None
    ):
        "List all roles"

        response = self.api_client("security/roles")
        if response.status_code != 200:
            return {}

        # Filter out results
        out = response.json()
        if limits:
            out = limit_reduce(out, key="name", limits=limits, select=select)
        if exclude_default:
            out = [
                item for item in out if item.get("id") not in self.nexus_default_roles
            ]
        if exclude_ldap:
            out = [item for item in out if item.get("source") != "LDAP"]

        return out

    def api_get_role(self, ident):
        "Show one role"

        # Return response
        response = self.api_client(f"security/roles/{ident}")
        if response.status_code == 200:
            return response.json()

        logger.debug(f"MISSING ROLE: {ident}")
        # pprint(response.__dict__)
        return {}

    def api_set_role(self, config, ident=None):
        "Set a role from a dict config"

        config = dict(config)
        ident = ident or config["id"]
        current = self.api_get_role(ident)

        if self.dry_mode:
            ret = (
                FakeResponse(status_code=200)
                if current
                else FakeResponse(status_code=204)
            )
        else:
            if current:
                # Update item
                ret = self.api_client(
                    f"security/roles/{ident}", method="PUT", data=config
                )
            else:
                # Create item
                ret = self.api_client("security/roles", method="POST", data=config)

        # Report status
        if ret.status_code == 200:
            logger.info(f"Role created: {ident}{self.dry_mode_str}")
        elif ret.status_code == 204:
            logger.info(f"Role updated: {ident}{self.dry_mode_str}")
        else:
            logger.warning(f"Failed to create role: {ident}")
            pprint(config)
            pprint(ret.__dict__)
            print("=" * 20)

    # LDAP management
    # =======================
    def api_get_ldaps(self, limits=None, select=None):
        "List all ldap"

        response = self.api_client("security/ldap")
        if response.status_code == 200:
            out = response.json()
            if limits:
                out = limit_reduce(out, key="name", limits=limits, select=select)
            return out

        return {}

    def api_get_ldap(self, ident):
        "Show one ldap"

        # Return response
        response = self.api_client(f"security/ldap/{ident}")
        if response.status_code == 200:
            return response.json()

        logger.debug(f"MISSING ROLE: {ident}")
        return {}

    def api_set_ldap(self, config, name=None):
        "Set a ldap from a dict config"

        config = dict(config)
        ident = name or config["name"]
        current = self.api_get_ldap(ident)

        if self.dry_mode:
            ret = (
                FakeResponse(status_code=204)
                if current
                else FakeResponse(status_code=201)
            )
        else:

            if current:
                # Update item
                ret = FakeResponse(status_code=204)
                # print (f"LDAP endpoint does not support updates for: {ident}")
                # return
                # ret = self.api_client(
                #     f"security/ldap/{ident}", method="PUT", data=config
                # )
            else:
                # Create item
                ret = self.api_client("security/ldap", method="POST", data=config)

        # Report status
        if ret.status_code == 201:
            logger.info(f"Ldap created: {ident}{self.dry_mode_str}")
        elif ret.status_code == 204:
            logger.info(
                f"LDAP endpoint does not support updates for: {ident}{self.dry_mode_str}"
            )
        else:
            logger.info(f"Failed to create ldap: {ident}")
            print("=" * 20)
            pprint(config)
            print("=" * 20)
            pprint(ret.__dict__)
            print("=" * 20)

    # Realms management
    # =======================
    def api_get_realms(self, limits=None, select=None):
        "List all realm"

        response = self.api_client("security/realms/active")
        if response.status_code == 200:
            out = response.json()
            if limits:
                out = limit_reduce(out, key="name", limits=limits, select=select)
            return out

        return {}

    def api_set_realms(self, config):
        "Set all realm"

        config = list(config)

        if self.dry_mode:
            ret = FakeResponse(status_code=200)
        else:
            ret = self.api_client("security/realms/active", method="PUT", data=config)

        # Report status
        if ret.status_code == 204:
            logger.info(f"Realms updated: {','.join(config)}{self.dry_mode_str}")
        else:
            logger.warning(f"Failed to create realms: {','.join(config)}")
            pprint(config)
            pprint(ret.__dict__)
            print("=" * 20)

    # Repo - CLI Interface
    # =======================

    # Realms
    # ------------
    def cli_export_realms(self, limits=None, select=None):
        "Export realm"

        items = self.api_get_realms(limits=limits, select=select)
        pprint(items)

        dest = os.path.join(self.target_dir, "conf", "realms")
        filename = write_to_file(dest, items, fmt=self.output_format, dry=self.dry_mode)
        logger.info(f"Export realms in: {filename}{self.dry_mode_str}")

    def cli_import_realms(self):
        "Import realm"

        # Load json files
        files = glob.glob(f"{self.target_dir}/conf/realms.*")
        if len(files) < 1:
            return

        file = files[0]
        realms = json.load(open(file, encoding="utf-8"))

        # logger.info(f"Importing realms config: {','.join(realms)}")
        self.api_set_realms(realms)

    # Ldaps
    # ------------
    def cli_export_ldap(self, limits=None, select=None):
        "Export ldap"

        items = self.api_get_ldaps(limits=limits, select=select)

        logger.info(f"Exporting {len(items)} ldap(s) ...")
        for item in items:

            name = item["name"]
            dest = os.path.join(self.target_dir, "ldap", name)
            filename = write_to_file(
                dest, item, fmt=self.output_format, dry=self.dry_mode
            )
            logger.info(f"Export ldap: {name} in {filename}{self.dry_mode_str}")

    def cli_import_ldap(self, limits=None, select=None):
        "Import ldap"

        # Load json files
        files = glob.glob(f"{self.target_dir}/ldap/*.json")
        ldaps = [json.load(open(file, encoding="utf-8")) for file in files]

        logger.info(f"Importing {len(ldaps)} ldap(s) ...")
        for ldap in ldaps:
            # Read payload and create/update via API
            self.api_set_ldap(ldap)

    # Roles
    # ------------
    def cli_export_roles(self, limits=None, select=None):
        "Export roles"

        items = self.api_get_roles(
            exclude_ldap=True, exclude_default=True, limits=limits, select=select
        )
        # items = limit_reduce(items, key="name", limits=limits, select=select)

        logger.info(f"Exporting {len(items)} role(s) ...")
        for item in items:

            name = item["name"]
            dest = os.path.join(self.target_dir, "roles", name)
            filename = write_to_file(
                dest, item, fmt=self.output_format, dry=self.dry_mode
            )
            logger.info(f"Export role: {name} in {filename}{self.dry_mode_str}")

    def cli_import_roles(self, limits=None, select=None):
        "Import roles"

        # Load json files
        files = glob.glob(f"{self.target_dir}/roles/*.json")

        # Sort and filter
        items = [json.load(open(file, encoding="utf-8")) for file in files]
        items = sorted(items, key=self.nexus_sort_roles)

        logger.info(f"Importing {len(items)} role(s) ...")
        for role in items:
            # Read payload and create/update via API
            self.api_set_role(role)

    # Repos
    # ------------
    def cli_export_repos(self, limits=None, select=None):
        "Export repositories"

        items = self.api_get_repos(limits=limits, select=select)

        logger.info(f"Exporting {len(items)} repo(s) ...")
        for repo in items:

            # Prepare vars
            name = repo["name"]
            repo_format = repo["format"]
            repo_type = repo["type"]
            dest = os.path.join(
                self.target_dir, "repos", f"{repo_format}-{repo_type}__{name}"
            )

            # # Skip limits
            # if limits:
            #     matches = [ name for limit in limits if name in limit]
            #     if not matches:
            #         logger.debug(f"Skip repo: {name}")
            #         continue

            # Fetch payload
            payload = self.api_get_repo(
                name, repo_format=repo_format, repo_type=repo_type
            )

            # Write to file
            assert isinstance(payload, dict)

            filename = write_to_file(
                dest, payload, fmt=self.output_format, dry=self.dry_mode
            )
            logger.info(f"Export repo: {name} in {filename}{self.dry_mode_str}")

    def cli_import_repos(self, limits=None, select=None):
        "Import repositories"

        files = glob.glob(f"{self.target_dir}/repos/*.json")
        # Sort types by: hosted>proxy>groups
        files = sorted(files, key=self.nexus_sort_repos)

        logger.info(f"Importing {len(files)} repo(s) ...")

        for file in files:
            # Read payload and create/update via API
            repo = json.load(open(file, encoding="utf-8"))
            self.api_set_repo(repo)


class OutputFormat(str, ExtendedEnum):
    "Available output formats"

    YAML = "yaml"
    JSON = "json"
    PYTHON = "python"
    # TOML = "toml"


class LimitSelect(str, ExtendedEnum):
    "Available limit selectors"

    EXACT = "exact"
    CONTAINS = "contains"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"
    REGEX = "regex"


# Core application definition
# ===============================

# Define Typer application
# -------------------
cli_app = typer.Typer(
    help="Nexus3Ctl, manage Nexus configurations",
    invoke_without_command=True,
    no_args_is_help=True,
    add_completion=True,

    context_settings={
        "help_option_names": ["-h", "--help"]
        },
)


# Define an init function, with common options
# -------------------
@cli_app.callback()
# pylint: disable=too-many-arguments
def main(
    ctx: typer.Context,
    verbose: int = typer.Option(
        0, "--verbose", "-v", count=True, min=0, max=3, 
        help="Increase verbosity",
        envvar="NEXUS3_VERBOSITY",
    ),
    working_dir: Path = typer.Option(
        ".",  # For relative paths
        # os.getcwd(),  # For abolute Paths
        "-c",
        "--config",
        help="Path of app.yml configuration file or directory.",
        envvar="NEXUS3_PROJECT_DIR",
    ),
    target: Path = typer.Option(
        "./out",
        "-d",
        "--target-dir",
        help="Directory to read or write Nexus resources",
        envvar="NEXUS3_TARGET_DIR",
    ),
    # pylint: disable=redefined-builtin
    format: OutputFormat = typer.Option(
        OutputFormat.JSON.value,
        "--format",
        "-m",
        help="Output format",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version",
    ),
    dry: bool = typer.Option(
        False,
        "--dry",
        "-n",
        help="Run in dry mode",
        envvar="NEXUS3_DRY",
    ),
    nexus_url: str = typer.Option(
        "-l",
        "--url",
        help="Nexus3 domain.",
        envvar="NEXUS3_URL",
    ),
    nexus_user: str = typer.Option(
        "-u",
        "--user",
        help="Nexus3 username.",
        envvar="NEXUS3_USERNAME",
    ),
    nexus_pass: str = typer.Option(
        "-p",
        "--pass",
        help="Nexus3 password.",
        envvar="NEXUS3_PASSWORD",
    ),
):
    """
    Nexus3Ctl Command Line Interface.
    """

    # Set logging level
    # -------------------
    # 50: Crit
    # 40: Err
    # 30: Warn
    # 20: Info
    # 10: Debug
    # 0: Not set
    verbose = verbose + 1
    # pylint: disable=redefined-outer-name
    logger = logging.getLogger(None if verbose >= 3 else __package__)
    verbose = 30 - (verbose * 10)
    verbose = verbose if verbose > 10 else logging.DEBUG
    logger.setLevel(level=verbose)

    # Init app
    # -------------------
    if version:
        print(__version__)
        return

    ctx.obj = {
        "app": Nexus3Ctl(
            working_dir,
            target_dir=target,
            output_format=format,
            dry_mode=dry,
            nexus_url=nexus_url,
            nexus_user=nexus_user,
            nexus_pass=nexus_pass,
        ),
    }


# Simple commands example
# ===============================


@cli_app.command("help")
def cli_help(
    ctx: typer.Context,
):
    """Show this help message"""
    print(ctx.parent.get_help())


@cli_app.command("ls")
def cli_ls(
    ctx: typer.Context,
    # pylint: disable=redefined-builtin
    all: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show item content",
    ),
    types: Optional[str] = typer.Option(
        "ALL",
        "--types",
        "-t",
        help="Add or remove types from list, comma separated.",
        metavar=f"[{','.join(ResourceTypes.list())}]",
    ),
    limits: Optional[str] = typer.Option(
        "",
        "--limit",
        "-l",
        help="Add or remove objects from list, accept coma separated values",
        metavar="RULE[,RULES...]",
    ),
    select: LimitSelect = typer.Option(
        LimitSelect.EXACT,
        "--select",
        "-s",
        help="How resources are limited",
        case_sensitive=False,
    ),
):
    """List all resources"""
    app = ctx.obj["app"]

    _types = control_list(types, defaults=app.targets, default="NONE")

    # Append selected items
    out = {}
    if "repos" in _types:
        out["repos"] = app.api_get_repos(limits=limits, select=select)

    if "ldap" in _types:
        out["ldap"] = app.api_get_ldaps(limits=limits, select=select)

    if "roles" in _types:
        out["roles"] = app.api_get_roles(limits=limits, select=select)

    if "realms" in _types:
        out["realms"] = app.api_get_realms(limits=limits, select=select)

    # Reduce output
    if not all:
        for key, val in out.items():

            out[key] = [
                item["name"] if isinstance(item, dict) else item for item in val
            ]

    # Reformat output
    fmt = app.output_format
    if fmt == OutputFormat.PYTHON:
        pprint(out)
    elif fmt == OutputFormat.JSON:
        print(json.dumps(out, indent=2))
    elif fmt == OutputFormat.YAML:
        print(yaml.dump(out))
    else:
        raise Nexus3CtlException(f"Unsupported format: {fmt}")


@cli_app.command("export")
def cli_export(
    ctx: typer.Context,
    types: Optional[str] = typer.Option(
        "ALL",
        "--types",
        "-t",
        help="Add or remove types from list, comma separated.",
        metavar=f"[{','.join(ResourceTypes.list())}]",
    ),
    limits: Optional[str] = typer.Option(
        "",
        "--limit",
        "-l",
        help="Add or remove objects from list, accept coma separated values",
        metavar="RULE[,RULES...]",
    ),
    select: LimitSelect = typer.Option(
        LimitSelect.EXACT, help="How resources are limited", case_sensitive=False
    ),
    clean: bool = typer.Option(
        False,
        "--clean",
        help="Remove existing files in target dir",
    ),
    # mode: Optional[str] = typer.Option(
    #     "Default Mode",
    #     help="Write anything here",
    # ),
):
    """Export configuration"""
    app = ctx.obj["app"]

    _types = control_list(types, defaults=app.targets, default="NONE")
    pprint(_types)
    if clean:
        app.clean_target_dir()

    if ResourceTypes.REPOS in _types:
        app.cli_export_repos(limits=limits, select=select)

    if ResourceTypes.LDAP in _types:
        app.cli_export_ldap(limits=limits, select=select)

    if ResourceTypes.ROLES in _types:
        app.cli_export_roles(limits=limits, select=select)

    if ResourceTypes.REALMS in _types:
        app.cli_export_realms(limits=limits, select=select)


@cli_app.command("import")
def cli_import(
    ctx: typer.Context,
    types: Optional[str] = typer.Option(
        "ALL",
        "--types",
        "-t",
        help="Add or remove types from list, comma separated.",
        metavar=f"[{','.join(ResourceTypes.list())}]",
    ),
    limits: Optional[str] = typer.Option(
        "",
        "--limit",
        "-l",
        help="Add or remove objects from list, accept coma separated values",
        metavar="RULE[,RULES...]",
    ),
    select: LimitSelect = typer.Option(
        LimitSelect.EXACT, help="How resources are limited", case_sensitive=False
    ),
):
    """Import configuration"""
    app = ctx.obj["app"]

    _types = control_list(types, defaults=app.targets, default="ALL")

    if ResourceTypes.REPOS in _types:
        app.cli_import_repos(limits=limits, select=select)

    if ResourceTypes.LDAP in _types:
        app.cli_import_ldap(limits=limits, select=select)

    if ResourceTypes.ROLES in _types:
        app.cli_import_roles(limits=limits, select=select)

    if ResourceTypes.REALMS in _types:
        app.cli_import_realms()


# Exception handler
# ===============================
def clean_terminate(err):
    "Terminate nicely the program depending the exception"

    user_errors = (
        PermissionError,
        FileExistsError,
        FileNotFoundError,
        InterruptedError,
        IsADirectoryError,
        NotADirectoryError,
        TimeoutError,
    ) + (
        Nexus3CtlException,
        # NodeCoreUserException,
        # yaml.parser.ParserError,
        # sh.ErrorReturnCode,
    )

    if isinstance(err, user_errors):

        # Fetch extra error informations
        rc = int(getattr(err, "rc", getattr(err, "errno", 1)))
        advice = getattr(err, "advice", None)
        if advice:
            logger.warning(advice)

        # Log error and exit
        logger.error(err)
        err_name = err.__class__.__name__
        logger.critical("Nexus3Ctl exited with error %s (%s)", err_name, rc)
        sys.exit(rc)

    # Developper bug catchall
    rc = 255
    logger.error(traceback.format_exc())
    logger.critical("Uncatched error: %s", err.__class__)
    logger.critical("This is a bug, please report it.")
    sys.exit(rc)


# Core application definition
# ===============================


# pylint: disable=inconsistent-return-statements
def cli_run():
    "Return a Nexus3Ctl App instance"
    app = None
    try:
        app = cli_app()
    # pylint: disable=broad-except
    except Exception as err:
        clean_terminate(err)
    return app


if __name__ == "__main__":
    cli_run()
