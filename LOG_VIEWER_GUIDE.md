# Strategy Log Viewer Guide

## Overview

A standalone web page to view strategy execution logs in real-time without integrating with the main trading app.

## Access the Log Viewer

### Production URL

Navigate directly to: **http://13.203.224.240/logs**

⚠️ **Important**: You must be logged in to the QuantStrike app first to access logs.

## Features

### 1. **Log Files Sidebar**

- Lists all user strategy log files
- Shows username, file size, and last modified time
- Click any file to view its contents
- "Refresh" button to reload the file list

### 2. **Log Content Viewer**

- Displays log file contents with syntax highlighting
- Dark theme optimized for readability
- Scrollable view for large log files

### 3. **Controls**

- **Lines Dropdown**: Select how many lines to display (100, 500, 1000, 2000, 5000)
- **Auto-refresh Toggle**: Enable to automatically refresh logs every 5 seconds
- **Refresh Button**: Manually reload the current log file

### 4. **File Information**

Shows metadata about the selected log:

- Filename
- File size (MB)
- Last modified timestamp
- Number of lines displayed

## What the Logs Show

Each log file contains detailed strategy execution information:

✅ **Execution Start/End** - Timestamps for each strategy run
✅ **Instruments Processed** - Which instruments (NIFTY, BANKNIFTY, etc.)
✅ **Market Data** - Current price, volume, contract details
✅ **Condition Checks** - Breakout detection, gap analysis, entry signals
✅ **Trade Decisions** - Why trades were or weren't taken
✅ **Open Trades** - Monitoring of existing positions with P&L
✅ **Execution Summary** - Opened/closed trades, net P&L

## Log Format Example

```
2026-03-01 12:43:41 | INFO | ═════════════════════════════════════════════
2026-03-01 12:43:41 | INFO | STRATEGY ALPHA EXECUTION - chandralingam
2026-03-01 12:43:41 | INFO | ═════════════════════════════════════════════
2026-03-01 12:43:41 | INFO | Mode: demo
2026-03-01 12:43:41 | INFO | ═══ Processing NIFTY ═══
2026-03-01 12:43:41 | INFO | Active: True, Direction: BUY, Lots: 1
2026-03-01 12:43:41 | INFO | 📊 Market Data: Price: 24850.50, Volume: 125000
2026-03-01 12:43:41 | INFO | ✅ Breakout detected above 24800
2026-03-01 12:43:41 | INFO | 🎯 Entry signal generated
```

## Authentication

The log viewer requires authentication:

1. First, login to the main QuantStrike app at http://13.203.224.240/
2. Once logged in, navigate to http://13.203.224.240/logs
3. Your authentication token is automatically used

If you see "Not authenticated. Please login first.", go back to the main app and login.

## Log Retention

- Logs are automatically retained for **5 days**
- A cron job runs daily at midnight UTC to clean up old logs
- This prevents disk space issues while keeping recent history

## Troubleshooting

### "No log files found"

- Strategy hasn't run yet for any user
- Check if the cron job is configured: `45 3 * * 1-5` (runs at 9:15 AM IST)
- Logs directory may be empty

### "Failed to fetch log files"

- Check if you're logged in
- Verify backend is running: `sudo systemctl status gunicorn`
- Check nginx is running: `sudo systemctl status nginx`

### Empty log content

- The log file exists but has no content yet
- Strategy may not have executed
- Check if it's during trading hours (9:15 AM - 3:30 PM IST)

## Technical Details

### API Endpoints

- `GET /api/logs/files/` - List all log files
- `GET /api/logs/content/?filename=<name>&lines=<count>&tail=true` - Get log content

### Log File Location (Server)

```
/var/www/QuantStrike/backend/logs/users/{username}_strategy.log
```

### Frontend Route

```
/logs - Standalone page (no app layout/navigation)
```

## Tips

1. **Use Auto-refresh** during trading hours to see real-time execution
2. **Increase lines** if you need to see more history
3. **Download logs** by copying the content if needed for analysis
4. **Check timestamps** to correlate with actual trade times
5. **Look for ERROR** messages to debug issues

## Privacy & Security

- ✅ Authentication required - no public access
- ✅ Only shows logs for authenticated users
- ✅ No direct file system access from web
- ✅ Path traversal protection implemented
- ✅ Automatic cleanup prevents log accumulation
