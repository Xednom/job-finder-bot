# job-finder-bot

A Discord bot that searches remote jobs via Remotive, RemoteOK, and RSS feeds. Uses PostgreSQL for storing saved searches and tracking seen jobs.

## Setup

### Prerequisites

- Python 3.10+
- Docker & Docker Compose (recommended for production)
- PostgreSQL 15+ (if running locally without Docker)

### Installation

#### Option 1: Using Docker Compose (Recommended)

1. Clone the repository and navigate to the project directory.

2. Create a `.env` file with your Discord token:

   ```bash
   cp .env.example .env
   # Edit .env and add your DISCORD_TOKEN
   ```

3. Build and run with Docker Compose:

   ```bash
   docker-compose up --build
   ```

   This will:
   - Start a PostgreSQL database
   - Build and run the bot
   - Automatically create the necessary tables

#### Option 2: Local Development with Poetry

1. Install dependencies:

   ```bash
   poetry install
   ```

2. Start a local PostgreSQL instance (or use Docker):

   ```bash
   # Using Docker for just the database
   docker run -d \
     --name jobfinder-db \
     -e POSTGRES_USER=jobfinder \
     -e POSTGRES_PASSWORD=secret \
     -e POSTGRES_DB=jobfinder \
     -p 5432:5432 \
     postgres:15
   ```

3. Create a `.env` file:

   ```bash
   cp .env.example .env
   # Add your DISCORD_TOKEN and DATABASE_URL
   ```

4. Run the bot:

   ```bash
   poetry run python job_finder_bot.py
   ```

#### Option 3: Using pip

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Set up PostgreSQL (see Option 2, step 2)

3. Create `.env` file and run:

   ```bash
   python job_finder_bot.py
   ```

## Configuration

Required environment variables:

- `DISCORD_TOKEN` - Your Discord bot token (required)
- `DATABASE_URL` - PostgreSQL connection string (default: `postgresql://jobfinder:secret@localhost:5432/jobfinder`)

## Usage

Once the bot is running and invited to your Discord server:

- `/findjob role:"virtual assistant" remote:true` - Search for jobs
- Results are paginated with navigation buttons
- The bot will DM users about new jobs matching their saved searches

## Database

The bot uses PostgreSQL with the following tables:

- `saved_search` - User-saved job search queries
- `seen_job` - Tracks which jobs have been shown to users

The database schema is automatically created on first run.

## Development

### Generating requirements.txt

```bash
poetry export -f requirements.txt --output requirements.txt --without-hashes
```

### Database Migrations

The bot currently uses simple SQL to create tables on startup. For production, consider using Alembic for migrations.

## Notes

If `DISCORD_TOKEN` is not available, the bot will raise a helpful error message instructing how to provide it.

