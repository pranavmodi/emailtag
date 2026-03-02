#!/bin/bash

# Script to kill screen sessions, rebuild and start docker containers locally,
# then tail logs in separate named screen sessions.
# Usage: ./docker-startup-local.sh

COMPOSE_FILE="/home/fret/work/emailtag/docker-compose.yml"

# Parallel arrays: screen session name -> docker compose service name
SCREEN_NAMES=("emailtag" "celery" "emailUI" "mcp")
DOCKER_SERVICES=("web" "worker" "frontend" "mcp")

# Step 1: Kill any existing log screen sessions
echo "Killing existing screen sessions..."
for s in emailtag celery emailUI claude scripts mcp; do
    if screen -list | grep -q "\.$s"; then
        screen -X -S "$s" quit 2>/dev/null
        echo "  Killed: $s"
    fi
done

# Step 2: Bring down containers
echo ""
echo "Bringing down docker containers..."
docker compose -f "$COMPOSE_FILE" down

# Step 3: Rebuild and start containers, capturing output
echo ""
echo "Building and starting docker containers (this may take a while)..."
docker compose -f "$COMPOSE_FILE" up -d --build
BUILD_EXIT=$?

if [ $BUILD_EXIT -ne 0 ]; then
    echo ""
    echo "ERROR: Docker build/startup failed (exit code $BUILD_EXIT). Log screens not created."
    exit 1
fi

echo ""
echo "Docker containers started successfully."

# Brief pause to let containers initialize before tailing
sleep 2

# Step 4: Create detached screen sessions tailing each service's logs
echo ""
echo "Creating log screen sessions..."
for i in "${!SCREEN_NAMES[@]}"; do
    screen_name="${SCREEN_NAMES[$i]}"
    service="${DOCKER_SERVICES[$i]}"
    screen -dmS "$screen_name" bash -c "docker compose -f '$COMPOSE_FILE' logs --tail 100 -f $service"
    echo "  Created screen '$screen_name' -> service '$service'"
done

echo ""
echo "Done. ${#SCREEN_NAMES[@]} log screen sessions running."
echo ""
echo "Useful commands:"
echo "  screen -ls                  List all screens"
echo "  screen -r emailtag          Attach to emailtag logs"
echo "  screen -r celery            Attach to celery logs"
echo "  screen -r emailUI           Attach to emailUI logs"
echo "  screen -r mcp               Attach to mcp logs"
echo "  Ctrl+A then D               Detach from a screen session"
