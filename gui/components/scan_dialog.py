"""
SMBSeek Scan Dialog

Modal dialog for configuring and starting new SMB security scans.
Provides simple interface for country selection and configuration management.

Design Decision: Simple modal approach focuses on essential parameters
while directing users to configuration editor for advanced settings.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
import sys
from pathlib import Path
from typing import Optional, Callable

# Add utils to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))

from style import get_theme


class ScanDialog:
    """
    Modal dialog for configuring and starting SMB scans.
    
    Provides interface for:
    - Optional country selection (global scan if empty)
    - Configuration file path display and editing
    - Scan initiation with validation
    
    Design Pattern: Simple modal with clear call-to-action flow
    that integrates with existing configuration and scan systems.
    """
    
    def __init__(self, parent: tk.Widget, config_path: str, 
                 config_editor_callback: Callable[[str], None],
                 scan_start_callback: Callable[[Optional[str]], None]):
        """
        Initialize scan dialog.
        
        Args:
            parent: Parent widget
            config_path: Path to configuration file
            config_editor_callback: Function to open config editor
            scan_start_callback: Function to start scan with country parameter
        """
        self.parent = parent
        self.config_path = Path(config_path).resolve()
        self.config_editor_callback = config_editor_callback
        self.scan_start_callback = scan_start_callback
        self.theme = get_theme()
        
        # Dialog result
        self.result = None
        self.country_code = None
        
        # UI components
        self.dialog = None
        self.country_var = tk.StringVar()
        self.country_entry = None
        
        self._create_dialog()
    
    def _create_dialog(self) -> None:
        """Create the scan configuration dialog."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Start New Scan")
        self.dialog.geometry("500x815")
        self.dialog.minsize(400, 250)
        
        # Apply theme
        self.theme.apply_to_widget(self.dialog, "main_window")
        
        # Make modal
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # Center dialog
        self._center_dialog()
        
        # Build UI
        self._create_header()
        self._create_scan_options()
        self._create_config_section()
        self._create_button_panel()
        
        # Setup event handlers
        self._setup_event_handlers()
        
        # Focus on country field
        self._focus_country_field()
    
    def _center_dialog(self) -> None:
        """Center dialog on parent window."""
        self.dialog.update_idletasks()
        
        # Get parent position and size
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        
        # Calculate center position
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = parent_x + (parent_width // 2) - (width // 2)
        y = parent_y + (parent_height // 2) - (height // 2)
        
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
    
    def _create_header(self) -> None:
        """Create dialog header with title and description."""
        header_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(header_frame, "main_window")
        header_frame.pack(fill=tk.X, padx=20, pady=(15, 5))
        
        # Title
        title_label = self.theme.create_styled_label(
            header_frame,
            "🔍 Start New Security Scan",
            "heading"
        )
        title_label.pack(anchor="w")
        
        # Description
        desc_label = self.theme.create_styled_label(
            header_frame,
            "Configure and start a new SMB security scan to discover accessible shares.",
            "body",
            fg=self.theme.colors["text_secondary"]
        )
        desc_label.pack(anchor="w", pady=(5, 0))
    
    def _create_scan_options(self) -> None:
        """Create scan configuration options."""
        options_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(options_frame, "card")
        options_frame.pack(fill=tk.X, padx=20, pady=5)
        
        # Section title
        section_title = self.theme.create_styled_label(
            options_frame,
            "Scan Parameters",
            "heading"
        )
        section_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Country selection
        country_container = tk.Frame(options_frame)
        self.theme.apply_to_widget(country_container, "card")
        country_container.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        # Country label and input
        country_label = self.theme.create_styled_label(
            country_container,
            "Country Code (optional):",
            "body"
        )
        country_label.pack(anchor="w")
        
        # Country input with example
        country_input_frame = tk.Frame(country_container)
        self.theme.apply_to_widget(country_input_frame, "card")
        country_input_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.country_entry = tk.Entry(
            country_input_frame,
            textvariable=self.country_var,
            width=10,
            font=self.theme.fonts["body"]
        )
        self.country_entry.pack(side=tk.LEFT)
        
        example_label = self.theme.create_styled_label(
            country_input_frame,
            "  (e.g., US, GB, CA or US,GB,CA - leave blank for global scan)",
            "small",
            fg=self.theme.colors["text_secondary"]
        )
        example_label.pack(side=tk.LEFT)
    
    def _create_config_section(self) -> None:
        """Create configuration file section."""
        config_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(config_frame, "card")
        config_frame.pack(fill=tk.X, padx=20, pady=(0, 5))
        
        # Section title
        config_title = self.theme.create_styled_label(
            config_frame,
            "Configuration",
            "heading"
        )
        config_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Config file info
        config_info_frame = tk.Frame(config_frame)
        self.theme.apply_to_widget(config_info_frame, "card")
        config_info_frame.pack(fill=tk.X, padx=15, pady=(0, 5))
        
        info_text = f"Using configuration from:\n{self.config_path}"
        config_path_label = self.theme.create_styled_label(
            config_info_frame,
            info_text,
            "small",
            fg=self.theme.colors["text_secondary"],
            justify="left"
        )
        config_path_label.pack(anchor="w")
        
        # Config editor button
        config_button_frame = tk.Frame(config_frame)
        self.theme.apply_to_widget(config_button_frame, "card")
        config_button_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        edit_config_button = tk.Button(
            config_button_frame,
            text="⚙ Edit Configuration",
            command=self._open_config_editor
        )
        self.theme.apply_to_widget(edit_config_button, "button_secondary")
        edit_config_button.pack(side=tk.LEFT)
    
    def _create_button_panel(self) -> None:
        """Create dialog button panel."""
        button_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(button_frame, "main_window")
        button_frame.pack(fill=tk.X, padx=20, pady=(5, 15))
        
        # Cancel button (left)
        cancel_button = tk.Button(
            button_frame,
            text="Cancel",
            command=self._cancel_scan
        )
        self.theme.apply_to_widget(cancel_button, "button_secondary")
        cancel_button.pack(side=tk.LEFT)
        
        # Start scan button (right)
        start_button = tk.Button(
            button_frame,
            text="🚀 Start Scan",
            command=self._start_scan
        )
        self.theme.apply_to_widget(start_button, "button_primary")
        start_button.pack(side=tk.RIGHT)
    
    def _setup_event_handlers(self) -> None:
        """Setup event handlers."""
        self.dialog.protocol("WM_DELETE_WINDOW", self._cancel_scan)
        
        # Keyboard shortcuts
        self.dialog.bind("<Return>", lambda e: self._start_scan())
        self.dialog.bind("<Escape>", lambda e: self._cancel_scan())
        
        # Country input validation
        self.country_var.trace_add("write", self._validate_country_input)
    
    def _focus_country_field(self) -> None:
        """Set focus to country input field."""
        self.country_entry.focus_set()
    
    def _parse_and_validate_countries(self, country_input: str) -> tuple[list[str], str]:
        """Parse and validate comma-separated country codes.
        
        Args:
            country_input: Raw country input string
            
        Returns:
            Tuple of (valid_countries_list, error_message)
            If error_message is empty, validation succeeded
        """
        if not country_input.strip():
            return [], ""  # Empty input is valid (global scan)
        
        # Parse comma-separated countries
        countries = [country.strip().upper() for country in country_input.split(',')]
        valid_countries = []
        
        for country in countries:
            if not country:  # Skip empty entries from double commas
                continue
                
            # Validate individual country code
            if len(country) < 2 or len(country) > 3:
                return [], f"Invalid country code '{country}': must be 2-3 characters (e.g., US, GB, CA)"
            
            if not country.isalpha():
                return [], f"Invalid country code '{country}': must contain only letters (e.g., US, GB, CA)"
            
            valid_countries.append(country)
        
        if not valid_countries:
            return [], "Please enter at least one valid country code"
            
        return valid_countries, ""
    
    def _validate_country_input(self, *args) -> None:
        """Validate country code input in real-time."""
        country_input = self.country_var.get()
        
        # Allow empty (global scan)
        if not country_input.strip():
            return
        
        # Convert to uppercase but preserve formatting for user experience
        upper_input = country_input.upper()
        if upper_input != country_input:
            self.country_var.set(upper_input)
    
    def _open_config_editor(self) -> None:
        """Open configuration editor."""
        try:
            self.config_editor_callback(str(self.config_path))
        except Exception as e:
            messagebox.showerror(
                "Configuration Editor Error",
                f"Failed to open configuration editor:\n{str(e)}\n\n"
                "Please ensure the configuration system is properly set up."
            )
    
    def _start_scan(self) -> None:
        """Start the scan with configured parameters."""
        country_input = self.country_var.get().strip()
        
        # Parse and validate country codes
        countries, error_msg = self._parse_and_validate_countries(country_input)
        
        if error_msg:
            messagebox.showerror(
                "Invalid Country Code(s)",
                error_msg + "\n\nExamples:\n• Single: US\n• Multiple: US,GB,CA or US, GB, CA"
            )
            self.country_entry.focus_set()
            return
        
        # Prepare country parameter for backend (comma-separated string or None)
        if countries:
            country_param = ",".join(countries)
            if len(countries) == 1:
                scan_desc = f"country: {countries[0]}"
            else:
                scan_desc = f"countries: {', '.join(countries)}"
        else:
            country_param = None
            scan_desc = "global (all countries)"
            
        result = messagebox.askyesno(
            "Start Scan",
            f"Start SMB security scan for {scan_desc}?\n\n"
            "This will discover SMB servers and test for accessible shares."
        )
        
        if result:
            try:
                # Set results and close dialog
                self.result = "start"
                self.country_code = country_param
                
                # Start the scan
                self.scan_start_callback(self.country_code)
                
                # Close dialog
                self.dialog.destroy()
            except Exception as e:
                # Handle scan start errors gracefully
                messagebox.showerror(
                    "Scan Start Error",
                    f"Failed to start scan:\n{str(e)}\n\n"
                    "Please check that the backend is properly configured and try again."
                )
                # Don't close dialog so user can try again
    
    def _cancel_scan(self) -> None:
        """Cancel scan and close dialog."""
        self.result = "cancel"
        self.dialog.destroy()
    
    def show(self) -> Optional[str]:
        """
        Show dialog and wait for result.
        
        Returns:
            "start" if scan was started, "cancel" if cancelled, None if closed
        """
        # Wait for dialog to close
        self.parent.wait_window(self.dialog)
        return self.result


def show_scan_dialog(parent: tk.Widget, config_path: str,
                    config_editor_callback: Callable[[str], None],
                    scan_start_callback: Callable[[Optional[str]], None]) -> Optional[str]:
    """
    Show scan configuration dialog.
    
    Args:
        parent: Parent widget
        config_path: Path to configuration file
        config_editor_callback: Function to open config editor
        scan_start_callback: Function to start scan with country parameter
        
    Returns:
        Dialog result ("start", "cancel", or None)
    """
    dialog = ScanDialog(parent, config_path, config_editor_callback, scan_start_callback)
    return dialog.show()