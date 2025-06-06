#!/bin/bash

# Extract PORT from .env file
PORT=$(grep "^PORT=" .env | cut -d= -f2)

# If PORT is not found, use default 8000
if [ -z "$PORT" ]; then
    PORT=8000
fi

echo "Starting server on port $PORT"
uvicorn app.main:app --reload --reload-dir app --port $PORT 