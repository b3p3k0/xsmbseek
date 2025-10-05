"""
SMBSeek Backend Interface

Provides subprocess wrapper for CLI commands with output parsing and progress tracking.
Implements complete backend isolation without any code modifications.

Design Decision: Use subprocess calls rather than direct imports to maintain
complete separation between GUI and backend teams' code.
"""

import subprocess
import sys
import threading
import queue
import json
import os
import re
import time
import signal
from contextlib import contextmanager
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

    
    def __init__(self, backend_path: str = "./smbseek", mock_mode: bool = False):
        """
        Initialize backend interface.

        Args:
            backend_path: Path to SMBSeek installation directory
            mock_mode: Enable mock mode for testing without backend

        Design Decision: Default to ./smbseek for new structure, but allow
        complete override for different deployment scenarios.
        """
        self.backend_path = Path(backend_path).resolve()
        self.cli_script = self.backend_path / "smbseek.py"
        self.config_path = self.backend_path / "conf" / "config.json"
        self.config_example_path = self.backend_path / "conf" / "config.json.example"

        # Mock mode for testing without backend
        self.mock_mode = mock_mode

        # Ensure configuration file exists (skip in mock mode)
        if not self.mock_mode:
            self._ensure_config_exists()
        
        # Progress tracking for long-running operations
        self.progress_queue = queue.Queue()
        self.current_operation = None

        # Cancellation tracking for subprocess operations
        self.active_process = None
        self.active_output_thread = None
        self.cancel_requested = False
        
        # Phase tracking with persistence for better progress accuracy
        self.last_known_phase = None
        self.phase_progression = ['discovery', 'authentication', 'access_testing']
        
        # Use gui directory for mock data (relative to where GUI components are)
        self.mock_data_path = Path(__file__).parent.parent / "test_data" / "mock_responses"
        
        # Timeout configuration - loaded from config with environment override support
        self.default_timeout = None  # No timeout by default
        self.enable_debug_timeouts = False
        
        # Recent filtering configuration - loaded from SMBSeek config
        self.default_recent_days = 90  # Default 90 days as per backend team recommendations
        
        # Load configuration and validate backend (skip in mock mode)
        if not self.mock_mode:
            self._load_timeout_configuration()
            self._load_workflow_configuration()
            self._cleanup_startup_locks()
            self._validate_backend()
        else:
            # Set mock defaults
            self.default_timeout = None
            self.enable_debug_timeouts = False
            self.default_recent_days = 90
    
    def _ensure_config_exists(self) -> None:
        """
        Ensure SMBSeek configuration file exists, creating from example if needed.
        
        Raises:
            RuntimeError: If configuration cannot be created or validated
        """
        if not self.config_path.exists():
            if self.config_example_path.exists():
                # Copy example config
                import shutil
                shutil.copy2(self.config_example_path, self.config_path)
            else:
                raise RuntimeError(f"SMBSeek configuration template not found at {self.config_example_path}")
    
    def _validate_config(self) -> Dict[str, Any]:
        """
        Validate SMBSeek configuration and return validation results.
        
        Returns:
            Dictionary with validation results and warnings
        """
        validation_result = {
            "valid": True,
            "warnings": [],
            "errors": []
        }
        
        if not self.config_path.exists():
            validation_result["valid"] = False
            validation_result["errors"].append("Configuration file does not exist")
            return validation_result
        
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # Check for required Shodan API key
            shodan_key = config.get('shodan', {}).get('api_key', '')
            if not shodan_key or shodan_key == 'YOUR_API_KEY_HERE':
                validation_result["warnings"].append(
                    "Shodan API key not configured - discovery functionality will be limited"
                )
            
            # Validate country codes if specified
            if 'countries' in config:
                country_codes = config['countries']
                if not isinstance(country_codes, dict) or not country_codes:
                    validation_result["warnings"].append("No country codes configured")
            
        except json.JSONDecodeError as e:
            validation_result["valid"] = False
            validation_result["errors"].append(f"Invalid JSON in configuration: {e}")
        except Exception as e:
            validation_result["valid"] = False
            validation_result["errors"].append(f"Error reading configuration: {e}")
        
        return validation_result
    
    def _extract_error_details(self, full_output: str, cmd: List[str]) -> str:
        """
        Extract meaningful error details from SMBSeek CLI output with enhanced
        error handling for recent filtering scenarios.
        
        Args:
            full_output: Complete output from failed command
            cmd: The command that failed
            
        Returns:
            User-friendly error message with actual CLI error details
        """
        lines = full_output.split('\n')
        
        # Check for specific recent filtering errors first (as per backend team recommendations)
        for line in lines:
            line_clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
            
            # Pattern: "No authenticated hosts found from the last N hours"
            if "No authenticated hosts found from the last" in line_clean:
                return f"RECENT_HOSTS_ERROR: {line_clean}"
            
            # Pattern: "None of the specified servers are authenticated"
            if "None of the specified servers are authenticated" in line_clean:
                return f"SERVERS_NOT_AUTHENTICATED: {line_clean}"

            # Missing dependency patterns (smbprotocol / pyspnego not installed)
            missing_dependency_substrings = (
                "SMB libraries not available",
                "ModuleNotFoundError: No module named 'smbprotocol'",
                'ModuleNotFoundError: No module named "smbprotocol"',
                "ModuleNotFoundError: No module named 'pyspnego'",
                'ModuleNotFoundError: No module named "pyspnego"',
                "No module named 'smbprotocol'",
                'No module named "smbprotocol"',
                "No module named 'pyspnego'",
                'No module named "pyspnego"'
            )
            if any(substring in line_clean for substring in missing_dependency_substrings):
                friendly_message = (
                    "SMBSeek backend is missing required SMB libraries (smbprotocol). "
                    "This usually happens when the xsmbseek GUI runs outside the project "
                    "virtual environment. Activate the venv (e.g., `source venv/bin/activate`) "
                    "or install the dependencies with `pip install -r requirements.txt`.\n"
                    f"Backend output: {line_clean}"
                )
                return f"DEPENDENCY_MISSING: {friendly_message}"
        
        # Look for common error patterns
        error_indicators = [
            'error:', 'Error:', 'ERROR:',
            'failed:', 'Failed:', 'FAILED:',
            'exception:', 'Exception:', 'EXCEPTION:',
            'traceback', 'Traceback',
            'invalid', 'Invalid', 'INVALID',
            'missing', 'Missing', 'MISSING',
            'not found', 'Not found', 'NOT FOUND'
        ]
        
        # Extract relevant error lines
        error_lines = []
        for line in lines:
            line_lower = line.lower().strip()
            if any(indicator.lower() in line_lower for indicator in error_indicators):
                # Clean up ANSI codes and whitespace
                clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
                if clean_line:
                    error_lines.append(clean_line)
        
        if error_lines:
            # Return first few error lines
            return '\n'.join(error_lines[:3])
        
        # If no specific errors found, look for last non-empty lines
        non_empty_lines = [line.strip() for line in lines if line.strip()]
        if non_empty_lines:
            # Return last few lines which often contain the error
            last_lines = non_empty_lines[-3:]
            # Clean up ANSI codes
            clean_lines = [re.sub(r'\x1b\[[0-9;]*m', '', line) for line in last_lines]
            return '\n'.join(clean_lines)
        
        # Fallback to command and basic info
        return f"Command failed: {' '.join(cmd[:3])}{'...' if len(cmd) > 3 else ''}"
    
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

    def _build_cli_command(self, *args) -> List[str]:
        """
        Build CLI command with proper Python interpreter.

        Uses the same Python interpreter that launched the GUI to ensure
        subprocess commands inherit the correct environment and dependencies.

        Args:
            *args: CLI arguments to pass to SMBSeek script

        Returns:
            Command list with interpreter, script path, and arguments
        """
        # Determine Python interpreter (same as GUI for environment consistency)
        interpreter = sys.executable
        if not interpreter:
            # Fallback chain for robustness
            interpreter = 'python3'  # Unix/Linux standard

        # Ensure script path is string (currently Path object)
        script_path = str(self.cli_script)

        command_list = [interpreter, script_path, *args]
        debug_enabled = os.getenv("XSMBSEEK_DEBUG_SUBPROCESS")
        if debug_enabled:
            print(f"DEBUG: CLI command -> interpreter={interpreter} cmd={command_list}")  # TODO: remove debug logging
        return command_list

    def _build_tool_command(self, script_name: str, *args) -> List[str]:
        """
        Build command for tools/ scripts with proper interpreter and path resolution.

        Args:
            script_name: Name of script in tools/ directory (e.g., "db_query.py")
            *args: Arguments to pass to the tool script

        Returns:
            Command list with interpreter, tool script path, and arguments
        """
        # Determine Python interpreter (same as GUI for environment consistency)
        interpreter = sys.executable
        if not interpreter:
            interpreter = 'python3'  # Unix/Linux standard

        # Build cross-platform path to tool script
        script_path = str(self.backend_path / "tools" / script_name)

        command_list = [interpreter, script_path, *args]
        debug_enabled = os.getenv("XSMBSEEK_DEBUG_SUBPROCESS")
        if debug_enabled:
            print(f"DEBUG: Tool command -> interpreter={interpreter} cmd={command_list}")  # TODO: remove debug logging
        return command_list

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
        Load timeout configuration from config files with environment override support.
        
        Configuration hierarchy (highest priority first):
        1. Environment variable: SMBSEEK_GUI_TIMEOUT
        2. xsmbseek-config.json gui.operation_timeout_seconds
        3. SMBSeek config.json gui.operation_timeout_seconds (if present)
        4. Default: None (no timeout)
        
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
            
            # Try to load from GUI config first (xsmbseek-config.json)
            gui_config_path = self.backend_path.parent / "xsmbseek-config.json"
            if gui_config_path.exists():
                with open(gui_config_path, 'r') as f:
                    gui_config = json.load(f)
                
                gui_settings = gui_config.get('gui', {})
                if 'operation_timeout_seconds' in gui_settings:
                    self.default_timeout = gui_settings.get('operation_timeout_seconds', None)
                    self.enable_debug_timeouts = gui_settings.get('enable_debug_timeouts', False)
                    
                    # Handle explicit zero as no timeout
                    if self.default_timeout == 0:
                        self.default_timeout = None
                    return
            
            # Fallback to SMBSeek config file
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
    
    def _load_workflow_configuration(self) -> None:
        """
        Load workflow configuration from SMBSeek config file.
        
        Loads settings for recent filtering and other workflow parameters.
        """
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                
                workflow_config = config.get('workflow', {})
                self.default_recent_days = workflow_config.get('access_recent_days', 90)
                
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            # Fallback to safe defaults
            self.default_recent_days = 90
            print(f"Warning: Could not load workflow configuration: {e}")
            print("Using default: 90 days for recent filtering")
    
    def _cleanup_startup_locks(self) -> None:
        """
        Clean up stale lock files on startup as recommended by backend team.
        
        Ensures proper coordination between GUI and backend operations by
        removing orphaned lock files from crashed processes.
        """
        try:
            # Define GUI directory (parent of backend path for xsmbseek layout)
            gui_dir = self.backend_path.parent
            
            # Clean up potential GUI lock files in xsmbseek directory
            gui_lock_patterns = [
                ".scan_lock",
                ".gui_operation_lock",
                ".access_verification_lock"
            ]
            
            for pattern in gui_lock_patterns:
                lock_path = gui_dir / pattern
                if lock_path.exists():
                    try:
                        # Check if lock file contains process information
                        with open(lock_path, 'r') as f:
                            lock_data = json.load(f)
                        
                        # Check if process is still running
                        pid = lock_data.get('process_id')
                        if pid and self._process_exists(pid):
                            # Process still exists, lock is valid - keep it
                            continue
                        
                        # Process doesn't exist, remove stale lock
                        lock_path.unlink()
                        
                    except (json.JSONDecodeError, FileNotFoundError, KeyError):
                        # Invalid or corrupted lock file, remove it
                        if lock_path.exists():
                            lock_path.unlink()
            
        except Exception:
            # Non-critical cleanup failure - continue without error
            # Backend team noted this should be graceful and not interrupt operations
            pass
    
    def _process_exists(self, pid: int) -> bool:
        """
        Check if process with given PID exists (for lock file validation).
        
        Args:
            pid: Process ID to check
            
        Returns:
            True if process exists, False otherwise
        """
        try:
            # Try psutil first if available (more reliable)
            try:
                import psutil
                return psutil.pid_exists(pid)
            except ImportError:
                pass
            
            # Fallback method using os.kill with signal 0
            import os
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
    
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
    
    def run_scan(self, countries: List[str], progress_callback: Optional[Callable] = None,
                 use_recent_filtering: bool = True, recent_days: Optional[int] = None,
                 additional_args: List[str] = None) -> Dict:
        """
        Execute complete SMBSeek scan workflow.

        Args:
            countries: List of country codes to scan
            progress_callback: Function to call with progress updates
            use_recent_filtering: Whether to apply recent filtering (default True)
            recent_days: Days for recent filtering (None uses config default)
            additional_args: Additional CLI arguments to pass to the scan command

        Returns:
            Dictionary with scan results and statistics

        Implementation: Recent filtering is now controlled through configuration
        overrides (workflow.access_recent_hours) instead of CLI --recent flag.
        SMBSeek 3.x removed the --recent CLI option in favor of config-based control.
        """
        if self.mock_mode:
            return self._mock_scan_operation(countries, progress_callback)

        # Build base command with verbose flag
        cmd = self._build_cli_command("--verbose")  # For detailed progress parsing

        # Only append --country when countries list is truthy per SMBSeek 3.0 requirements
        if countries:
            countries_str = ",".join(countries)
            cmd.extend(["--country", countries_str])

        # Add any additional CLI arguments
        if additional_args:
            cmd.extend(additional_args)

        # Handle recent filtering through config overrides instead of CLI flags
        config_overrides = {}
        if not use_recent_filtering:
            # Disable recent filtering by setting access_recent_hours to 0
            config_overrides['workflow'] = {'access_recent_hours': 0}
        elif recent_days is not None:
            # Apply custom recent filtering value
            recent_hours = recent_days * 24
            config_overrides['workflow'] = {'access_recent_hours': recent_hours}

        # Execute with config overrides if needed
        if config_overrides:
            with self._temporary_config_override(config_overrides):
                return self._execute_with_progress(cmd, progress_callback)
        else:
            # Use default config values (no override needed)
            return self._execute_with_progress(cmd, progress_callback)
    
    def run_discover(self, countries: List[str], progress_callback: Optional[Callable] = None) -> Dict:
        """
        DEPRECATED: Discovery-only mode has been removed in SMBSeek 3.0.
        This method now redirects to the unified scan workflow (no subcommands).
        Will be removed in a future version.

        Args:
            countries: List of country codes to scan
            progress_callback: Function to call with progress updates

        Returns:
            Dictionary with scan results (same as run_scan)
        """
        import warnings
        warnings.warn(
            "run_discover() is deprecated. Use run_scan() instead. "
            "Discovery-only mode has been removed in SMBSeek 3.0.",
            DeprecationWarning,
            stacklevel=2
        )
        print("⚠️  DEPRECATED: run_discover() called - redirecting to unified workflow")
        return self.run_scan(countries, progress_callback)
    
    def run_access_verification(self, recent_days: Optional[int] = None,
                               progress_callback: Optional[Callable] = None) -> Dict:
        """
        Execute access verification operation with recent filtering.

        Args:
            recent_days: Filter to hosts from last N days (None uses config default)
            progress_callback: Function to call with progress updates

        Returns:
            Dictionary with access verification results

        Implementation: Recent filtering is now controlled through configuration
        overrides (workflow.access_recent_hours) instead of CLI --recent flag.
        SMBSeek 3.x removed the --recent CLI option in favor of config-based control.
        """
        if self.mock_mode:
            return self._mock_access_verification_operation(recent_days, progress_callback)

        # Use configured default if not specified
        if recent_days is None:
            recent_days = self.default_recent_days

        # Convert days to hours for config override
        recent_hours = recent_days * 24

        # Build base command without --recent flag
        cmd = self._build_cli_command("--verbose")

        # Apply recent filtering through config override
        config_overrides = {'workflow': {'access_recent_hours': recent_hours}}
        with self._temporary_config_override(config_overrides):
            return self._execute_with_progress(cmd, progress_callback)
    
    def run_access_on_servers(self, ip_list: List[str], 
                             progress_callback: Optional[Callable] = None) -> Dict:
        """
        Execute access verification on specific servers.
        
        Args:
            ip_list: List of IP addresses to test
            progress_callback: Function to call with progress updates
            
        Returns:
            Dictionary with access verification results
        """
        if self.mock_mode:
            return self._mock_access_on_servers_operation(ip_list, progress_callback)
        
        if not ip_list:
            raise ValueError("Server list cannot be empty")
        
        servers_str = ",".join(ip_list)
        cmd = self._build_cli_command(
            "--servers", servers_str,
            "--verbose"
        )
        
        return self._execute_with_progress(cmd, progress_callback)
    
    def should_skip_recent_scan(self, recent_days: Optional[int] = None) -> bool:
        """
        Check if recent scan makes new scan redundant.

        Args:
            recent_days: Days to check for recent activity (None uses config default)

        Returns:
            True if recent scan exists and new scan should be skipped

        Note: This method is currently unused and may be deprecated.
        It uses db_query.py tool with --recent flag, which may differ from
        the main SMBSeek CLI that removed --recent in 3.x. The main scan
        methods now use config-based recent filtering instead.
        """
        if recent_days is None:
            recent_days = self.default_recent_days
            
        try:
            # Query database for recent scan activity using tool script
            recent_hours = recent_days * 24
            cmd = self._build_tool_command(
                "db_query.py",
                "--recent", str(recent_hours),
                "--count-only"
            )
            
            result = subprocess.run(
                cmd,
                cwd=self.backend_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Parse count from output
                output = result.stdout.strip()
                try:
                    count = int(output)
                    return count > 0  # Skip if we have recent results
                except ValueError:
                    return False
            else:
                return False  # Error - don't skip, let scan proceed
                
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            return False  # Error - don't skip, let scan proceed
    
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
        
        cmd = self._build_tool_command("db_query.py", "--summary")
        
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
            # Validate configuration before starting subprocess
            config_validation = self._validate_config()
            if not config_validation["valid"]:
                raise RuntimeError(f"Configuration validation failed: {'; '.join(config_validation['errors'])}")
            
            # Start subprocess with pipes for real-time output
            # Force unbuffered output for immediate progress updates
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'  # Force Python unbuffered output
            
            # Ensure Python path includes current directory for imports
            if 'PYTHONPATH' in env:
                env['PYTHONPATH'] = f"{self.backend_path}:{env['PYTHONPATH']}"
            else:
                env['PYTHONPATH'] = str(self.backend_path)
            
            # Platform-specific process group creation for proper cancellation
            if sys.platform.startswith('win'):
                # Windows: Create new process group to allow terminating children
                process = subprocess.Popen(
                    cmd,
                    cwd=self.backend_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=0,  # Unbuffered for real-time output
                    universal_newlines=True,
                    env=env,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                # POSIX: Start new session to create process group
                process = subprocess.Popen(
                    cmd,
                    cwd=self.backend_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=0,  # Unbuffered for real-time output
                    universal_newlines=True,
                    env=env,
                    start_new_session=True
                )
            
            # Thread for reading output and parsing progress
            output_lines = []
            progress_thread = threading.Thread(
                target=self._parse_output_stream,
                args=(process.stdout, output_lines, progress_callback)
            )
            progress_thread.start()

            # Track active process and thread for cancellation
            self.active_process = process
            self.active_output_thread = progress_thread

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

            # Check for cancellation before processing results
            if self.cancel_requested:
                # Operation was cancelled - return cancellation result
                return {
                    "success": False,
                    "cancelled": True,
                    "error": "Scan cancelled by user"
                }

            # Parse final results for normal completion
            full_output = "\n".join(output_lines)
            debug_enabled = os.getenv("XSMBSEEK_DEBUG_SUBPROCESS")
            if debug_enabled:
                print("DEBUG: CLI output start")  # TODO: remove debug logging
                print(full_output)
                print("DEBUG: CLI output end")  # TODO: remove debug logging
            results = self._parse_final_results(full_output)

            self.current_operation["status"] = "completed" if returncode == 0 else "failed"
            self.current_operation["end_time"] = time.time()

            if returncode != 0:
                # Extract meaningful error message from output
                error_details = self._extract_error_details(full_output, cmd)

                # Handle specific error cases with automatic recovery
                if error_details.startswith("RECENT_HOSTS_ERROR:"):
                    # No recent hosts found - attempt automatic discovery as fallback
                    return self._handle_no_recent_hosts_error(cmd, error_details, progress_callback)
                elif error_details.startswith("SERVERS_NOT_AUTHENTICATED:"):
                    # Specified servers not authenticated - suggest discovery
                    return self._handle_servers_not_authenticated_error(cmd, error_details)
                elif error_details.startswith("DEPENDENCY_MISSING:"):
                    _, _, friendly_message = error_details.partition(":")
                    raise RuntimeError(friendly_message.strip())
                else:
                    # Regular error - no automatic recovery
                    raise subprocess.CalledProcessError(returncode, cmd, error_details)

            return results

        except Exception as e:
            self.current_operation["status"] = "failed"
            self.current_operation["error"] = str(e)
            raise
        finally:
            # Clean up cancellation state after operation completes/fails/is cancelled
            # Ensure thread is joined and state is reset
            if progress_thread.is_alive():
                try:
                    progress_thread.join(timeout=5)
                except (threading.ThreadError, RuntimeError):
                    pass

            # Reset cancellation tracking state
            self.active_process = None
            self.active_output_thread = None
            self.cancel_requested = False
    
    def _handle_no_recent_hosts_error(self, original_cmd: List[str], error_details: str, 
                                     progress_callback: Optional[Callable]) -> Dict:
        """
        Handle 'no recent hosts found' error with automatic discovery fallback.
        
        Args:
            original_cmd: The original command that failed
            error_details: Error details from CLI output
            progress_callback: Progress callback for discovery operation
            
        Returns:
            Dictionary with discovery results or error information
        """
        try:
            if progress_callback:
                progress_callback(0, "No recent hosts found - running discovery first...")
            
            # Extract countries from original command if available
            countries = []
            if "--country" in original_cmd:
                country_index = original_cmd.index("--country")
                if country_index + 1 < len(original_cmd):
                    countries_str = original_cmd[country_index + 1]
                    countries = countries_str.split(",")
            
            # If no countries found, default to US
            if not countries:
                countries = ["US"]
            
            # Run discovery operation
            discovery_result = self.run_discover(countries, progress_callback)
            
            # Return discovery result with indication of fallback
            discovery_result["fallback_reason"] = "no_recent_hosts"
            discovery_result["original_error"] = error_details
            discovery_result["automatic_discovery"] = True
            
            return discovery_result
            
        except Exception as e:
            # Discovery also failed - return combined error information
            return {
                "success": False,
                "error": f"Automatic discovery fallback failed: {str(e)}",
                "original_error": error_details,
                "fallback_attempted": True
            }
    
    def _handle_servers_not_authenticated_error(self, original_cmd: List[str], error_details: str) -> Dict:
        """
        Handle 'servers not authenticated' error.
        
        Args:
            original_cmd: The original command that failed
            error_details: Error details from CLI output
            
        Returns:
            Dictionary with error information and suggested recovery
        """
        # Extract server list from command if available
        servers = []
        if "--servers" in original_cmd:
            server_index = original_cmd.index("--servers")
            if server_index + 1 < len(original_cmd):
                servers_str = original_cmd[server_index + 1]
                servers = servers_str.split(",")
        
        return {
            "success": False,
            "error": "Specified servers are not authenticated",
            "error_type": "servers_not_authenticated",
            "affected_servers": servers,
            "suggestion": "Run discovery on these servers first to establish authentication",
            "original_error": error_details,
            "recovery_action": "discovery_needed"
        }


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
        # Reset phase tracking for new scan
        self.last_known_phase = None
        # Enhanced progress patterns matching real backend output format
        # Formats: "\033[96mℹ 📊 Progress: 45/120 (37.5%)\033[0m" OR "📊 Progress: 25/100 (25.0%) | Success: 5, Failed: 20"
        # Also handles recent filtering: "Testing recent hosts: 25/100 (25.0%)"
        # Made info symbol optional to capture authentication testing progress
        progress_pattern = re.compile(r'(?:\033\[\d+m)?(?:ℹ\s*)?(?:📊\s*Progress:|Testing\s+recent\s+hosts?:)\s*(\d+)/(\d+)\s*\((\d+(?:\.\d+)?)\%\)(?:\s*\|.*?)?(?:\033\[\d+m)?')
        
        # Workflow step detection for phase transitions
        # Format: "\033[94m[1/4] Discovery & Authentication\033[0m"
        workflow_pattern = re.compile(r'(?:\033\[\d+m)?\[(\d+)/(\d+)\]\s*(.+?)(?:\033\[\d+m)?$')
        
        # General status pattern with ANSI color support
        status_pattern = re.compile(r'(?:\033\[\d+m)?([ℹ✓⚠✗🚀])\s*(.+?)(?:\033\[\d+m)?$')
        
        # Early-stage patterns for immediate feedback
        shodan_pattern = re.compile(r'(?:Shodan|Query|Discovery|API).*?(\d+).*?(?:results?|found|hosts?|entries)', re.IGNORECASE)
        database_pattern = re.compile(r'(?:Database|DB).*?(\d+).*?(?:servers?|hosts?|known)', re.IGNORECASE)
        
        # Recent filtering specific patterns (as per backend team recommendations)
        recent_filtering_pattern = re.compile(r'(?:Loading|Found|Testing).*?(?:from\s+last|within\s+last|recent).*?(\d+).*?(?:days?|hours?).*?(\d+)?.*?(?:hosts?|servers?)', re.IGNORECASE)
        skipped_hosts_pattern = re.compile(r'(?:Skipped|Skipping).*?(\d+).*?(?:hosts?|servers?).*?(?:recent|within|last)', re.IGNORECASE)
        
        # Authentication testing detection (for phase transition)
        auth_testing_start_pattern = re.compile(r'Testing SMB authentication on (\d+) hosts', re.IGNORECASE)
        
        # Enhanced detailed progress patterns
        host_progress_pattern = re.compile(r'(?:Testing|Processing|Checking).*?(?:host|server).*?(\d+).*?of.*?(\d+)', re.IGNORECASE)
        share_progress_pattern = re.compile(r'(?:Enumerating|Checking).*?share.*?(\d+).*?of.*?(\d+)', re.IGNORECASE)
        auth_success_pattern = re.compile(r'Success:\s*(\d+),?\s*Failed:\s*(\d+)', re.IGNORECASE)
        
        # Individual host testing pattern - matches: "[1/10] Testing 213.217.247.165..."
        individual_host_pattern = re.compile(r'\[(\d+)/(\d+)\]\s*Testing\s+([\d.]+)', re.IGNORECASE)
        
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
                
                # Enhanced progress capping to prevent 100% during active scans
                # Detect if we're testing the final host (X/X pattern with 100%)
                is_final_host_testing = (raw_percentage >= 100.0 and current == total)
                
                # Apply comprehensive progress capping
                # Only allow 100% if: in reporting phase AND phase detected AND not testing final host
                allow_100_percent = (current_phase == 'reporting' and current_phase is not None and not is_final_host_testing)
                if not allow_100_percent and mapped_percentage >= 99.0:
                    mapped_percentage = 98.5
                
                # Extract additional context if present
                auth_match = auth_success_pattern.search(line)
                if auth_match:
                    success, failed = auth_match.groups()
                    # Check if this is recent filtering context
                    if "recent" in line.lower() or "Testing recent hosts:" in line:
                        message = f"Testing recent hosts: {current}/{total} (Success: {success}, Failed: {failed})"
                    else:
                        message = f"Testing hosts: {current}/{total} (Success: {success}, Failed: {failed})"
                else:
                    # Check if this is recent filtering progress
                    if "Testing recent hosts:" in line or "recent hosts:" in line.lower():
                        message = f"Testing recent hosts: {current}/{total}"
                    else:
                        message = f"Processing {current}/{total} hosts"
                
                # Validate host count parsing
                try:
                    current_count = int(current)
                    total_count = int(total)
                    if total_count <= 0:
                        # Fallback message for invalid counts
                        message += " (⚠ Unable to determine total host count)"
                except ValueError:
                    # Progress parsing worked but counts are invalid
                    message += " (⚠ Progress parsing issue - check logs)"
                
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
            
            # Parse recent filtering activity
            recent_filter_match = recent_filtering_pattern.search(line)
            if recent_filter_match:
                # Extract numbers - first is timeframe, second (if present) is host count
                numbers = recent_filter_match.groups()
                timeframe = numbers[0]
                host_count = numbers[1] if len(numbers) > 1 and numbers[1] else "some"
                
                if "loading" in line.lower():
                    progress_callback(8.0, f"Loading hosts from last {timeframe} days...")
                elif "found" in line.lower():
                    progress_callback(12.0, f"Found {host_count} hosts within recent timeframe")
                elif "testing" in line.lower():
                    progress_callback(20.0, f"Testing {host_count} recent hosts...")
                continue
            
            # Parse skipped hosts due to recent filtering
            skipped_match = skipped_hosts_pattern.search(line)
            if skipped_match:
                count = skipped_match.group(1)
                progress_callback(5.0, f"Skipped {count} hosts (scanned within recent timeframe)")
                continue
            
            # Parse individual host testing for granular progress (e.g., "[5/100] Testing 192.168.1.5...")
            individual_host_match = individual_host_pattern.search(line)
            if individual_host_match:
                current, total, ip_address = individual_host_match.groups()
                
                try:
                    current_count = int(current)
                    total_count = int(total)
                    
                    # Calculate percentage within the current phase (assume authentication for individual testing)
                    if total_count > 0:
                        raw_percentage = (current_count / total_count) * 100
                        
                        # Enhanced capping for individual host testing
                        # If testing final host (X/X), cap at 99% to prevent premature 100%
                        if current_count == total_count and raw_percentage >= 100.0:
                            raw_percentage = 99.0
                        
                        mapped_percentage = self._map_progress_to_workflow_range(raw_percentage, 'authentication')
                        
                        # Cap progress to avoid reaching phase end
                        if mapped_percentage >= 24.5:  # Authentication phase ends at 25%
                            mapped_percentage = 24.0
                        
                        message = f"Testing {current}/{total}: {ip_address}"
                        progress_callback(mapped_percentage, message)
                        continue
                        
                except ValueError:
                    # Invalid counts - continue without error
                    pass
            
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
        Enhanced phase detection with persistence and inference.
        
        Args:
            line: Output line to analyze
            phase_patterns: Dictionary of phase patterns
            
        Returns:
            Detected phase name, persisted phase, or inferred phase
        """
        # Try direct pattern matching first
        for phase, pattern in phase_patterns.items():
            if pattern.search(line):
                self.last_known_phase = phase  # Update persistent phase
                return phase
        
        # If no direct match, try to infer from progress indicators and context
        if "📊 Progress:" in line:
            # Infer phase from progress context
            if "Testing SMB authentication" in line or "authentication" in line.lower():
                self.last_known_phase = 'authentication'
                return 'authentication'
            elif "Testing" in line or "Processing" in line:
                # Most likely access testing if we're testing/processing hosts
                self.last_known_phase = 'access_testing'
                return 'access_testing'
        
        # Use persisted phase if available (phases tend to persist for multiple lines)
        if self.last_known_phase:
            return self.last_known_phase
            
        # Fallback: infer phase from percentage if no context available
        return self._infer_phase_from_context(line)
    
    def _infer_phase_from_context(self, line: str) -> Optional[str]:
        """
        Infer phase from line context when direct detection fails.
        
        Args:
            line: Output line to analyze
            
        Returns:
            Inferred phase or None
        """
        line_lower = line.lower()
        
        # Simple keyword-based inference for common cases
        if any(keyword in line_lower for keyword in ['shodan', 'query', 'discovery']):
            return 'discovery'
        elif any(keyword in line_lower for keyword in ['authentication', 'auth', 'login']):
            return 'authentication' 
        elif any(keyword in line_lower for keyword in ['testing', 'processing', 'host']):
            return 'access_testing'  # Most common phase
        elif any(keyword in line_lower for keyword in ['collection', 'enumeration', 'share']):
            return 'collection'
        elif any(keyword in line_lower for keyword in ['report', 'complete', 'summary']):
            return 'reporting'
        
        return None  # Let caller handle this case
    
    def _calculate_workflow_step_percentage(self, step_num: int, total_steps: int) -> float:
        """
        Calculate progress percentage based on workflow step.
        
        Maps workflow steps to progress ranges (Updated for realistic timing):
        - Step 1 (Discovery): 5-25% (includes Shodan: 5-15%, Authentication: 15-25%)
        - Step 2 (Access Testing): 25-80% (Expanded - longest phase)
        - Step 3 (Collection): 80-95%
        - Step 4 (Reporting): 95-100%
        
        Args:
            step_num: Current step number (1-based)
            total_steps: Total number of steps
            
        Returns:
            Progress percentage for step start
        """
        if total_steps == 4:  # Standard workflow
            step_ranges = {1: 5.0, 2: 25.0, 3: 80.0, 4: 95.0}  # Updated ranges
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
        
        Workflow step ranges (Updated for realistic timing):
        - Discovery/Shodan: 0-100% → 5-15%
        - Authentication: 0-100% → 15-25%  
        - Access Testing: 0-100% → 25-80% (Expanded - this is the longest phase)
        - Collection: 0-100% → 80-95%
        - Reporting: 0-100% → 95-100%
        
        Args:
            backend_percentage: Raw percentage from backend (0-100)
            phase: Detected phase name
            
        Returns:
            Mapped percentage for GUI workflow display
        """
        # Phase-specific ranges (start, end) - Updated for realistic timing
        phase_ranges = {
            'discovery': (5.0, 15.0),
            'authentication': (15.0, 25.0), 
            'access_testing': (25.0, 80.0),  # Expanded - longest phase
            'collection': (80.0, 95.0),      # Reduced range
            'reporting': (95.0, 100.0)       # Reduced range
        }
        
        if phase not in phase_ranges:
            # Fallback behavior: never return 100% during active scans
            # Assume we're in access_testing phase (most common case) if phase unknown
            if backend_percentage >= 100.0:
                # Cap at high percentage in access_testing range to prevent premature 100%
                return 79.0  # Near end of access_testing phase (25-80%)
            else:
                # Map to access_testing range for unknown phases
                start, end = 25.0, 80.0
                range_size = end - start
                mapped = start + (backend_percentage / 100.0) * range_size
                return min(end, max(start, mapped))
            
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
        # Strip ANSI escape sequences once for both regex extraction and success detection
        cleaned_output = re.sub(r'\x1B\[[0-9;]*m', '', output)

        results = {
            "success": False,
            "shodan_results": 0,
            "hosts_tested": 0,
            "successful_auth": 0,
            "failed_auth": 0,
            "session_id": None,
            "raw_output": output
        }

        # Detect explicit Shodan credit errors and surface them
        shodan_error_match = re.search(r'Shodan API error:\s*(.+)', cleaned_output, re.IGNORECASE)
        if shodan_error_match:
            results["error"] = shodan_error_match.group(0).lstrip('✗❌ ').strip()
            return results

        # Parse results section
        patterns = {
            "shodan_results": r'Shodan Results: (\d[\d,]*)',
            "hosts_tested": r'Hosts Tested: (\d[\d,]*)',
            "successful_auth": r'Successful Auth: (\d[\d,]*)',
            "failed_auth": r'Failed Auth: (\d[\d,]*)',
            "session_id": r'session: (\d+)'
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, cleaned_output)
            if match:
                value = match.group(1).replace(',', '')  # Strip commas before int conversion
                results[key] = int(value) if value.isdigit() else value

        # Check for success indicators using cleaned output
        if ("🎉 SMBSeek security assessment completed successfully!" in cleaned_output or
            ("✓ Found" in cleaned_output and "accessible SMB servers" in cleaned_output) or
            "✓ Discovery completed:" in cleaned_output):
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
    
    def _mock_access_verification_operation(self, recent_days: Optional[int], progress_callback: Optional[Callable]) -> Dict:
        """Mock access verification operation."""
        if progress_callback:
            # Simulate recent filtering progress
            stages = [
                (10, f"Loading hosts from last {recent_days or 90} days"),
                (25, "Found 45 hosts within recent timeframe"),
                (40, "Testing SMB access on 45 recent hosts"),
                (70, "Progress: 32/45 (71.1%) | Success: 12, Failed: 20"),
                (90, "Progress: 43/45 (95.6%) | Success: 18, Failed: 25"),
                (100, "Access verification completed")
            ]
            
            for percentage, message in stages:
                time.sleep(0.3)  # Simulate work
                progress_callback(percentage, message)
        
        return {
            "success": True,
            "recent_days_filter": recent_days or 90,
            "hosts_tested": 45,
            "successful_auth": 18,
            "failed_auth": 27,
            "skipped_hosts": 75  # Hosts skipped due to recent filtering
        }
    
    def _mock_access_on_servers_operation(self, ip_list: List[str], progress_callback: Optional[Callable]) -> Dict:
        """Mock access verification on specific servers."""
        if progress_callback:
            # Simulate targeted server testing
            total_servers = len(ip_list)
            for i, ip in enumerate(ip_list):
                percentage = ((i + 1) / total_servers) * 100
                progress_callback(percentage, f"Testing {ip}...")
                time.sleep(0.2)
        
        return {
            "success": True,
            "servers_specified": ip_list,
            "hosts_tested": len(ip_list),
            "successful_auth": len(ip_list) // 3,  # Mock some successes
            "failed_auth": len(ip_list) - (len(ip_list) // 3)
        }

    def terminate_current_operation(self, graceful: bool = False) -> None:
        """
        Terminate the currently running operation by killing the subprocess and its children.

        Args:
            graceful: Whether to attempt graceful termination first (currently unused)

        Design: Kills entire process tree using platform-specific process groups to ensure
        all child processes (workers spawned by backend) are terminated.
        """
        # Mock mode safety - no subprocess operations to terminate
        if self.mock_mode:
            return

        # No active process to terminate
        if self.active_process is None:
            return

        # Set cancellation flag for _execute_with_progress to detect
        self.cancel_requested = True

        try:
            process = self.active_process

            # Platform-specific process group termination
            if sys.platform.startswith('win'):
                # Windows: Send CTRL_BREAK_EVENT to process group, then terminate
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                    # Wait briefly for graceful shutdown
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.terminate()  # Force kill on Windows
                except (ProcessLookupError, PermissionError, OSError):
                    # Process may have already exited, continue with cleanup
                    pass
            else:
                # POSIX: Send SIGTERM to entire process group, escalate to SIGKILL if needed
                try:
                    # Kill entire process group to catch worker children
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    # Wait for graceful shutdown
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # Escalate to SIGKILL for process group
                        try:
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                        except (ProcessLookupError, PermissionError, OSError):
                            pass
                except (ProcessLookupError, PermissionError, OSError):
                    # Process group may not exist or we lack permissions, try individual process
                    try:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                    except (ProcessLookupError, PermissionError, OSError):
                        pass

            # Clean up stdout pipe to unblock reader thread
            try:
                if process.stdout and not process.stdout.closed:
                    process.stdout.close()
            except (AttributeError, OSError):
                pass

            # Join the output reader thread with timeout
            if self.active_output_thread is not None:
                try:
                    self.active_output_thread.join(timeout=3)
                except (threading.ThreadError, RuntimeError):
                    # Thread may have already finished or be in invalid state
                    pass
                # Clear thread reference after join
                self.active_output_thread = None

            # Update operation status to cancelled
            if self.current_operation:
                self.current_operation.update({
                    "status": "cancelled",
                    "end_time": time.time()
                })

        except Exception as e:
            # Log termination errors but don't raise - cancellation should always succeed
            print(f"Warning: Error during operation termination: {e}")

        # Note: Don't clear active_process or cancel_requested here - let _execute_with_progress
        # see these values and handle the cancellation properly in its finally block

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
                self._build_cli_command("--help"),
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
                self._build_cli_command("--version"),
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

    def load_effective_config(self) -> Dict[str, Any]:
        """
        Load the effective configuration with defaults for scan dialog.

        Returns:
            Dictionary with config values, including safe defaults
        """
        if self.mock_mode:
            return {
                'shodan': {
                    'api_key': 'mock_api_key_12345678901234567890123456789012',
                    'query_limits': {'max_results': 1000}
                },
                'workflow': {
                    'access_recent_hours': 2160  # 90 days * 24 hours
                }
            }

        config = {}
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError):
            # Return safe defaults if config unavailable
            pass

        # Ensure required sections exist with defaults
        if 'shodan' not in config:
            config['shodan'] = {}
        if 'query_limits' not in config['shodan']:
            config['shodan']['query_limits'] = {}
        if 'max_results' not in config['shodan']['query_limits']:
            config['shodan']['query_limits']['max_results'] = 1000

        if 'workflow' not in config:
            config['workflow'] = {}
        if 'access_recent_hours' not in config['workflow']:
            # Convert from existing access_recent_days if available
            recent_days = config['workflow'].get('access_recent_days', 90)
            config['workflow']['access_recent_hours'] = recent_days * 24

        if 'connection' not in config or not isinstance(config['connection'], dict):
            config['connection'] = {}
        connection_config = config['connection']
        connection_config.setdefault('rate_limit_delay', 1)
        connection_config.setdefault('share_access_delay', 1)

        if 'discovery' not in config or not isinstance(config['discovery'], dict):
            config['discovery'] = {'max_concurrent_hosts': 1}
        else:
            config['discovery'].setdefault('max_concurrent_hosts', 1)

        if 'access' not in config or not isinstance(config['access'], dict):
            config['access'] = {'max_concurrent_hosts': 1}
        else:
            config['access'].setdefault('max_concurrent_hosts', 1)

        return config

    @contextmanager
    def _temporary_config_override(self, overrides: Dict[str, Any]):
        """
        Context manager for temporary config file with overrides.

        Args:
            overrides: Dictionary of config values to override

        Yields:
            Path to temporary config file

        Usage:
            with self._temporary_config_override({'shodan': {'api_key': 'new_key'}}):
                # Use temp config for subprocess calls
        """
        import tempfile

        # Load current config and apply overrides
        base_config = self.load_effective_config()

        # Deep merge overrides into base config
        def deep_merge(base: dict, override: dict) -> dict:
            """Deep merge two dictionaries."""
            result = base.copy()
            for key, value in override.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result

        temp_config = deep_merge(base_config, overrides)

        # Create temporary file with proper cleanup
        fd = None
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(suffix=".json", prefix="smbseek_config_")

            # Write merged config to temp file
            with os.fdopen(fd, 'w') as f:
                json.dump(temp_config, f, indent=2)
                fd = None  # fdopen closes the descriptor

            yield temp_path

        finally:
            # Cleanup: close descriptor if still open, then remove file
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass  # Already closed

            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass  # Cleanup failed, but don't crash
