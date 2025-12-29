#!/bin/bash
#
# QuantStrike Automated Scheduler Setup Script
# 
# This script sets up cron jobs for:
# 1. Daily instrument data refresh (7:00 AM IST)
# 2. Daily strategy execution (9:15 AM IST)
# 3. Monitoring all trading days (Monday-Friday)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  QuantStrike Automated Scheduler Setup${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

# Get the script directory (works for both local and production)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
VENV_DIR="$BACKEND_DIR/venv"

# Check if running on production or local
if [[ "$SCRIPT_DIR" == "/home"* ]] || [[ "$SCRIPT_DIR" == "/root"* ]] || [[ "$SCRIPT_DIR" == "/opt"* ]]; then
    ENVIRONMENT="production"
    echo -e "${GREEN}✓ Detected: Production environment${NC}"
else
    ENVIRONMENT="local"
    echo -e "${YELLOW}⚠ Detected: Local/Development environment${NC}"
fi

echo "   Script Dir: $SCRIPT_DIR"
echo "   Backend Dir: $BACKEND_DIR"
echo "   Environment: $ENVIRONMENT"
echo ""

# Check if backend directory exists
if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}✗ Error: Backend directory not found at $BACKEND_DIR${NC}"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}⚠ Virtual environment not found. Creating...${NC}"
    cd "$BACKEND_DIR"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment found${NC}"
fi

# Create log directory
LOG_DIR="$BACKEND_DIR/logs"
mkdir -p "$LOG_DIR"
echo -e "${GREEN}✓ Log directory created: $LOG_DIR${NC}"
echo ""

# Create cron job entries
echo -e "${BLUE}Creating cron job entries...${NC}"
echo ""

CRON_FILE="/tmp/quantstrike_cron.txt"
cat > "$CRON_FILE" << EOF
# QuantStrike Automated Trading Scheduler
# Generated on: $(date)
# Environment: $ENVIRONMENT

# 1. Update instruments and expiry data (7:00 AM IST, Mon-Fri)
0 7 * * 1-5 cd $BACKEND_DIR && $VENV_DIR/bin/python3 manage.py update_scrip_master >> $LOG_DIR/instruments.log 2>&1

# 2. Load instrument metadata (7:05 AM IST, Mon-Fri)
5 7 * * 1-5 cd $BACKEND_DIR && $VENV_DIR/bin/python3 manage.py load_instrument_metadata >> $LOG_DIR/metadata.log 2>&1

# 3. Run strategies for all active users (9:15 AM IST, Mon-Fri)
15 9 * * 1-5 cd $BACKEND_DIR && $VENV_DIR/bin/python3 manage.py run_all_strategies --strategy strategy_alpha >> $LOG_DIR/strategies.log 2>&1

EOF

echo -e "${GREEN}✓ Cron jobs configuration:${NC}"
echo ""
cat "$CRON_FILE"
echo ""

# Prompt user to install cron jobs
echo -e "${YELLOW}Would you like to install these cron jobs? (y/n)${NC}"
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
    # Backup existing crontab
    crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt 2>/dev/null || true
    
    # Add new cron jobs (remove old QuantStrike entries first)
    (crontab -l 2>/dev/null | grep -v "QuantStrike\|update_scrip_master\|load_instrument_metadata\|run_all_strategies" || true; cat "$CRON_FILE") | crontab -
    
    echo -e "${GREEN}✓ Cron jobs installed successfully!${NC}"
    echo ""
    echo -e "${GREEN}Current crontab:${NC}"
    crontab -l | grep -A 10 "QuantStrike"
else
    echo -e "${YELLOW}⚠ Cron jobs not installed. Configuration saved to: $CRON_FILE${NC}"
    echo -e "${YELLOW}  To install manually, run: crontab $CRON_FILE${NC}"
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Scheduler setup completed!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}📋 Summary:${NC}"
echo "   • Instruments update: Daily at 7:00 AM IST (Mon-Fri)"
echo "   • Metadata refresh: Daily at 7:05 AM IST (Mon-Fri)"
echo "   • Strategy execution: Daily at 9:15 AM IST (Mon-Fri)"
echo "   • Logs location: $LOG_DIR"
echo ""
echo -e "${BLUE}📝 Logs:${NC}"
echo "   • Instruments: tail -f $LOG_DIR/instruments.log"
echo "   • Metadata: tail -f $LOG_DIR/metadata.log"
echo "   • Strategies: tail -f $LOG_DIR/strategies.log"
echo ""
echo -e "${BLUE}🔧 Management:${NC}"
echo "   • View cron jobs: crontab -l"
echo "   • Edit cron jobs: crontab -e"
echo "   • Remove cron jobs: crontab -r"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT:${NC}"
echo "   1. Ensure Django server is NOT running when cron executes"
echo "   2. Monitor logs for first few days to ensure everything works"
echo "   3. Trades auto-close at 3:35 PM (demo) via monitor service"
echo "   4. Broker auto-squares off at EOD for INTRADAY (MIS) positions"
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
