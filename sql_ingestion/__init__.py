"""
MySQL Ingestion Module
Handles loading Spark parquet outputs to MySQL database.
"""

from .mysql_ingestion import MySQLDataIngestion

__all__ = ['MySQLDataIngestion']
__version__ = '1.0.0'