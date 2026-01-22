#!/bin/bash

# QuantStrike Production Deployment Script
# Run this on your EC2 instance to deploy latest changes

echo "🚀 Starting QuantStrike deployment..."

# Stop on any error
set -e

# Navigate to project
cd /var/www/QuantStrike

# Pull latest code
echo "📥 Pulling latest code from GitHub..."
git pull origin main

# ============================================
# BACKEND DEPLOYMENT
# ============================================
echo ""
echo "🔧 Deploying backend..."
cd /var/www/QuantStrike/backend

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "🐍 Activating virtual environment..."
    source venv/bin/activate
fi

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Run migrations
echo "📊 Running database migrations..."
python manage.py migrate --noinput || true

# Collect static files
echo "📦 Collecting static files..."
python manage.py collectstatic --noinput || true

# Ensure instrument data files exist
echo "📊 Ensuring instrument data files are up to date..."
if [ ! -f "data/instruments_expiries.json" ] || [ ! -f "data/instruments.json" ]; then
    echo "⚠️  Instrument data files missing. Running update_scrip_master..."
    python manage.py update_scrip_master || echo "⚠️  Warning: Could not update scrip master. Please run manually."
else
    echo "✅ Instrument data files exist"
    # Optionally update if files are older than 7 days
    if find data/instruments_expiries.json -mtime +7 | grep -q .; then
        echo "⚠️  Instrument data is older than 7 days. Updating..."
        python manage.py update_scrip_master || echo "⚠️  Warning: Could not update scrip master"
    fi
fi

# Setup cron job for daily scrip master update
echo "⏰ Setting up cron job for daily scrip master update..."
(crontab -l 2>/dev/null | grep -v "update_scrip_master"; echo "0 5 * * * cd /var/www/QuantStrike/backend && /usr/bin/python3 manage.py update_scrip_master >> /var/log/scrip_master_update.log 2>&1") | crontab -
echo "✅ Cron job configured to run at 5 AM daily"

# Restart gunicorn
echo "🚀 Restarting gunicorn service..."
sudo systemctl restart gunicorn || sudo systemctl restart quantstrike-backend || echo "⚠️  Gunicorn restart issue"
sleep 3

# ============================================
# FRONTEND DEPLOYMENT
# ============================================
echo ""
echo "🎨 Deploying frontend..."
cd /var/www/QuantStrike/frontend

# Install dependencies
echo "📦 Installing Node.js dependencies..."
npm ci

# Build frontend
echo "🏗️  Building frontend..."
npm run build

# Deploy built files
echo "📋 Copying built files to nginx directory..."
sudo rm -rf /var/www/quantstrike-frontend/*
sudo cp -r dist/* /var/www/quantstrike-frontend/

# Set proper permissions
sudo chown -R www-data:www-data /var/www/quantstrike-frontend || true

# Restart nginx
echo "🔄 Restarting nginx service..."
sudo systemctl restart nginx
sleep 2

echo ""
echo "✅ Deployment completed successfully!"
echo "🌐 Frontend: http://13.203.224.240"
echo "📡 API: http://13.203.224.240/api"
echo ""
echo "📝 Next steps:"
echo "   - Clear browser cache (Ctrl+Shift+Delete)"
echo "   - Try logging in again"
