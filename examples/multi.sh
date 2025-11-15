#!/bin/bash

SESSION="multiinput"
APP_CMD="ironswarm -s"
JOB_ARG="-j http_scenario:scenario"
# JOB_ARG=""
HOST_ARG="-H local"
BIND_ARG="-b tcp://127.0.0.1:42042"

# Create the tmux session and first window (window 0)
tmux new-session -d -s "$SESSION" -n "win0"

# Launch the first process in window 0
tmux send-keys -t "$SESSION:0.0" "$APP_CMD $HOST_ARG $JOB_ARG --web-port 8081" Enter

sleep 1.0

for i in {1..4}; do
  tmux split-window -t "$SESSION:0" -c "#{pane_current_path}" "$APP_CMD $HOST_ARG $BIND_ARG"
  tmux select-layout -t "$SESSION:0" tiled
done

tmux setw -t "$SESSION:0" synchronize-panes on

# Enable mouse support
tmux set -t "$SESSION" mouse on

# Attach to the session
tmux attach -t "$SESSION"
