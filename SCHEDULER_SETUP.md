# QuantStrike Automated Scheduler Setup Guide

## 🚀 Quick Start

### Local/Development Setup

```bash
cd /path/to/QuantStrike
./deploy-scheduler.sh
```

### Production Setup (SSH Access)

```bash
# 1. SSH into production server
ssh user@your-production-server

# 2. Navigate to project directory
cd /path/to/QuantStrike

# 3. Run setup script
./deploy-scheduler.sh

# 4. Verify cron jobs
crontab -l
```

---

## 📅 Scheduled Tasks

### 1. **Instrument Data Update** (7:00 AM IST, Mon-Fri)

Updates instrument and expiry data from Angel SmartAPI.

```bash
# Manual execution:
cd backend
python3 manage.py update_scrip_master
```

**Purpose:**

- Refresh contract symbols and tokens
- Update expiry dates
- Ensure latest instrument data

**Logs:** `backend/logs/instruments.log`

---

### 2. **Metadata Refresh** (7:05 AM IST, Mon-Fri)

Loads instrument metadata into database.

```bash
# Manual execution:
python3 manage.py load_instrument_metadata
```

**Purpose:**

- Populate instrument database
- Update lot sizes and exchange info
- Prepare for strategy execution

**Logs:** `backend/logs/metadata.log`

---

### 3. **Strategy Execution** (9:15 AM IST, Mon-Fri)

Runs activated strategies for all eligible users automatically.

```bash
# Manual execution:
python3 manage.py run_all_strategies --strategy strategy_alpha

# Force demo mode:
python3 manage.py run_all_strategies --strategy strategy_alpha --mode demo

# Force live mode:
python3 manage.py run_all_strategies --strategy strategy_alpha --mode live
```

**Purpose:**

- Execute strategies for all active users
- Open trades based on strategy logic
- Auto-start monitor service for each user

**Logs:** `backend/logs/strategies.log`

---

## ⚙️ Configuration

### Cron Schedule Format

```
# ┌───────────── minute (0 - 59)
# │ ┌───────────── hour (0 - 23)
# │ │ ┌───────────── day of month (1 - 31)
# │ │ │ ┌───────────── month (1 - 12)
# │ │ │ │ ┌───────────── day of week (0 - 6) (Sun - Sat)
# │ │ │ │ │
# * * * * *  command to execute
```

### Current Schedule

```bash
# Update instruments (7:00 AM IST, Mon-Fri)
0 7 * * 1-5 cd /path/to/backend && venv/bin/python3 manage.py update_scrip_master

# Load metadata (7:05 AM IST, Mon-Fri)
5 7 * * 1-5 cd /path/to/backend && venv/bin/python3 manage.py load_instrument_metadata

# Run strategies (9:15 AM IST, Mon-Fri)
15 9 * * 1-5 cd /path/to/backend && venv/bin/python3 manage.py run_all_strategies
```

---

## 📊 How It Works

### Daily Workflow

```
6:00 AM  → Server wakes up
7:00 AM  → Update instruments from SmartAPI
7:05 AM  → Load metadata into database
9:15 AM  → Execute strategies for all active users
         → Open trades + Start monitors
         → Monitors run continuously
3:35 PM  → Demo trades auto-close (EOD)
         → Live trades continue (broker squares off)
         → Monitors exit when no trades left
```

### User Eligibility Criteria

For a user to have strategies executed automatically:

1. ✅ `AlgoConfiguration.algo_active = True`
2. ✅ `StrategyActivation.is_active = True`
3. ✅ For LIVE mode:
   - `AlgoConfiguration.market_active = True`
   - `UserProfile.api_key` exists
   - `UserProfile.jwt_token` exists
4. ✅ At least one instrument selected and active

---

## 🔍 Monitoring & Logs

### View Logs in Real-Time

```bash
# Instrument updates
tail -f backend/logs/instruments.log

# Metadata loading
tail -f backend/logs/metadata.log

# Strategy execution
tail -f backend/logs/strategies.log

# All logs combined
tail -f backend/logs/*.log
```

### Check Cron Job Status

```bash
# View installed cron jobs
crontab -l

# Check system cron logs (Linux)
grep CRON /var/log/syslog

# Check system cron logs (macOS)
log show --predicate 'process == "cron"' --last 1h
```

### Verify Last Execution

```bash
# Check log file timestamps
ls -lh backend/logs/

# View last 50 lines of strategy log
tail -50 backend/logs/strategies.log
```

---

## 🛠️ Troubleshooting

### Cron Jobs Not Running

**Problem:** Scheduled tasks not executing

**Solutions:**

```bash
# 1. Check cron service status (Linux)
sudo systemctl status cron

# 2. Verify crontab is installed
crontab -l

# 3. Check cron logs
grep CRON /var/log/syslog

# 4. Test command manually
cd /path/to/backend && venv/bin/python3 manage.py run_all_strategies
```

---

### Path Issues

**Problem:** `python3: command not found` or `manage.py not found`

**Solutions:**

```bash
# 1. Use absolute paths in crontab
which python3  # Get full python path
pwd  # Get current directory

# 2. Update crontab with absolute paths
15 9 * * 1-5 cd /full/path/to/backend && /full/path/to/venv/bin/python3 manage.py run_all_strategies
```

---

### Environment Variables

**Problem:** Django settings not loaded

**Solutions:**

```bash
# 1. Add to crontab (before jobs)
DJANGO_SETTINGS_MODULE=quantstrike_backend.settings
PYTHONPATH=/path/to/backend

# 2. Or source .env in cron command
15 9 * * 1-5 cd /path/to/backend && source .env && venv/bin/python3 manage.py run_all_strategies
```

---

### Email Notifications (Optional)

Add email to crontab for error notifications:

```bash
MAILTO=your-email@example.com

# Your cron jobs below...
15 9 * * 1-5 cd /path/to/backend && venv/bin/python3 manage.py run_all_strategies
```

---

## 🔧 Manual Management

### Test Strategy Execution

```bash
cd backend

# Test for single user
python3 manage.py run_strategy_alpha chandralingam

# Test for all users
python3 manage.py run_all_strategies --strategy strategy_alpha

# Force demo mode (safe testing)
python3 manage.py run_all_strategies --strategy strategy_alpha --mode demo
```

---

### Edit Cron Jobs

```bash
# Open crontab editor
crontab -e

# Make changes, save and exit
# Cron will automatically reload
```

---

### Disable Scheduler Temporarily

```bash
# Comment out jobs in crontab
crontab -e

# Add # before each line:
# 15 9 * * 1-5 cd /path/to/backend && venv/bin/python3 manage.py run_all_strategies
```

---

### Remove All Cron Jobs

```bash
# Remove all crontab entries
crontab -r

# Or selectively remove QuantStrike jobs
crontab -e
# Delete only QuantStrike lines
```

---

## 🔐 Production Setup

### SSH Access Setup

```bash
# 1. Connect to production
ssh username@production-server-ip

# 2. Navigate to app directory
cd /path/to/QuantStrike

# 3. Pull latest changes
git pull origin main

# 4. Install dependencies
cd backend
source venv/bin/activate
pip install -r requirements.txt

# 5. Run scheduler setup
cd ..
./deploy-scheduler.sh

# 6. Verify setup
crontab -l
```

---

### Security Considerations

1. **Use Environment Variables**

   ```bash
   # Store in .env file
   DJANGO_SECRET_KEY=your-secret-key
   DATABASE_PASSWORD=your-db-password
   ```

2. **Restrict File Permissions**

   ```bash
   chmod 600 backend/.env
   chmod 700 backend/logs/
   ```

3. **Monitor Logs Regularly**
   ```bash
   # Set up log rotation
   sudo vi /etc/logrotate.d/quantstrike
   ```

---

## 📈 Success Metrics

After setup, you should see:

- ✅ Cron jobs listed in `crontab -l`
- ✅ Log files created in `backend/logs/`
- ✅ Strategies executing at 9:15 AM daily
- ✅ Trades being opened automatically
- ✅ Monitors starting for each user
- ✅ Trades closing at SL/TP/EOD

---

## 🆘 Support

If you encounter issues:

1. **Check Logs:** Review execution logs in `backend/logs/`
2. **Test Manually:** Run commands manually to identify errors
3. **Verify Paths:** Ensure all paths in crontab are absolute
4. **Check Permissions:** Verify file and directory permissions
5. **Contact Admin:** Provide log excerpts for debugging

---

## 📝 Notes

- **Timezone:** All times are IST (India Standard Time)
- **Trading Days:** Monday to Friday only
- **Holidays:** Cron runs even on market holidays (strategies skip automatically)
- **Monitor Service:** Auto-starts when trades open, auto-stops when trades close
- **Product Type:** INTRADAY (MIS) - broker squares off at EOD automatically

---

**Last Updated:** 29 December 2025  
**Version:** 1.0
