# EmailTag

EmailTag is a Python application that automatically tags emails from a CRM (FrontApp) using AI. The purpose of tagging is to enable the right departments at Precise Imaging to look at the right emails.

## Features

- Webhook endpoint to receive emails from FrontApp
- Email parsing and content extraction
- AI-based tagging system using OpenAI
- Integration with FrontApp API for applying tags
- Asynchronous processing with Celery and RabbitMQ
- PostgreSQL database for data storage

## Architecture

The application is built with the following components:

- **FastAPI**: Web framework for building the API
- **SQLAlchemy**: ORM for database interactions
- **Alembic**: Database migration tool
- **Celery**: Distributed task queue
- **RabbitMQ**: Message broker for Celery
- **PostgreSQL**: Database for storing emails and tags
- **OpenAI**: AI service for analyzing email content
- **FrontApp API**: Integration with the CRM

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL
- RabbitMQ

### Environment Variables

Create a `.env` file based on the `.env.example` file:

```bash
cp .env.example .env
```

Update the values in the `.env` file with your own configuration.

### Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd emailtag
```

2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run database migrations:

```bash
alembic upgrade head
```

### Running the Application

#### Using Docker

The easiest way to run the application is using Docker Compose:

```bash
docker-compose up -d
```

This will start the following services:
- Web server (FastAPI)
- Celery worker
- Flower (Celery monitoring)
- PostgreSQL
- RabbitMQ

#### Without Docker

1. Start the web server:

```bash
uvicorn app.main:app --reload
```

2. Start the Celery worker:

```bash
celery -A app.tasks.worker worker -l info -Q emails,tagging
```

3. (Optional) Start Flower for monitoring Celery tasks:

```bash
celery -A app.tasks.worker flower
```

## API Documentation

Once the application is running, you can access the API documentation at:

- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

## FrontApp Webhook Setup

1. In your FrontApp account, go to Settings > Webhooks
2. Create a new webhook with the following settings:
   - URL: `https://your-domain.com/api/v1/webhooks/frontapp`
   - Events: Select "Inbound message"
   - Secret: Generate a random string and add it to your `.env` file

## Development

### Running Tests

```bash
pytest
```

### Creating Database Migrations

After making changes to the database models, create a new migration:

```bash
alembic revision --autogenerate -m "Description of changes"
```

Apply the migration:

```bash
alembic upgrade head
``` 