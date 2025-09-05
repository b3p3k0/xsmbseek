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
    
    def __init__(self, backend_path: str = "./smbseek"):
        """
        Initialize backend interface.
        
        Args:
            backend_path: Path to SMBSeek installation directory
            
        Design Decision: Default to ./smbseek for new structure, but allow 
        complete override for different deployment scenarios.
        """
        self.backend_path = Path(backend_path).resolve()
        self.cli_script = self.backend_path / "smbseek.py"
        self.config_path = self.backend_path / "conf" / "config.json"
        self.config_example_path = self.backend_path / "conf" / "config.json.example"
        
        # Ensure configuration file exists
        self._ensure_config_exists()
        
        # Progress tracking for long-running operations
        self.progress_queue = queue.Queue()
        self.current_operation = None
        
        # Phase tracking with persistence for better progress accuracy
        self.last_known_phase = None
        self.phase_progression = ['discovery', 'authentication', 'access_testing', 'collection', 'reporting']
        
        # Mock mode for testing without backend
        self.mock_mode = False
        # Use gui directory for mock data (relative to where GUI components are)
        self.mock_data_path = Path(__file__).parent.parent / "test_data" / "mock_responses"
        
        # Timeout configuration - loaded from config with environment override support
        self.default_timeout = None  # No timeout by default
        self.enable_debug_timeouts = False
        self._load_timeout_configuration()
        
        self._validate_backend()
    
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
        Extract meaningful error details from SMBSeek CLI output.
        
        Args:
            full_output: Complete output from failed command
            cmd: The command that failed
            
        Returns:
            User-friendly error message with actual CLI error details
        """
        lines = full_output.split('\n')
        
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
                # Extract meaningful error message from output
                error_details = self._extract_error_details(full_output, cmd)
                raise subprocess.CalledProcessError(returncode, cmd, error_details)
            
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
        # Reset phase tracking for new scan
        self.last_known_phase = None
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
                    message = f"Testing hosts: {current}/{total} (Success: {success}, Failed: {failed})"
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
        # Scan is successful if it completed without fatal errors
        if ("🎉 SMBSeek security assessment completed successfully!" in output or
            ("✓ Found" in output and "accessible SMB servers" in output) or
            "✓ Discovery completed:" in output):
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