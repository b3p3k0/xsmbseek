"""
SMBSeek Backend Interface

Provides subprocess wrapper for CLI commands with output parsing and progress tracking.
Implements complete backend isolation without any code modifications.

Design Decision: Use subprocess calls rather than direct imports to maintain
complete separation between GUI and backend teams' code.
"""

import subprocess
import threading
import queue
import json
import os
import re
import time
from typing import Dict, List, Optional, Callable, Tuple, Any
from pathlib import Path


class BackendInterface:
    """
    Interface for communicating with SMBSeek backend via subprocess calls.
    
    Provides methods for executing CLI commands, parsing output, and tracking
    progress for long-running operations. All communication is through the
    existing CLI interface to avoid backend modifications.
    
    Design Pattern: Complete backend isolation with graceful error handling
    and user-friendly progress updates.
    """
    
    def __init__(self, backend_path: str = "../backend"):
        """
        Initialize backend interface.
        
        Args:
            backend_path: Path to backend directory relative to GUI
            
        Design Decision: Default to relative path for development environment,
        but allow override for different deployment scenarios.
        """
        self.backend_path = Path(backend_path).resolve()
        self.cli_script = self.backend_path / "smbseek.py"
        self.config_path = self.backend_path / "conf" / "config.json"
        
        # Progress tracking for long-running operations
        self.progress_queue = queue.Queue()
        self.current_operation = None
        
        # Mock mode for testing without backend
        self.mock_mode = False
        self.mock_data_path = Path("../test_data/mock_responses")
        
        # Timeout configuration - loaded from config with environment override support
        self.default_timeout = None  # No timeout by default
        self.enable_debug_timeouts = False
        self._load_timeout_configuration()
        
        self._validate_backend()
    
    def _validate_backend(self) -> None:
        """
        Validate that backend is accessible and functional.
        
        Raises:
            FileNotFoundError: If backend CLI script not found
            PermissionError: If backend not executable
        """
        if not self.cli_script.exists():
            raise FileNotFoundError(
                f"Backend CLI not found at {self.cli_script}. "
                f"Ensure backend is properly installed."
            )
        
        if not os.access(self.cli_script, os.X_OK):
            raise PermissionError(
                f"Backend CLI not executable: {self.cli_script}. "
                f"Run: chmod +x {self.cli_script}"
            )
    
    def enable_mock_mode(self, mock_data_path: Optional[str] = None) -> None:
        """
        Enable mock mode for testing without real backend calls.
        
        Args:
            mock_data_path: Path to mock response files
            
        Design Decision: Mock mode allows safe GUI testing without requiring
        real Shodan API keys or network access.
        """
        self.mock_mode = True
        if mock_data_path:
            self.mock_data_path = Path(mock_data_path)
    
    def disable_mock_mode(self) -> None:
        """Disable mock mode and use real backend calls."""
        self.mock_mode = False
    
    # ===== TIMEOUT CONFIGURATION SYSTEM =====
    
    def _load_timeout_configuration(self) -> None:
        """
        Load timeout configuration from config file with environment override support.
        
        Configuration hierarchy (highest priority first):
        1. Environment variable: SMBSEEK_GUI_TIMEOUT
        2. Config file gui.operation_timeout_seconds
        3. Default: None (no timeout)
        
        Design Decision: Multi-level configuration allows development, testing, 
        and production flexibility while maintaining safe defaults.
        """
        try:
            # Check environment variable first (highest priority)
            env_timeout = os.environ.get('SMBSEEK_GUI_TIMEOUT')
            if env_timeout is not None:
                if env_timeout.lower() in ('none', 'null', '0'):
                    self.default_timeout = None
                else:
                    self.default_timeout = int(env_timeout)
                return
            
            # Load from config file
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                
                gui_config = config.get('gui', {})
                self.default_timeout = gui_config.get('operation_timeout_seconds', None)
                self.enable_debug_timeouts = gui_config.get('enable_debug_timeouts', False)
                
                # Handle explicit zero as no timeout
                if self.default_timeout == 0:
                    self.default_timeout = None
            
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            # Fallback to safe default - no timeout
            self.default_timeout = None
            self.enable_debug_timeouts = False
            print(f"Warning: Could not load timeout configuration: {e}")
            print("Using default: no timeout")
    
    def _get_operation_timeout(self, timeout_override: Optional[int] = None) -> Optional[int]:
        """
        Resolve timeout for operation with override support.
        
        Args:
            timeout_override: Optional per-operation timeout override
            
        Returns:
            Resolved timeout in seconds, or None for no timeout
            
        Resolution order:
        1. timeout_override parameter (highest priority)
        2. self.default_timeout from config/env
        3. None (no timeout fallback)
        """
        if timeout_override is not None:
            return timeout_override
        
        return self.default_timeout
    
    def _format_timeout_duration(self, timeout_seconds: Optional[int]) -> str:
        """
        Format timeout duration for user-friendly error messages.
        
        Args:
            timeout_seconds: Timeout in seconds, or None
            
        Returns:
            Formatted duration string (e.g., "2 hours", "30 minutes", "never")
        """
        if timeout_seconds is None:
            return "never"
        
        if timeout_seconds < 60:
            return f"{timeout_seconds} seconds"
        elif timeout_seconds < 3600:
            minutes = timeout_seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = timeout_seconds / 3600
            if hours == int(hours):
                return f"{int(hours)} hour{'s' if int(hours) != 1 else ''}"
            else:
                return f"{hours:.1f} hours"
    
    def get_timeout_info(self) -> Dict[str, Any]:
        """
        Get current timeout configuration information for debugging/verification.
        
        Returns:
            Dictionary with timeout configuration details
        """
        env_timeout = os.environ.get('SMBSEEK_GUI_TIMEOUT')
        
        return {
            'effective_timeout_seconds': self.default_timeout,
            'effective_timeout_display': self._format_timeout_duration(self.default_timeout),
            'environment_variable': env_timeout,
            'debug_timeouts_enabled': self.enable_debug_timeouts,
            'config_file_path': str(self.config_path),
            'config_file_exists': self.config_path.exists()
        }
    
    def run_scan(self, countries: List[str], progress_callback: Optional[Callable] = None) -> Dict:
        """
        Execute complete SMBSeek scan workflow.
        
        Args:
            countries: List of country codes to scan
            progress_callback: Function to call with progress updates
            
        Returns:
            Dictionary with scan results and statistics
            
        Design Decision: Wrapper around 'smbseek run' command provides the
        most common GUI operation with progress tracking.
        """
        if self.mock_mode:
            return self._mock_scan_operation(countries, progress_callback)
        
        countries_str = ",".join(countries)
        cmd = [
            str(self.cli_script),
            "run",
            "--country", countries_str,
            "--verbose"  # For detailed progress parsing
        ]
        
        return self._execute_with_progress(cmd, progress_callback)
    
    def run_discover(self, countries: List[str], progress_callback: Optional[Callable] = None) -> Dict:
        """
        Execute discovery-only operation.
        
        Args:
            countries: List of country codes to scan
            progress_callback: Function to call with progress updates
            
        Returns:
            Dictionary with discovery results
        """
        if self.mock_mode:
            return self._mock_discover_operation(countries, progress_callback)
        
        countries_str = ",".join(countries)
        cmd = [
            str(self.cli_script),
            "discover",
            "--country", countries_str,
            "--verbose"
        ]
        
        return self._execute_with_progress(cmd, progress_callback)
    
    def get_database_summary(self) -> Dict:
        """
        Get summary statistics from database.
        
        Returns:
            Dictionary with database statistics
            
        Design Decision: Use CLI query command rather than direct database
        access to maintain backend interface consistency.
        """
        if self.mock_mode:
            return {
                "total_servers": 7,
                "accessible_shares": 17,
                "vulnerabilities": 7,
                "recent_discoveries": {
                    "discovered": 24,
                    "accessible": 12,
                    "display": "24 / 12"
                }
            }
        
        cmd = [str(self.cli_script), "db", "query", "--summary"]
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.backend_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return self._parse_summary_output(result.stdout)
            else:
                raise subprocess.CalledProcessError(result.returncode, cmd, result.stderr)
                
        except subprocess.TimeoutExpired:
            raise TimeoutError("Database summary query timed out")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Database query failed: {e.stderr}")
    
    def _execute_with_progress(self, cmd: List[str], progress_callback: Optional[Callable], 
                               timeout_override: Optional[int] = None) -> Dict:
        """
        Execute command with real-time progress tracking and configurable timeout.
        
        Args:
            cmd: Command list for subprocess
            progress_callback: Function to call with (percentage, message) updates
            timeout_override: Optional timeout override in seconds (None = use config default)
            
        Returns:
            Dictionary with execution results
            
        Raises:
            TimeoutError: If operation exceeds configured timeout
            
        Implementation: Uses threading to capture output in real-time and
        parse progress indicators from CLI output. Timeout is configurable
        via config file, environment variable, or method parameter.
        """
        self.current_operation = {
            "command": " ".join(cmd),
            "start_time": time.time(),
            "status": "running"
        }
        
        try:
            # Start subprocess with pipes for real-time output
            # Force unbuffered output for immediate progress updates
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'  # Force Python unbuffered output
            
            process = subprocess.Popen(
                cmd,
                cwd=self.backend_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,  # Unbuffered for real-time output
                universal_newlines=True,
                env=env
            )
            
            # Thread for reading output and parsing progress
            output_lines = []
            progress_thread = threading.Thread(
                target=self._parse_output_stream,
                args=(process.stdout, output_lines, progress_callback)
            )
            progress_thread.start()
            
            # Wait for completion with configurable timeout
            operation_timeout = self._get_operation_timeout(timeout_override)
            
            # Debug logging for timeout resolution
            if self.enable_debug_timeouts:
                timeout_source = "override" if timeout_override else "config/env"
                timeout_display = self._format_timeout_duration(operation_timeout)
                print(f"DEBUG: Using timeout: {timeout_display} (source: {timeout_source})")
            
            try:
                returncode = process.wait(timeout=operation_timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                timeout_duration = self._format_timeout_duration(operation_timeout)
                cmd_str = " ".join(cmd[:3])  # First 3 command parts for context
                raise TimeoutError(f"Operation '{cmd_str}...' timed out after {timeout_duration}")
            
            progress_thread.join()
            
            # Parse final results
            full_output = "\n".join(output_lines)
            results = self._parse_final_results(full_output)
            
            self.current_operation["status"] = "completed" if returncode == 0 else "failed"
            self.current_operation["end_time"] = time.time()
            
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, cmd, full_output)
            
            return results
            
        except Exception as e:
            self.current_operation["status"] = "failed"
            self.current_operation["error"] = str(e)
            raise
    
    def _parse_output_stream(self, stdout, output_lines: List[str], progress_callback: Optional[Callable]) -> None:
        """
        Parse CLI output stream for progress indicators.
        
        Args:
            stdout: Process stdout stream
            output_lines: List to append output lines to
            progress_callback: Function to call with progress updates
            
        Design Decision: Regex patterns match the specific progress format
        used by the backend CLI for consistent progress tracking.
        """
        # Enhanced progress patterns matching real backend output format
        # Formats: "\033[96mℹ 📊 Progress: 45/120 (37.5%)\033[0m" OR "📊 Progress: 25/100 (25.0%) | Success: 5, Failed: 20"
        # Made info symbol optional to capture authentication testing progress
        progress_pattern = re.compile(r'(?:\033\[\d+m)?(?:ℹ\s*)?📊 Progress: (\d+)/(\d+) \((\d+(?:\.\d+)?)\%\)(?:\s*\|.*?)?(?:\033\[\d+m)?')
        
        # Workflow step detection for phase transitions
        # Format: "\033[94m[1/4] Discovery & Authentication\033[0m"
        workflow_pattern = re.compile(r'(?:\033\[\d+m)?\[(\d+)/(\d+)\]\s*(.+?)(?:\033\[\d+m)?$')
        
        # General status pattern with ANSI color support
        status_pattern = re.compile(r'(?:\033\[\d+m)?([ℹ✓⚠✗🚀])\s*(.+?)(?:\033\[\d+m)?$')
        
        # Early-stage patterns for immediate feedback
        shodan_pattern = re.compile(r'(?:Shodan|Query|Discovery|API).*?(\d+).*?(?:results?|found|hosts?|entries)', re.IGNORECASE)
        database_pattern = re.compile(r'(?:Database|DB).*?(\d+).*?(?:servers?|hosts?|known)', re.IGNORECASE)
        
        # Authentication testing detection (for phase transition)
        auth_testing_start_pattern = re.compile(r'Testing SMB authentication on (\d+) hosts', re.IGNORECASE)
        
        # Enhanced detailed progress patterns
        host_progress_pattern = re.compile(r'(?:Testing|Processing|Checking).*?(?:host|server).*?(\d+).*?of.*?(\d+)', re.IGNORECASE)
        share_progress_pattern = re.compile(r'(?:Enumerating|Checking).*?share.*?(\d+).*?of.*?(\d+)', re.IGNORECASE)
        auth_success_pattern = re.compile(r'Success:\s*(\d+),?\s*Failed:\s*(\d+)', re.IGNORECASE)
        
        # Phase detection patterns with workflow step support
        phase_patterns = {
            'discovery': re.compile(r'(?:Discovery|Shodan|Query|Found.*SMB.*servers|Step\s*1)', re.IGNORECASE),
            'authentication': re.compile(r'(?:Testing SMB authentication|Authentication testing)', re.IGNORECASE),
            'access_testing': re.compile(r'(?:Access|Share.*Verification|Step\s*2)', re.IGNORECASE), 
            'collection': re.compile(r'(?:Collection|Enumeration|File|Step\s*3)', re.IGNORECASE),
            'reporting': re.compile(r'(?:Report|Intelligence|Step\s*4)', re.IGNORECASE)
        }
        
        for line in stdout:
            line = line.strip()
            output_lines.append(line)
            
            if not progress_callback:
                continue
            
            # Parse workflow step transitions first (gives us phase context)
            workflow_match = workflow_pattern.search(line)
            if workflow_match:
                step_num, total_steps, step_name = workflow_match.groups()
                step_percentage = self._calculate_workflow_step_percentage(int(step_num), int(total_steps))
                progress_callback(step_percentage, f"Step {step_num}/{total_steps}: {step_name}")
                continue
            
            # Parse explicit progress indicators (main progress tracking)
            progress_match = progress_pattern.search(line)
            if progress_match:
                current, total, percentage = progress_match.groups()
                
                # Detect current phase for progress mapping
                current_phase = self._detect_phase(line, phase_patterns)
                
                # Map backend percentage to workflow step range
                raw_percentage = float(percentage)
                mapped_percentage = self._map_progress_to_workflow_range(raw_percentage, current_phase)
                
                # Extract additional context if present
                auth_match = auth_success_pattern.search(line)
                if auth_match:
                    success, failed = auth_match.groups()
                    message = f"Testing hosts: {current}/{total} (Success: {success}, Failed: {failed})"
                else:
                    message = f"Processing {current}/{total} hosts"
                
                progress_callback(mapped_percentage, message)
                continue
            
            # Parse early-stage activity for immediate feedback
            shodan_match = shodan_pattern.search(line)
            if shodan_match:
                count = shodan_match.group(1)
                progress_callback(10.0, f"Shodan query found {count} potential targets")
                continue
            
            database_match = database_pattern.search(line)
            if database_match:
                count = database_match.group(1)
                progress_callback(5.0, f"Database loaded: {count} known servers")
                continue
            
            # Detect authentication testing start
            auth_start_match = auth_testing_start_pattern.search(line)
            if auth_start_match:
                count = auth_start_match.group(1)
                progress_callback(15.0, f"Starting authentication tests on {count} hosts...")
                continue
            
            # Determine current phase for context
            current_phase = self._detect_phase(line, phase_patterns)
            
            # Parse detailed progress based on enhanced patterns
            detailed_progress = self._parse_detailed_progress(line, {
                'host_progress': host_progress_pattern,
                'share_progress': share_progress_pattern,
                'auth_success': auth_success_pattern
            })
            
            if detailed_progress:
                percentage, message = detailed_progress
                progress_callback(percentage, message)
                continue
            
            # Parse general status messages with improved context
            status_match = status_pattern.search(line)
            if status_match:
                icon, message = status_match.groups()
                # Estimate progress based on phase, icon, and keywords
                percentage = self._estimate_progress_from_status(message, current_phase, icon)
                # Only report if we have meaningful progress to show
                if percentage is not None and percentage > 0:
                    progress_callback(percentage, message)
    
    def _detect_phase(self, line: str, phase_patterns: Dict) -> Optional[str]:
        """
        Detect current scan phase from output line.
        
        Args:
            line: Output line to analyze
            phase_patterns: Dictionary of phase patterns
            
        Returns:
            Detected phase name or None
        """
        for phase, pattern in phase_patterns.items():
            if pattern.search(line):
                return phase
        return None
    
    def _calculate_workflow_step_percentage(self, step_num: int, total_steps: int) -> float:
        """
        Calculate progress percentage based on workflow step.
        
        Maps workflow steps to progress ranges (updated for authentication phase):
        - Step 1 (Discovery): 5-25% (includes Shodan: 5-15%, Authentication: 15-25%)
        - Step 2 (Access Testing): 25-60%  
        - Step 3 (Collection): 60-90%
        - Step 4 (Reporting): 90-100%
        
        Args:
            step_num: Current step number (1-based)
            total_steps: Total number of steps
            
        Returns:
            Progress percentage for step start
        """
        if total_steps == 4:  # Standard workflow
            step_ranges = {1: 5.0, 2: 25.0, 3: 60.0, 4: 90.0}
            return step_ranges.get(step_num, 0.0)
        else:
            # Generic calculation for non-standard workflows
            return ((step_num - 1) / total_steps) * 100
    
    def _parse_detailed_progress(self, line: str, patterns: Dict) -> Optional[Tuple[float, str]]:
        """
        Parse detailed progress information from output line.
        
        Args:
            line: Output line to analyze
            patterns: Dictionary of progress patterns
            
        Returns:
            Tuple of (percentage, message) or None if no match
        """
        # Host processing progress (access testing phase)
        host_match = patterns['host_progress'].search(line)
        if host_match:
            current, total = host_match.groups()
            percentage = 25 + ((int(current) / int(total)) * 35)  # 25-60% range for access testing
            return percentage, f"Testing host {current}/{total}"
        
        # Share enumeration progress (collection phase)
        share_match = patterns['share_progress'].search(line)
        if share_match:
            current, total = share_match.groups()
            percentage = 60 + ((int(current) / int(total)) * 30)  # 60-90% range for collection
            return percentage, f"Enumerating share {current}/{total}"
        
        # Authentication success/failure tracking
        auth_match = patterns['auth_success'].search(line)
        if auth_match:
            success, failed = auth_match.groups()
            total_processed = int(success) + int(failed)
            # Return context but let main progress pattern handle percentage
            return None, f"Auth results: {success} success, {failed} failed"
        
        return None
    
    def _estimate_progress_from_status(self, message: str, phase: Optional[str], icon: str = "") -> Optional[float]:
        """
        Estimate progress percentage from status message, phase, and icon.
        
        Args:
            message: Status message
            phase: Current detected phase
            icon: Status icon (ℹ✓⚠✗🚀)
            
        Returns:
            Estimated percentage or None if no meaningful progress
        """
        message_lower = message.lower()
        
        # Phase-based base percentages
        phase_bases = {
            'discovery': 5,
            'authentication': 15,
            'access_testing': 30,
            'collection': 70,
            'reporting': 90
        }
        
        base_percentage = phase_bases.get(phase, 0)
        
        # Keyword-based adjustments
        if "starting" in message_lower or "initializing" in message_lower:
            return base_percentage
        elif "complete" in message_lower or "finished" in message_lower:
            return min(95, base_percentage + 20)
        elif "processing" in message_lower or "working" in message_lower:
            return base_percentage + 10
        elif "found" in message_lower:
            return base_percentage + 5
        elif "failed" in message_lower or "error" in message_lower:
            return None  # Don't estimate for errors
        
        return base_percentage
    
    def _map_progress_to_workflow_range(self, backend_percentage: float, phase: Optional[str]) -> float:
        """
        Map backend progress percentage (0-100%) to workflow step range based on detected phase.
        
        Workflow step ranges:
        - Discovery/Shodan: 0-100% → 5-15%
        - Authentication: 0-100% → 15-25%  
        - Access Testing: 0-100% → 25-60%
        - Collection: 0-100% → 60-90%
        - Reporting: 0-100% → 90-100%
        
        Args:
            backend_percentage: Raw percentage from backend (0-100)
            phase: Detected phase name
            
        Returns:
            Mapped percentage for GUI workflow display
        """
        # Phase-specific ranges (start, end)
        phase_ranges = {
            'discovery': (5.0, 15.0),
            'authentication': (15.0, 25.0), 
            'access_testing': (25.0, 60.0),
            'collection': (60.0, 90.0),
            'reporting': (90.0, 100.0)
        }
        
        if phase not in phase_ranges:
            # Fallback to raw percentage if phase unknown
            return backend_percentage
            
        start, end = phase_ranges[phase]
        range_size = end - start
        
        # Map backend 0-100% to phase range
        mapped_percentage = start + (backend_percentage / 100.0) * range_size
        
        # Ensure we don't exceed the phase range
        return min(end, max(start, mapped_percentage))
    
    def _parse_final_results(self, output: str) -> Dict:
        """
        Parse final results from CLI output.
        
        Args:
            output: Complete CLI output text
            
        Returns:
            Dictionary with parsed results
            
        Implementation: Regex patterns extract key statistics from the
        "Discovery Results" section of CLI output.
        """
        results = {
            "success": False,
            "shodan_results": 0,
            "hosts_tested": 0,
            "successful_auth": 0,
            "failed_auth": 0,
            "session_id": None,
            "raw_output": output
        }
        
        # Parse results section
        patterns = {
            "shodan_results": r'Shodan Results: (\d+)',
            "hosts_tested": r'Hosts Tested: (\d+)',
            "successful_auth": r'Successful Auth: (\d+)',
            "failed_auth": r'Failed Auth: (\d+)',
            "session_id": r'session: (\d+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, output)
            if match:
                value = match.group(1)
                results[key] = int(value) if value.isdigit() else value
        
        # Check for success indicators
        if "✓ Found" in output and "accessible SMB servers" in output:
            results["success"] = True
        
        return results
    
    def _parse_summary_output(self, output: str) -> Dict:
        """
        Parse database summary output.
        
        Args:
            output: CLI summary output
            
        Returns:
            Dictionary with summary statistics
        """
        # Default values
        summary = {
            "total_servers": 0,
            "accessible_shares": 0,
            "vulnerabilities": 0,
            "recent_discoveries": {
                "display": "--",
                "warning": "Cannot load recent scan results"
            }
        }
        
        # Parse summary statistics from output
        # This would need to match the actual CLI output format
        lines = output.split('\n')
        for line in lines:
            if "servers" in line.lower():
                numbers = re.findall(r'\d+', line)
                if numbers:
                    summary["total_servers"] = int(numbers[0])
            elif "shares" in line.lower():
                numbers = re.findall(r'\d+', line)
                if numbers:
                    summary["accessible_shares"] = int(numbers[0])
            elif "vulnerabilities" in line.lower():
                numbers = re.findall(r'\d+', line)
                if numbers:
                    summary["vulnerabilities"] = int(numbers[0])
        
        return summary
    
    def run_initialization_scan(self, config_path: Optional[str] = None,
                               progress_callback: Optional[Callable[[float, str], None]] = None) -> Dict[str, Any]:
        """
        Run initialization scan to create a new database.
        
        Args:
            config_path: Path to configuration file 
            progress_callback: Function to call with progress updates (percentage, message)
            
        Returns:
            Dictionary with scan results and database path
        """
        if self.mock_mode:
            return self._mock_initialization_scan(progress_callback)
        
        try:
            if progress_callback:
                progress_callback(5, "Reading configuration...")
            
            # Read configuration to get scan parameters
            config = self._load_config(config_path)
            if not config:
                raise RuntimeError(f"Failed to load configuration from {config_path}")
            
            if progress_callback:
                progress_callback(10, f"Configuration loaded: {config_path}")
            
            # Extract scan parameters from config
            countries = config.get('countries', ['US'])  # Default to US if not specified
            if isinstance(countries, str):
                countries = [countries]
            
            if progress_callback:
                progress_callback(15, f"Starting scan for countries: {', '.join(countries)}")
            
            # Run the scan using existing run_scan method
            scan_result = self.run_scan(countries, progress_callback)
            
            # Determine database path
            db_path = os.path.join(self.backend_path, "smbseek.db")
            
            # Enhance result with database information
            result = {
                'success': scan_result.get('success', False),
                'database_path': db_path,
                'servers_found': scan_result.get('hosts_tested', 0),
                'scan_result': scan_result
            }
            
            if not result['success']:
                result['error'] = scan_result.get('error', 'Scan failed for unknown reason')
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'database_path': None
            }
    
    def _load_config(self, config_path: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Load configuration from file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Configuration dictionary or None if failed
        """
        if not config_path:
            config_path = os.path.join(self.backend_path, "conf", "config.json")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def _mock_initialization_scan(self, progress_callback: Optional[Callable[[float, str], None]] = None) -> Dict[str, Any]:
        """
        Mock initialization scan for testing.
        
        Args:
            progress_callback: Progress callback function
            
        Returns:
            Mock scan results
        """
        import time
        
        progress_steps = [
            (5, "Reading configuration..."),
            (15, "Configuration loaded: ../backend/conf/config.json"),
            (25, "Starting scan for countries: US"),
            (40, "Connecting to Shodan API..."),
            (55, "Processing host discovery..."),
            (70, "Testing SMB connections..."),
            (85, "Analyzing results..."),
            (95, "Creating database..."),
            (100, "Scan completed successfully")
        ]
        
        for percentage, message in progress_steps:
            if progress_callback:
                progress_callback(percentage, message)
            time.sleep(0.5)  # Simulate work
        
        return {
            'success': True,
            'database_path': '../backend/smbseek.db',
            'servers_found': 25,
            'scan_result': {
                'success': True,
                'hosts_tested': 25,
                'successful_auth': 5,
                'failed_auth': 20
            }
        }
    
    def _mock_scan_operation(self, countries: List[str], progress_callback: Optional[Callable]) -> Dict:
        """
        Mock scan operation for testing.
        
        Args:
            countries: Countries to "scan"
            progress_callback: Progress callback function
            
        Returns:
            Mock scan results
            
        Design Decision: Realistic progress simulation helps test UI
        responsiveness and progress display functionality.
        """
        if progress_callback:
            # Simulate realistic scan progress
            stages = [
                (10, "Querying Shodan for SMB servers"),
                (20, "Applying exclusion filters"),
                (25, "Database filtering complete"),
                (30, "Testing SMB authentication on 120 hosts"),
                (50, "Progress: 60/120 (50.0%) | Success: 8, Failed: 52"),
                (75, "Progress: 90/120 (75.0%) | Success: 18, Failed: 72"),
                (100, "Discovery complete")
            ]
            
            for percentage, message in stages:
                time.sleep(0.5)  # Simulate work
                progress_callback(percentage, message)
        
        return {
            "success": True,
            "shodan_results": 150,
            "hosts_tested": 120,
            "successful_auth": 23,
            "failed_auth": 97,
            "session_id": 3,
            "countries": countries
        }
    
    def _mock_discover_operation(self, countries: List[str], progress_callback: Optional[Callable]) -> Dict:
        """Mock discovery-only operation."""
        return self._mock_scan_operation(countries, progress_callback)
    
    def get_operation_status(self) -> Optional[Dict]:
        """
        Get status of current operation.
        
        Returns:
            Dictionary with operation status or None if no operation running
        """
        return self.current_operation
    
    def is_backend_available(self) -> bool:
        """
        Check if backend is available and functional.
        
        Returns:
            True if backend can be accessed, False otherwise
        """
        if self.mock_mode:
            return True
        
        try:
            result = subprocess.run(
                [str(self.cli_script), "--help"],
                cwd=self.backend_path,
                capture_output=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
            return False
    
    def get_backend_version(self) -> Optional[str]:
        """
        Get backend version information.
        
        Returns:
            Version string or None if unavailable
        """
        if self.mock_mode:
            return "2.0.0 (mock)"
        
        try:
            result = subprocess.run(
                [str(self.cli_script), "--version"],
                cwd=self.backend_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                # Extract version from output
                version_match = re.search(r'SMBSeek (\S+)', result.stdout)
                if version_match:
                    return version_match.group(1)
            return "Unknown"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None