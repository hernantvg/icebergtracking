from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import os
import time
import threading
import db_manager
import scraper

app = Flask(__name__)

# Secure static secret key for persistent administrator sessions
app.secret_key = "polar_sentinel_encryption_secret_key_2026_secure_key"

# Random, high-security admin password
ADMIN_PASSWORD = "IceSentinel_#9t8P_v2026!"

# Flag to prevent multiple concurrent imports
_sync_lock = threading.Lock()

def start_daily_scheduler():
    """Launches a daemon background thread that runs daily sync automation."""
    # Prevent launching twice during Werkzeug reloader startup in debug mode
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and app.debug:
        return
        
    def scheduler_loop():
        print("Daily background synchronization scheduler started.")
        # Sleep for 10 seconds initially on startup to let the app fully initialize
        time.sleep(10)
        while True:
            print("Executing scheduled daily USNIC data synchronization...")
            try:
                status_msg, filepath, filename = scraper.scrape_usnic_latest_csv()
                if filepath:
                    files, rows = db_manager.import_all_csvs(force=False)
                    print(f"Daily Sync Complete: {status_msg}. Ingested {rows} new records.")
                else:
                    print(f"Daily Sync Log: {status_msg}")
            except Exception as e:
                print(f"Error during automated daily sync: {e}")
            
            # Sleep for 24 hours (86,400 seconds)
            time.sleep(86400)
            
    thread = threading.Thread(target=scheduler_loop)
    thread.daemon = True
    thread.start()

def initialize_application():
    """Initializes the database, pre-loads historical data, and starts the automation scheduler."""
    print("Initializing Iceberg Sentinel backend...")
    db_manager.init_db()
    
    # Check if database is populated
    stats = db_manager.get_db_stats()
    if stats["total_records"] == 0:
        print("Database is empty. Initiating background historical CSV data load...")
        # Run in a background thread to allow the server to start instantly
        thread = threading.Thread(target=db_manager.import_all_csvs)
        thread.daemon = True
        thread.start()
    else:
        print(f"Database ready. Loaded {stats['total_records']} reports across {stats['unique_icebergs']} unique icebergs.")

    # Start the automated daily scheduler
    start_daily_scheduler()

# Trigger startup checks
initialize_application()

@app.route('/')
def index():
    """Renders the central system Dashboard."""
    # We pass active icebergs for the search autocomplete feature
    icebergs = db_manager.get_active_icebergs()
    return render_template('index.html', icebergs=icebergs)

@app.route('/tracking')
def tracking():
    """Renders the Trajectory Tracking interface."""
    icebergs = db_manager.get_active_icebergs()
    return render_template('tracking.html', icebergs=icebergs)

@app.route('/sync')
def sync_panel():
    """Renders the System Administration and Synchronization dashboard if authenticated."""
    if not session.get('admin_logged_in'):
        return redirect(url_for('login', next=request.path))
    return render_template('sync.html')

@app.route('/about')
def about():
    """Renders the educational and scientific about page."""
    return render_template('about.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles administrator authentication interface."""
    error = None
    next_page = request.args.get('next', '/')
    
    # If already logged in, redirect straight to next page
    if session.get('admin_logged_in'):
        return redirect(next_page)
        
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(next_page)
        else:
            error = "Invalid administrator key. Access denied."
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    """Logs out the administrator and clears session credentials."""
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

# ==========================================
#              REST API ENDPOINTS
# ==========================================

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Returns database and iceberg analytics statistics."""
    try:
        stats = db_manager.get_db_stats()
        return jsonify({"status": "success", "data": stats})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/latest-positions', methods=['GET'])
def api_latest_positions():
    """Returns the most recent coordinates and metrics of all tracked icebergs."""
    try:
        positions = db_manager.get_latest_positions()
        return jsonify({"status": "success", "count": len(positions), "data": positions})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/iceberg/<name>', methods=['GET'])
def api_iceberg_detail(name):
    """Returns complete chronological coordinates, area history, and status of a single iceberg."""
    try:
        trajectory = db_manager.get_trajectory(name)
        if not trajectory:
            return jsonify({"status": "error", "message": f"Iceberg '{name}' not found."}), 404
            
        return jsonify({
            "status": "success",
            "iceberg": name.upper(),
            "count": len(trajectory),
            "data": trajectory
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/sync-data', methods=['POST'])
def api_sync_data():
    """Triggers data scraper to fetch USNIC updates and ingestion logic (Admin-only)."""
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error", "message": "Unauthorized. Administrator key required."}), 401
        
    if not _sync_lock.acquire(blocking=False):
        return jsonify({
            "status": "error",
            "message": "Synchronization is already in progress. Please wait for the current job to complete."
        }), 409
        
    try:
        # Run scraping logic
        status_msg, filepath, filename = scraper.scrape_usnic_latest_csv()
        
        db_updates = 0
        files_processed = 0
        
        # If scraper found new files or fallback succeeded, run ingestion
        if filepath:
            # We import all newly added CSVs in our folder
            files_processed, db_updates = db_manager.import_all_csvs(force=False)
            
        return jsonify({
            "status": "success",
            "message": status_msg,
            "files_processed": files_processed,
            "records_inserted": db_updates
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        _sync_lock.release()

@app.route('/api/rebuild-db', methods=['POST'])
def api_rebuild_db():
    """Deletes and rebuilds database from all local CSV files (Admin-only)."""
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error", "message": "Unauthorized. Administrator key required."}), 401
        
    if not _sync_lock.acquire(blocking=False):
        return jsonify({
            "status": "error",
            "message": "Rebuilding/Synchronization in progress. Action locked."
        }), 409
        
    try:
        files_processed, db_updates = db_manager.import_all_csvs(force=True)
        return jsonify({
            "status": "success",
            "message": "Database successfully wiped and rebuilt from local CSV archives.",
            "files_processed": files_processed,
            "records_inserted": db_updates
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        _sync_lock.release()

if __name__ == '__main__':
    app.run(debug=True)