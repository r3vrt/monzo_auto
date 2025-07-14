# Deployment Guide

This guide covers deploying the Monzo Automation App to production environments.

## Prerequisites

- Python 3.11+
- Web server (Nginx, Apache, or similar)
- WSGI server (Gunicorn, uWSGI, or similar)
- SSL certificate for HTTPS
- Domain name (optional but recommended)

## Environment Setup

### 1. Production Environment

Create a production Python environment:

```bash
# Install Python 3.11+
pyenv install 3.11.6
pyenv virtualenv 3.11.6 monzo_app_prod
pyenv activate monzo_app_prod

# Install dependencies
pip install -r requirements.txt
```

### 2. Production Dependencies

Add production dependencies to `requirements.txt`:

```txt
# Add these to requirements.txt for production
gunicorn==21.2.0
python-dotenv==1.0.0
```

### 3. Environment Variables

Create a `.env` file for production configuration:

```bash
# Production configuration
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your-secret-key-here
MONZO_CLIENT_ID=your-monzo-client-id
MONZO_CLIENT_SECRET=your-monzo-client-secret
MONZO_REDIRECT_URI=https://your-domain.com/auth/callback

# Database (if using one in the future)
# DATABASE_URL=postgresql://user:password@localhost/dbname

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/monzo_app/app.log

# Security
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE=Lax
```

## WSGI Configuration

### Gunicorn Configuration

Create `gunicorn.conf.py`:

```python
# Gunicorn configuration
bind = "127.0.0.1:8000"
workers = 4
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 30
keepalive = 2
preload_app = True

# Logging
accesslog = "/var/log/monzo_app/gunicorn_access.log"
errorlog = "/var/log/monzo_app/gunicorn_error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "monzo_app"

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
```

### Systemd Service

Create `/etc/systemd/system/monzo_app.service`:

```ini
[Unit]
Description=Monzo Automation App
After=network.target

[Service]
Type=notify
User=monzo_app
Group=monzo_app
WorkingDirectory=/opt/monzo_app
Environment=PATH=/opt/monzo_app/venv/bin
ExecStart=/opt/monzo_app/venv/bin/gunicorn --config gunicorn.conf.py run:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Web Server Configuration

### Nginx Configuration

Create `/etc/nginx/sites-available/monzo_app`:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL Configuration
    ssl_certificate /path/to/your/certificate.crt;
    ssl_certificate_key /path/to/your/private.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security Headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Logging
    access_log /var/log/nginx/monzo_app_access.log;
    error_log /var/log/nginx/monzo_app_error.log;

    # Static files (if any)
    location /static/ {
        alias /opt/monzo_app/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Application
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
}
```

## Deployment Steps

### 1. Server Setup

```bash
# Create application user
sudo useradd -r -s /bin/false monzo_app

# Create application directory
sudo mkdir -p /opt/monzo_app
sudo chown monzo_app:monzo_app /opt/monzo_app

# Create log directories
sudo mkdir -p /var/log/monzo_app
sudo chown monzo_app:monzo_app /var/log/monzo_app
```

### 2. Application Deployment

```bash
# Clone or copy application
sudo -u monzo_app git clone https://github.com/your-username/monzo_app.git /opt/monzo_app
cd /opt/monzo_app

# Set up Python environment
sudo -u monzo_app pyenv install 3.11.6
sudo -u monzo_app pyenv virtualenv 3.11.6 monzo_app_prod
sudo -u monzo_app pyenv activate monzo_app_prod
sudo -u monzo_app pip install -r requirements.txt

# Copy configuration files
sudo -u monzo_app cp .env.example .env
# Edit .env with production values
sudo -u monzo_app nano .env

# Create configuration directory
sudo -u monzo_app mkdir -p config
```

### 3. Service Setup

```bash
# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable monzo_app
sudo systemctl start monzo_app

# Check status
sudo systemctl status monzo_app
```

### 4. Web Server Setup

```bash
# Enable Nginx site
sudo ln -s /etc/nginx/sites-available/monzo_app /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5. SSL Certificate

```bash
# Using Let's Encrypt (recommended)
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

## Monitoring and Logging

### 1. Log Management

```bash
# Set up log rotation
sudo nano /etc/logrotate.d/monzo_app

# Add:
/var/log/monzo_app/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 monzo_app monzo_app
    postrotate
        systemctl reload monzo_app
    endscript
}
```

### 2. Health Monitoring

```bash
# Create health check script
sudo nano /usr/local/bin/monzo_app_health.sh

#!/bin/bash
curl -f http://localhost:8000/monitoring/api/health || exit 1
```

### 3. System Monitoring

Consider using monitoring tools like:
- **Prometheus + Grafana**: For metrics and alerting
- **Sentry**: For error tracking
- **Uptime Robot**: For uptime monitoring

## Security Considerations

### 1. Firewall Configuration

```bash
# Configure UFW firewall
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

### 2. File Permissions

```bash
# Secure configuration files
sudo chmod 600 /opt/monzo_app/.env
sudo chmod 600 /opt/monzo_app/config/auth.json
sudo chown monzo_app:monzo_app /opt/monzo_app/.env
sudo chown monzo_app:monzo_app /opt/monzo_app/config/auth.json
```

### 3. Regular Updates

```bash
# Set up automatic security updates
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

## Backup Strategy

### 1. Configuration Backup

```bash
# Create backup script
sudo nano /usr/local/bin/monzo_app_backup.sh

#!/bin/bash
BACKUP_DIR="/var/backups/monzo_app"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
tar -czf $BACKUP_DIR/config_$DATE.tar.gz -C /opt/monzo_app config/ .env
find $BACKUP_DIR -name "config_*.tar.gz" -mtime +30 -delete
```

### 2. Automated Backups

```bash
# Add to crontab
sudo crontab -e
# Add: 0 2 * * * /usr/local/bin/monzo_app_backup.sh
```

## Troubleshooting

### Common Issues

1. **Service won't start**:
   ```bash
   sudo journalctl -u monzo_app -f
   ```

2. **Permission errors**:
   ```bash
   sudo chown -R monzo_app:monzo_app /opt/monzo_app
   ```

3. **SSL certificate issues**:
   ```bash
   sudo certbot renew --dry-run
   ```

4. **Database connection issues** (if using database):
   ```bash
   sudo -u monzo_app python -c "from app import create_app; app = create_app(); print('Database connection OK')"
   ```

### Performance Tuning

1. **Adjust Gunicorn workers**:
   ```python
   # In gunicorn.conf.py
   workers = (2 * cpu_count) + 1
   ```

2. **Enable Nginx caching**:
   ```nginx
   # Add to Nginx config
   location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg)$ {
       expires 1y;
       add_header Cache-Control "public, immutable";
   }
   ```

## Scaling Considerations

### Horizontal Scaling

For high-traffic applications:

1. **Load Balancer**: Use HAProxy or Nginx as load balancer
2. **Multiple Instances**: Deploy multiple application instances
3. **Database**: Use external database (PostgreSQL, MySQL)
4. **Caching**: Implement Redis for session storage
5. **CDN**: Use CloudFlare or similar for static assets

### Vertical Scaling

1. **Increase Resources**: More CPU, RAM, and storage
2. **Optimize Code**: Profile and optimize slow queries
3. **Database Optimization**: Add indexes, optimize queries
4. **Caching**: Implement application-level caching

## Maintenance

### Regular Maintenance Tasks

1. **Weekly**:
   - Check logs for errors
   - Monitor disk space
   - Review security updates

2. **Monthly**:
   - Update dependencies
   - Review backup integrity
   - Performance analysis

3. **Quarterly**:
   - Security audit
   - SSL certificate renewal
   - System updates

### Update Process

```bash
# Create update script
sudo nano /usr/local/bin/monzo_app_update.sh

#!/bin/bash
cd /opt/monzo_app
sudo -u monzo_app git pull
sudo -u monzo_app pip install -r requirements.txt
sudo systemctl restart monzo_app
sudo systemctl reload nginx
```

This deployment guide provides a solid foundation for running the Monzo Automation App in production. Adjust the configuration based on your specific requirements and infrastructure. 