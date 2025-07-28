# Monzo App Setup Guide

## Prerequisites

- Python 3.11+
- PostgreSQL database
- Monzo API credentials

## Database Setup

### 1. Install PostgreSQL (if not already installed)

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

**CentOS/RHEL:**
```bash
sudo yum install postgresql postgresql-server
sudo postgresql-setup initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 2. Create Database and User

```bash
# Switch to postgres user
sudo -u postgres psql

# In the PostgreSQL prompt, run:
CREATE DATABASE monzo_app;
CREATE USER monzo_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE monzo_app TO monzo_user;
\q
```

### 3. Configure PostgreSQL Authentication

Edit the PostgreSQL configuration file:
```bash
sudo nano /etc/postgresql/*/main/pg_hba.conf
```

Find the lines that look like this:
```
# Database administrative login by Unix domain socket
local   all             postgres                                peer

# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     peer
```

Change the `peer` to `md5` for local connections:
```
# Database administrative login by Unix domain socket
local   all             postgres                                peer

# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     md5
```

### 4. Restart PostgreSQL
```bash
sudo systemctl restart postgresql
```

### 5. Grant Schema Permissions

```bash
sudo -u postgres psql -d monzo_app -c "GRANT ALL ON SCHEMA public TO monzo_user;"
sudo -u postgres psql -d monzo_app -c "GRANT CREATE ON SCHEMA public TO monzo_user;"
sudo -u postgres psql -d monzo_app -c "GRANT USAGE ON SCHEMA public TO monzo_user;"
sudo -u postgres psql -d monzo_app -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO monzo_user;"
```

### 6. Test Database Connection

```bash
psql -U monzo_user -d monzo_app -h localhost
# Enter the password when prompted
```

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables by creating a `.env` file in the root directory:
   ```bash
   # Database Configuration
   DATABASE_URL=postgresql://monzo_user:your_secure_password@localhost/monzo_app
   
   # Flask Configuration
   FLASK_SECRET_KEY=your-secret-key-here-change-in-production
   FLASK_ENV=development
   
   # Logging Configuration
   LOG_LEVEL=INFO
   ```

4. Initialize the database:
   ```bash
   alembic upgrade head
   ```

5. Run the application:
   ```bash
   python run.py
   ```

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Yes | - |
| `FLASK_SECRET_KEY` | Secret key for Flask sessions | Yes | dev-secret-key-change-in-production |
| `FLASK_ENV` | Flask environment | No | development |
| `LOG_LEVEL` | Logging level | No | INFO |

## Monzo API Setup

1. Create a Monzo API application at https://developers.monzo.com/
2. Get your Client ID and Client Secret
3. Configure the redirect URI in your Monzo app settings
4. Use the app's web interface to authenticate with Monzo

## Troubleshooting

### Database Connection Issues

If you get "Peer authentication failed" errors:
1. Ensure you've configured `pg_hba.conf` to use `md5` authentication
2. Restart PostgreSQL after configuration changes
3. Use the correct password when connecting

### Migration Issues

If migrations fail with "table does not exist" errors:
1. Ensure all schema permissions are granted to `monzo_user`
2. Check that the database was created successfully
3. Verify the `DATABASE_URL` in your `.env` file is correct

### Permission Issues

If you get "permission denied for schema public" errors:
1. Run the schema permission commands as the postgres user
2. Ensure `monzo_user` has `CREATE` and `USAGE` privileges on the public schema

## Security Notes

- Never commit your `.env` file to version control
- Use a strong, unique `FLASK_SECRET_KEY` in production
- Store Monzo API credentials securely
- Use HTTPS in production environments
- Use strong, unique passwords for database users
- Consider using SSL connections for PostgreSQL in production 