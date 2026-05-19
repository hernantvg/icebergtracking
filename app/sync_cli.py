#!/usr/bin/env python3
"""
Iceberg Sentinel CLI - Scheduled Synchronization Utility
Designed to be executed programmatically via system schedulers like crontab or Windows Task Scheduler.
Bypasses HTTP session authorization checks by running locally on the host server.
"""
import sys
import os

# Ensure the app folder is in the python resolution path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import scraper
import db_manager

def execute_scheduled_sync():
    print("==================================================")
    print("      Iceberg Sentinel Scheduled CLI Sync         ")
    print("==================================================")
    
    try:
        # 1. Initialize database schema
        db_manager.init_db()
        
        # 2. Scrape USNIC portal or fallback to retrieve the latest CSV
        status_msg, filepath, filename = scraper.scrape_usnic_latest_csv()
        print(f"[*] Scraper Response: {status_msg}")
        
        if filepath:
            # 3. Ingest new reports into the indexed database
            files_processed, records_inserted = db_manager.import_all_csvs(force=False)
            print(f"[+] Sync Successful. Ingested {records_inserted} positions from {files_processed} files.")
            sys.exit(0)  # Standard success exit code
        else:
            print("[-] No new tracking logs discovered. Database is up to date.")
            sys.exit(0)
            
    except Exception as e:
        print(f"[!] CRITICAL ERROR during cron execution: {e}", file=sys.stderr)
        sys.exit(1)  # Return exit code 1 to indicate failure to cron system

if __name__ == "__main__":
    execute_scheduled_sync()
