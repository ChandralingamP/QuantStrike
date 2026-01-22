# Instrument Update Failed - Troubleshooting Guide

## Problem

When trying to update instrument values in production, you're getting an "Update Failed" error message.

## Root Cause

The issue is caused by **missing or empty instrument expiry data files** in the production environment. Specifically:

- `/var/www/QuantStrike/backend/data/instruments.json`
- `/var/www/QuantStrike/backend/data/instruments_expiries.json`

When these files are missing or empty, the instrument serializer validation fails because it can't verify that the selected expiry is valid.

## Immediate Fix (Production)

### Step 1: SSH into your EC2 instance

```bash
ssh ec2-user@13.203.224.240
# or use your EC2 key
ssh -i your-key.pem ec2-user@13.203.224.240
```

### Step 2: Check if the data files exist

```bash
cd /var/www/QuantStrike/backend
ls -la data/
```

### Step 3: Generate the instrument data files

Run the management command to download and generate the expiry data:

```bash
cd /var/www/QuantStrike/backend
python manage.py update_scrip_master
```

This will:

- Download the latest scrip master from Angel One API
- Generate `data/instruments.json`
- Generate `data/instruments_expiries.json` with valid expiry dates

### Step 4: Verify the files were created

```bash
ls -la data/
cat data/instruments_expiries.json | head -20
```

You should see JSON data with expiry dates for NIFTY, BANKNIFTY, and SENSEX.

### Step 5: Restart the backend service

```bash
sudo systemctl restart gunicorn
# or
sudo systemctl restart quantstrike-backend
```

### Step 6: Test the instrument update

Now try updating an instrument from the frontend. It should work.

## Alternative: Manual File Creation

If the `update_scrip_master` command fails, you can manually create the files:

```bash
cd /var/www/QuantStrike/backend
mkdir -p data

# Create instruments_expiries.json with current expiries
cat > data/instruments_expiries.json << 'EOF'
{
  "NIFTY": ["30JAN2025", "06FEB2025", "13FEB2025", "20FEB2025", "27FEB2025"],
  "BANKNIFTY": ["29JAN2025", "05FEB2025", "12FEB2025", "19FEB2025", "26FEB2025"],
  "SENSEX": ["31JAN2025", "07FEB2025", "14FEB2025", "21FEB2025", "28FEB2025"]
}
EOF

# Create empty instruments.json
echo "[]" > data/instruments.json

# Set proper permissions
chmod 644 data/*.json
```

**Note:** Replace the dates above with actual valid expiry dates for the current month.

## Code Fix Applied

I've already updated the code to handle missing expiry data more gracefully:

**File:** `backend/api/serializers.py`

The validation now:

1. Only validates against allowed expiries if the expiry map is loaded and has entries
2. Provides a better error message that shows which expiries are available
3. Won't block updates when the expiry data files are temporarily unavailable

## Preventing Future Issues

### 1. Ensure the cron job is running

The `update_scrip_master` command should run daily. Verify:

```bash
crontab -l | grep update_scrip_master
```

You should see:

```
0 5 * * * cd /var/www/QuantStrike/backend && /usr/bin/python3 manage.py update_scrip_master >> /var/log/scrip_master_update.log 2>&1
```

### 2. Check the cron logs

```bash
tail -50 /var/log/scrip_master_update.log
```

### 3. Include data files in deployment

Add to your deployment script to ensure files exist:

```bash
# In deploy-prod.sh, after migrations
echo "📊 Ensuring instrument data files are up to date..."
python manage.py update_scrip_master || echo "⚠️  Warning: Could not update scrip master"
```

### 4. Set up monitoring

Add a check to verify the files exist and are recent:

```bash
# Check if files are older than 2 days
find /var/www/QuantStrike/backend/data -name "instruments_expiries.json" -mtime +2
```

## Testing Locally

To test the fix locally:

1. **Simulate the problem:**

   ```bash
   cd backend
   rm -f data/instruments_expiries.json  # Remove the file
   # Try updating an instrument - should now work or give better error
   ```

2. **Fix it:**

   ```bash
   python manage.py update_scrip_master
   ```

3. **Verify:**
   ```bash
   cat data/instruments_expiries.json
   ```

## Deployment

Deploy the code fix to production:

```bash
# On your local machine
git add backend/api/serializers.py
git commit -m "Fix instrument update validation for missing expiry data"
git push origin main

# On EC2
cd /var/www/QuantStrike
./deploy-prod.sh
```

## Additional Commands

### Manually update instruments in database

If you need to roll forward expired contracts:

```bash
python manage.py update_instruments
```

### Check Django logs

```bash
# If using gunicorn
sudo journalctl -u gunicorn -n 100

# Or check Django logs location
tail -f /var/log/quantstrike_backend.log  # adjust path as needed
```

## Summary of Changes

1. ✅ **Code Fix**: Updated `InstrumentSerializer.validate()` to handle missing expiry data
2. ✅ **Better Error Messages**: Now shows which expiries are available when validation fails
3. 🔧 **Production Action Required**: Run `update_scrip_master` command on EC2
4. 🔧 **Cron Job**: Ensure daily updates are scheduled

## Next Steps

1. Apply the immediate fix on production (Steps 1-6 above)
2. Deploy the code changes
3. Verify the cron job is running
4. Test instrument updates work correctly
5. Set up monitoring/alerts for missing data files

## Support

If you continue to have issues:

1. Check the Django error logs for detailed error messages
2. Verify the Angel One API credentials are configured
3. Ensure network access to Angel One API from EC2
4. Check file permissions on the data directory
