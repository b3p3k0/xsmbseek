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
    
    def start_scan(self, country: Optional[str], backend_path: str,
                  progress_callback: Callable[[float, str, str], None]) -> bool:
        """
        Start a new SMB security scan.
        
        Args:
            country: Country code (None for global scan)
            backend_path: Path to backend directory
            progress_callback: Function called with (percentage, status, phase)
            
        Returns:
            True if scan started successfully, False otherwise
        """
        if self.is_scan_active():
            return False
        
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
                "status": "running"
            }
            
            # Start scan in background thread
            self.scan_thread = threading.Thread(
                target=self._scan_worker,
                args=(country,),
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
    
    def _scan_worker(self, country: Optional[str]) -> None:
        """
        Background worker thread for scan execution.
        
        Args:
            country: Country code for scan
        """
        try:
            # Prepare scan parameters
            countries = [country] if country else []
            
            # Start scan
            self._update_progress(5, "Initializing scan...", "initialization")
            
            # Execute scan with progress tracking
            results = self.backend_interface.run_scan(
                countries, 
                self._handle_backend_progress
            )
            
            # Process results
            self._process_scan_results(results)
            
        except Exception as e:
            # Handle scan errors
            self._handle_scan_error(e)
        
        finally:
            # Clean up
            self._cleanup_scan()
    
    def _handle_backend_progress(self, percentage: float, message: str) -> None:
        """
        Handle progress updates from backend interface.
        
        Backend interface already does sophisticated parsing, so we trust its
        percentage calculations and add minimal processing for phase detection.
        
        Args:
            percentage: Progress percentage (0-100) from backend interface
            message: Progress message from backend interface
        """
        # Ensure progress always moves forward (prevent stuck states)
        if hasattr(self, 'last_progress_update') and self.last_progress_update:
            last_percentage = self.last_progress_update.get("percentage", 0)
            # Only use new percentage if it's higher, or if significant time has passed
            if percentage < last_percentage:
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
        
        # Simple keyword-based phase detection (order matters - check specific first)
        if any(keyword in message_lower for keyword in ['complete', 'finished', 'done']):
            return "completed"
        elif any(keyword in message_lower for keyword in ['error', 'fail', 'exception']):
            return "error"
        elif any(keyword in message_lower for keyword in ['report', 'results', 'summary', 'generating']):
            return "reporting"
        elif any(keyword in message_lower for keyword in ['collect', 'enum', 'shares', 'files']):
            return "collection"
        elif any(keyword in message_lower for keyword in ['auth', 'access', 'testing', 'login']):
            return "access_testing"
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
        
        # Add phase-specific prefixes for clarity
        phase_prefixes = {
            "initialization": "🚀 Starting",
            "discovery": "🔍 Discovering",
            "access_testing": "🔐 Testing Access",
            "collection": "📁 Collecting Data",
            "reporting": "📊 Generating Report",
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
        
        # Update scan results
        self.scan_results.update({
            "end_time": end_time.isoformat(),
            "duration_seconds": duration.total_seconds(),
            "status": "completed" if results.get("success", False) else "failed",
            "backend_results": results,
            "hosts_scanned": results.get("hosts_tested", 0),
            "accessible_hosts": results.get("successful_auth", 0),
            "shares_found": results.get("shares_discovered", 0),
            "files_collected": results.get("files_collected", 0)
        })
        
        # Final progress update
        if results.get("success", False):
            hosts = self.scan_results["hosts_scanned"]
            accessible = self.scan_results["accessible_hosts"]
            self._update_progress(
                100,
                f"Scan completed: {accessible}/{hosts} hosts accessible",
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
        Interrupt currently running scan.
        
        Returns:
            True if scan was interrupted, False if no scan active
        """
        if not self.is_scanning:
            return False
        
        try:
            # Signal scan to stop
            self.is_scanning = False
            
            # Update results to indicate interruption
            self.scan_results.update({
                "status": "interrupted",
                "end_time": datetime.now().isoformat(),
                "interrupted_by": "user"
            })
            
            return True
            
        except Exception:
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