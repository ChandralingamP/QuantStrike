#!/bin/bash

# QuantStrike Instrument Update Diagnostic Script
# Run this script to check the status of instrument data files and related services

echo "🔍 QuantStrike Instrument Update Diagnostics"
echo "=============================================="
echo ""

# Check if running in backend directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: Please run this script from the backend directory"
    echo "   cd /var/www/QuantStrike/backend && bash ../check-instruments.sh"
    exit 1
fi

# 1. Check data directory exists
echo "1️⃣  Checking data directory..."
if [ -d "data" ]; then
    echo "   ✅ data/ directory exists"
    ls -lh data/
else
    echo "   ❌ data/ directory missing"
    echo "   Fix: mkdir -p data"
fi
echo ""

# 2. Check instruments.json
echo "2️⃣  Checking instruments.json..."
if [ -f "data/instruments.json" ]; then
    SIZE=$(stat -f%z "data/instruments.json" 2>/dev/null || stat -c%s "data/instruments.json" 2>/dev/null)
    AGE=$(find data/instruments.json -mtime +7 2>/dev/null | wc -l)
    echo "   ✅ File exists"
    echo "   📏 Size: $SIZE bytes"
    echo "   📅 Last modified: $(stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S' data/instruments.json 2>/dev/null || stat -c '%y' data/instruments.json 2>/dev/null | cut -d. -f1)"
    if [ "$AGE" -gt 0 ]; then
        echo "   ⚠️  File is older than 7 days"
    fi
else
    echo "   ❌ instruments.json missing"
    echo "   Fix: python manage.py update_scrip_master"
fi
echo ""

# 3. Check instruments_expiries.json
echo "3️⃣  Checking instruments_expiries.json..."
if [ -f "data/instruments_expiries.json" ]; then
    SIZE=$(stat -f%z "data/instruments_expiries.json" 2>/dev/null || stat -c%s "data/instruments_expiries.json" 2>/dev/null)
    AGE=$(find data/instruments_expiries.json -mtime +7 2>/dev/null | wc -l)
    echo "   ✅ File exists"
    echo "   📏 Size: $SIZE bytes"
    echo "   📅 Last modified: $(stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S' data/instruments_expiries.json 2>/dev/null || stat -c '%y' data/instruments_expiries.json 2>/dev/null | cut -d. -f1)"
    if [ "$AGE" -gt 0 ]; then
        echo "   ⚠️  File is older than 7 days"
    fi
    echo ""
    echo "   📋 Content preview:"
    head -20 data/instruments_expiries.json
else
    echo "   ❌ instruments_expiries.json missing"
    echo "   Fix: python manage.py update_scrip_master"
fi
echo ""

# 4. Check cron job
echo "4️⃣  Checking cron job..."
if crontab -l 2>/dev/null | grep -q "update_scrip_master"; then
    echo "   ✅ Cron job exists:"
    crontab -l | grep "update_scrip_master"
else
    echo "   ❌ Cron job not configured"
    echo "   Fix: Add to crontab:"
    echo "   0 5 * * * cd /var/www/QuantStrike/backend && /usr/bin/python3 manage.py update_scrip_master >> /var/log/scrip_master_update.log 2>&1"
fi
echo ""

# 5. Check cron logs
echo "5️⃣  Checking cron logs..."
if [ -f "/var/log/scrip_master_update.log" ]; then
    echo "   ✅ Log file exists"
    echo "   📋 Last 10 lines:"
    tail -10 /var/log/scrip_master_update.log
else
    echo "   ⚠️  Log file not found at /var/log/scrip_master_update.log"
fi
echo ""

# 6. Check Django service
echo "6️⃣  Checking Django service..."
if systemctl is-active --quiet gunicorn 2>/dev/null; then
    echo "   ✅ gunicorn service is running"
elif systemctl is-active --quiet quantstrike-backend 2>/dev/null; then
    echo "   ✅ quantstrike-backend service is running"
else
    echo "   ⚠️  Django service status unclear"
    echo "   Check with: sudo systemctl status gunicorn"
fi
echo ""

# 7. Test Python can load the files
echo "7️⃣  Testing Python can load expiry data..."
python3 -c "
from pathlib import Path
import json
import sys

expiries_path = Path('data/instruments_expiries.json')
if expiries_path.exists():
    try:
        with open(expiries_path) as f:
            data = json.load(f)
        if data:
            print('   ✅ Successfully loaded expiry data')
            print('   📊 Instruments found:', ', '.join(data.keys()))
            for k, v in data.items():
                print(f'      {k}: {len(v)} expiries')
        else:
            print('   ⚠️  File is empty')
            sys.exit(1)
    except Exception as e:
        print(f'   ❌ Error loading file: {e}')
        sys.exit(1)
else:
    print('   ❌ File does not exist')
    sys.exit(1)
" 2>&1
echo ""

# 8. Recommendations
echo "8️⃣  Recommendations:"
echo ""

NEEDS_FIX=false

if [ ! -f "data/instruments_expiries.json" ] || [ ! -f "data/instruments.json" ]; then
    echo "   🔧 Run: python manage.py update_scrip_master"
    NEEDS_FIX=true
fi

if ! crontab -l 2>/dev/null | grep -q "update_scrip_master"; then
    echo "   🔧 Set up cron job for daily updates"
    NEEDS_FIX=true
fi

if [ "$NEEDS_FIX" = false ]; then
    echo "   ✅ Everything looks good!"
    echo ""
    echo "   If you're still seeing 'Update Failed' errors:"
    echo "   1. Check Django logs: sudo journalctl -u gunicorn -n 50"
    echo "   2. Restart backend: sudo systemctl restart gunicorn"
    echo "   3. Check browser console for frontend errors"
fi

echo ""
echo "=============================================="
echo "Diagnostics complete"
