```
██╗██████╗  ██████╗ ███╗   ██╗    ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗
██║██╔══██╗██╔═══██╗████╗  ██║    ██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║
██║██████╔╝██║   ██║██╔██╗ ██║    ███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║
██║██╔══██╗██║   ██║██║╚██╗██║    ╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║
██║██║  ██║╚██████╔╝██║ ╚████║    ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║
╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝    ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
```

[![Tests](https://github.com/ryan-h265/ironswarm/actions/workflows/test.yml/badge.svg)](https://github.com/ryan-h265/ironswarm/actions/workflows/test.yml)
[![Docker Build](https://github.com/ryan-h265/ironswarm/actions/workflows/docker.yml/badge.svg)](https://github.com/ryan-h265/ironswarm/actions/workflows/docker.yml)
[![PyPI version](https://badge.fury.io/py/ironswarm.svg)](https://badge.fury.io/py/ironswarm)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

-----

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)

## Installation

```console
pip install ironswarm
```

## Usage

```
usage: ironswarm [-h] [-b BOOTSTRAP] [-H HOST] [-p PORT] [-j JOB] [-v | --verbose | --no-verbose] [--log-file LOG_FILE]

options:
  -h, --help            show this help message and exit
  -b, --bootstrap BOOTSTRAP
                        bootstrap node(s) to initially connect to
  -H, --host HOST       network interface to bind to local/public or IP address (default: public)
  -p, --port PORT       port to bind to (default: 42042)
  -j, --job JOB         job to run (default: None)
  -v, --verbose, --no-verbose
                        enable verbose logging
  --log-file LOG_FILE   Optional path to write logs to a file.
```


Run a single node with no bootstrap
```bash
ironswarm -H local
```

Run multiple nodes in a tmux session
```bash
./example/multi.sh
```

Run a single node bootstrapping to another node
```bash
ironswarm -H local -b tcp://127.0.0.1:42042
```


## Development

Useful hatch commands
```console
hatch run types:check
hatch test --cover
```

## CI/CD

This project uses GitHub Actions for automated testing, Docker builds, and releases.

### Automated Testing

Tests run automatically on every push and pull request to all branches:
- Tests execute on Python 3.10, 3.11, and 3.12
- Coverage reports upload to Codecov
- Type checking with mypy
- Code formatting checks with Ruff

### Docker Builds

Docker images build automatically and publish to GitHub Container Registry (ghcr.io):
- **On push to master/main**: Builds and pushes with `latest` tag
- **On version tags (v*)**: Builds and pushes with semantic version tags (e.g., `1.2.3`, `1.2`, `1`)
- **Multi-platform**: Supports both `linux/amd64` and `linux/arm64`
- **Pull requests**: Builds only (no push) to validate Dockerfile

Pull the latest image:
```bash
docker pull ghcr.io/ryan-h265/ironswarm:latest
```

### Publishing Releases

Releases to PyPI are automated using [trusted publishing](https://docs.pypi.org/trusted-publishers/) (no API tokens required):

1. **Create a new release on GitHub** with a version tag (e.g., `v1.2.3`)
2. The release workflow automatically:
   - Builds the package with Hatch
   - Validates the distribution with twine
   - Publishes to PyPI using OIDC authentication

**Test releases**: You can manually trigger the release workflow and enable the "test-pypi" option to publish to TestPyPI for validation.

### Dependabot

Automated dependency updates run weekly for:
- GitHub Actions (workflow dependencies)
- Python packages (pip dependencies)

Updates create pull requests automatically with grouped test dependencies to reduce PR noise.
