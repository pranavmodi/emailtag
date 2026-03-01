# Docker Deployment Guide

This document explains how to deploy the EmailTag application using Docker Compose in a **hybrid** setup: application services run in Docker containers while PostgreSQL and RabbitMQ run directly on the host.

## Architecture

```
Host Machine
├── PostgreSQL (host service, port 5432)
├── RabbitMQ  (host service, port 5672)
│
└── Docker Containers (network_mode: host)
    ├── emailtag-web       → FastAPI backend        (port 8444, HTTPS)
    ├── emailtag-worker    → Celery task worker      (no port)
    ├── emailtag-frontend  → Next.js settings UI     (port 3001)
    ├── emailtag-flower    → Celery monitoring        (port 5555)
    └── precisemcp         → MCP server              (port 8001)
```

All containers use `network_mode: host`, meaning they share the host's network stack. They connect to PostgreSQL and RabbitMQ via `localhost` or host IPs — no Docker networking needed.

## Prerequisites

1. **Docker & Docker Compose** installed:
   ```bash
   sudo apt-get update
   sudo apt-get install docker.io docker-compose-v2
   ```

2. **PostgreSQL** running on the host (port 5432)

3. **RabbitMQ** running on the host (port 5672):
   ```bash
   # Verify both are running
   systemctl status postgresql rabbitmq-server
   ```

4. **Environment files** in place:
   - `/home/fret/work/emailtag/.env` — backend config (database URLs, API keys, Celery broker, etc.)
   - `/home/fret/work/precisemcp/.env` — MCP server config

5. **SSL certificates** at `emailtag/certs/`:
   - `fullchain.pem`
   - `privkey.pem`

## Deploying

All commands are run from the `emailtag/` directory.

### First-time setup

```bash
# Build all images
docker compose build

# Start everything in the background
docker compose up -d
```

### Verify services are running

```bash
docker compose ps
```

Expected output:
```
NAME                STATUS
emailtag-web        Up (healthy)
emailtag-worker     Up
emailtag-frontend   Up
emailtag-flower     Up
precisemcp          Up (healthy)
```

### Quick health checks

```bash
# Backend API
curl -k https://localhost:8444/health

# Frontend
curl http://localhost:3001/settings

# Flower dashboard
curl http://localhost:5555

# MCP server
curl http://localhost:8001/health
```

## Managing Services

### View logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f web
docker compose logs -f worker
docker compose logs -f frontend
docker compose logs -f flower
docker compose logs -f mcp
```

### Restart a single service

```bash
docker compose restart web
docker compose restart worker
```

### Stop everything

```bash
docker compose down
```

### Rebuild after code changes

```bash
# Rebuild and restart a single service
docker compose up -d --build web

# Rebuild everything
docker compose up -d --build
```

## Auto-Start on Boot

All services have `restart: unless-stopped`, so they automatically restart when Docker starts. Ensure Docker itself starts on boot:

```bash
sudo systemctl enable docker
```

**Boot order**: systemd starts PostgreSQL and RabbitMQ first (they're native services), then starts Docker, which starts the application containers. The containers will retry connections if the host services aren't ready yet.

## Migrating from Screen Sessions

This Docker setup replaces the following screen sessions:

| Old (screen) | Command | Port | New (Docker) |
|---|---|---|---|
| `screen -S emailtag` | `uvicorn app.main:app --reload --port 8444 --ssl-keyfile certs/privkey.pem --ssl-certfile certs/fullchain.pem` | 8444 | `emailtag-web` |
| `screen -S celery` | `celery -A app.tasks.worker worker -l info -Q emails,tagging,processing,ocr` | — | `emailtag-worker` |
| `screen -S emailUI` | `cd frontend/settings2 && npm run dev` | 3001 | `emailtag-frontend` |
| `screen -S mcp` | `cd /home/fret/work/precisemcp && PORT=8001 uv run python3 server.py` | 8001 | `precisemcp` |
| _(not previously running)_ | | 5555 | `emailtag-flower` |

To stop the old screen sessions before migration:

```bash
screen -S emailtag -X quit
screen -S celery -X quit
screen -S emailUI -X quit
screen -S mcp -X quit
```

**Important:** Since Docker containers use `network_mode: host`, they bind to the same ports on the host. Make sure no other processes are using ports 8444, 3000, 5555, or 8001 before starting the containers. Check with:
```bash
ss -tlnp | grep -E '8444|3001|5555|8001'
```

## SSL

SSL/TLS is terminated directly by uvicorn in the `web` container. The cert files are mounted read-only from the host:

```
./certs/fullchain.pem  →  /app/certs/fullchain.pem
./certs/privkey.pem    →  /app/certs/privkey.pem
```

When renewing certificates, just replace the files in `certs/` and restart the web service:

```bash
docker compose restart web
```

## Ports Summary

| Port | Service          | Protocol |
|------|------------------|----------|
| 8444 | FastAPI backend  | HTTPS    |
| 3001 | Next.js frontend | HTTP     |
| 5555 | Flower dashboard | HTTP     |
| 8001 | MCP server       | HTTP     |
| 5432 | PostgreSQL       | TCP (host) |
| 5672 | RabbitMQ         | AMQP (host) |

## Troubleshooting

**Container won't start — port already in use:**
A screen session or another process may still be using the port. Check with:
```bash
ss -tlnp | grep <port>
```
Kill the conflicting process or stop the old screen session.

**Worker can't connect to RabbitMQ:**
Ensure RabbitMQ is running on the host and the `CELERY_BROKER_URL` in `.env` points to `localhost:5672`.

**Database connection refused:**
Ensure PostgreSQL is running and the `DATABASE_URL` in `.env` uses the correct host/port. Check that `pg_hba.conf` allows connections from `127.0.0.1`.

**Viewing container resource usage:**
```bash
docker stats
```
