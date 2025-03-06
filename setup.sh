#!/bin/bash

# EmailTag setup script

echo "Setting up EmailTag..."

# Check for Python 3.11+
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not found. Please install Python 3.11 or newer."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    echo "Python 3.11+ is required. Found Python $PYTHON_VERSION"
    exit 1
fi

echo "✅ Python $PYTHON_VERSION found"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Dependencies installed"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from .env.example..."
    cp .env.example .env
    echo "✅ .env file created. Please update it with your actual configuration values."
else
    echo "✅ .env file already exists"
fi

# Check if database exists and run migrations
echo "Running database migrations..."
if ! alembic current &> /dev/null; then
    echo "⚠️  Alembic migrations may not be initialized."
    echo "Do you want to initialize Alembic migrations? (y/n)"
    read answer
    if [ "$answer" == "y" ] || [ "$answer" == "Y" ]; then
        alembic init -t async migrations
        echo "✅ Alembic initialized"
    fi
fi

echo "Running database migrations..."
alembic upgrade head
echo "✅ Database migrations applied"

echo "Setup complete! You can now run the application with:"
echo "1. Start the web server: uvicorn app.main:app --reload"
echo "2. Start Celery worker: celery -A app.tasks.worker worker -l info -Q emails,tagging"
echo "3. Start Flower (optional): celery -A app.tasks.worker flower"
echo ""
echo "Alternatively, run with Docker Compose: docker-compose up -d" 