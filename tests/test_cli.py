from unittest.mock import MagicMock, patch

from ironswarm import parse_arguments


@patch("argparse.ArgumentParser.parse_args")
def test_parse_arguments(mock_parse_args):
    mock_args = MagicMock()
    mock_args.bootstrap = "tcp://node1:42042,tcp://node2:42043"
    mock_args.host = "localhost"
    mock_args.port = 42042
    mock_args.job = "test:job"
    mock_args.verbose = True
    mock_args.log_file = "test.log"
    mock_parse_args.return_value = mock_args

    args = parse_arguments()
    assert args.bootstrap == "tcp://node1:42042,tcp://node2:42043"
    assert args.host == "localhost"
    assert args.port == 42042
    assert args.job == "test:job"
    assert args.verbose is True
    assert args.log_file == "test.log"
