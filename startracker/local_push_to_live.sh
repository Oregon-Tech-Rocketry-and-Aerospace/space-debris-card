#!/bin/bash
# Small bash script to push current source code to live systemd service. Stops service, copies new files, then restarts service.

DIRECTORY=/usr/share/oresat-star-tracker/src
SERVICE=oresat-star-tracker.service

# Copies code to service directory.
push () {
    echo "Checking if $DIRECTORY exists..."
    if test -d "$DIRECTORY"; then
        echo "$DIRECTORY found."
        echo "Copying .py files to $DIRECTORY"
        cp *.py $DIRECTORY
        echo "Copy complete."
    fi
}

# Restarts systemd service to run new code.
run () {
    echo "Restarting systemd service."
    systemctl restart $SERVICE
    echo "Service started."
}

# Opens journalctl to see live service updates.
live () {
    echo "Starting journalctl live service monitoring..."
    journalctl -fu $SERVICE
}

# Call getopt to validate the provided input. 
options=$(getopt -o prl -- "$@")
[ $? -eq 0 ] || { 
    echo "Incorrect options provided"
    exit 1
}
eval set -- "$options"
while true; do
    case "$1" in
    -p)
        push
        ;;
    -r)
        run
        ;;
    -l)
        live
        ;;
    --)
        shift
        break
        ;;
    esac
    shift
done