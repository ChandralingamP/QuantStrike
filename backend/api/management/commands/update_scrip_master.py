"""Management command to download and process scrip master data daily.

This command should be run once per day (e.g., at 5 AM before market opens) to:
1. Download the latest scrip master from Angel Broking API
2. Extract and optimize option contracts for NIFTY, BANKNIFTY, SENSEX
3. Generate local JSON files for fast access during trading hours
4. Update instruments_expiries.json with current expiry dates

Usage:
    python manage.py update_scrip_master
    python manage.py update_scrip_master --force  # Force update even if recent
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Set

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Download scrip master and generate optimized local JSON files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force update even if files were recently updated",
        )

    def handle(self, *args, **options):
        force_update = options.get("force", False)
        
        # Define file paths
        data_dir = settings.BASE_DIR / "data"
        data_dir.mkdir(exist_ok=True)
        
        instruments_file = data_dir / "instruments.json"
        expiries_file = data_dir / "instruments_expiries.json"
        
        # Check if update is needed
        if not force_update and instruments_file.exists():
            file_age = datetime.now() - datetime.fromtimestamp(instruments_file.stat().st_mtime)
            if file_age < timedelta(hours=12):
                self.stdout.write(
                    self.style.WARNING(
                        f"Scrip master was updated {file_age.seconds // 3600} hours ago. "
                        "Use --force to update anyway."
                    )
                )
                return
        
        self.stdout.write("📥 Downloading scrip master from Angel Broking...")
        
        try:
            # Download scrip master
            url = (
                "https://margincalculator.angelbroking.com/OpenAPI_File/files/"
                "OpenAPIScripMaster.json"
            )
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            scrip_data = response.json()
            
            self.stdout.write(
                self.style.SUCCESS(f"✅ Downloaded {len(scrip_data)} instruments")
            )
            
            # Process and optimize data
            self.stdout.write("🔄 Processing option contracts...")
            
            instruments, expiries = self._process_scrip_data(scrip_data)
            
            # Save instruments.json
            with instruments_file.open("w", encoding="utf-8") as f:
                json.dump(instruments, f, indent=2, ensure_ascii=False)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Saved {len(instruments)} option contracts to {instruments_file}"
                )
            )
            
            # Save instruments_expiries.json
            with expiries_file.open("w", encoding="utf-8") as f:
                json.dump(expiries, f, indent=2, ensure_ascii=False)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Saved expiry mappings to {expiries_file}"
                )
            )
            
            # Display summary
            self._display_summary(expiries, instruments)
            
        except Exception as exc:
            self.stdout.write(
                self.style.ERROR(f"❌ Failed to update scrip master: {exc}")
            )
            logger.exception("Error updating scrip master")
            raise

    def _process_scrip_data(
        self, scrip_data: List[Dict]
    ) -> tuple[List[Dict], Dict[str, List[str]]]:
        """Process scrip master and extract option contracts."""
        
        # Target underlyings
        target_underlyings = {"NIFTY", "BANKNIFTY", "SENSEX"}
        
        instruments = []
        expiry_map: Dict[str, Set[str]] = {name: set() for name in target_underlyings}
        
        for item in scrip_data:
            name = (item.get("name") or "").upper().strip()
            
            # Filter only our target underlyings
            if name not in target_underlyings:
                continue
            
            # Must be an option
            instrument_type = (item.get("instrumenttype") or "").upper()
            if instrument_type not in ("OPTIDX", "OPTSTK"):
                continue
            
            symbol = item.get("symbol", "")
            
            # Must end with CE or PE
            if not (symbol.endswith("CE") or symbol.endswith("PE")):
                continue
            
            # Parse strike price
            try:
                strike_raw = item.get("strike", 0)
                if strike_raw == 0:
                    continue
                strike = float(strike_raw)
            except (ValueError, TypeError):
                continue
            
            # Parse expiry
            expiry_str = (item.get("expiry") or "").strip()
            if not expiry_str:
                continue
            
            expiry_dt = self._parse_expiry(expiry_str)
            if not expiry_dt:
                continue
            
            # Store expiry in standardized format
            expiry_standardized = expiry_dt.strftime("%d%b%Y").upper()
            expiry_map[name].add(expiry_standardized)
            
            # Extract relevant fields
            instrument = {
                "token": str(item.get("token", "")),
                "symbol": symbol,
                "name": name,
                "expiry": expiry_standardized,
                "strike": str(strike),
                "lotsize": str(item.get("lotsize", "1")),
                "instrumenttype": instrument_type,
                "exch_seg": item.get("exch_seg", "NFO"),
                "tick_size": str(item.get("tick_size", "5.00")),
            }
            
            instruments.append(instrument)
        
        # Convert sets to sorted lists and filter to 3 months (current + next 2)
        expiry_dict = {}
        current_date = datetime.now()
        # Calculate end of next 2 months from current month
        # E.g., if current is Dec 2025, include Dec 2025, Jan 2026, Feb 2026
        cutoff_date = current_date.replace(day=1) + timedelta(days=90)  # ~3 months
        
        for name, expiries in expiry_map.items():
            # Parse and filter expiries: must be future dates within 3 months
            filtered_expiries = []
            for exp in expiries:
                exp_dt = self._parse_expiry(exp)
                # Only include expiries that are today or in the future, and within 3 months
                if exp_dt and exp_dt.date() >= current_date.date() and exp_dt <= cutoff_date:
                    filtered_expiries.append(exp)
            
            # Sort filtered expiries
            sorted_expiries = sorted(
                filtered_expiries,
                key=lambda x: self._parse_expiry(x) or datetime.min
            )
            expiry_dict[name] = sorted_expiries
        
        # Filter instruments to only include those with expiries in our 3-month window
        valid_expiries = set()
        for expiry_list in expiry_dict.values():
            valid_expiries.update(expiry_list)
        
        instruments = [
            inst for inst in instruments
            if inst["expiry"] in valid_expiries
        ]
        
        # Sort instruments by name, expiry, strike
        instruments.sort(
            key=lambda x: (
                x["name"],
                self._parse_expiry(x["expiry"]) or datetime.min,
                float(x["strike"]),
                x["symbol"],
            )
        )
        
        return instruments, expiry_dict

    def _parse_expiry(self, expiry_str: str) -> datetime | None:
        """Parse expiry date from various formats."""
        cleaned = (expiry_str or "").strip().upper()
        for fmt in ("%d%b%Y", "%d%b%y", "%d-%b-%Y", "%d-%b-%y"):
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
        return None

    def _display_summary(self, expiries: Dict, instruments: List[Dict]):
        """Display summary of processed data."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("📊 Summary")
        self.stdout.write("=" * 60)
        
        for name in sorted(expiries.keys()):
            count = sum(1 for i in instruments if i["name"] == name)
            expiry_list = expiries[name]
            
            self.stdout.write(f"\n{name}:")
            self.stdout.write(f"  Contracts: {count}")
            self.stdout.write(f"  Expiries: {len(expiry_list)}")
            
            if expiry_list:
                # Show next 3 expiries
                self.stdout.write("  Next expiries:")
                for exp in expiry_list[:3]:
                    exp_dt = self._parse_expiry(exp)
                    if exp_dt:
                        days_to_expiry = (exp_dt.date() - datetime.now().date()).days
                        self.stdout.write(f"    - {exp} ({days_to_expiry} days)")
        
        self.stdout.write("\n" + "=" * 60)
