# Docker Setup - Quick Overview

The EmailTag system runs inside **Docker containers** — small, isolated packages that each run one part of the application. They are all managed by a single file (`docker-compose.yml`).

## Does it start automatically?

**Yes.** If the server reboots, all services come back up on their own. No manual intervention needed.

## How to check if things are running

```
docker compose -f /home/fret/work/emailtag/docker-compose.yml ps
```

All services should show "Up".

## How to view logs

```
docker compose -f /home/fret/work/emailtag/docker-compose.yml logs -f web
```

Replace `web` with `worker`, `frontend`, or `mcp` to see other services. Press `Ctrl+C` to stop.

## How to restart everything

```
cd /home/fret/work/emailtag
docker compose down && docker compose up -d
```

## How to restart just one service

```
cd /home/fret/work/emailtag
docker compose restart web
```
