import json
import mysql.connector
from pathlib import Path
from datetime import datetime

# --- Configuration ---
# Path to the JSON log file
LOG_FILE_PATH = r"d:\PredectiveIntelligenceSystem\flow\logs\audit_log.json" 

# MySQL Database connection parameters
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "Telecom_Activity",
    "port": 3306
}
# ---------------------

def backfill_audit_logs(LOG_PATH,DB_CONFIG):
    log_file = Path(LOG_PATH)
    
    if not log_file.exists():
        print(f"Error: Log file '{LOG_FILE_PATH}' not found.")
        return

    try:
        # Establish database connection
        print("Connecting to MySQL database...")
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # SQL Insert Statement
        insert_sql = """
            INSERT INTO audit_log 
            (event_type, status, filename, row_count, error_message, duration_seconds, processed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        records_inserted = 0
        records_failed = 0

        print(f"Reading logs from {LOG_FILE_PATH}...")
        
        with open(log_file, "r") as file:
            for line_num, line in enumerate(file, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    entry = json.loads(line)
                    
                    # Safely map JSON fields to database columns
                    values = (
                        "FILE_PROCESSING",                                # event_type (default)
                        entry.get("status"),                              # status
                        entry.get("filename"),                            # filename
                        entry.get("row_count", 0),                        # row_count
                        entry.get("reason", entry.get("error_message")),  # error_message
                        entry.get("duration_seconds", 0.0),               # duration_seconds
                        entry.get("processed_at", datetime.now().isoformat()) # processed_at
                    )
                    
                    cursor.execute(insert_sql, values)
                    records_inserted += 1
                    
                except json.JSONDecodeError:
                    print(f"Warning: Failed to parse JSON on line {line_num}: {line}")
                    records_failed += 1
                except Exception as e:
                    print(f"Error inserting line {line_num}: {e}")
                    records_failed += 1

        # Commit the transaction
        conn.commit()
        
        print("\n--- Backfill Summary ---")
        print(f"Successfully inserted: {records_inserted} records")
        print(f"Failed to process: {records_failed} records")

    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
    finally:
        if 'cursor' in locals() and cursor is not None:
            cursor.close()
        if 'conn' in locals() and conn.is_connected():
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    backfill_audit_logs()