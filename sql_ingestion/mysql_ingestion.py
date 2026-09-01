"""
MySQL Session Handler and Data Ingestion Module
Handles database connections, transactions, and bulk loading of processed telecom data
from Spark parquet outputs into MySQL analytical tables.
"""

import sqlite3
import mysql.connector
from mysql.connector import Error as MySQLError, pooling
from pathlib import Path
from typing import Dict, Tuple, Any, Optional, List
import logging
from datetime import datetime
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)


class MySQLConnectionPool:
    """
    Manages connection pooling to MySQL database.
    Supports both local SQLite (development) and remote MySQL (production).
    """
    
    def __init__(
        self,
        host: str = 'localhost',
        user: str = 'root',
        password: str = '',
        database: str = 'telecom_analytics',
        port: int = 3306,
        pool_name: str = 'telecom_pool',
        pool_size: int = 5,
        use_sqlite: bool = False,
        sqlite_path: str = None
    ):
        """
        Initialize connection pool.
        
        Args:
            host: MySQL host
            user: MySQL user
            password: MySQL password
            database: Database name
            port: MySQL port
            pool_name: Name for the connection pool
            pool_size: Number of connections in pool
            use_sqlite: If True, use SQLite instead of MySQL
            sqlite_path: Path to SQLite database file
        """
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.port = port
        self.use_sqlite = use_sqlite
        self.sqlite_path = sqlite_path or 'telecom_analytics.db'
        self.pool = None
        
        if not use_sqlite:
            try:
                self.pool = pooling.MySQLConnectionPool(
                    pool_name=pool_name,
                    pool_size=pool_size,
                    pool_reset_session=True,
                    host=host,
                    user=user,
                    password=password,
                    database=database,
                    port=port,
                    autocommit=False
                )
                logger.info(f"✓ MySQL connection pool created ({pool_size} connections)")
            except MySQLError as e:
                logger.error(f"✗ Failed to create MySQL connection pool: {e}")
                raise
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = None
        try:
            if self.use_sqlite:
                conn = sqlite3.connect(self.sqlite_path)
                conn.row_factory = sqlite3.Row
                yield conn
            else:
                conn = self.pool.get_connection()
                yield conn
        except (MySQLError, sqlite3.Error) as e:
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")


class MySQLDataIngestion:
    """
    Handles ingestion of processed telecom data into MySQL.
    Supports both SQLite (development) and MySQL (production).
    """
    
    def __init__(
        self,
        host: str = '127.0.0.1',
        user: str = 'root',
        password: str = 'root',
        database: str = 'TelecomActivity',
        port: int = 3306,
        use_sqlite: bool = False,
        sqlite_path: str = None
    ):
        """
        Initialize MySQL ingestion handler.
        
        Connection String: jdbc:mysql://127.0.0.1:3306/TelecomActivity
        Username: root
        Password: root
        """
        self.pool = MySQLConnectionPool(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
            use_sqlite=use_sqlite,
            sqlite_path=sqlite_path
        )
        self.use_sqlite = use_sqlite
    
    def ingest_from_parquet(
        self,
        parquet_dirs: Dict[str, Path],
        batch_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Ingest processed data from Spark parquet outputs.
        
        Args:
            parquet_dirs: Dictionary of parquet directory paths:
                {
                    'curated_usage': Path,
                    'quarantine': Path,
                    'hourly_grid_summary': Path,
                    'daily_summary': Path,
                    'grid_summary': Path,
                    'enriched_spatial_hourly': Path
                }
            batch_size: Number of rows per batch insert
            
        Returns:
            Dictionary with ingestion statistics
        """
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas required for parquet ingestion. Install with: pip install pandas")
            raise
        
        logger.info("=" * 70)
        logger.info("STARTING PARQUET INGESTION TO DATABASE")
        logger.info("=" * 70)
        
        stats = {
            'curated_usage': 0,
            'quarantine': 0,
            'hourly_grid_summary': 0,
            'daily_summary': 0,
            'grid_summary': 0,
            'enriched_spatial_hourly': 0,
            'errors': []
        }
        
        # Define table mappings
        table_mappings = {
            'curated_usage': ('curated_usage', self._insert_curated_usage),
            'quarantine': ('quarantine', self._insert_quarantine),
            'hourly_grid_summary': ('hourly_grid_summary', self._insert_hourly_grid_summary),
            'daily_summary': ('daily_summary', self._insert_daily_summary),
            'grid_summary': ('grid_summary', self._insert_grid_summary),
            'enriched_spatial_hourly': ('enriched_spatial_hourly', self._insert_enriched_spatial),
        }
        
        for dataset_key, (table_name, insert_func) in table_mappings.items():
            parquet_path = parquet_dirs.get(dataset_key)
            if not parquet_path or not parquet_path.exists():
                logger.warning(f"Skipping {dataset_key}: path not found")
                continue
            
            try:
                logger.info(f"\nIngesting {dataset_key} from {parquet_path}...")
                df = pd.read_parquet(str(parquet_path))
                
                if len(df) == 0:
                    logger.warning(f"  {dataset_key}: empty parquet file")
                    stats[dataset_key] = 0
                    continue
                
                # Normalize column names
                df.columns = df.columns.str.lower()
                
                # Insert using batch processing
                rows_inserted = 0
                for i in range(0, len(df), batch_size):
                    batch = df.iloc[i:i + batch_size]
                    inserted = insert_func(batch)
                    rows_inserted += inserted
                
                logger.info(f"  ✓ {dataset_key}: {rows_inserted} rows inserted")
                stats[dataset_key] = rows_inserted
                
            except Exception as e:
                logger.error(f"  ✗ Error ingesting {dataset_key}: {str(e)}")
                stats['errors'].append({
                    'dataset': dataset_key,
                    'error': str(e)
                })
                continue
        
        logger.info("\n" + "=" * 70)
        logger.info("INGESTION SUMMARY")
        logger.info("=" * 70)
        for key, count in stats.items():
            if key != 'errors':
                logger.info(f"  {key:30s}: {count:,} rows")
        if stats['errors']:
            logger.warning(f"  Errors: {len(stats['errors'])}")
        logger.info("=" * 70)
        
        return stats
    
    def _insert_curated_usage(self, batch: 'pd.DataFrame') -> int:
        """Insert curated (clean) usage data."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor() if not self.use_sqlite else conn
            
            sql = '''
                INSERT INTO curated_usage 
                (timestamp, grid_id, country_code, sms_in_count, sms_out_count, 
                 call_in_count, call_out_count, internet_usage, date, hour, 
                 day_of_week, total_sms, total_calls, total_activity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''' if self.use_sqlite else '''
                INSERT INTO curated_usage 
                (timestamp, grid_id, country_code, sms_in_count, sms_out_count, 
                 call_in_count, call_out_count, internet_usage, date, hour, 
                 day_of_week, total_sms, total_calls, total_activity)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            '''
            
            for _, row in batch.iterrows():
                values = (
                    row.get('timestamp'),
                    int(row.get('grid_id', 0)),
                    row.get('country_code'),
                    float(row.get('sms_in_count', 0)),
                    float(row.get('sms_out_count', 0)),
                    float(row.get('call_in_count', 0)),
                    float(row.get('call_out_count', 0)),
                    float(row.get('internet_usage', 0)),
                    row.get('date'),
                    int(row.get('hour', 0)),
                    int(row.get('day_of_week', 0)),
                    float(row.get('total_sms', 0)),
                    float(row.get('total_calls', 0)),
                    float(row.get('total_activity', 0))
                )
                cursor.execute(sql, values)
            
            conn.commit()
        
        return len(batch)
    
    def _insert_quarantine(self, batch: 'pd.DataFrame') -> int:
        """Insert quarantined (rejected) data."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor() if not self.use_sqlite else conn
            
            sql = '''
                INSERT INTO quarantine 
                (timestamp, grid_id, country_code, sms_in_count, sms_out_count,
                 call_in_count, call_out_count, internet_usage, date, 
                 quarantine_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''' if self.use_sqlite else '''
                INSERT INTO quarantine 
                (timestamp, grid_id, country_code, sms_in_count, sms_out_count,
                 call_in_count, call_out_count, internet_usage, date, 
                 quarantine_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            '''
            
            for _, row in batch.iterrows():
                values = (
                    row.get('timestamp'),
                    row.get('grid_id'),
                    row.get('country_code'),
                    float(row.get('sms_in_count', 0)),
                    float(row.get('sms_out_count', 0)),
                    float(row.get('call_in_count', 0)),
                    float(row.get('call_out_count', 0)),
                    float(row.get('internet_usage', 0)),
                    row.get('date'),
                    row.get('quarantine_reason', 'UNKNOWN')
                )
                cursor.execute(sql, values)
            
            conn.commit()
        
        return len(batch)
    
    def _insert_hourly_grid_summary(self, batch: 'pd.DataFrame') -> int:
        """Insert hourly grid summary aggregates."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor() if not self.use_sqlite else conn
            
            sql = '''
                INSERT INTO hourly_grid_summary
                (date, hour, grid_id, sms_in, sms_out, call_in, call_out,
                 internet_activity, total_activity, record_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''' if self.use_sqlite else '''
                INSERT INTO hourly_grid_summary
                (date, hour, grid_id, sms_in, sms_out, call_in, call_out,
                 internet_activity, total_activity, record_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            '''
            
            for _, row in batch.iterrows():
                values = (
                    row.get('date'),
                    int(row.get('hour', 0)),
                    int(row.get('grid_id', 0)),
                    float(row.get('sms_in', 0)),
                    float(row.get('sms_out', 0)),
                    float(row.get('call_in', 0)),
                    float(row.get('call_out', 0)),
                    float(row.get('internet_activity', 0)),
                    float(row.get('total_activity', 0)),
                    int(row.get('record_count', 0))
                )
                cursor.execute(sql, values)
            
            conn.commit()
        
        return len(batch)
    
    def _insert_daily_summary(self, batch: 'pd.DataFrame') -> int:
        """Insert daily summary aggregates."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor() if not self.use_sqlite else conn
            
            sql = '''
                INSERT INTO daily_summary
                (date, total_sms, total_calls, internet_usage, total_activity,
                 active_grids, total_records)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''' if self.use_sqlite else '''
                INSERT INTO daily_summary
                (date, total_sms, total_calls, internet_usage, total_activity,
                 active_grids, total_records)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            '''
            
            for _, row in batch.iterrows():
                values = (
                    row.get('date'),
                    float(row.get('total_sms', 0)),
                    float(row.get('total_calls', 0)),
                    float(row.get('internet_usage', 0)),
                    float(row.get('total_activity', 0)),
                    int(row.get('active_grids', 0)),
                    int(row.get('total_records', 0))
                )
                cursor.execute(sql, values)
            
            conn.commit()
        
        return len(batch)
    
    def _insert_grid_summary(self, batch: 'pd.DataFrame') -> int:
        """Insert grid-level summary aggregates."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor() if not self.use_sqlite else conn
            
            sql = '''
                INSERT INTO grid_summary
                (date, grid_id, total_sms, total_calls, internet_usage,
                 total_activity, active_hours)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''' if self.use_sqlite else '''
                INSERT INTO grid_summary
                (date, grid_id, total_sms, total_calls, internet_usage,
                 total_activity, active_hours)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            '''
            
            for _, row in batch.iterrows():
                values = (
                    row.get('date'),
                    int(row.get('grid_id', 0)),
                    float(row.get('total_sms', 0)),
                    float(row.get('total_calls', 0)),
                    float(row.get('internet_usage', 0)),
                    float(row.get('total_activity', 0)),
                    int(row.get('active_hours', 0))
                )
                cursor.execute(sql, values)
            
            conn.commit()
        
        return len(batch)
    
    def _insert_enriched_spatial(self, batch: 'pd.DataFrame') -> int:
        """Insert spatially enriched data with geometry references."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor() if not self.use_sqlite else conn
            
            sql = '''
                INSERT INTO enriched_spatial_hourly
                (date, hour, grid_id, sms_in, sms_out, call_in, call_out,
                 internet_activity, total_activity, geometry)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''' if self.use_sqlite else '''
                INSERT INTO enriched_spatial_hourly
                (date, hour, grid_id, sms_in, sms_out, call_in, call_out,
                 internet_activity, total_activity, geometry)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            '''
            
            for _, row in batch.iterrows():
                values = (
                    row.get('date'),
                    int(row.get('hour', 0)),
                    int(row.get('grid_id', 0)),
                    float(row.get('sms_in', 0)),
                    float(row.get('sms_out', 0)),
                    float(row.get('call_in', 0)),
                    float(row.get('call_out', 0)),
                    float(row.get('internet_activity', 0)),
                    float(row.get('total_activity', 0)),
                    row.get('geometry')  # Store as text
                )
                cursor.execute(sql, values)
            
            conn.commit()
        
        return len(batch)


if __name__ == '__main__':
    import sys
    
    logger.info("=" * 70)
    logger.info("MYSQL DATA INGESTION MODULE")
    logger.info("=" * 70)
    logger.info("This module is designed to be imported by Airflow DAGs.")
    logger.info("See README.md or Airflow task documentation for usage.")
    logger.info("=" * 70)
