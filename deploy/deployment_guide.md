# SwapMate AI VPS Deployment Guide (Ubuntu 22.04+)

This guide will help you set up your Django ASGI application on a $4-6 DigitalOcean Droplet.

## 1. Initial Server Setup
Connect to your droplet:
```bash
ssh root@your_server_ip
```

Update system:
```bash
apt update && apt upgrade -y
apt install python3-pip python3-venv nginx redis-server postgresql postgresql-contrib libpq-dev -y
```

## 2. PostgreSQL Database Setup
Log in to Postgres and create your database:
```bash
sudo -u postgres psql
```
Inside the Postgres terminal, run these (replace `my_password` with a strong password):
```sql
CREATE DATABASE swap_db;
CREATE USER swap_user WITH PASSWORD 'my_password';
ALTER ROLE swap_user SET client_encoding TO 'utf8';
ALTER ROLE swap_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE swap_user SET timezone TO 'Africa/Nairobi';
GRANT ALL PRIVILEGES ON DATABASE swap_db TO swap_user;
\q
```

## 3. Project Setup
Clone your repository (replace with your repo link):
```bash
git clone https://github.com/kamcho/swap.git /root/swap
cd /root/swap
```

Create Virtual Environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Database & Migrations
```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

## 4. Configure Services
Copy the provided service files to the system directory:
```bash
cp deploy/daphne.service /etc/systemd/system/
```

Start and Enable Daphne:
```bash
systemctl start daphne
systemctl enable daphne
```

## 5. Configure Nginx
Copy Nginx config:
```bash
cp deploy/nginx.conf /etc/nginx/sites-available/swap
ln -s /etc/nginx/sites-available/swap /etc/nginx/sites-enabled
```

Test and Restart Nginx:
```bash
nginx -t
systemctl restart nginx
```

## 6. SSL Security (Mandatory for WhatsApp)
Install Certbot:
```bash
apt install certbot python3-certbot-nginx -y
certbot --nginx -d your_domain.com
```

## 7. Environment Variables
Create a `.env` file in `/root/swap/` and paste your keys:
```bash
nano .env
```
Example `.env` content:
```text
SECRET_KEY=your_secret_key
DEBUG=False
DATABASE_URL=postgres://swap_user:my_password@localhost:5432/swap_db
REDIS_URL=redis://127.0.0.1:6379/0
OPENAI_API_KEY=your_key
WHATSAPP_ACCESS_TOKEN=your_token
```

---
**Note:** Your WebSockets are served via Daphne on port 8001, and Nginx proxies them correctly using the `/ws/` location block.
