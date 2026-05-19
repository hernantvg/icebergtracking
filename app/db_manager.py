import os
import sqlite3
import pandas as pd
from datetime import datetime

# Path to the SQLite database file
DB_PATH = os.path.join(os.path.dirname(__file__), "icebergs.db")
CSV_DIR = os.path.join(os.path.dirname(__file__), "csv")

def get_db_connection():
    """Establish a connection to the SQLite database with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database schema and establish indexes."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create main icebergs tracking table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS icebergs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        iceberg TEXT NOT NULL,
        length_nm REAL,
        width_nm REAL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        remarks TEXT,
        area_sqmi REAL,
        area_sqnm REAL,
        area_sqkm REAL,
        last_update TEXT NOT NULL,
        source_file TEXT,
        UNIQUE(iceberg, last_update) ON CONFLICT REPLACE
    )
    """)
    
    # Indexes to drastically improve query performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_icebergs_name ON icebergs(iceberg)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_icebergs_date ON icebergs(last_update DESC)")
    
    conn.commit()
    conn.close()
    print("SQLite Database initialized and indexed.")

def clean_date(date_val):
    """Normalize date inputs to YYYY-MM-DD format."""
    if pd.isna(date_val) or not str(date_val).strip():
        return None
    
    date_str = str(date_val).strip()
    # Try parsing common formats
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%y", "%d/%m/%y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
            
    # Try pandas timestamp conversion fallback
    try:
        dt = pd.to_datetime(date_str, errors='raise')
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
        
    return date_str  # Return original if parsing fails

def import_single_csv(filepath, conn):
    """Parse a single CSV file, clean, normalize schema, and bulk insert into SQLite."""
    filename = os.path.basename(filepath)
    try:
        # Load CSV using pandas
        df = pd.read_csv(filepath, on_bad_lines='skip')
        if df.empty:
            return 0
            
        # Clean column names (strip spaces, resolve casing)
        df.columns = [col.strip() for col in df.columns]
        
        # Verify required columns exist
        required_cols = ['Iceberg', 'Latitude', 'Longitude', 'Last Update']
        missing_reqs = [col for col in required_cols if col not in df.columns]
        if missing_reqs:
            print(f"Skipping {filename}: Missing core columns: {missing_reqs}")
            return 0
            
        inserted_count = 0
        cursor = conn.cursor()
        
        # Extract columns dynamically (accommodating differences between older and newer reports)
        for _, row in df.iterrows():
            iceberg_name = str(row['Iceberg']).strip().upper()
            if not iceberg_name or pd.isna(row['Latitude']) or pd.isna(row['Longitude']):
                continue
                
            latitude = float(row['Latitude'])
            longitude = float(row['Longitude'])
            
            # Format and validate date
            last_update = clean_date(row['Last Update'])
            if not last_update:
                continue
                
            # Optional parameters (handle dynamic columns across years)
            length_nm = float(row['Length (NM)']) if 'Length (NM)' in row and not pd.isna(row['Length (NM)']) else None
            width_nm = float(row['Width (NM)']) if 'Width (NM)' in row and not pd.isna(row['Width (NM)']) else None
            remarks = str(row['Remarks']).strip() if 'Remarks' in row and not pd.isna(row['Remarks']) else None
            
            area_sqmi = float(row['Area (sqMI)']) if 'Area (sqMI)' in row and not pd.isna(row['Area (sqMI)']) else None
            area_sqnm = float(row['Area (sqNM)']) if 'Area (sqNM)' in row and not pd.isna(row['Area (sqNM)']) else None
            area_sqkm = float(row['Area (sqKM)']) if 'Area (sqKM)' in row and not pd.isna(row['Area (sqKM)']) else None
            
            # Try to calculate approximate area if missing but length & width exist (1 sqNM = 3.43 sqKM)
            if area_sqkm is None and length_nm is not None and width_nm is not None:
                # Approximation: icebergs are often approximated as rectangular or elliptical
                # Let's use simple multiplication as a rough estimate
                area_sqnm_calc = length_nm * width_nm
                area_sqkm = area_sqnm_calc * 3.43
                area_sqnm = area_sqnm_calc
                area_sqmi = area_sqnm_calc * 1.32
            
            try:
                cursor.execute("""
                INSERT INTO icebergs (
                    iceberg, length_nm, width_nm, latitude, longitude, remarks,
                    area_sqmi, area_sqnm, area_sqkm, last_update, source_file
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(iceberg, last_update) DO UPDATE SET
                    length_nm = COALESCE(excluded.length_nm, length_nm),
                    width_nm = COALESCE(excluded.width_nm, width_nm),
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    remarks = COALESCE(excluded.remarks, remarks),
                    area_sqmi = COALESCE(excluded.area_sqmi, area_sqmi),
                    area_sqnm = COALESCE(excluded.area_sqnm, area_sqnm),
                    area_sqkm = COALESCE(excluded.area_sqkm, area_sqkm),
                    source_file = excluded.source_file
                """, (
                    iceberg_name, length_nm, width_nm, latitude, longitude, remarks,
                    area_sqmi, area_sqnm, area_sqkm, last_update, filename
                ))
                inserted_count += 1
            except Exception as insert_err:
                print(f"Error inserting row in {filename}: {insert_err}")
                
        return inserted_count
    except Exception as e:
        print(f"Failed to process CSV file {filepath}: {e}")
        return 0

def import_all_csvs(force=False):
    """
    Scans the csv folder (including archives) and parses all files into the SQLite database.
    Optimized by committing once at the end and tracking imported files.
    """
    init_db()
    conn = get_db_connection()
    
    # Gather all CSV files
    csv_files = []
    
    # 1. Look in base folder
    if os.path.exists(CSV_DIR):
        for f in os.listdir(CSV_DIR):
            if f.lower().endswith(".csv"):
                csv_files.append(os.path.join(CSV_DIR, f))
                
    # 2. Look in archive folder
    archive_dir = os.path.join(CSV_DIR, "archive")
    if os.path.exists(archive_dir):
        for f in os.listdir(archive_dir):
            if f.lower().endswith(".csv"):
                csv_files.append(os.path.join(archive_dir, f))
                
    print(f"Found {len(csv_files)} CSV files to process.")
    
    if not csv_files:
        conn.close()
        return 0, 0
        
    # Check already imported files to avoid redundant work unless force=True
    imported_files = set()
    if not force:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT source_file FROM icebergs WHERE source_file IS NOT NULL")
        imported_files = {row['source_file'] for row in cursor.fetchall()}
        
    processed_files_count = 0
    total_inserted_rows = 0
    
    # Turn off synchronous writing and journal mode temporarily for maximum bulk load speed
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = MEMORY")
    
    for idx, filepath in enumerate(csv_files):
        filename = os.path.basename(filepath)
        if filename in imported_files:
            continue
            
        rows_inserted = import_single_csv(filepath, conn)
        total_inserted_rows += rows_inserted
        processed_files_count += 1
        
        # Periodic output log for tracking
        if processed_files_count % 50 == 0 or idx == len(csv_files) - 1:
            print(f"Processed {processed_files_count} new files... Total imported: {total_inserted_rows} rows.")
            
    conn.commit()
    conn.close()
    
    print(f"Data ingestion complete. Processed {processed_files_count} files, inserted/updated {total_inserted_rows} records.")
    return processed_files_count, total_inserted_rows

def get_active_icebergs():
    """Retrieve list of unique tracked icebergs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT iceberg FROM icebergs ORDER BY iceberg ASC")
    icebergs = [row['iceberg'] for row in cursor.fetchall()]
    conn.close()
    return icebergs

def get_latest_positions():
    """
    Get the most recent observation data for all unique tracked icebergs.
    Utilizes SQL window functions for maximum performance.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
    WITH RankedPositions AS (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY iceberg ORDER BY last_update DESC) as rn
        FROM icebergs
    )
    SELECT *
    FROM RankedPositions
    WHERE rn = 1
    ORDER BY iceberg ASC
    """
    cursor.execute(query)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_trajectory(iceberg_name):
    """Retrieve chronological tracking trajectory history for a single iceberg."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM icebergs 
        WHERE iceberg = ? 
        ORDER BY last_update ASC
    """, (iceberg_name.strip().upper(),))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_db_stats():
    """Retrieve full database statistics and summary parameters."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Total records count
    cursor.execute("SELECT COUNT(*) FROM icebergs")
    total_records = cursor.fetchone()[0]
    
    # 2. Unique icebergs count
    cursor.execute("SELECT COUNT(DISTINCT iceberg) FROM icebergs")
    unique_icebergs = cursor.fetchone()[0]
    
    # 3. Date Range
    cursor.execute("SELECT MIN(last_update), MAX(last_update) FROM icebergs")
    min_date, max_date = cursor.fetchone()
    
    # 4. Details of the largest active iceberg (by area)
    largest_iceberg = None
    query_largest = """
    WITH Latest AS (
        SELECT iceberg, area_sqkm, length_nm, width_nm, latitude, longitude, last_update,
               ROW_NUMBER() OVER (PARTITION BY iceberg ORDER BY last_update DESC) as rn
        FROM icebergs
        WHERE area_sqkm IS NOT NULL
    )
    SELECT iceberg, area_sqkm, length_nm, width_nm, latitude, longitude, last_update
    FROM Latest
    WHERE rn = 1
    ORDER BY area_sqkm DESC
    LIMIT 1
    """
    cursor.execute(query_largest)
    largest_row = cursor.fetchone()
    if largest_row:
        largest_iceberg = dict(largest_row)
        
    # 5. Database file size
    db_size_mb = 0
    if os.path.exists(DB_PATH):
        db_size_mb = round(os.path.getsize(DB_PATH) / (1024 * 1024), 2)
        
    conn.close()
    
    return {
        "total_records": total_records,
        "unique_icebergs": unique_icebergs,
        "date_range": f"{min_date} to {max_date}" if min_date and max_date else "N/A",
        "largest_iceberg": largest_iceberg,
        "db_size_mb": db_size_mb
    }
