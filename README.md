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
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8444 --ssl-keyfile=/home/fret/work/emailtag/certs/privkey.pem --ssl-certfile=/home/fret/work/emailtag/certs/fullchain.pem
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

## SSL Configuration

The application is configured to use SSL by default for secure communication. To enable SSL:

### Creating Self-Signed Certificates for Development

For development or testing environments, you can create self-signed certificates:

1. Create a directory for your certificates:

```bash
mkdir -p certs
```

2. Generate self-signed certificates using OpenSSL:

```bash
openssl req -x509 -newkey rsa:4096 -keyout certs/privkey.pem -out certs/fullchain.pem -days 365 -nodes
```

3. When prompted, fill in the certificate information. For a development certificate, you can use any values.

### Using SSL Certificates

1. Update your `.env` file with the following settings:
   ```
   SSL_ENABLED=true
   SSL_CERT_FILE=/path/to/your/fullchain.pem
   SSL_KEY_FILE=/path/to/your/privkey.pem
   FORCE_HTTPS=true
   ```

2. If you're using Docker, update your `docker-compose.yml` file to mount the certificate files:
   ```yaml
   volumes:
     - /path/to/your/certs:/app/certs
   ```

### Starting the Server with SSL

#### Using Docker

```bash
docker-compose up -d
```

The Docker Compose file is configured to automatically use SSL if the certificate files are available.

#### Without Docker

Start the web server with SSL:

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8444 --ssl-keyfile=/home/fret/work/emailtag/certs/privkey.pem --ssl-certfile=/home/fret/work/emailtag/certs/fullchain.pem
```

Or let the application automatically detect and use SSL certificates:

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8444
```

### Production SSL Certificates

For production environments, it's recommended to use a trusted certificate authority like Let's Encrypt:

1. Install Certbot:

```bash
sudo apt-get update
sudo apt-get install certbot
```

2. Obtain certificates (replace `your-domain.com` with your actual domain):

```bash
sudo certbot certonly --standalone -d your-domain.com
```

3. Update your `.env` file with the certificate paths:

```
SSL_CERT_FILE=/etc/letsencrypt/live/your-domain.com/fullchain.pem
SSL_KEY_FILE=/etc/letsencrypt/live/your-domain.com/privkey.pem
```

### Using a Reverse Proxy

For production environments, it's recommended to use a reverse proxy (like Nginx) to handle SSL:

1. Configure Nginx with your SSL certificates
2. Set up a proxy pass to your application
3. In your application's `.env` file, you can set:
   ```
   SSL_ENABLED=false  # Let Nginx handle SSL
   FORCE_HTTPS=true   # Still enforce HTTPS redirects
   ```

Example Nginx configuration:
```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

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

## Data Processing

The system includes several data processing steps:

### 1. Raw Data Collection
- Receives emails via webhook
- Stores raw conversation and message data in `/data/emailtag/rawdata/`
- Files are named with conversation ID and timestamp:
  - `conv_[conversation_id]_[timestamp].json`: Raw conversation data
  - `msgs_[conversation_id]_[timestamp].json`: Raw message data

### 2. Data Cleaning
The `training/clean_conversations.py` script processes raw data into a cleaned format:

```bash
# Process all conversations
python3 training/clean_conversations.py

# Debug mode - process single conversation
python3 training/clean_conversations.py --debug

# Debug mode - process specific conversation
python3 training/clean_conversations.py --debug --conv-id cnv_xxxxx
```

Cleaned data is stored in `/data/emailtag/cleaned_data/cleaned_conversations.jsonl` with:
- One conversation per line in JSONL format
- Cleaned HTML content (tags removed, whitespace normalized)
- Normalized email addresses
- Structured sender and recipient information
- Attachment metadata
- Conversation metadata (tags, status, etc.)

### 3. Training Data
- Processed data is used to train the AI tagging system
- Training examples include both cleaned and raw data
- Stored in `/data/emailtag/training_set.jsonl`

## Development Guidelines

- Follow PEP 8 style guidelines
- Write comprehensive docstrings
- Include unit tests for all functionality
- Use environment variables for configuration
- Log all errors and important events

## Environment Variables

Required environment variables:
- `DATA_DIR`: Base directory for data storage
- `FRONT_APP_TOKEN`: FrontApp API authentication token
- `FRONT_APP_CHANNEL_ID`: FrontApp channel ID for webhook
- `FRONT_APP_TAG_ID`: FrontApp tag ID for AI-tagged conversations

## Project Structure

```
emailtag/
├── data/
│   └── emailtag/
│       ├── rawdata/          # Raw conversation and message data
│       ├── cleaned_data/     # Processed and cleaned data
│       └── training_set.jsonl # Training data for AI
├── training/
│   ├── create_training_set.py    # Creates training examples
│   └── clean_conversations.py    # Cleans raw data
├── webhook/
│   └── app.py                    # Webhook endpoint
└── .env                         # Environment variables
```

## Testing Utilities

### Simulating Inbound Emails (Webhook)

The `test_webhook.py` script allows you to simulate incoming emails from FrontApp without actually sending emails. This is useful for testing the webhook processing and AI tagging logic.

**Prerequisites:**
- Install required packages: `pip install requests python-dotenv`
- Optionally, add `FRONTAPP_WEBHOOK_SECRET` to your `.env` file (defaults to "testsecret").

**Usage:**
```bash
# Send a random test email to the default endpoint (localhost:8444)
python test_webhook.py

# Send a specific template (e.g., urgent results request)
python test_webhook.py --template 2

# Send to a specific URL
python test_webhook.py --url https://your-webhook-url.com/api/v1/webhooks/frontapp

# Send multiple emails
python test_webhook.py --count 5

# Disable SSL verification (for self-signed certs not on localhost)
python test_webhook.py --no-verify-ssl

# Send a complex email with raw data and attachment simulation
python test_webhook.py --raw
```
See the script's comments for more details and options (`test_webhook.py`).

### Creating Test Conversations via API

The `test/test_create_conversation.py` script allows you to directly create a new conversation in FrontApp using the API. This can be useful for testing downstream workflows or seeding data.

**Prerequisites:**
- Install required packages: `pip install requests python-dotenv`
- Add `FRONTAPP_API_KEY` and `FRONTAPP_CHANNEL_ID` to your `.env` file.

**Usage:**
```bash
# Create a conversation with default subject/body
python test/test_create_conversation.py --recipient someone@example.com

# Create a conversation with custom subject and body
python test/test_create_conversation.py --recipient user@domain.tld --subject "Important Test" --body "Please review this API-generated message."
```

## Contributing

Contributions are welcome! Please follow these guidelines:

- Follow PEP 8 style guidelines
- Write comprehensive docstrings
- Include unit tests for all new functionality
- Use environment variables for configuration
- Log all errors and important events

## License

This project is licensed under the MIT License. 