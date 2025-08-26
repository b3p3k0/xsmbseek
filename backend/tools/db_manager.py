#!/usr/bin/env python3
"""
SMBSeek Database Manager
Centralized database connection and operations management for SQLite backend
"""

import sqlite3
import json
import os
import logging
from datetime import datetime
import sys
import os

# Add shared directory to path
shared_path = os.path.join(os.path.dirname(__file__), '..', 'shared')
sys.path.insert(0, shared_path)

from config import get_standard_timestamp
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Union
import threading


class DatabaseManager:
    """
    Thread-safe SQLite database manager for SMBSeek toolkit.
    
    Provides connection management, schema initialization, and common database operations.
    Follows the established SMBSeek architecture patterns.
    """
    
    def __init__(self, db_path: str = "smbseek.db", config: Optional[Dict] = None):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
            config: Configuration dictionary (optional)
        """
        self.db_path = db_path
        self.config = config or {}
        self._local = threading.local()
        self.logger = logging.getLogger(__name__)
        
        # Ensure database directory exists
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        # Initialize database if it doesn't exist
        if not os.path.exists(db_path):
            self.initialize_database()
    
    def get_connection(self) -> sqlite3.Connection:
        """
        Get thread-local database connection.
        
        Returns:
            SQLite connection object
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable foreign key constraints
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            self._local.connection.execute("PRAGMA journal_mode = WAL")
        
        return self._local.connection
    
    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions with automatic rollback on error.
        
        Usage:
            with db_manager.transaction():
                cursor.execute("INSERT ...")
                cursor.execute("UPDATE ...")
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Database transaction failed: {e}")
            raise
        finally:
            cursor.close()
    
    def initialize_database(self):
        """
        Initialize database schema from schema file.
        """
        schema_path = os.path.join(os.path.dirname(__file__), 'db_schema.sql')
        
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Database schema file not found: {schema_path}")
        
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        
        with self.transaction() as cursor:
            # Execute schema creation
            cursor.executescript(schema_sql)
        
        self.logger.info(f"Database initialized: {self.db_path}")
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[sqlite3.Row]:
        """
        Execute a SELECT query and return results.
        
        Args:
            query: SQL query string
            params: Query parameters (optional)
        
        Returns:
            List of result rows
        """
        with self.transaction() as cursor:
            cursor.execute(query, params or ())
            return cursor.fetchall()
    
    def execute_insert(self, table: str, data: Dict[str, Any]) -> int:
        """
        Execute INSERT operation and return the new row ID.
        
        Args:
            table: Table name
            data: Dictionary of column names and values
        
        Returns:
            ID of inserted row
        """
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        with self.transaction() as cursor:
            cursor.execute(query, tuple(data.values()))
            return cursor.lastrowid
    
    def execute_update(self, table: str, data: Dict[str, Any], where_clause: str, where_params: tuple) -> int:
        """
        Execute UPDATE operation and return number of affected rows.
        
        Args:
            table: Table name
            data: Dictionary of column names and new values
            where_clause: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause
        
        Returns:
            Number of affected rows
        """
        set_clause = ', '.join([f"{col} = ?" for col in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        
        with self.transaction() as cursor:
            cursor.execute(query, tuple(data.values()) + where_params)
            return cursor.rowcount
    
    def close(self):
        """
        Close database connections.
        """
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None


class SMBSeekDataAccessLayer:
    """
    High-level data access layer for SMBSeek operations.
    
    Provides domain-specific database operations following SMBSeek data patterns.
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize data access layer.
        
        Args:
            db_manager: DatabaseManager instance
        """
        self.db = db_manager
        self.logger = logging.getLogger(__name__)
    
    def create_scan_session(self, tool_name: str, config_snapshot: Optional[Dict] = None) -> int:
        """
        Create a new scan session record.
        
        Args:
            tool_name: Name of the scanning tool
            config_snapshot: Configuration used for the scan
        
        Returns:
            Session ID
        """
        data = {
            'tool_name': tool_name,
            'timestamp': datetime.now().isoformat(),
            'config_snapshot': json.dumps(config_snapshot) if config_snapshot else None,
            'status': 'running'
        }
        return self.db.execute_insert('scan_sessions', data)
    
    def update_scan_session(self, session_id: int, **kwargs) -> bool:
        """
        Update scan session with results.
        
        Args:
            session_id: Session ID to update
            **kwargs: Fields to update (total_targets, successful_targets, etc.)
        
        Returns:
            True if update successful
        """
        kwargs['updated_at'] = datetime.now().isoformat()
        return self.db.execute_update('scan_sessions', kwargs, 'id = ?', (session_id,)) > 0
    
    def get_or_create_server(self, ip_address: str, country: Optional[str] = None, 
                           auth_method: Optional[str] = None) -> int:
        """
        Get existing server or create new one.
        
        Args:
            ip_address: Server IP address
            country: Country name (optional)
            auth_method: Authentication method used (optional)
        
        Returns:
            Server ID
        """
        # Try to find existing server
        result = self.db.execute_query(
            "SELECT id FROM smb_servers WHERE ip_address = ?", 
            (ip_address,)
        )
        
        if result:
            server_id = result[0]['id']
            # Update last_seen and scan_count using direct SQL to increment
            query = """
                UPDATE smb_servers 
                SET last_seen = ?, scan_count = scan_count + 1, updated_at = ?
                WHERE id = ?
            """
            timestamp = get_standard_timestamp()
            self.db.execute_query(query, (
                timestamp,
                timestamp,
                server_id
            ))
            return server_id
        else:
            # Create new server
            timestamp = get_standard_timestamp()
            data = {
                'ip_address': ip_address,
                'country': country,
                'auth_method': auth_method,
                'first_seen': timestamp,
                'last_seen': timestamp,
                'scan_count': 1
            }
            return self.db.execute_insert('smb_servers', data)
    
    def add_share_access(self, server_id: int, session_id: int, share_name: str, 
                        accessible: bool, **kwargs) -> int:
        """
        Record share access test results.
        
        Args:
            server_id: Server ID
            session_id: Scan session ID
            share_name: Name of the share
            accessible: Whether share was accessible
            **kwargs: Additional share details
        
        Returns:
            Record ID
        """
        data = {
            'server_id': server_id,
            'session_id': session_id,
            'share_name': share_name,
            'accessible': accessible,
            'test_timestamp': datetime.now().isoformat(),
            **kwargs
        }
        return self.db.execute_insert('share_access', data)
    
    def add_file_manifest(self, server_id: int, session_id: int, share_name: str,
                         file_path: str, **kwargs) -> int:
        """
        Add file discovery record.
        
        Args:
            server_id: Server ID
            session_id: Scan session ID
            share_name: Share containing the file
            file_path: Full path to the file
            **kwargs: Additional file metadata
        
        Returns:
            Record ID
        """
        file_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_name)[1].lower()
        
        data = {
            'server_id': server_id,
            'session_id': session_id,
            'share_name': share_name,
            'file_path': file_path,
            'file_name': file_name,
            'file_extension': file_ext,
            'discovery_timestamp': datetime.now().isoformat(),
            **kwargs
        }
        return self.db.execute_insert('file_manifests', data)
    
    def add_vulnerability(self, server_id: int, session_id: int, vuln_type: str,
                         severity: str, title: str, **kwargs) -> int:
        """
        Record vulnerability finding.
        
        Args:
            server_id: Server ID
            session_id: Scan session ID
            vuln_type: Type of vulnerability
            severity: Severity level (low, medium, high, critical)
            title: Vulnerability title
            **kwargs: Additional vulnerability details
        
        Returns:
            Record ID
        """
        data = {
            'server_id': server_id,
            'session_id': session_id,
            'vuln_type': vuln_type,
            'severity': severity,
            'title': title,
            'discovery_timestamp': datetime.now().isoformat(),
            **kwargs
        }
        return self.db.execute_insert('vulnerabilities', data)
    
    def add_failure_log(self, ip_address: str, failure_type: str, 
                       failure_reason: Optional[str] = None, session_id: Optional[int] = None) -> int:
        """
        Record connection failure.
        
        Args:
            ip_address: Target IP address
            failure_type: Type of failure
            failure_reason: Detailed failure reason (optional)
            session_id: Associated scan session (optional)
        
        Returns:
            Record ID
        """
        data = {
            'ip_address': ip_address,
            'failure_type': failure_type,
            'failure_reason': failure_reason,
            'failure_timestamp': datetime.now().isoformat(),
            'session_id': session_id
        }
        return self.db.execute_insert('failure_logs', data)
    
    def get_server_summary(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Get summary of all servers with basic statistics.
        
        Args:
            limit: Maximum number of results (optional)
        
        Returns:
            List of server summary dictionaries
        """
        query = "SELECT * FROM v_active_servers ORDER BY last_seen DESC"
        if limit:
            query += f" LIMIT {limit}"
        
        results = self.db.execute_query(query)
        return [dict(row) for row in results]
    
    def get_vulnerability_summary(self) -> List[Dict]:
        """
        Get vulnerability summary statistics.
        
        Returns:
            List of vulnerability summary dictionaries
        """
        results = self.db.execute_query("SELECT * FROM v_vulnerability_summary")
        return [dict(row) for row in results]
    
    def get_scan_statistics(self, days: int = 30) -> List[Dict]:
        """
        Get scan statistics for recent time period.
        
        Args:
            days: Number of days to include
        
        Returns:
            List of scan statistics dictionaries
        """
        query = """
        SELECT * FROM v_scan_statistics 
        WHERE scan_date >= date('now', '-{} days')
        ORDER BY scan_date DESC
        """.format(days)
        
        results = self.db.execute_query(query)
        return [dict(row) for row in results]