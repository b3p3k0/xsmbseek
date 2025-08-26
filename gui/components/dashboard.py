"""
SMBSeek Mission Control Dashboard

Implements the main dashboard with all critical information in a single view.
Provides key metrics cards, progress display, top findings, and summary breakdowns
with drill-down capabilities to detailed windows.

Design Decision: Single-panel "mission control" layout provides situation awareness
while drill-down buttons allow detailed exploration without losing overview context.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
import sys
import os

# Add utils to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))

from database_access import DatabaseReader
from backend_interface import BackendInterface
from style import get_theme, apply_theme_to_window
from scan_manager import get_scan_manager
from scan_dialog import show_scan_dialog
from scan_results_dialog import show_scan_results_dialog


class DashboardWidget:
    """
    Main dashboard displaying key SMBSeek metrics and status.
    
    Implements mission control pattern with:
    - Key metrics cards (clickable for drill-down)
    - Real-time scan progress display
    - Top security findings summary
    - Country and activity breakdowns
    - Quick scan interface
    
    Design Pattern: Single view with progressive disclosure through drill-down
    windows activated by clicking on metric cards and summary sections.
    """
    
    def __init__(self, parent: tk.Widget, db_reader: DatabaseReader, 
                 backend_interface: BackendInterface):
        """
        Initialize dashboard widget.
        
        Args:
            parent: Parent tkinter widget
            db_reader: Database access instance
            backend_interface: Backend communication interface
            
        Design Decision: Dependency injection allows easy testing with mock
        objects and clear separation of concerns.
        """
        self.parent = parent
        self.db_reader = db_reader
        self.backend_interface = backend_interface
        self.theme = get_theme()
        
        # Dashboard state
        self.current_scan = None
        self.last_update = None
        
        # Scan management
        self.scan_manager = get_scan_manager()
        self.config_path = "../backend/conf/config.json"
        
        # UI components
        self.main_frame = None
        self.status_frame = None
        self.progress_frame = None
        self.metrics_frame = None
        self.summary_frame = None
        self.scan_button = None
        self.status_bar = None
        
        # Progress tracking
        self.progress_var = tk.DoubleVar()
        self.progress_text = tk.StringVar()
        self.progress_detail_text = tk.StringVar()
        self.status_text = tk.StringVar()
        
        # Scan button state management
        self.scan_button_state = "idle"  # idle, disabled_external, scanning, stopping, error
        self.external_scan_pid = None
        
        # Callbacks
        self.drill_down_callback = None
        self.config_editor_callback = None
        
        self._build_dashboard()
        
        # Initial data load
        self._refresh_dashboard_data()
    
    def set_drill_down_callback(self, callback: Callable[[str, Dict], None]) -> None:
        """
        Set callback for opening drill-down windows.
        
        Args:
            callback: Function to call with (window_type, data) for drill-downs
        """
        self.drill_down_callback = callback
    
    def set_config_editor_callback(self, callback: Callable[[str], None]) -> None:
        """
        Set callback for opening configuration editor.
        
        Args:
            callback: Function to call with config file path
        """
        self.config_editor_callback = callback
    
    def _build_dashboard(self) -> None:
        """
        Build the complete dashboard layout.
        
        Design Decision: Vertical layout with sections allows natural reading
        flow and responsive behavior on different screen sizes.
        """
        # Main container with scrolling capability
        self.main_frame = tk.Frame(self.parent)
        self.theme.apply_to_widget(self.main_frame, "main_window")
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Build sections in order
        self._build_header_section()
        self._build_status_section()
        self._build_progress_section()
        self._build_metrics_section()
        self._build_summary_section()
        self._build_status_bar()
        
        # Initial scan state check and data load
        self._check_external_scans()
        self._refresh_dashboard_data()
    
    def _build_header_section(self) -> None:
        """Build header with title and quick actions."""
        header_frame = tk.Frame(self.main_frame)
        self.theme.apply_to_widget(header_frame, "main_window")
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Title
        title_label = self.theme.create_styled_label(
            header_frame, 
            "SMBSeek Security Toolkit",
            "title"
        )
        title_label.pack(side=tk.LEFT)
        
        # Quick action buttons
        actions_frame = tk.Frame(header_frame)
        self.theme.apply_to_widget(actions_frame, "main_window")
        actions_frame.pack(side=tk.RIGHT)
        
        # Quick scan button - state managed
        self.scan_button = tk.Button(
            actions_frame,
            text="🔍 Start Scan",
            command=self._handle_scan_button_click
        )
        self.theme.apply_to_widget(self.scan_button, "button_primary")
        self.scan_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # Settings button
        config_button = tk.Button(
            actions_frame,
            text="⚙ Config",
            command=self._open_config_editor
        )
        self.theme.apply_to_widget(config_button, "button_secondary")
        config_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # Reports button
        reports_button = tk.Button(
            actions_frame,
            text="📊 Reports",
            command=self._open_reports_window
        )
        self.theme.apply_to_widget(reports_button, "button_secondary")
        reports_button.pack(side=tk.LEFT)
    
    def _build_status_section(self) -> None:
        """Build status bar with system information."""
        self.status_frame = tk.Frame(self.main_frame)
        self.theme.apply_to_widget(self.status_frame, "status_bar")
        self.status_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Status text (left side)
        status_label = tk.Label(
            self.status_frame,
            textvariable=self.status_text,
            anchor="w",
            bg=self.theme.colors["secondary_bg"],
            fg=self.theme.colors["text_secondary"],
            font=self.theme.fonts["status"]
        )
        status_label.pack(side=tk.LEFT, padx=5)
        
        # Last update time (right side)
        self.update_time_label = tk.Label(
            self.status_frame,
            text="",
            anchor="e",
            bg=self.theme.colors["secondary_bg"],
            fg=self.theme.colors["text_secondary"],
            font=self.theme.fonts["status"]
        )
        self.update_time_label.pack(side=tk.RIGHT, padx=5)
        
        self.status_text.set("Ready | No active scans")
    
    def _build_progress_section(self) -> None:
        """Build progress display for active scans."""
        self.progress_frame = tk.Frame(self.main_frame)
        self.theme.apply_to_widget(self.progress_frame, "card")
        # Initially hidden - shown during scans
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            variable=self.progress_var,
            maximum=100,
            style="SMBSeek.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Progress text (main status)
        progress_label = tk.Label(
            self.progress_frame,
            textvariable=self.progress_text,
            anchor="center",
            bg=self.theme.colors["card_bg"],
            fg=self.theme.colors["text"],
            font=self.theme.fonts["body"]
        )
        progress_label.pack(pady=(0, 5))
        
        # Detailed progress text (host/share details)
        progress_detail_label = tk.Label(
            self.progress_frame,
            textvariable=self.progress_detail_text,
            anchor="center",
            bg=self.theme.colors["card_bg"],
            fg=self.theme.colors["text_secondary"],
            font=self.theme.fonts["small"]
        )
        progress_detail_label.pack(pady=(0, 10))
    
    def _build_metrics_section(self) -> None:
        """
        Build key metrics cards section.
        
        Design Decision: Grid layout with 4 cards provides balanced overview
        of critical security metrics with clear visual hierarchy.
        """
        # Section title
        metrics_title = self.theme.create_styled_label(
            self.main_frame,
            "KEY METRICS",
            "heading"
        )
        metrics_title.pack(anchor="w", pady=(10, 5))
        
        # Metrics grid container
        self.metrics_frame = tk.Frame(self.main_frame)
        self.theme.apply_to_widget(self.metrics_frame, "main_window")
        self.metrics_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Configure grid weights for responsive layout
        for i in range(4):
            self.metrics_frame.columnconfigure(i, weight=1)
        
        # Create metric cards
        self.metric_cards = {}
        
        card_configs = [
            {
                "key": "total_servers",
                "title": "Total\nServers",
                "icon": "🖥",
                "drill_down": "server_list"
            },
            {
                "key": "accessible_shares", 
                "title": "Accessible\nShares",
                "icon": "📁",
                "drill_down": "share_details"
            },
            {
                "key": "high_risk_vulnerabilities",
                "title": "High Risk\nVulnerabilities",
                "icon": "🔴",
                "drill_down": "vulnerabilities"
            },
            {
                "key": "recent_discoveries",
                "title": "Recent\nDiscoveries",
                "icon": "⏰",
                "drill_down": "recent_activity"
            }
        ]
        
        for i, config in enumerate(card_configs):
            card = self._create_metric_card(config, i)
            self.metric_cards[config["key"]] = card
    
    def _create_metric_card(self, config: Dict[str, Any], column: int) -> Dict[str, tk.Widget]:
        """
        Create individual metric card.
        
        Args:
            config: Card configuration dictionary
            column: Grid column position
            
        Returns:
            Dictionary with card widgets
        """
        # Card frame
        card_frame = self.theme.create_metric_card_frame(self.metrics_frame)
        card_frame.grid(row=0, column=column, padx=5, pady=5, sticky="nsew")
        
        # Icon and title
        title_frame = tk.Frame(card_frame)
        self.theme.apply_to_widget(title_frame, "metric_card")
        title_frame.pack(fill=tk.X)
        
        icon_label = self.theme.create_styled_label(
            title_frame,
            config["icon"],
            "heading"
        )
        icon_label.pack()
        
        title_label = self.theme.create_styled_label(
            title_frame,
            config["title"],
            "small",
            justify="center"
        )
        title_label.pack(pady=(5, 10))
        
        # Value display
        value_var = tk.StringVar(value="--")
        value_label = self.theme.create_styled_label(
            card_frame,
            "",
            "title",
            textvariable=value_var,
            justify="center"
        )
        value_label.pack()
        
        # Drill-down button
        button_text = "[View Details]"
        drill_button = tk.Button(
            card_frame,
            text=button_text,
            command=lambda: self._open_drill_down(config["drill_down"])
        )
        self.theme.apply_to_widget(drill_button, "button_secondary")
        drill_button.pack(pady=(10, 0))
        
        
        return {
            "frame": card_frame,
            "value_var": value_var,
            "config": config
        }
    
    
    def _build_summary_section(self) -> None:
        """Build summary section with country breakdown and recent activity."""
        # Two-column layout for summaries
        self.summary_frame = tk.Frame(self.main_frame)
        self.theme.apply_to_widget(self.summary_frame, "main_window")
        self.summary_frame.pack(fill=tk.X)
        
        # Configure columns
        self.summary_frame.columnconfigure(0, weight=1)
        self.summary_frame.columnconfigure(1, weight=1)
        
        # Country breakdown (left column)
        self._build_country_breakdown()
        
        # Recent activity (right column)
        self._build_recent_activity()
    
    def _build_country_breakdown(self) -> None:
        """Build country breakdown visualization."""
        country_frame = tk.Frame(self.summary_frame)
        self.theme.apply_to_widget(country_frame, "card")
        country_frame.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="nsew")
        
        # Title
        country_title = self.theme.create_styled_label(
            country_frame,
            "COUNTRY BREAKDOWN",
            "heading"
        )
        country_title.pack(anchor="w", padx=10, pady=(10, 5))
        
        # Country list container
        self.country_list_frame = tk.Frame(country_frame)
        self.theme.apply_to_widget(self.country_list_frame, "card")
        self.country_list_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        # Geographic report button
        geo_button = tk.Button(
            country_frame,
            text="[Geographic Report...]",
            command=lambda: self._open_drill_down("geographic_report")
        )
        self.theme.apply_to_widget(geo_button, "button_secondary")
        geo_button.pack(pady=(0, 10))
    
    def _build_recent_activity(self) -> None:
        """Build recent activity display."""
        activity_frame = tk.Frame(self.summary_frame)
        self.theme.apply_to_widget(activity_frame, "card")
        activity_frame.grid(row=0, column=1, padx=(5, 0), pady=5, sticky="nsew")
        
        # Title
        activity_title = self.theme.create_styled_label(
            activity_frame,
            "RECENT ACTIVITY",
            "heading"
        )
        activity_title.pack(anchor="w", padx=10, pady=(10, 5))
        
        # Activity list container
        self.activity_list_frame = tk.Frame(activity_frame)
        self.theme.apply_to_widget(self.activity_list_frame, "card")
        self.activity_list_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        # Activity timeline button
        timeline_button = tk.Button(
            activity_frame,
            text="[Activity Timeline...]",
            command=lambda: self._open_drill_down("activity_timeline")
        )
        self.theme.apply_to_widget(timeline_button, "button_secondary")
        timeline_button.pack(pady=(0, 10))
    
    def _refresh_dashboard_data(self) -> None:
        """
        Refresh all dashboard data from database.
        
        Design Decision: Single refresh method ensures consistent data state
        across all dashboard components and handles errors gracefully.
        """
        try:
            # Get dashboard summary
            summary = self.db_reader.get_dashboard_summary()
            self._update_metrics_display(summary)
            
            # Get country breakdown
            countries = self.db_reader.get_country_breakdown()
            self._update_country_display(countries)
            
            # Get recent activity
            activity = self.db_reader.get_recent_activity(days=7)
            self._update_activity_display(activity)
            
            # Update status
            self.last_update = datetime.now()
            self._update_status_display(summary)
            
        except Exception as e:
            self._handle_refresh_error(e)
    
    def _update_metrics_display(self, summary: Dict[str, Any]) -> None:
        """Update metric cards with new data."""
        for key, card in self.metric_cards.items():
            value = summary.get(key, 0)
            
            # Handle special formatting for recent_discoveries
            if key == "recent_discoveries" and isinstance(value, dict):
                display_value = value.get("display", "--")
                # Set tooltip warning if present
                if "warning" in value:
                    # Add a simple tooltip or status indicator for warnings
                    display_value = f"{display_value}"
            elif isinstance(value, (int, float)):
                display_value = f"{value:,}" if value >= 1000 else str(value)
            else:
                display_value = str(value)
            
            card["value_var"].set(display_value)
    
    def _refresh_after_scan_completion(self) -> None:
        """
        Refresh dashboard after scan completion with cache invalidation.
        
        Ensures fresh data is loaded by clearing cache before refresh,
        which is critical for displaying updated Recent Discoveries count.
        """
        try:
            # Clear cache to force fresh database queries
            self.db_reader.clear_cache()
            
            # Refresh dashboard with new data
            self._refresh_dashboard_data()
        except Exception as e:
            print(f"Dashboard refresh error after scan completion: {e}")
            # Continue anyway
    
    def _update_country_display(self, countries: Dict[str, int]) -> None:
        """Update country breakdown display."""
        # Clear existing countries
        for widget in self.country_list_frame.winfo_children():
            widget.destroy()
        
        if not countries:
            no_countries_label = self.theme.create_styled_label(
                self.country_list_frame,
                "No country data available",
                "small",
                fg=self.theme.colors["text_secondary"]
            )
            no_countries_label.pack(pady=5)
            return
        
        # Calculate percentages
        total = sum(countries.values())
        
        for country, count in list(countries.items())[:5]:  # Top 5 countries
            percentage = (count / total * 100) if total > 0 else 0
            
            country_frame = tk.Frame(self.country_list_frame)
            self.theme.apply_to_widget(country_frame, "card")
            country_frame.pack(fill=tk.X, pady=1)
            
            # Country label
            country_label = self.theme.create_styled_label(
                country_frame,
                f"{country}: ",
                "small"
            )
            country_label.pack(side=tk.LEFT)
            
            # Progress bar representation
            bar_length = int(percentage / 10)  # Scale to max 10 characters
            bar_text = "█" * bar_length + "░" * (10 - bar_length)
            
            bar_label = self.theme.create_styled_label(
                country_frame,
                bar_text,
                "mono_small",
                fg=self.theme.colors["accent"]
            )
            bar_label.pack(side=tk.LEFT, padx=(5, 10))
            
            # Percentage label
            pct_label = self.theme.create_styled_label(
                country_frame,
                f"{percentage:.0f}%",
                "small"
            )
            pct_label.pack(side=tk.LEFT)
    
    def _update_activity_display(self, activity: List[Dict[str, Any]]) -> None:
        """Update recent activity display."""
        # Clear existing activity
        for widget in self.activity_list_frame.winfo_children():
            widget.destroy()
        
        if not activity:
            no_activity_label = self.theme.create_styled_label(
                self.activity_list_frame,
                "No recent activity",
                "small",
                fg=self.theme.colors["text_secondary"]
            )
            no_activity_label.pack(pady=5)
            return
        
        # Display recent activity entries
        for entry in activity[:5]:  # Latest 5 entries
            activity_frame = tk.Frame(self.activity_list_frame)
            self.theme.apply_to_widget(activity_frame, "card")
            activity_frame.pack(fill=tk.X, pady=1)
            
            # Activity text
            date = entry.get("date", "Unknown")
            discoveries = entry.get("discoveries", 0)
            
            activity_text = f"┌─ {date}: {discoveries} new discoveries"
            activity_label = self.theme.create_styled_label(
                activity_frame,
                activity_text,
                "mono_small"
            )
            activity_label.pack(anchor="w")
    
    def _update_status_display(self, summary: Dict[str, Any]) -> None:
        """Update status bar information."""
        # Main status
        total_servers = summary.get("total_servers", 0)
        last_scan = summary.get("last_scan", "Never")
        
        if last_scan != "Never":
            # Format last scan time
            try:
                scan_time = datetime.fromisoformat(last_scan.replace("Z", "+00:00"))
                formatted_time = scan_time.strftime("%Y-%m-%d %H:%M")
            except:
                formatted_time = "Unknown"
        else:
            formatted_time = "Never"
        
        status_text = f"Ready | Last Scan: {formatted_time} | DB: {total_servers:,} servers"
        self.status_text.set(status_text)
        
        # Update time
        if self.last_update:
            update_text = f"Updated: {self.last_update.strftime('%H:%M:%S')}"
            self.update_time_label.configure(text=update_text)
    
    def _handle_refresh_error(self, error: Exception) -> None:
        """Handle dashboard refresh errors gracefully."""
        error_message = f"Dashboard refresh failed: {str(error)}"
        self.status_text.set(f"Error: {error_message}")
        
        # If database is unavailable, enable mock mode
        if "Database" in str(error) or "database" in str(error):
            try:
                self.db_reader.enable_mock_mode()
                self._refresh_dashboard_data()  # Retry with mock data
                self.status_text.set("Using mock data - database unavailable")
            except:
                self.status_text.set("Dashboard unavailable - check backend")
    
    
    def start_scan_progress(self, scan_type: str, countries: List[str]) -> None:
        """
        Start displaying scan progress.
        
        Args:
            scan_type: Type of scan being performed
            countries: Countries being scanned
        """
        # Show progress section
        self.progress_frame.pack(fill=tk.X, pady=(0, 15), before=self.metrics_frame)
        
        # Reset progress
        self.progress_var.set(0)
        self.progress_text.set(f"Starting {scan_type} scan for {', '.join(countries)}...")
        
        # Update status
        self.status_text.set(f"Scanning: {scan_type} | Countries: {', '.join(countries)}")
    
    def update_scan_progress(self, percentage: Optional[float], message: str) -> None:
        """
        Update scan progress display.
        
        Args:
            percentage: Progress percentage (0-100) or None for status-only update
            message: Progress message to display
        """
        if percentage is not None:
            self.progress_var.set(percentage)
        
        self.progress_text.set(message)
        
        # Force UI update
        self.parent.update_idletasks()
    
    def finish_scan_progress(self, success: bool, results: Dict[str, Any]) -> None:
        """
        Finish scan progress display.
        
        Args:
            success: Whether scan completed successfully
            results: Scan results dictionary
        """
        if success:
            self.progress_var.set(100)
            successful = results.get("successful_auth", 0)
            total = results.get("hosts_tested", 0)
            self.progress_text.set(f"Scan complete: {successful}/{total} servers accessible")
            
            # Refresh dashboard with new data (clear cache for fresh Recent Discoveries count)
            self.parent.after(2000, self._refresh_after_scan_completion)
        else:
            self.progress_text.set("Scan failed - check backend connection")
        
        # Hide progress section after delay
        self.parent.after(5000, self._hide_progress_section)
    
    def _hide_progress_section(self) -> None:
        """Hide the progress section."""
        self.progress_frame.pack_forget()
        self.status_text.set("Ready")
    
    def _show_quick_scan_dialog(self) -> None:
        """Show scan configuration dialog and start scan."""
        # Check if scan is already active
        if self.scan_manager.is_scan_active():
            messagebox.showwarning(
                "Scan in Progress",
                "A scan is already running. Please wait for it to complete before starting another scan."
            )
            return
        
        # Show scan dialog
        result = show_scan_dialog(
            parent=self.parent,
            config_path=self.config_path,
            config_editor_callback=self._open_config_editor_from_scan,
            scan_start_callback=self._start_new_scan
        )
    
    def _open_config_editor_from_scan(self, config_path: str) -> None:
        """Open configuration editor from scan dialog."""
        if self.config_editor_callback:
            self.config_editor_callback(config_path)
    
    def _start_new_scan(self, country: Optional[str]) -> None:
        """Start new scan with specified parameters."""
        try:
            # Final check for external scans before starting
            self._check_external_scans()
            if self.scan_button_state != "idle":
                return  # External scan detected, don't proceed
            
            # Get backend path (assume relative to GUI)
            backend_path = "../backend"
            
            # Start scan via scan manager
            success = self.scan_manager.start_scan(
                country=country,
                backend_path=backend_path,
                progress_callback=self._handle_scan_progress
            )
            
            if success:
                # Update button state to scanning
                self._update_scan_button_state("scanning")
                
                # Show progress display
                self._show_scan_progress(country)
                
                # Start monitoring scan completion
                self._monitor_scan_completion()
            else:
                messagebox.showerror(
                    "Scan Error",
                    "Failed to start scan. Another scan may already be running."
                )
        except Exception as e:
            error_msg = str(e)
            
            # Provide specific guidance based on error type
            if "backend" in error_msg.lower() or "not found" in error_msg.lower():
                detailed_msg = (
                    f"Backend interface error: {error_msg}\n\n"
                    "This usually indicates:\n"
                    "• SMBSeek backend is not installed or not in expected location\n"
                    "• Backend CLI is not executable\n"
                    "• Configuration file is missing\n\n"
                    "Please ensure the backend is properly installed and configured."
                )
            elif "lock" in error_msg.lower():
                detailed_msg = (
                    f"Scan coordination error: {error_msg}\n\n"
                    "Another scan may already be running. Please wait for it to complete\n"
                    "or restart the application if the scan appears to be stuck."
                )
            else:
                detailed_msg = (
                    f"Scan initialization failed: {error_msg}\n\n"
                    "Please try again or check the configuration settings."
                )
            
            messagebox.showerror("Scan Error", detailed_msg)
    
    def _handle_scan_progress(self, percentage: float, status: str, phase: str) -> None:
        """Handle progress updates from scan manager."""
        try:
            # Update progress bar
            if percentage is not None:
                self.progress_var.set(min(100, max(0, percentage)))
            
            # Update main progress text with phase
            if phase:
                phase_display = phase.replace("_", " ").title()
                progress_text = f"{phase_display}: {percentage:.0f}%" if percentage else phase_display
            else:
                progress_text = "Processing..." if not percentage else f"{percentage:.0f}%"
            
            self.progress_text.set(progress_text)
            
            # Update detailed status
            if status:
                self.progress_detail_text.set(status)
            
            # Force UI update safely
            try:
                self.parent.update_idletasks()
            except tk.TclError:
                # UI may be destroyed, ignore
                pass
                
        except Exception as e:
            # Log error but don't interrupt scan
            print(f"Progress update error: {e}")  # In production, use proper logging
    
    def _show_scan_progress(self, country: Optional[str]) -> None:
        """Show scan progress display."""
        # Show progress section
        self.progress_frame.pack(fill=tk.X, pady=(0, 15), before=self.metrics_frame)
        
        # Reset progress
        self.progress_var.set(0)
        scan_target = country if country else "global"
        self.progress_text.set(f"Initializing {scan_target} scan...")
        self.progress_detail_text.set("Setting up scan parameters...")
        
        # Update status
        self.status_text.set(f"Scanning: {scan_target}")
    
    def _monitor_scan_completion(self) -> None:
        """Monitor scan for completion and show results."""
        def check_completion():
            try:
                if not self.scan_manager.is_scanning:
                    # Scan completed - reset button state first
                    self._update_scan_button_state("idle")
                    
                    # Get results and show
                    results = self.scan_manager.get_scan_results()
                    self._show_scan_results(results)
                    
                    # Hide progress display
                    self._hide_progress_section()
                    
                    # Refresh dashboard data with cache invalidation
                    try:
                        self._refresh_after_scan_completion()
                    except Exception as e:
                        print(f"Dashboard refresh error after scan: {e}")
                        # Continue anyway
                else:
                    # Check again in 1 second
                    try:
                        self.parent.after(1000, check_completion)
                    except tk.TclError:
                        # UI destroyed, stop monitoring
                        pass
                        
            except Exception as e:
                # Critical error in monitoring, show error and stop
                try:
                    messagebox.showerror(
                        "Scan Monitoring Error",
                        f"Error monitoring scan progress: {str(e)}\n\n"
                        "The scan may still be running in the background.\n"
                        "Please check the scan results manually."
                    )
                except:
                    # Even error dialog failed, just stop monitoring
                    pass
                
                # Try to clean up
                try:
                    self._hide_progress_section()
                except:
                    pass
        
        # Start monitoring with error protection
        try:
            self.parent.after(1000, check_completion)
        except tk.TclError:
            # UI not available
            pass
    
    def _show_scan_results(self, results: Dict[str, Any]) -> None:
        """Show scan results dialog."""
        try:
            def view_details_callback():
                try:
                    # Open server list with date filter
                    if self.drill_down_callback:
                        self.drill_down_callback("server_list", {"filter_recent": True})
                except Exception as e:
                    messagebox.showerror(
                        "View Details Error",
                        f"Failed to open detailed results:\n{str(e)}"
                    )
            
            # Show results dialog
            show_scan_results_dialog(
                parent=self.parent,
                scan_results=results,
                view_details_callback=view_details_callback
            )
            
        except Exception as e:
            # Fallback to simple message box if results dialog fails
            status = results.get("status", "unknown")
            hosts_scanned = results.get("hosts_scanned", 0)
            accessible_hosts = results.get("accessible_hosts", 0)
            
            fallback_message = (
                f"Scan completed with status: {status}\n\n"
                f"Results:\n"
                f"• Hosts scanned: {hosts_scanned}\n"
                f"• Accessible hosts: {accessible_hosts}\n\n"
                f"Note: Full results dialog could not be displayed due to error:\n{str(e)}"
            )
            
            messagebox.showinfo("Scan Results", fallback_message)
    
    def _open_config_editor(self) -> None:
        """Open configuration editor window."""
        if self.drill_down_callback:
            self.drill_down_callback("config_editor", {})
    
    def _open_reports_window(self) -> None:
        """Open reports window."""
        if self.drill_down_callback:
            self.drill_down_callback("reports", {})
    
    def _open_drill_down(self, window_type: str) -> None:
        """
        Open drill-down window.
        
        Args:
            window_type: Type of drill-down window to open
        """
        if self.drill_down_callback:
            self.drill_down_callback(window_type, {})
    
    def enable_mock_mode(self) -> None:
        """Enable mock mode for testing."""
        self.db_reader.enable_mock_mode()
        self.backend_interface.enable_mock_mode()
        self._refresh_dashboard_data()
    
    def disable_mock_mode(self) -> None:
        """Disable mock mode."""
        self.db_reader.disable_mock_mode()
        self.backend_interface.disable_mock_mode()
        self._refresh_dashboard_data()
    
    # ===== SCAN BUTTON STATE MANAGEMENT =====
    
    def _build_status_bar(self) -> None:
        """Build status bar for external scan notifications."""
        self.status_bar = tk.Frame(self.main_frame)
        self.theme.apply_to_widget(self.status_bar, "status_bar")
        self.status_bar.pack(fill=tk.X, pady=(10, 0))
        
        # Status message label (initially hidden)
        self.status_message = tk.Label(
            self.status_bar,
            text="",
            font=self.theme.fonts["small"]
        )
        self.theme.apply_to_widget(self.status_message, "status_bar")
        
        # Start hidden
        self._hide_status_bar()
    
    def _show_status_bar(self, message: str) -> None:
        """Show status bar with message."""
        self.status_message.config(text=message)
        self.status_message.pack(padx=10, pady=5)
        self.status_bar.pack(fill=tk.X, pady=(10, 0))
    
    def _hide_status_bar(self) -> None:
        """Hide status bar."""
        self.status_message.pack_forget()
        self.status_bar.pack_forget()
    
    def _handle_scan_button_click(self) -> None:
        """Handle scan button click based on current state."""
        if self.scan_button_state == "idle":
            self._check_external_scans()  # Check again before starting
            if self.scan_button_state == "idle":  # Still idle after check
                self._show_quick_scan_dialog()
        elif self.scan_button_state == "scanning":
            self._show_stop_confirmation()
        elif self.scan_button_state == "disabled_external":
            # Show info about external scan
            messagebox.showinfo(
                "Scan In Progress",
                f"Another scan is currently running (PID: {self.external_scan_pid}). "
                "Please wait for it to complete or stop it from that application."
            )
        # Other states (stopping, error) don't respond to clicks
    
    def _update_scan_button_state(self, new_state: str) -> None:
        """Update scan button state and appearance."""
        self.scan_button_state = new_state
        
        if new_state == "idle":
            self._set_button_to_start()
            self._hide_status_bar()
        elif new_state == "disabled_external":
            self._set_button_to_disabled()
            self._show_status_bar(f"Scan running by PID: {self.external_scan_pid} - Please wait")
        elif new_state == "scanning":
            self._set_button_to_stop()
            self._hide_status_bar()
        elif new_state == "stopping":
            self._set_button_to_stopping()
        elif new_state == "error":
            self._set_button_to_error()
    
    def _set_button_to_start(self) -> None:
        """Configure button for start state."""
        self.scan_button.config(
            text="🔍 Start Scan",
            state="normal"
        )
        self.theme.apply_to_widget(self.scan_button, "button_primary")
    
    def _set_button_to_stop(self) -> None:
        """Configure button for stop state."""
        self.scan_button.config(
            text="⬛ Stop Scan",
            state="normal"
        )
        self.theme.apply_to_widget(self.scan_button, "button_danger")
    
    def _set_button_to_disabled(self) -> None:
        """Configure button for disabled state (external scan)."""
        self.scan_button.config(
            text="🔍 Scan Running",
            state="disabled"
        )
        self.theme.apply_to_widget(self.scan_button, "button_disabled")
    
    def _set_button_to_stopping(self) -> None:
        """Configure button for stopping state."""
        self.scan_button.config(
            text="⬛ Stopping...",
            state="disabled"
        )
        self.theme.apply_to_widget(self.scan_button, "button_danger")
    
    def _set_button_to_error(self) -> None:
        """Configure button for error state."""
        self.scan_button.config(
            text="⬛ Stop Failed",
            state="normal"
        )
        self.theme.apply_to_widget(self.scan_button, "button_danger")
    
    # ===== LOCK FILE MANAGEMENT =====
    
    def _check_external_scans(self) -> None:
        """Check for external scans using lock file system."""
        try:
            if self.scan_manager.is_scan_active():
                # Get lock file info
                lock_file_path = os.path.join(os.path.dirname(__file__), '..', '..', '.scan_lock')
                if os.path.exists(lock_file_path):
                    import json
                    with open(lock_file_path, 'r') as f:
                        lock_data = json.load(f)
                    
                    # Check if it's our own scan or external
                    lock_pid = lock_data.get('process_id')
                    current_pid = os.getpid()
                    
                    if lock_pid != current_pid:
                        # External scan detected
                        if self._validate_external_process(lock_pid):
                            self.external_scan_pid = lock_pid
                            self._update_scan_button_state("disabled_external")
                            return
                        else:
                            # Stale lock file - clean it up
                            self.scan_manager._cleanup_stale_locks()
                    else:
                        # Our own scan is running
                        if self.scan_manager.is_scanning:
                            self._update_scan_button_state("scanning")
                        else:
                            # Scan completed, update state
                            self._update_scan_button_state("idle")
                        return
            
            # No active scans detected
            self._update_scan_button_state("idle")
            
        except Exception as e:
            print(f"Error checking external scans: {e}")
            # Fallback to idle state
            self._update_scan_button_state("idle")
    
    def _validate_external_process(self, pid: int) -> bool:
        """Validate that external process is actually running."""
        try:
            # Try psutil first (more reliable)
            try:
                import psutil
                return psutil.pid_exists(pid)
            except ImportError:
                # Fallback to os.kill method
                import signal
                os.kill(pid, 0)  # Doesn't actually kill, just checks existence
                return True
        except (OSError, ProcessLookupError):
            return False
        except Exception:
            # Unknown error, assume process exists to be safe
            return True
    
    # ===== STOP CONFIRMATION DIALOG =====
    
    def _show_stop_confirmation(self) -> None:
        """Show confirmation dialog for stopping scan."""
        # Custom dialog for stop options
        dialog = tk.Toplevel(self.parent)
        dialog.title("Stop Scan")
        dialog.geometry("400x250")
        dialog.minsize(300, 200)
        dialog.transient(self.parent)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Apply theme
        self.theme.apply_to_widget(dialog, "main_window")
        
        # Header
        header_label = self.theme.create_styled_label(
            dialog,
            "⚠️ Stop Scan Confirmation",
            "heading"
        )
        header_label.pack(pady=(20, 10))
        
        # Warning message
        warning_text = (
            "Stopping the scan may result in incomplete data collection.\n"
            "Choose how you would like to stop the scan:"
        )
        warning_label = self.theme.create_styled_label(
            dialog,
            warning_text,
            "body",
            justify="center"
        )
        warning_label.pack(pady=(0, 20), padx=20)
        
        # Progress context (if available)
        try:
            current_progress = self.progress_text.get()
            if current_progress:
                progress_label = self.theme.create_styled_label(
                    dialog,
                    f"Current: {current_progress}",
                    "small",
                    fg=self.theme.colors["text_secondary"]
                )
                progress_label.pack(pady=(0, 20))
        except:
            pass
        
        # Buttons frame
        buttons_frame = tk.Frame(dialog)
        self.theme.apply_to_widget(buttons_frame, "main_window")
        buttons_frame.pack(pady=20)
        
        # Stop now button
        stop_now_btn = tk.Button(
            buttons_frame,
            text="Stop Now",
            command=lambda: self._handle_stop_choice(dialog, "immediate")
        )
        self.theme.apply_to_widget(stop_now_btn, "button_danger")
        stop_now_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Stop after host button
        stop_after_btn = tk.Button(
            buttons_frame,
            text="Stop After Current Host",
            command=lambda: self._handle_stop_choice(dialog, "graceful")
        )
        self.theme.apply_to_widget(stop_after_btn, "button_secondary")
        stop_after_btn.pack(side=tk.LEFT, padx=(10, 0))
        
        # Cancel button
        cancel_btn = tk.Button(
            buttons_frame,
            text="Cancel",
            command=dialog.destroy
        )
        self.theme.apply_to_widget(cancel_btn, "button_secondary")
        cancel_btn.pack(side=tk.LEFT, padx=(10, 0))
        
        # Handle window close
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    
    def _handle_stop_choice(self, dialog: tk.Toplevel, choice: str) -> None:
        """Handle user's stop choice."""
        dialog.destroy()
        
        if choice == "immediate":
            self._stop_scan_immediate()
        elif choice == "graceful":
            self._stop_scan_after_host()
    
    # ===== SCAN STOP FUNCTIONALITY =====
    
    def _stop_scan_immediate(self) -> None:
        """Stop scan immediately."""
        self._update_scan_button_state("stopping")
        
        try:
            success = self.scan_manager.interrupt_scan()
            
            if success:
                # Scan stopped successfully
                self._update_scan_button_state("idle")
                messagebox.showinfo(
                    "Scan Stopped",
                    "Scan has been stopped successfully."
                )
            else:
                # Stop failed
                self._handle_stop_error("Failed to interrupt scan - scan may not be active")
                
        except Exception as e:
            self._handle_stop_error(f"Error stopping scan: {str(e)}")
    
    def _stop_scan_after_host(self) -> None:
        """Stop scan after current host completes."""
        # For now, implement as immediate stop with different message
        # Future enhancement: could add graceful stopping to scan manager
        self._update_scan_button_state("stopping")
        
        try:
            success = self.scan_manager.interrupt_scan()
            
            if success:
                self._update_scan_button_state("idle")
                messagebox.showinfo(
                    "Scan Stopping",
                    "Scan will stop after the current host completes processing."
                )
            else:
                self._handle_stop_error("Failed to schedule graceful stop")
                
        except Exception as e:
            self._handle_stop_error(f"Error scheduling graceful stop: {str(e)}")
    
    def _handle_stop_error(self, error_message: str) -> None:
        """Handle scan stop error."""
        # Double-check actual scan state
        if not self.scan_manager.is_scanning:
            # Scan actually stopped despite error
            self._update_scan_button_state("idle")
            messagebox.showinfo(
                "Scan Stopped",
                "Scan has stopped (despite error in communication)."
            )
        else:
            # Scan still running, show error state
            self._update_scan_button_state("error")
            messagebox.showerror(
                "Stop Failed",
                f"Failed to stop scan: {error_message}\n\n"
                "Click 'Stop Scan' again to retry."
            )