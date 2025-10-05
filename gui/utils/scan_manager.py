"""
SMBSeek Scan Manager

Manages SMB security scan operations with lock file coordination,
progress tracking, and graceful error handling.

Design Decision: Centralized scan management with lock file coordination
ensures single scan execution and proper resource cleanup.
"""

import json
import os
import subprocess
import threading
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Tuple
try:
    import psutil
except ImportError:
    # Fallback if psutil is not available
    psutil = None
import sys

# Add utils to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from backend_interface import BackendInterface


class ScanManager:
    """
    Manages SMB security scan operations.
    
    Handles:
    - Lock file management for single scan execution
    - Progress tracking and CLI output parsing
    - Error handling and recovery
    - Results collection and database integration
    - Graceful interruption handling
    
    Design Pattern: Singleton-style manager with comprehensive
    lifecycle management and error recovery capabilities.
    """
    
    def __init__(self, gui_directory: str = None):
        """
        Initialize scan manager.
        
        Args:
            gui_directory: Path to GUI directory for lock files
        """
        if gui_directory:
            self.gui_dir = Path(gui_directory)
        else:
            self.gui_dir = Path(__file__).parent.parent
        
        self.lock_file = self.gui_dir / ".scan_lock"
        
        # Scan state
        self.current_scan = None
        self.scan_start_time = None
        self.scan_thread = None
        self.is_scanning = False
        
        # Backend interface
        self.backend_interface = None
        
        # Progress tracking
        self.progress_callback = None
        self.last_progress_update = None
        
        # Results tracking
        self.scan_results = {}
        
        # Clean up any stale lock files on startup
        self._cleanup_stale_locks()
        
        # Also initialize backend interface cleanup if backend_interface is available
        self._initialize_backend_lock_cleanup()
    
    def _process_exists(self, pid: int) -> bool:
        """
        Check if process with given PID exists.
        
        Args:
            pid: Process ID to check
            
        Returns:
            True if process exists, False otherwise
        """
        if psutil:
            return psutil.pid_exists(pid)
        else:
            # Fallback method using os
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False
    
    def _cleanup_stale_locks(self) -> None:
        """Clean up stale lock files from previous sessions."""
        if self.lock_file.exists():
            try:
                # Read lock file metadata
                with open(self.lock_file, 'r') as f:
                    lock_data = json.load(f)
                
                # Check if process is still running
                pid = lock_data.get('process_id')
                if pid and self._process_exists(pid):
                    # Process still exists, lock is valid
                    return
                
                # Process doesn't exist, remove stale lock
                self.lock_file.unlink()
                
            except (json.JSONDecodeError, FileNotFoundError, KeyError):
                # Invalid or corrupted lock file, remove it
                if self.lock_file.exists():
                    self.lock_file.unlink()
    
    def _initialize_backend_lock_cleanup(self) -> None:
        """
        Initialize backend interface lock cleanup for coordination.
        
        Ensures that both GUI and backend lock files are cleaned up
        as recommended by backend team integration guidelines.
        """
        try:
            # Clean up any additional lock patterns that might exist
            lock_patterns = [
                ".scan_lock",
                ".access_lock", 
                ".discovery_lock",
                ".collection_lock"
            ]
            
            for pattern in lock_patterns:
                lock_path = self.gui_dir / pattern
                if lock_path.exists():
                    try:
                        # Check if lock file contains process information
                        with open(lock_path, 'r') as f:
                            lock_data = json.load(f)
                        
                        # Check if process is still running
                        pid = lock_data.get('process_id')
                        if pid and self._process_exists(pid):
                            # Process still exists, lock is valid
                            continue
                        
                        # Process doesn't exist, remove stale lock
                        lock_path.unlink()
                        
                    except (json.JSONDecodeError, FileNotFoundError, KeyError):
                        # Invalid or corrupted lock file, remove it
                        if lock_path.exists():
                            lock_path.unlink()
                            
        except Exception:
            # Non-critical cleanup failure - continue without error
            pass
    
    def is_scan_active(self) -> bool:
        """
        Check if a scan is currently active.
        
        Returns:
            True if scan is active, False otherwise
        """
        if self.is_scanning:
            return True
        
        if not self.lock_file.exists():
            return False
        
        try:
            with open(self.lock_file, 'r') as f:
                lock_data = json.load(f)
            
            # Check if process is still running
            pid = lock_data.get('process_id')
            if pid and self._process_exists(pid):
                return True
            else:
                # Stale lock file
                self.lock_file.unlink()
                return False
                
        except (json.JSONDecodeError, FileNotFoundError, KeyError):
            return False
    
    def create_lock_file(self, country: Optional[str] = None, scan_type: str = "complete") -> bool:
        """
        Create scan lock file with metadata.
        
        Args:
            country: Country code for scan (None for global)
            scan_type: Type of scan being performed
            
        Returns:
            True if lock created successfully, False if scan already active
        """
        if self.is_scan_active():
            return False
        
        lock_data = {
            "start_time": datetime.now().isoformat(),
            "scan_type": scan_type,
            "country": country,
            "process_id": os.getpid(),
            "created_by": "SMBSeek GUI"
        }
        
        try:
            with open(self.lock_file, 'w') as f:
                json.dump(lock_data, f, indent=2)
            return True
        except Exception:
            return False
    
    def remove_lock_file(self) -> None:
        """Remove scan lock file."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except Exception:
            pass
    
    def start_scan(self, scan_options: dict, backend_path: str,
                  progress_callback: Callable[[float, str, str], None]) -> bool:
        """
        Start a new SMB security scan with extended options.

        Args:
            scan_options: Dictionary containing scan configuration:
                - country: Country code (None for global scan)
                - max_shodan_results: Maximum Shodan results to fetch
                - recent_hours: Hours for recent filtering (None for default)
                - rescan_all: Whether to rescan all hosts
                - rescan_failed: Whether to rescan failed hosts
                - api_key_override: API key override (None for config default)
            backend_path: Path to backend directory
            progress_callback: Function called with (percentage, status, phase)

        Returns:
            True if scan started successfully, False otherwise
        """
        if self.is_scan_active():
            return False

        country = scan_options.get('country')

        # Create lock file
        if not self.create_lock_file(country, "complete"):
            return False

        try:
            # Initialize backend interface
            self.backend_interface = BackendInterface(backend_path)

            # Set up scan state
            self.is_scanning = True
            self.scan_start_time = datetime.now()
            self.progress_callback = progress_callback
            self.scan_results = {
                "start_time": self.scan_start_time.isoformat(),
                "country": country,
                "scan_options": scan_options,
                "status": "running"
            }

            # Start scan in background thread with new options
            self.scan_thread = threading.Thread(
                target=self._scan_worker,
                args=(scan_options,),
                daemon=True
            )
            self.scan_thread.start()

            return True

        except Exception as e:
            # Clean up on error
            self.is_scanning = False
            self.remove_lock_file()
            self._update_progress(0, f"Failed to start scan: {str(e)}", "error")
            return False
    
    def _scan_worker(self, scan_options: dict) -> None:
        """
        Background worker thread for scan execution with extended options.

        Args:
            scan_options: Dictionary containing scan configuration
        """
        try:
            # Extract parameters
            country = scan_options.get('country')
            countries = [country] if country else []

            # Start scan
            self._update_progress(5, "Initializing scan...", "initialization")

            # Build config overrides
            config_overrides = {}

            # Apply max results override
            max_results = scan_options.get('max_shodan_results')
            if max_results is not None:
                config_overrides['shodan'] = {'query_limits': {'max_results': max_results}}

            # Apply API key override
            api_key = scan_options.get('api_key_override')
            if api_key:
                if 'shodan' not in config_overrides:
                    config_overrides['shodan'] = {}
                config_overrides['shodan']['api_key'] = api_key

            # Apply recent hours override (convert to access_recent_hours for config)
            recent_hours = scan_options.get('recent_hours')
            if recent_hours is not None:
                config_overrides['workflow'] = {'access_recent_hours': recent_hours}

            discovery_concurrency = scan_options.get('discovery_max_concurrent_hosts')
            if discovery_concurrency is not None:
                config_overrides.setdefault('discovery', {})['max_concurrent_hosts'] = discovery_concurrency

            access_concurrency = scan_options.get('access_max_concurrent_hosts')
            if access_concurrency is not None:
                config_overrides.setdefault('access', {})['max_concurrent_hosts'] = access_concurrency

            rate_limit_delay = scan_options.get('rate_limit_delay')
            if rate_limit_delay is not None:
                config_overrides.setdefault('connection', {})['rate_limit_delay'] = rate_limit_delay

            share_access_delay = scan_options.get('share_access_delay')
            if share_access_delay is not None:
                config_overrides.setdefault('connection', {})['share_access_delay'] = share_access_delay

            # Execute scan with temporary config override
            if config_overrides:
                self._update_progress(7, "Applying configuration overrides...", "initialization")
                with self.backend_interface._temporary_config_override(config_overrides):
                    results = self._execute_scan_with_options(countries, scan_options)
            else:
                results = self._execute_scan_with_options(countries, scan_options)

            # Process results
            self._process_scan_results(results)

        except Exception as e:
            # Handle scan errors
            self._handle_scan_error(e)
        finally:
            # Ensure cleanup happens regardless of success, failure, or cancellation
            self._cleanup_scan()

    def _execute_scan_with_options(self, countries: List[str], scan_options: dict) -> dict:
        """Execute scan with CLI options and config overrides."""
        # Build CLI arguments
        cli_args = []

        # Add CLI flags for rescan options
        if scan_options.get('rescan_all'):
            cli_args.append('--rescan-all')

        if scan_options.get('rescan_failed'):
            cli_args.append('--rescan-failed')

        # Recent hours filtering is now handled through config overrides
        # in the _execute_scan method via _temporary_config_override
        # (lines 324-327). CLI --recent flag removed for SMBSeek 3.x compatibility.

        # Execute scan with additional CLI arguments
        self._update_progress(10, "Starting scan execution...", "discovery")

        # Use the backend interface run_scan method but with enhanced parameters
        # For now, use the existing run_scan method and let config overrides handle the rest
        return self.backend_interface.run_scan(
            countries,
            self._handle_backend_progress,
            additional_args=cli_args
        )
    
    def _handle_backend_progress(self, percentage: float, message: str) -> None:
        """
        Handle progress updates from backend interface.

        Backend interface already does sophisticated parsing, so we trust its
        percentage calculations and add minimal processing for phase detection.

        Args:
            percentage: Progress percentage (0-100) from backend interface
            message: Progress message from backend interface
        """
        # Handle message-only updates where percentage is None
        if percentage is None:
            percentage = float(self.last_progress_update.get("percentage", 0)) if hasattr(self, 'last_progress_update') and self.last_progress_update else 0.0

        # Ensure progress always moves forward (prevent stuck states)
        if hasattr(self, 'last_progress_update') and self.last_progress_update:
            last_percentage = self.last_progress_update.get("percentage", 0)
            # Only use new percentage if it's higher, or if significant time has passed
            # Skip comparison if either value is not numeric
            if isinstance(percentage, (int, float)) and isinstance(last_percentage, (int, float)) and percentage < last_percentage:
                import time
                last_time = self.last_progress_update.get("timestamp", "")
                current_time = datetime.now().isoformat()
                if last_time and (datetime.now() - datetime.fromisoformat(last_time)).total_seconds() > 30:
                    # Force progress increment if stuck for more than 30 seconds
                    percentage = min(last_percentage + 1, 100)
                else:
                    # Use the higher percentage to prevent going backwards
                    percentage = last_percentage
        
        # Simple phase detection based on message content (don't re-parse extensively)
        phase = self._detect_scan_phase(message)
        
        # Enhance message with activity indicators for better user feedback
        enhanced_message = self._enhance_progress_message(message, percentage, phase)
        
        # Update progress with enhanced information
        self._update_progress(percentage, enhanced_message, phase)
        
        # Store last update with timestamp
        self.last_progress_update = {
            "percentage": percentage,
            "message": enhanced_message,
            "phase": phase,
            "timestamp": datetime.now().isoformat(),
            "backend_message": message  # Store original for debugging
        }
    
    def _detect_scan_phase(self, message: str) -> str:
        """
        Simple phase detection from backend message.
        
        Backend interface has already done sophisticated parsing, so we only
        need basic phase detection for UI display purposes.
        
        Args:
            message: Progress message from backend interface
            
        Returns:
            Detected phase name
        """
        message_lower = message.lower()
        
        # Simple keyword-based phase detection (SMBSeek 3.0 three-phase model)
        if any(keyword in message_lower for keyword in ['complete', 'finished', 'done']):
            return "completed"

        scoreboard_message = (
            ("testing hosts" in message_lower or "testing recent hosts" in message_lower)
            and ("success:" in message_lower or "failed:" in message_lower)
        ) or "auth results" in message_lower
        if scoreboard_message:
            return "access_testing"

        error_indicators = [
            'error:', ' error', 'critical', 'fatal', 'exception', 'traceback',
            'scan failed', 'failed to', 'failed due', 'failure', ' aborted', ' terminated'
        ]
        if any(indicator in message_lower for indicator in error_indicators):
            return "error"

        if any(keyword in message_lower for keyword in ['auth', 'access', 'testing', 'login', 'shares', 'enum']):
            return "access_testing"  # Combined access testing and enumeration
        elif any(keyword in message_lower for keyword in ['discover', 'shodan', 'query', 'search']):
            return "discovery"
        elif any(keyword in message_lower for keyword in ['initializ', 'start', 'begin']):
            return "initialization"
        else:
            return "scanning"  # Default fallback
    
    def _enhance_progress_message(self, message: str, percentage: float, phase: str) -> str:
        """
        Enhance progress message with additional context and user feedback.
        
        Args:
            message: Original message from backend interface
            percentage: Current progress percentage
            phase: Detected scan phase
            
        Returns:
            Enhanced message for better user experience
        """
        # Add activity indicator to show system is working
        activity_indicators = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        indicator_index = int((percentage // 2) % len(activity_indicators))
        activity_indicator = activity_indicators[indicator_index]
        
        # Add phase-specific prefixes for clarity (SMBSeek 3.0 three-phase model)
        phase_prefixes = {
            "initialization": "🚀 Starting",
            "discovery": "🔍 Discovering",
            "authentication": "🔐 Testing Authentication",
            "access_testing": "⚡ Testing Access",
            "completed": "✅ Complete",
            "error": "❌ Error",
            "scanning": "⚡ Scanning"
        }
        
        prefix = phase_prefixes.get(phase, "⚡ Processing")
        
        # Enhance message with context
        if percentage < 100 and phase not in ["completed", "error"]:
            # Add activity indicator and percentage for active scans
            enhanced = f"{activity_indicator} {prefix}: {message} ({percentage:.0f}%)"
        else:
            # Simpler format for completed/error states
            enhanced = f"{prefix}: {message}"
        
        # Add time-based activity for very long phases
        if hasattr(self, 'last_progress_update') and self.last_progress_update:
            last_time = self.last_progress_update.get("timestamp")
            if last_time:
                time_diff = (datetime.now() - datetime.fromisoformat(last_time)).total_seconds()
                if time_diff > 60 and percentage < 100:  # More than 1 minute in same phase
                    enhanced += f" (running {time_diff/60:.0f}m)"
        
        return enhanced
    
    def _update_progress(self, percentage: float, status: str, phase: str) -> None:
        """
        Update scan progress and notify callback.
        
        Args:
            percentage: Progress percentage (0-100)
            status: Status message
            phase: Current scan phase
        """
        if self.progress_callback:
            self.progress_callback(percentage, status, phase)
    
    def _process_scan_results(self, results: Dict[str, Any]) -> None:
        """
        Process scan results and update scan state.
        
        Args:
            results: Results dictionary from backend interface
        """
        end_time = datetime.now()
        duration = end_time - self.scan_start_time
        
        # Check for cancellation first
        if results.get("cancelled", False):
            # Handle cancelled scan
            self.scan_results.update({
                "end_time": end_time.isoformat(),
                "duration_seconds": duration.total_seconds(),
                "status": "cancelled",
                "backend_results": results,
                "hosts_scanned": results.get("hosts_tested", 0),
                "accessible_hosts": results.get("successful_auth", 0),
                "shares_found": results.get("shares_discovered", 0),
                "summary_message": "Scan cancelled by user"
            })

            # Update progress with cancellation message using dedicated phase
            self._update_progress(
                self.last_progress_update.get("percentage", 0) if self.last_progress_update else 50,
                "Scan cancelled by user",
                "cancelled"
            )
            return

        # Update scan results for normal completion/failure
        self.scan_results.update({
            "end_time": end_time.isoformat(),
            "duration_seconds": duration.total_seconds(),
            "status": "completed" if results.get("success", False) else "failed",
            "backend_results": results,
            "hosts_scanned": results.get("hosts_tested", 0),
            "accessible_hosts": results.get("successful_auth", 0),
            "shares_found": results.get("shares_discovered", 0)
        })

        # Final progress update
        if results.get("success", False):
            hosts = self.scan_results["hosts_scanned"]
            accessible = self.scan_results["accessible_hosts"]

            # Build enhanced summary message (SMBSeek 3.0 - no file collection)
            summary_message = f"Scan completed: {accessible}/{hosts} hosts accessible"

            # Store summary message for UI display
            self.scan_results["summary_message"] = summary_message

            self._update_progress(
                100,
                summary_message,
                "completed"
            )
        else:
            error_msg = results.get("error", "Unknown error")
            self._update_progress(
                self.last_progress_update.get("percentage", 0) if self.last_progress_update else 0,
                f"Scan failed: {error_msg}",
                "error"
            )
    
    def _handle_scan_error(self, error: Exception) -> None:
        """
        Handle scan errors gracefully.
        
        Args:
            error: Exception that occurred during scan
        """
        end_time = datetime.now()
        
        if self.scan_start_time:
            duration = end_time - self.scan_start_time
            duration_seconds = duration.total_seconds()
        else:
            duration_seconds = 0
        
        # Update scan results with error information
        self.scan_results.update({
            "end_time": end_time.isoformat(),
            "duration_seconds": duration_seconds,
            "status": "error",
            "error": str(error),
            "error_type": type(error).__name__
        })
        
        # Determine which phase we were in
        current_phase = "unknown"
        if self.last_progress_update:
            current_phase = self.last_progress_update.get("phase", "unknown")
        
        # Update progress with error
        progress_percentage = 0
        if self.last_progress_update:
            progress_percentage = self.last_progress_update.get("percentage", 0)
        
        self._update_progress(
            progress_percentage,
            f"Scan interrupted in {current_phase} phase: {str(error)}",
            "error"
        )
    
    def _cleanup_scan(self) -> None:
        """Clean up after scan completion or failure."""
        self.is_scanning = False
        self.remove_lock_file()
        
        # Store final scan timestamp for results filtering
        if self.scan_results:
            self.scan_results["cleanup_time"] = datetime.now().isoformat()
    
    def get_scan_results(self) -> Dict[str, Any]:
        """
        Get current scan results.
        
        Returns:
            Dictionary with scan results and statistics
        """
        return self.scan_results.copy()
    
    def interrupt_scan(self) -> bool:
        """
        Interrupt currently running scan by terminating backend subprocess.

        Returns:
            True if cancellation was initiated, False if no scan active or error
        """
        if not self.is_scanning:
            return False

        try:
            # Update status to indicate cancellation in progress
            self.scan_results.update({
                "status": "cancelling",
                "cancellation_start": datetime.now().isoformat()
            })

            # Terminate the backend subprocess and its children
            if self.backend_interface:
                self.backend_interface.terminate_current_operation()

            # Keep is_scanning = True - let _cleanup_scan() reset it
            # This prevents dashboard monitor from bailing out early

            return True

        except Exception as e:
            # Log error but don't expose details to UI
            print(f"Error during scan cancellation: {e}")
            return False
    
    def get_last_scan_time(self) -> Optional[datetime]:
        """
        Get timestamp of last completed scan for filtering.
        
        Returns:
            Datetime of last scan completion or None if no scans
        """
        if not self.scan_results or not self.scan_results.get("end_time"):
            return None
        
        try:
            return datetime.fromisoformat(self.scan_results["end_time"])
        except (ValueError, TypeError):
            return None


# Global scan manager instance
_scan_manager = None


def get_scan_manager(gui_directory: str = None) -> ScanManager:
    """
    Get global scan manager instance.
    
    Args:
        gui_directory: Path to GUI directory for lock files
        
    Returns:
        ScanManager instance
    """
    global _scan_manager
    if _scan_manager is None:
        _scan_manager = ScanManager(gui_directory)
    return _scan_manager
