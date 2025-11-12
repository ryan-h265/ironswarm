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
- [Docker](#docker)
- [Development](#development)
- [License](#license)


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

## Docker

Pull the latest image:
```bash
docker pull ghcr.io/ryan-h265/ironswarm:latest
```

Run the latest image:
```bash
docker run -it ghcr.io/ryan-h265/ironswarm:latest ironswarm -H local
```

#### Running with Custom Scenario Files

To run the container with your own scenario files, copy them into the running container:

1. Start the container with a name:
```bash
docker run -d --name ironswarm-node ghcr.io/ryan-h265/ironswarm:latest tail -f /dev/null
```

2. Copy your scenario file into the container:
```bash
docker cp examples/http_scenario.py ironswarm-node:/usr/src/app/http_scenario.py
```

3. Execute ironswarm with your scenario:
```bash
docker exec -it ironswarm-node ironswarm -j http_scenario:scenario -H local
```

4. Clean up when done:
```bash
docker stop ironswarm-node
docker rm ironswarm-node
```

## Development

Useful hatch commands
```console
hatch run types:check
hatch test --cover
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.