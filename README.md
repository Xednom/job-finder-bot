# job-finder-bot

A Discord bot that searches remote jobs from multiple platforms including Remotive, RemoteOK, OnlineJobs.ph, WeWorkRemotely, FlexJobs, JobStreet PH, Upwork, and RSS feeds. Uses PostgreSQL for storing saved searches and tracking seen jobs.

## Supported Job Platforms

- **Remotive** - Remote jobs from various companies
- **RemoteOK** - Popular remote job board
- **OnlineJobs.ph** - Philippines-focused remote jobs
- **WeWorkRemotely** - Premium remote job listings
- **FlexJobs** - Flexible and remote positions
- **JobStreet PH** - Philippines job market (remote filter)
- **Upwork** - Freelance opportunities
- **RSS Feeds** - Custom job feeds

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

Once the bot is running and invited to your Discord server, use these slash commands:

### Basic Job Search

```
/findjob role:"virtual assistant"
```

### Search Specific Platforms

```
/findjob role:"developer" source:remoteok
/findjob role:"data entry" source:onlinejobs
/findjob role:"writer" source:upwork experience:entry
/findjob role:"customer support" source:weworkremotely
/findjob role:"virtual assistant" source:flexjobs
/findjob role:"accountant" source:jobstreet
```

### Upwork Experience Levels

When using `source:upwork`, you can specify the experience level:

```
/findjob role:"virtual assistant" source:upwork experience:entry
/findjob role:"developer" source:upwork experience:intermediate
/findjob role:"designer" source:upwork experience:expert
```

Experience levels:
- `entry` - Entry level (contractor_tier=1) - Default
- `intermediate` - Intermediate level (contractor_tier=2)
- `expert` - Expert level (contractor_tier=3)

### Available Sources

- `remotive` (default) - Remotive API
- `remoteok` - RemoteOK
- `onlinejobs` - OnlineJobs.ph (Philippines)
- `weworkremotely` - WeWorkRemotely
- `flexjobs` - FlexJobs
- `jobstreet` - JobStreet Philippines
- `upwork` - Upwork freelance jobs

### Advanced Search Options

```
/findjob role:"software engineer" location:"Philippines" remote:true
/findjob role:"designer" source:remotive
```

Results are paginated with ◀️ Prev and Next ▶️ buttons. The bot will also DM users about new jobs matching their saved searches every 15 minutes.

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

