#!/bin/bash

# Quick Deployment Script - Run this to deploy to production
# This script provides the exact commands to run on EC2

echo "=================================================="
echo "🚀 QuantStrike Production Deployment"
echo "=================================================="
echo ""
echo "✅ Code has been pushed to GitHub (main branch)"
echo ""
echo "Now SSH into your EC2 server and run these commands:"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
cat << 'EOF'
# Step 1: SSH into EC2
ssh ec2-user@13.203.224.240
# or with your key:
# ssh -i ~/.ssh/your-key.pem ec2-user@13.203.224.240

# Step 2: Run deployment script
cd /var/www/QuantStrike
./deploy-prod.sh

# Step 3: Generate missing instrument data files
cd /var/www/QuantStrike/backend
python manage.py update_scrip_master

# Step 4: Verify everything is working
bash ../check-instruments.sh

# Step 5: Restart services
sudo systemctl restart gunicorn
sudo systemctl restart nginx

# Done! Test in browser: http://13.203.224.240
EOF
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎯 What's been fixed:"
echo "  • Instrument update validation now handles missing data"
echo "  • Deployment script auto-checks for instrument files"
echo "  • Better error messages with available expiries"
echo "  • Diagnostic tool to check system health"
echo ""
echo "📋 After deployment, verify:"
echo "  1. Can update instruments in the UI"
echo "  2. Expiries are showing correctly"
echo "  3. No errors in browser console"
echo ""
echo "=================================================="
