"""
SMBSeek Shared Database Operations

Enhanced database operations for the unified CLI including new host filtering,
workflow management, and intelligent scanning logic.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
import sys

# Add tools directory to path for DatabaseManager import
tools_path = os.path.join(os.path.dirname(__file__), '..', 'tools')
sys.path.insert(0, tools_path)

from db_manager import DatabaseManager, SMBSeekDataAccessLayer


class SMBSeekWorkflowDatabase:
    """
    Enhanced database operations for SMBSeek unified CLI workflow.
    
    Provides intelligent host filtering, workflow tracking, and database
    operations optimized for the new unified interface.
    """
    
    def __init__(self, config):
        """
        Initialize workflow database manager.
        
        Args:
            config: SMBSeekConfig instance
        """
        self.config = config
        self.db_path = config.get_database_path()
        self.db_manager = DatabaseManager(self.db_path, config.config)
        self.dal = SMBSeekDataAccessLayer(self.db_manager)
        
        # Check if this is first run (database creation)
        self.is_first_run = self._check_first_run()
    
    def _check_first_run(self) -> bool:
        """
        Check if this is the first run (new database).
        
        Returns:
            True if database was just created or is empty
        """
        if not os.path.exists(self.db_path):
            return True
        
        try:
            servers = self.db_manager.execute_query("SELECT COUNT(*) as count FROM smb_servers")
            return servers[0]['count'] == 0
        except:
            return True
    
    def show_database_status(self):
        """Display database status and first-run warning if needed."""
        if self.is_first_run:
            # Yellow warning for first run
            print(f"\033[93m⚠ No database found; will be created at {os.path.abspath(self.db_path)}\033[0m")
            print(f"🆕 First run detected - will scan all Shodan results for initial population")
        else:
            try:
                servers = self.db_manager.execute_query("SELECT COUNT(*) as count FROM smb_servers")
                count = servers[0]['count']
                print(f"📊 Database found with {count} known servers")
            except:
                print(f"📊 Database found at {self.db_path}")
    
    def get_new_hosts_filter(self, shodan_ips: Set[str], rescan_all: bool = False, 
                           rescan_failed: bool = False, output_manager=None) -> Tuple[Set[str], Dict[str, int]]:
        """
        Filter Shodan results to identify hosts that need scanning.
        
        Args:
            shodan_ips: Set of IP addresses from Shodan query
            rescan_all: Force rescan of all hosts regardless of age
            rescan_failed: Include previously failed hosts for rescanning
            output_manager: Output manager for progress messages
            
        Returns:
            Tuple of (ips_to_scan, statistics_dict)
        """
        if output_manager:
            output_manager.info(f"Checking {len(shodan_ips)} IPs against database ({self._get_known_servers_count()} known servers)...")
        
        if self.is_first_run:
            # First run - scan everything
            stats = {
                'total_from_shodan': len(shodan_ips),
                'known_hosts': 0,
                'new_hosts': len(shodan_ips),
                'recently_scanned': 0,
                'failed_hosts': 0,
                'to_scan': len(shodan_ips)
            }
            return shodan_ips, stats
        
        # Get information about known hosts
        if output_manager:
            output_manager.info("Analyzing scan history and rescan policies...")
        known_hosts_info = self._get_known_hosts_info(shodan_ips)
        
        # Calculate cutoff date for rescanning
        rescan_cutoff = datetime.now() - timedelta(days=self.config.get("workflow", "rescan_after_days", 30))
        
        ips_to_scan = set()
        stats = {
            'total_from_shodan': len(shodan_ips),
            'known_hosts': 0,
            'new_hosts': 0,
            'recently_scanned': 0,
            'failed_hosts': 0,
            'to_scan': 0
        }
        
        for ip in shodan_ips:
            if ip not in known_hosts_info:
                # New host - always scan
                ips_to_scan.add(ip)
                stats['new_hosts'] += 1
            else:
                # Known host - check scanning rules
                host_info = known_hosts_info[ip]
                stats['known_hosts'] += 1
                
                last_seen = datetime.fromisoformat(host_info['last_seen'])
                is_old = last_seen < rescan_cutoff
                was_successful = host_info['scan_count'] > 0
                
                if rescan_all:
                    # Force rescan all
                    ips_to_scan.add(ip)
                elif not was_successful and rescan_failed:
                    # Rescan failed hosts if requested
                    ips_to_scan.add(ip)
                    stats['failed_hosts'] += 1
                elif not was_successful and not self.config.should_skip_failed_hosts():
                    # Rescan failed hosts if not skipping them
                    ips_to_scan.add(ip)
                    stats['failed_hosts'] += 1
                elif was_successful and is_old:
                    # Rescan successful hosts that are old enough
                    ips_to_scan.add(ip)
                else:
                    # Skip recently scanned hosts
                    stats['recently_scanned'] += 1
        
        stats['to_scan'] = len(ips_to_scan)
        
        if output_manager:
            output_manager.info(f"Database filtering complete: {stats['new_hosts']} new, {stats['known_hosts']} known, {stats['to_scan']} to scan")
        
        return ips_to_scan, stats
    
    def _get_known_servers_count(self) -> int:
        """Get count of known servers in database."""
        try:
            result = self.db_manager.execute_query("SELECT COUNT(*) as count FROM smb_servers")
            return result[0]['count']
        except:
            return 0
    
    def _get_known_hosts_info(self, ips: Set[str]) -> Dict[str, Dict]:
        """
        Get information about known hosts from database.
        Uses batch processing for large IP sets to improve performance.
        
        Args:
            ips: Set of IP addresses to check
            
        Returns:
            Dictionary mapping IP to host information
        """
        if not ips:
            return {}
        
        # For large IP sets, process in batches to avoid SQL query limits
        batch_size = 500  # SQLite SQLITE_MAX_VARIABLE_NUMBER default is 999
        ips_list = list(ips)
        host_info = {}
        
        try:
            for i in range(0, len(ips_list), batch_size):
                batch = ips_list[i:i + batch_size]
                
                # Create query with placeholders for this batch
                placeholders = ','.join(['?' for _ in batch])
                query = f"""
                    SELECT ip_address, last_seen, scan_count, status
                    FROM smb_servers 
                    WHERE ip_address IN ({placeholders})
                """
                
                results = self.db_manager.execute_query(query, tuple(batch))
                
                # Convert batch results to dictionary
                for row in results:
                    host_info[row['ip_address']] = dict(row)
            
            return host_info
            
        except Exception as e:
            print(f"⚠ Error checking known hosts: {e}")
            return {}
    
    def display_scan_statistics(self, stats: Dict[str, int], ips_to_scan: Set[str]):
        """
        Display scanning statistics to user.
        
        Args:
            stats: Statistics dictionary from get_new_hosts_filter
            ips_to_scan: Set of IPs that will be scanned
        """
        print(f"\n📊 Scan Planning:")
        print(f"  • Total from Shodan: {stats['total_from_shodan']}")
        
        if not self.is_first_run:
            print(f"  • Already known: {stats['known_hosts']}")
            print(f"  • New discoveries: {stats['new_hosts']}")
            if stats['recently_scanned'] > 0:
                print(f"  • Recently scanned (skipping): {stats['recently_scanned']}")
            if stats['failed_hosts'] > 0:
                print(f"  • Previously failed: {stats['failed_hosts']}")
        
        print(f"  • Will scan: {stats['to_scan']}")
        
        if stats['to_scan'] == 0:
            print(f"✅ No new hosts to scan. Use --rescan-all or --rescan-failed to override.")
        else:
            print(f"🚀 Proceeding with {stats['to_scan']} hosts...")
    
    def record_scan_session(self, session_data: Dict) -> str:
        """
        Record a new scan session in the database.
        
        Args:
            session_data: Session information dictionary
            
        Returns:
            Session ID
        """
        return self.dal.create_scan_session(
            tool_name=session_data.get('tool_name', 'smbseek'),
            config_snapshot=session_data
        )
    
    def get_recent_activity_summary(self, days: int = 7) -> Dict:
        """
        Get summary of recent scanning activity.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Summary dictionary
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_date.isoformat()
        
        try:
            # Recent sessions
            sessions = self.db_manager.execute_query("""
                SELECT COUNT(*) as session_count,
                       SUM(targets_found) as total_targets,
                       SUM(successful_connections) as total_successful
                FROM scan_sessions 
                WHERE timestamp >= ?
            """, (cutoff_str,))
            
            # Recently updated servers
            servers = self.db_manager.execute_query("""
                SELECT COUNT(*) as updated_servers
                FROM smb_servers 
                WHERE last_seen >= ?
            """, (cutoff_str,))
            
            return {
                'days': days,
                'scan_sessions': sessions[0]['session_count'] or 0,
                'targets_found': sessions[0]['total_targets'] or 0,
                'successful_connections': sessions[0]['total_successful'] or 0,
                'updated_servers': servers[0]['updated_servers'] or 0
            }
        except Exception as e:
            print(f"⚠ Error getting activity summary: {e}")
            return {
                'days': days,
                'scan_sessions': 0,
                'targets_found': 0,
                'successful_connections': 0,
                'updated_servers': 0
            }
    
    def get_authenticated_hosts(self) -> List[Dict]:
        """
        Get hosts that have successful SMB authentication.
        
        Returns:
            List of host dictionaries with authentication information
        """
        try:
            hosts = self.db_manager.execute_query("""
                SELECT DISTINCT s.ip_address, s.country, s.auth_method
                FROM smb_servers s
                WHERE s.status = 'active' 
                  AND s.auth_method IS NOT NULL 
                  AND s.auth_method != 'failed'
                  AND s.auth_method != 'Failed'
                ORDER BY s.last_seen DESC
            """)
            
            return hosts
            
        except Exception as e:
            print(f"⚠ Error getting authenticated hosts: {e}")
            return []

    def get_recently_discovered_hosts(self, hours: int = 1) -> List[Dict]:
        """
        Get hosts discovered within the specified time period that have successful authentication.
        
        Args:
            hours: Number of hours to look back for recent discoveries
            
        Returns:
            List of host dictionaries with authentication information
        """
        try:
            hosts = self.db_manager.execute_query("""
                SELECT DISTINCT s.ip_address, s.country, s.auth_method, s.last_seen
                FROM smb_servers s
                WHERE s.last_seen >= datetime('now', '-{} hour')
                  AND s.status = 'active' 
                  AND s.auth_method IS NOT NULL 
                  AND s.auth_method != 'failed'
                  AND s.auth_method != 'Failed'
                ORDER BY s.last_seen DESC
            """.format(hours))
            
            return hosts
            
        except Exception as e:
            print(f"⚠ Error getting recently discovered hosts: {e}")
            return []
    
    def get_hosts_with_accessible_shares(self) -> List[Dict]:
        """
        Get hosts that have accessible SMB shares.
        
        Returns:
            List of host dictionaries with accessible share information
        """
        try:
            hosts = self.db_manager.execute_query("""
                SELECT DISTINCT s.ip_address, s.country, s.auth_method,
                       GROUP_CONCAT(sa.share_name) as accessible_shares
                FROM smb_servers s
                INNER JOIN share_access sa ON s.ip_address = sa.ip_address 
                WHERE sa.accessible = 1
                GROUP BY s.ip_address, s.country, s.auth_method
            """)
            
            # Parse accessible_shares from comma-separated string to list
            for host in hosts:
                if host['accessible_shares']:
                    host['accessible_shares'] = host['accessible_shares'].split(',')
                else:
                    host['accessible_shares'] = []
            
            return hosts
            
        except Exception as e:
            print(f"⚠ Error getting hosts with accessible shares: {e}")
            return []
    
    def get_failed_connections(self) -> List[Dict]:
        """
        Get failed connection attempts for analysis.
        
        Returns:
            List of failed connection records
        """
        try:
            failed = self.db_manager.execute_query("""
                SELECT ip_address, country, last_seen, status
                FROM smb_servers 
                WHERE status = 'failed' OR status = 'timeout'
                ORDER BY last_seen DESC
            """)
            
            return failed
            
        except Exception as e:
            print(f"⚠ Error getting failed connections: {e}")
            return []
    
    def create_session(self, session_type: str) -> str:
        """
        Create a new scan session.
        
        Args:
            session_type: Type of session (e.g., 'access', 'discovery', 'collection')
            
        Returns:
            Session ID
        """
        try:
            session_data = {
                'tool_name': f'smbseek_{session_type}',
                'session_type': session_type,
                'timestamp': datetime.now().isoformat()
            }
            return self.dal.create_scan_session(
                tool_name=session_data['tool_name'],
                config_snapshot=session_data
            )
        except Exception as e:
            print(f"⚠ Error creating session: {e}")
            return str(int(datetime.now().timestamp()))
    
    def store_share_access_result(self, session_id: str, result: Dict) -> bool:
        """
        Store share access test results in the database.
        
        Args:
            session_id: Session ID for this scan
            result: Result dictionary with share access data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get server ID from IP address
            ip_address = result['ip_address']
            server_query = "SELECT id FROM smb_servers WHERE ip_address = ?"
            server_results = self.db_manager.execute_query(server_query, (ip_address,))
            
            if not server_results:
                print(f"⚠ Warning: Server {ip_address} not found in database")
                return False
            
            server_id = server_results[0]['id']
            
            # Store each share access result
            for share_detail in result.get('share_details', []):
                self.db_manager.add_share_access(
                    server_id=server_id,
                    session_id=int(session_id),
                    share_name=share_detail['share_name'],
                    accessible=share_detail['accessible'],
                    error_message=share_detail.get('error'),
                    ip_address=ip_address,  # Additional field for easier querying
                    timestamp=result['timestamp']
                )
            
            return True
            
        except Exception as e:
            print(f"⚠ Error storing share access results: {e}")
            return False
    
    def close(self):
        """Close database connections."""
        if hasattr(self, 'db_manager'):
            self.db_manager.close()


def create_workflow_database(config) -> SMBSeekWorkflowDatabase:
    """
    Create and initialize workflow database manager.
    
    Args:
        config: SMBSeekConfig instance
        
    Returns:
        SMBSeekWorkflowDatabase instance
    """
    return SMBSeekWorkflowDatabase(config)