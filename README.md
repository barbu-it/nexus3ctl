# Nexus3 Config Export/Import

Simple tool to import, export, backup or provision nexus3 instances.


Overview:

- [Nexus3 Config Export/Import](#nexus3-config-exportimport)
  - [Quickstart](#quickstart)
  - [Usage](#usage)
  - [Import and Exports](#import-and-exports)
    - [Export command](#export-command)
    - [Import command](#import-command)
  - [Help usage](#help-usage)
  - [Informations](#informations)



## Quickstart

Install script dependencies:
```
pip install git+https://github.com/barbu-it/nexus3ctl
```

Check it is correctly installed
```
$ nexus3ctl --version
0.1.0
```

Configure credentials:
```
export NEXUS3_URL=https://my-nexus.example.org
export NEXUS3_USERNAME=USER
export NEXUS3_PASSWORD=MYPASS
```
Note it is also possible to use `--user`, '--pass' and `--url` directly from the command line.


## Usage

To see what's on server:
```
nexus3ctl ls
nexus3ctl ls -a
```

You can filter output by types:
```
nexus3ctl ls --types roles,ldap
```

List specific resources by exact names:
```
./nexus3ctl ls --types ldap -l pattern
```

List specific resources with other selectors:
```
nexus3ctl ls --types repos,roles -l prod -s contains
nexus3ctl ls --types repos -l dev,prod -s endswith
nexus3ctl ls --types repos -l 'pattern1,pattern2,p.t{2}.rn[3-9]' -s regex
```

All those options are available for `import` and `export` commands.


## Import and Exports

The import/export process relies on a file hierrarchy, there is an example of an instance export:
```
out/
|-- conf
|   `-- realms.json
|-- ldap
|   |-- Org-ldap01.json
|   `-- Org-ldap02.json
|-- repos
|   |-- docker-group__container-all.json
|   |-- go-proxy__go-proxy.golang.org.json
|   |-- maven2-group__maven-all.json
|   |-- maven2-hosted__maven-dev.json
|   |-- maven2-hosted__maven-legacy.json
|   |-- maven2-hosted__maven-prod.json
|   |-- npm-group__npm-all.json
|   |-- npm-hosted__npm-prod.json
|   |-- npm-proxy__npm-js.org.json
|   |-- raw-hosted__raw-prod.json
|   |-- yum-group__yum-all.json
|   |-- yum-hosted__yum-prod.json
|   `-- yum-proxy__yum-epel.json
`-- roles
    |-- Domain\ Users.json
    |-- ForJenkins.json
    `-- NexusAdmins.json
```

You can store those files in a git repository. This would allow you to track configuration drift.

### Export command

To run an export:
```
nexus3ctl export
```
A default `out` directory will be created, with all resources in it.

Export specific types:
```
nexus3ctl export --types ldap,roles,repos
```

Export to another dir, or run a backup:
```
nexus3ctl -d backup_$(date --iso-8601) export
```

### Import command

As simple as this:
```
# Test in dry mode first
nexus3ctl -d ../other_instance/out -n import

# Run the import
nexus3ctl -d ../other_instance/out import
```
Like export, you can use `--types`, `--limit` and `--select` options.

### Work with many instances

With the help of (direnv](https://direnv.net/), you can create a folder structure like:
```
instances/
|-- dev-nexus.localhost
|   `-- .envrc
|-- nexus.company.org
|   `-- .envrc
`-- nexus02.company.org
|   `-- .envrc
```

You should adapt the content of the `.envrc` file according each instances, like `instances/dev-nexus.localhost/.envrc`:
```
# Direnv support
source_up_if_exists 2>/dev/null || true

export NEXUS3_URL=https://local-dev-nexus.localhost
export NEXUS3_USERNAME=admin
export NEXUS3_PASSWORD=admin
```

Then cd into the instance you want to get, all credentials should be loaded in your shell session.


## Help usage

Show full usage:
```
$ nexus3ctl --help

 Usage: nexus3ctl [OPTIONS] COMMAND [ARGS]...

 Nexus3Ctl, manage Nexus configurations

╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --verbose             -v      INTEGER RANGE [0<=x<=3]  Increase verbosity [default: 0]           │
│ --config              -c      PATH                     Path of myapp.yml configuration file or   │
│                                                        directory.                                │
│                                                        [env var: MYAPP_PROJECT_DIR]              │
│                                                        [default: .]                              │
│ --target-dir          -d      PATH                     Directory to read or write Nexus          │
│                                                        resources                                 │
│                                                        [env var: MYAPP_TARGET_DIR]               │
│                                                        [default: ./out]                          │
│ --format              -m      [yaml|json|python]       Output format [default: json]             │
│ --version             -V                               Show version                              │
│ --dry                 -n                               Run in dry mode                           │
│ --url                         TEXT                     Nexus3 domain. [env var: NEXUS3_URL]      │
│                                                        [default: -l]                             │
│ --user                        TEXT                     Nexus3 username.                          │
│                                                        [env var: NEXUS3_USERNAME]                │
│                                                        [default: -u]                             │
│ --pass                        TEXT                     Nexus3 password.                          │
│                                                        [env var: NEXUS3_PASSWORD]                │
│                                                        [default: -p]                             │
│ --install-completion                                   Install completion for the current shell. │
│ --show-completion                                      Show completion for the current shell, to │
│                                                        copy it or customize the installation.    │
│ --help                                                 Show this message and exit.               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ export   Export configuration                                                                    │
│ help     Show this help message                                                                  │
│ import   Import configuration                                                                    │
│ ls       List all resources                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## Develop

Follow this procedure:
```
git clone https://github.com/barbu-it/nexus3ctl.git nexus3ctl_dev
cd nexus3ctl_dev
python -m venv .venv
. .venv/bin/activate
pip install -e .
```


## Informations

Limitation:

* App lacks of some extensive testing
* There is only limited support for: repositories,roles,ldap and realms


License:

```
GPL - rcordier - Stratacache.com - 2024
```

