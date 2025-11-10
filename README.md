```
██╗██████╗  ██████╗ ███╗   ██╗    ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗
██║██╔══██╗██╔═══██╗████╗  ██║    ██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║
██║██████╔╝██║   ██║██╔██╗ ██║    ███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║
██║██╔══██╗██║   ██║██║╚██╗██║    ╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║
██║██║  ██║╚██████╔╝██║ ╚████║    ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║
╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝    ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
```


-----

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)

## Installation

Use [hatch](https://hatch.pypa.io/dev/install/).


```console
hatch create env
hatch shell
```

or, if you prefer

```console
python3 -m venv venv
source venv/bin/activate
pip install -e .
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
./multi.sh
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
