"""
SMBSeek Server List Browser Window

Detailed server list browser with filtering, sorting, and export capabilities.
Provides comprehensive view of all discovered SMB servers with drill-down
to individual server details.

Design Decision: Separate window allows detailed analysis without cluttering
the main dashboard while supporting the key export/import collaboration workflow.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
import os
import sys
import subprocess
import platform

# Add utils to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))

try:
    from gui.utils.database_access import DatabaseReader
    from gui.utils.style import get_theme
    from gui.utils.data_export_engine import get_export_engine
    from gui.utils.scan_manager import get_scan_manager
except ImportError:
    # Handle relative imports when running from gui directory
    from utils.database_access import DatabaseReader
    from utils.style import get_theme
    from utils.data_export_engine import get_export_engine
    from utils.scan_manager import get_scan_manager


class ServerListWindow:
    """
    Server list browser window with filtering and export capabilities.
    
    Provides detailed view of all discovered SMB servers with:
    - Sortable table display
    - Multi-criteria filtering
    - Individual server detail popups
    - CSV export functionality
    - Data selection and bulk operations
    
    Design Pattern: Modal window with comprehensive data access and export
    capabilities for team collaboration workflows.
    """
    
    def __init__(self, parent: tk.Widget, db_reader: DatabaseReader,
                 window_data: Dict[str, Any] = None, settings_manager = None):
        """
        Initialize server list browser window.

        Args:
            parent: Parent widget
            db_reader: Database access instance
            window_data: Optional data for filtering/focus
            settings_manager: Optional settings manager for favorites functionality
        """
        self.parent = parent
        self.db_reader = db_reader
        self.theme = get_theme()
        self.window_data = window_data or {}
        self.settings_manager = settings_manager

        # Favorites and avoid functionality
        self.favorites_only = tk.BooleanVar()
        self.avoid_only = tk.BooleanVar()
        
        # Window and UI components
        self.window = None
        self.main_frame = None
        self.filter_frame = None
        self.table_frame = None
        self.button_frame = None
        
        # Table components
        self.tree = None
        self.scrollbar_v = None
        self.scrollbar_h = None
        # Filter variables - simplified for enhanced share tracking
        self.search_text = tk.StringVar()
        self.search_var = tk.StringVar()  # Additional search reference
        self.date_filter = tk.StringVar(value="All")
        self.shares_filter = tk.BooleanVar(value=True)  # Fixed: BooleanVar for checkbox, default checked to hide zero-share servers
        
        # Filter UI components - simplified
        self.advanced_filters_frame = None
        self.date_combo = None
        self.shares_filter_checkbox = None
        
        # UI components
        self.count_label = None
        self.selection_label = None
        self.status_label = None
        self.mode_button = None
        self.show_all_button = None
        
        # Date filtering state
        self.filter_recent = self.window_data.get("filter_recent", False)
        self.last_scan_time = None
        
        # Data management
        self.all_servers = []
        self.filtered_servers = []
        self.selected_servers = []
        
        # Window state
        self.is_advanced_mode = False

        # Sort state tracking for bidirectional column sorting
        self.current_sort_column = None
        self.current_sort_direction = None
        self.original_headers = {}  # Cache original column text for clean restoration

        # Default sort directions for each column
        self.default_sort_directions = {
            "IP Address": "asc",      # alphabetical A-Z
            "Shares": "desc",         # high numbers first (10, 5, 1)
            "Accessible": "desc",     # high share count first (sorts by number of shares)
            "Last Seen": "desc",      # MOST RECENT dates first (2024-01-02, 2024-01-01, 2023-12-31)
            "Country": "asc"          # alphabetical A-Z
        }

        self._create_window()
        self._load_data()
    
    def _create_window(self) -> None:
        """Create the server list window."""
        self.window = tk.Toplevel(self.parent)
        self.window.title("SMBSeek - Server List Browser")
        self.window.geometry("1500x1000")
        self.window.minsize(800, 500)
        
        # Apply theme
        self.theme.apply_to_widget(self.window, "main_window")
        
        # Make window modal (use master window if available)
        if hasattr(self.parent, 'winfo_toplevel'):
            master_window = self.parent.winfo_toplevel()
            self.window.transient(master_window)
        self.window.grab_set()
        
        # Center window
        self._center_window()
        
        # Build UI components
        self._create_header()
        self._create_filter_panel()
        self._create_server_table()
        self._create_button_panel()
        
        # Bind events
        self._setup_event_handlers()
    
    def _center_window(self) -> None:
        """Center window on parent."""
        if self.window is not None:
            self.window.update_idletasks()
            # Get parent window position and size
            parent_x = self.parent.winfo_x()
            parent_y = self.parent.winfo_y()
            parent_width = self.parent.winfo_width()
            parent_height = self.parent.winfo_height()
            # Calculate center position
            width = self.window.winfo_width()
            height = self.window.winfo_height()
            x = parent_x + (parent_width // 2) - (width // 2)
            y = parent_y + (parent_height // 2) - (height // 2)
            self.window.geometry(f"{width}x{height}+{x}+{y}")
    
    def _create_header(self) -> None:
        """Create window header with title and controls."""
        header_frame = tk.Frame(self.window)
        self.theme.apply_to_widget(header_frame, "main_window")
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Title
        title_label = self.theme.create_styled_label(
            header_frame,
            "🖥 SMB Server List",
            "heading"
        )
        title_label.pack(side=tk.LEFT)
        
        # Server count
        self.count_label = self.theme.create_styled_label(
            header_frame,
            "Loading...",
            "body"
        )
        self.count_label.pack(side=tk.LEFT, padx=(20, 0))
        
        # Close button
        close_button = tk.Button(
            header_frame,
            text="✕ Close",
            command=self._close_window
        )
        self.theme.apply_to_widget(close_button, "button_secondary")
        close_button.pack(side=tk.RIGHT)
        
        # Mode toggle button
        self.mode_button = tk.Button(
            header_frame,
            text="🔧 Advanced",
            command=self._toggle_mode
        )
        self.theme.apply_to_widget(self.mode_button, "button_secondary")
        self.mode_button.pack(side=tk.RIGHT, padx=(0, 10))
    
    def _create_filter_panel(self) -> None:
        """Create filtering controls panel."""
        # Filter container (initially hidden for simple mode)
        self.filter_frame = tk.Frame(self.window)
        self.theme.apply_to_widget(self.filter_frame, "card")
        
        # Search box (always visible)
        search_frame = tk.Frame(self.filter_frame)
        self.theme.apply_to_widget(search_frame, "card")
        search_frame.pack(fill=tk.X, padx=10, pady=5)
        
        search_label = self.theme.create_styled_label(
            search_frame,
            "🔍 Search:",
            "body"
        )
        search_label.pack(side=tk.LEFT, padx=(0, 5))
        
        search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_text,
            width=30
        )
        search_entry.pack(side=tk.LEFT, padx=(0, 10))
        search_entry.bind("<KeyRelease>", lambda e: self._apply_filters())
        
        # Clear search button
        clear_button = tk.Button(
            search_frame,
            text="Clear",
            command=self._clear_search
        )
        self.theme.apply_to_widget(clear_button, "button_secondary")
        clear_button.pack(side=tk.LEFT, padx=(0, 10))

        # Favorites only filter checkbox
        self.favorites_checkbox = tk.Checkbutton(
            search_frame,
            text="Favorites only",
            variable=self.favorites_only,
            command=self._apply_filters
        )
        # Disable if no settings manager available
        if not self.settings_manager:
            self.favorites_checkbox.configure(state="disabled")
        self.theme.apply_to_widget(self.favorites_checkbox, "checkbox")
        self.favorites_checkbox.pack(side=tk.LEFT, padx=(0, 10))

        # Avoid only filter checkbox
        self.avoid_checkbox = tk.Checkbutton(
            search_frame,
            text="Avoid only",
            variable=self.avoid_only,
            command=self._apply_filters
        )
        # Disable if no settings manager available
        if not self.settings_manager:
            self.avoid_checkbox.configure(state="disabled")
        self.theme.apply_to_widget(self.avoid_checkbox, "checkbox")
        self.avoid_checkbox.pack(side=tk.LEFT, padx=(0, 10))
        
        # Show all results toggle (if we started with filtered results)
        if self.filter_recent:
            self.show_all_button = tk.Button(
                search_frame,
                text="📈 Show All Results",
                command=self._toggle_show_all_results
            )
            self.theme.apply_to_widget(self.show_all_button, "button_primary")
            self.show_all_button.pack(side=tk.LEFT)
        
        # Advanced filters (hidden initially)
        self.advanced_filters_frame = tk.Frame(self.filter_frame)
        self.theme.apply_to_widget(self.advanced_filters_frame, "card")

        # Accessible shares filter (checkbox) - simplified filtering
        shares_filter_frame = tk.Frame(self.advanced_filters_frame)
        self.theme.apply_to_widget(shares_filter_frame, "card")
        shares_filter_frame.pack(side=tk.LEFT, padx=10, pady=5)

        self.shares_filter_checkbox = tk.Checkbutton(
            shares_filter_frame,
            text="Show only servers with accessible shares > 0",
            variable=self.shares_filter,
            command=self._apply_filters
        )
        self.shares_filter_checkbox.pack()
        
        # Date filter
        date_frame = tk.Frame(self.advanced_filters_frame)
        self.theme.apply_to_widget(date_frame, "card")
        date_frame.pack(side=tk.LEFT, padx=10, pady=5)
        
        date_label = self.theme.create_styled_label(
            date_frame,
            "Discovery Date:",
            "small"
        )
        date_label.pack()
        
        self.date_combo = ttk.Combobox(
            date_frame,
            textvariable=self.date_filter,
            values=["All", "Since Last Scan", "Last 24 Hours", "Last 7 Days", "Last 30 Days"],
            width=15,
            state="readonly"
        )
        self.date_combo.set("All")
        self.date_combo.pack()
        self.date_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())
        
        # Reset filters button
        reset_button = tk.Button(
            self.advanced_filters_frame,
            text="Reset Filters",
            command=self._reset_filters
        )
        self.theme.apply_to_widget(reset_button, "button_secondary")
        reset_button.pack(side=tk.RIGHT, padx=10, pady=5)
        
        # Pack filter frame (shown/hidden based on mode)
        self._update_mode_display()
    
    def _create_server_table(self) -> None:
        """Create server data table with scrollbars."""
        # Table container
        self.table_frame = tk.Frame(self.window)
        self.theme.apply_to_widget(self.table_frame, "main_window")
        self.table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Define columns - updated for enhanced share tracking with favorites and avoid
        columns = (
            "favorite",
            "avoid",
            "IP Address",
            "Shares",
            "Accessible",
            "Last Seen",
            "Country"
        )
        
        # Create treeview
        self.tree = ttk.Treeview(
            self.table_frame,
            columns=columns,
            show="tree headings",
            selectmode="extended"
        )
        
        # Configure columns - optimized dimensions for enhanced share tracking with favorites and avoid
        self.tree.column("#0", width=0, stretch=False)  # Hide tree column
        self.tree.column("favorite", width=40, anchor="center")  # Favorite star column
        self.tree.column("avoid", width=40, anchor="center")  # Avoid skull column
        self.tree.column("IP Address", width=160, anchor="w")
        self.tree.column("Shares", width=100, anchor="center")
        self.tree.column("Accessible", width=780, anchor="w")  # Wide for extensive share lists
        self.tree.column("Last Seen", width=150, anchor="w")
        self.tree.column("Country", width=100, anchor="w", stretch=True)  # Flexible width
        
        # Configure headings
        for col in columns:
            if col == "favorite":
                self.tree.heading(col, text="★", command=lambda c=col: self._sort_by_column(c))
            elif col == "avoid":
                self.tree.heading(col, text="☠", command=lambda c=col: self._sort_by_column(c))
            else:
                self.tree.heading(col, text=col, command=lambda c=col: self._sort_by_column(c))
        
        # Add scrollbars
        self.scrollbar_v = ttk.Scrollbar(
            self.table_frame,
            orient="vertical",
            command=self.tree.yview
        )
        self.scrollbar_h = ttk.Scrollbar(
            self.table_frame,
            orient="horizontal", 
            command=self.tree.xview
        )
        
        self.tree.configure(yscrollcommand=self.scrollbar_v.set)
        self.tree.configure(xscrollcommand=self.scrollbar_h.set)
        
        # Pack components
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.scrollbar_v.grid(row=0, column=1, sticky="ns")
        self.scrollbar_h.grid(row=1, column=0, sticky="ew")
        
        # Configure grid weights
        self.table_frame.grid_rowconfigure(0, weight=1)
        self.table_frame.grid_columnconfigure(0, weight=1)
    
    def _create_button_panel(self) -> None:
        """Create bottom button panel with actions."""
        self.button_frame = tk.Frame(self.window)
        self.theme.apply_to_widget(self.button_frame, "main_window")
        self.button_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        # Left side - selection info
        self.selection_label = self.theme.create_styled_label(
            self.button_frame,
            "No selection",
            "small"
        )
        self.selection_label.pack(side=tk.LEFT)
        
        # Right side - action buttons
        button_container = tk.Frame(self.button_frame)
        self.theme.apply_to_widget(button_container, "main_window")
        button_container.pack(side=tk.RIGHT)
        
        # Server details button
        details_button = tk.Button(
            button_container,
            text="📋 View Details",
            command=self._view_server_details
        )
        self.theme.apply_to_widget(details_button, "button_secondary")
        details_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # Export selected button
        export_selected_button = tk.Button(
            button_container,
            text="📤 Export Selected",
            command=self._export_selected_servers
        )
        self.theme.apply_to_widget(export_selected_button, "button_secondary")
        export_selected_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # Export all button
        export_all_button = tk.Button(
            button_container,
            text="📊 Export All",
            command=self._export_all_servers
        )
        self.theme.apply_to_widget(export_all_button, "button_primary")
        export_all_button.pack(side=tk.LEFT)

    def _set_header_text(self, column: str, text: str) -> None:
        """Helper to update column header text."""
        self.tree.heading(column, text=text)

    def _reset_sort_state(self) -> None:
        """Reset sort state and restore all headers to original text."""
        # Restore all headers to original text
        for column, original_text in self.original_headers.items():
            self._set_header_text(column, original_text)

        # Clear sort state
        self.current_sort_column = None
        self.current_sort_direction = None

    def _setup_event_handlers(self) -> None:
        """Setup event handlers for the window."""
        # Table selection events
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_changed)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-1>", self._on_treeview_click)
        
        # Window close event
        self.window.protocol("WM_DELETE_WINDOW", self._close_window)
        
        # Keyboard shortcuts
        self.window.bind("<Control-a>", self._select_all)
        self.window.bind("<Control-e>", lambda e: self._export_selected_servers())
        self.window.bind("<Escape>", lambda e: self._close_window())
        self.window.bind("<F5>", lambda e: self._refresh_data())
    
    def apply_recent_discoveries_filter(self) -> None:
        """
        Programmatically filter server list to show only servers from most recent scan.
        
        Called when user clicks "View Details" on Recent Discoveries dashboard card.
        """
        try:
            # Clear existing filters first - updated for simplified filtering
            self.search_text.set("")
            self.date_filter.set("All")
            
            # Load servers with recent scan filter
            servers, total_count = self.db_reader.get_server_list(
                limit=10000,
                offset=0,
                recent_scan_only=True
            )
            
            self.all_servers = servers
            
            # Repopulate filter options for the new dataset
            self._populate_filter_options()
            
            # Apply filters (should be no-op since we cleared them, but updates display)
            self._apply_filters()
            
            # Update count display to indicate filtered view
            self.count_label.configure(text=f"Recent Scan: {len(self.all_servers)} servers discovered")
            
            # Add visual indicator that this is a filtered view
            if hasattr(self, 'status_label'):
                self.status_label.configure(
                    text="📊 Showing servers from most recent scan session",
                    fg=self.theme.colors.get("accent", "#007acc")
                )
            
        except Exception as e:
            messagebox.showerror(
                "Filter Error",
                f"Failed to apply recent discoveries filter: {e}"
            )
    
    def _load_data(self) -> None:
        """Load server data from database."""
        try:
            # Get last scan time from scan manager
            scan_manager = get_scan_manager()
            self.last_scan_time = scan_manager.get_last_scan_time()
            
            # Get all servers with pagination (large limit to get all)
            servers, total_count = self.db_reader.get_server_list(
                limit=10000,  # Large limit to get all servers
                offset=0
            )
            
            self.all_servers = servers
            
            # Populate filter dropdowns
            self._populate_filter_options()
            
            # Set initial date filter if requested
            if self.filter_recent and self.last_scan_time:
                self.date_combo.set("Since Last Scan")
            
            # Reset sort state for fresh dataset
            self._reset_sort_state()

            # Apply initial filters and display data
            self._apply_filters()

            # Update count display
            self.count_label.configure(text=f"Total: {len(self.all_servers)} servers")
            
        except Exception as e:
            messagebox.showerror(
                "Data Loading Error",
                f"Failed to load server data:\n{str(e)}"
            )
    
    def _populate_filter_options(self) -> None:
        """Populate filter dropdown options based on data - simplified for enhanced tracking."""
        if not self.all_servers:
            return
        
        # No longer need to populate country/auth filters since they've been removed
        # Date filter options are static and defined in the UI creation
    
    def _apply_filters(self) -> None:
        """Apply current filters to server list - simplified for enhanced share tracking."""
        filtered = self.all_servers[:]
        
        # Apply search filter (IP address and accessible shares list)
        search_term = self.search_text.get().lower()
        if search_term:
            filtered = [
                server for server in filtered
                if search_term in server.get("ip_address", "").lower() or
                   search_term in server.get("accessible_shares_list", "").lower()
            ]
        
        # Apply date filter
        date_filter_value = self.date_filter.get()
        if date_filter_value and date_filter_value != "All":
            filtered = self._apply_date_filter(filtered, date_filter_value)
        
        # Apply accessible shares filter
        if self.shares_filter.get():
            filtered = [server for server in filtered if server.get("accessible_shares", 0) > 0]

        # Apply favorites filter
        if self.favorites_only.get() and self.settings_manager:
            favorite_ips = self.settings_manager.get_favorite_servers()
            filtered = [server for server in filtered if server.get("ip_address") in favorite_ips]

        # Apply avoid filter
        if self.avoid_only.get() and self.settings_manager:
            avoid_ips = self.settings_manager.get_avoid_servers()
            filtered = [server for server in filtered if server.get("ip_address") in avoid_ips]

        self.filtered_servers = filtered
        self._update_table_display()
    
    def _apply_date_filter(self, servers: List[Dict[str, Any]], filter_type: str) -> List[Dict[str, Any]]:
        """
        Apply date-based filtering to server list.
        
        Args:
            servers: List of servers to filter
            filter_type: Type of date filter to apply
            
        Returns:
            Filtered list of servers
        """
        from datetime import datetime, timedelta
        
        now = datetime.now()
        cutoff_time = None
        
        if filter_type == "Since Last Scan" and self.last_scan_time:
            cutoff_time = self.last_scan_time
        elif filter_type == "Last 24 Hours":
            cutoff_time = now - timedelta(hours=24)
        elif filter_type == "Last 7 Days":
            cutoff_time = now - timedelta(days=7)
        elif filter_type == "Last 30 Days":
            cutoff_time = now - timedelta(days=30)
        
        if not cutoff_time:
            return servers
        
        filtered = []
        for server in servers:
            # Check various date fields that might be available
            server_date = None
            
            # Try different date field names
            for date_field in ["first_seen", "last_seen", "discovery_date", "created_at"]:
                if date_field in server and server[date_field]:
                    try:
                        server_date = datetime.fromisoformat(server[date_field].replace("Z", "+00:00"))
                        break
                    except (ValueError, AttributeError):
                        continue
            
            # If we found a valid date, compare it
            if server_date and server_date >= cutoff_time:
                filtered.append(server)
            elif not server_date:
                # If no date available and we're filtering for recent items, exclude
                # But if filtering "Since Last Scan" and no date, include (assume old data)
                if filter_type == "Since Last Scan":
                    filtered.append(server)
        
        return filtered
    
    def _update_table_display(self) -> None:
        """Update table display with filtered data."""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add filtered servers
        for server in self.filtered_servers:
            # Format display values - updated for enhanced share tracking
            ip_addr = server.get("ip_address", "")
            shares_count = str(server.get("accessible_shares", 0))
            accessible_shares = server.get("accessible_shares_list", "")
            last_seen = server.get("last_seen", "Never")
            country = server.get("country", "Unknown")
            
            # Format last seen date
            if last_seen and last_seen != "Never":
                try:
                    date_obj = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                    last_seen = date_obj.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            
            # Format accessible shares list (ensure no spaces after commas)
            if accessible_shares:
                # Remove any spaces after commas and ensure clean formatting
                accessible_shares = ",".join([share.strip() for share in accessible_shares.split(",") if share.strip()])

            # Determine favorite star
            if self.settings_manager and self.settings_manager.is_favorite_server(ip_addr):
                star = "★"
            else:
                star = "☆"

            # Determine avoid skull
            if self.settings_manager and self.settings_manager.is_avoid_server(ip_addr):
                skull = "☠"
            else:
                skull = "💀"

            # Insert row with new column structure including favorite star and avoid skull
            item_id = self.tree.insert(
                "",
                "end",
                values=(star, skull, ip_addr, shares_count, accessible_shares, last_seen, country)
            )
            
            # Add visual indicators for shares count
            share_count = server.get("accessible_shares", 0)
            if share_count > 0:
                self.tree.set(item_id, "Shares", f"📁 {shares_count}")
            else:
                self.tree.set(item_id, "Shares", shares_count)
        
        # Update status
        self.count_label.configure(
            text=f"Showing: {len(self.filtered_servers)} of {len(self.all_servers)} servers"
        )
    
    def _sort_by_column(self, column: str) -> None:
        """Sort table by specified column with bidirectional toggle support."""
        # Short-circuit for favorite and avoid columns - no meaningful sort order
        if column in ("favorite", "avoid"):
            return

        # Cache original header text on first access to this column
        if column not in self.original_headers:
            # Get current header text (remove any existing indicators)
            current_text = self.tree.heading(column)["text"]
            # Clean text by removing any existing indicators
            clean_text = current_text.replace(" (↑)", "").replace(" (↓)", "")
            self.original_headers[column] = clean_text

        # Determine sort direction
        if self.current_sort_column == column:
            # Same column clicked - toggle direction
            self.current_sort_direction = "asc" if self.current_sort_direction == "desc" else "desc"
        else:
            # Different column clicked - use default direction for this column
            self.current_sort_direction = self.default_sort_directions.get(column, "desc")

            # Clear previous column's indicator if there was one
            if self.current_sort_column and self.current_sort_column in self.original_headers:
                self._set_header_text(self.current_sort_column, self.original_headers[self.current_sort_column])

            # Update current column
            self.current_sort_column = column

        # Preserve selection and focus before sorting
        selected_items = list(self.tree.selection())
        focused_item = self.tree.focus()

        # Get current data with sort key
        data_with_keys = []

        for item in self.tree.get_children():
            values = self.tree.item(item)["values"]

            # Determine sort key based on column
            col_index = self.tree["columns"].index(column)
            sort_key = values[col_index]

            # Convert to appropriate type for sorting
            if column == "Shares":
                # Extract number from string (remove emojis)
                import re
                numbers = re.findall(r'\d+', str(sort_key))
                sort_key = int(numbers[0]) if numbers else 0
            elif column == "Last Seen":
                # Sort by date
                try:
                    sort_key = datetime.strptime(sort_key, "%Y-%m-%d %H:%M")
                except:
                    sort_key = datetime.min
            elif column == "Accessible":
                # Sort by length of accessible shares list (number of shares)
                sort_key = len(str(sort_key).split(",")) if str(sort_key).strip() else 0

            data_with_keys.append((sort_key, item, values))

        # Sort with correct direction
        reverse_sort = (self.current_sort_direction == "desc")
        data_with_keys.sort(key=lambda x: x[0], reverse=reverse_sort)

        # Rearrange items in tree
        for index, (_, item, _) in enumerate(data_with_keys):
            self.tree.move(item, "", index)

        # Update header with visual indicator
        indicator = " (↓)" if self.current_sort_direction == "desc" else " (↑)"
        self._set_header_text(column, f"{self.original_headers[column]}{indicator}")

        # Restore selection and focus
        if selected_items:
            # Filter out any items that no longer exist
            valid_items = [item for item in selected_items if self.tree.exists(item)]
            if valid_items:
                self.tree.selection_set(valid_items)

        if focused_item and self.tree.exists(focused_item):
            self.tree.focus(focused_item)
    
    def _on_selection_changed(self, event=None) -> None:
        """Handle table selection changes."""
        selected_items = self.tree.selection()
        selected_count = len(selected_items)
        
        if selected_count == 0:
            self.selection_label.configure(text="No selection")
        elif selected_count == 1:
            self.selection_label.configure(text="1 server selected")
        else:
            self.selection_label.configure(text=f"{selected_count} servers selected")
    
    def _on_double_click(self, event) -> None:
        """Handle double-click on table row - equivalent to select + View Details button."""
        # Check if the double-click was on a header - if so, ignore to prevent popup interference
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            return

        # File browser UX: identify exactly which row was double-clicked
        clicked_item = self.tree.identify_row(event.y)

        if not clicked_item:
            # Error handling: double-click didn't hit a valid data row
            messagebox.showwarning("Invalid Selection", "Please double-click on a server entry to view details.")
            return
        
        # File browser UX: select the double-clicked row for visual feedback
        self.tree.selection_set(clicked_item)
        
        # Use identical logic as "View Details" button - get data from clicked row
        values = self.tree.item(clicked_item)["values"]
        if not values:
            messagebox.showerror("Error", "Unable to retrieve server data.")
            return

        ip_address = values[2]  # IP Address is now at index 2 due to favorite and avoid columns
        
        # Same data lookup as working "View Details" button
        server_data = next(
            (server for server in self.filtered_servers if server.get("ip_address") == ip_address),
            None
        )
        
        if not server_data:
            # Same error message as "View Details" button for consistency
            messagebox.showerror("Error", "Server data not found.")
            return
        
        # Same popup method as "View Details" button - ensures identical behavior
        self._show_server_detail_popup(server_data)

    def _on_treeview_click(self, event) -> None:
        """Handle treeview clicks, specifically for favorite and avoid column toggles."""
        column = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)

        if not item or not self.settings_manager:
            return

        values = self.tree.item(item)["values"]
        if not values or len(values) < 3:
            return

        ip_address = values[2]  # IP is at index 2

        # Handle favorite column clicks (#1, since #0 hidden)
        if column == '#1':
            # Toggle favorite status
            is_now_favorite = self.settings_manager.toggle_favorite_server(ip_address)
            star = "★" if is_now_favorite else "☆"
            self.tree.set(item, "favorite", star)

            # Re-apply filters if favorites-only is enabled
            if self.favorites_only.get():
                self._apply_filters()

            # Maintain focus and selection for keyboard navigation
            self.tree.selection_set(item)
            self.tree.focus(item)

            return "break"  # Only consume event when we actually toggled

        # Handle avoid column clicks (#2)
        elif column == '#2':
            # Toggle avoid status
            is_now_avoided = self.settings_manager.toggle_avoid_server(ip_address)
            skull = "☠" if is_now_avoided else "💀"
            self.tree.set(item, "avoid", skull)

            # Re-apply filters if avoid-only is enabled
            if self.avoid_only.get():
                self._apply_filters()

            # Maintain focus and selection for keyboard navigation
            self.tree.selection_set(item)
            self.tree.focus(item)

            return "break"  # Only consume event when we actually toggled

    def _select_all(self, event=None) -> None:
        """Select all items in table."""
        self.tree.selection_set(self.tree.get_children())
    
    def _view_server_details(self) -> None:
        """Show detailed information for selected server."""
        selected_items = self.tree.selection()
        
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select a server to view details.")
            return
        
        if len(selected_items) > 1:
            messagebox.showwarning("Multiple Selection", "Please select only one server to view details.")
            return
        
        # Get server data - updated for new column structure
        item = selected_items[0]
        values = self.tree.item(item)["values"]
        ip_address = values[2]  # IP Address is now at index 2 due to favorite and avoid columns
        
        # Find server in data
        server_data = next(
            (server for server in self.filtered_servers if server.get("ip_address") == ip_address),
            None
        )
        
        if not server_data:
            messagebox.showerror("Error", "Server data not found.")
            return
        
        # Show details in popup
        self._show_server_detail_popup(server_data)
    
    def _show_server_detail_popup(self, server: Dict[str, Any]) -> None:
        """Show server detail popup window."""
        # Create popup window
        detail_window = tk.Toplevel(self.window)
        detail_window.title(f"Server Details - {server.get('ip_address', 'Unknown')}")
        detail_window.geometry("700x700")
        detail_window.transient(self.window)
        
        self.theme.apply_to_widget(detail_window, "main_window")
        
        # Create scrollable text area
        text_frame = tk.Frame(detail_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        text_widget = tk.Text(text_frame, wrap=tk.WORD, state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Format server details
        details = self._format_server_details(server)
        
        # Insert details
        text_widget.configure(state=tk.NORMAL)
        text_widget.insert(tk.END, details)
        text_widget.configure(state=tk.DISABLED)
        
        # Button frame for Explore and Close buttons
        button_frame = tk.Frame(detail_window)
        self.theme.apply_to_widget(button_frame, "main_window")
        button_frame.pack(pady=(0, 10))
        
        # Explore button
        explore_button = tk.Button(
            button_frame,
            text="Explore",
            command=lambda: self._explore_server(server)
        )
        self.theme.apply_to_widget(explore_button, "button_secondary")
        explore_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Close button
        close_button = tk.Button(
            button_frame,
            text="Close",
            command=detail_window.destroy
        )
        self.theme.apply_to_widget(close_button, "button_primary")
        close_button.pack(side=tk.LEFT)
        
        # Ensure window is fully rendered before setting grab
        detail_window.update_idletasks()
        detail_window.grab_set()
    
    def _explore_server(self, server: Dict[str, Any]) -> None:
        """
        Open server in system file explorer via SMB/CIFS protocol.
        
        Args:
            server: Server dictionary containing IP address and authentication info
        """
        ip_address = server.get('ip_address')
        auth_method = server.get('auth_method', 'Unknown')
        
        if not ip_address:
            messagebox.showerror(
                "Invalid Server",
                "Server IP address is not available."
            )
            return
        
        try:
            system = platform.system()
            
            if system == "Linux":
                # Use xdg-open to open SMB URL in default file manager
                subprocess.run(['xdg-open', f'smb://{ip_address}/'], check=True)
            elif system == "Windows":
                # Use explorer to open UNC path
                subprocess.run(['explorer', f'\\\\{ip_address}\\'], check=True)
            elif system == "Darwin":  # macOS
                # Use open to launch SMB URL in Finder
                subprocess.run(['open', f'smb://{ip_address}/'], check=True)
            else:
                raise OSError(f"Unsupported operating system: {system}")
                
        except subprocess.CalledProcessError as e:
            messagebox.showerror(
                "Connection Failed",
                f"Could not open SMB connection to {ip_address}\n\n"
                f"The server may be offline, unreachable, or your system may not support SMB connections.\n\n"
                f"Authentication method: {auth_method}\n"
                f"Command failed with exit code: {e.returncode}"
            )
        except FileNotFoundError:
            messagebox.showerror(
                "System Error",
                f"Could not find system file explorer.\n\n"
                f"Please ensure your system supports SMB connections and has a file manager installed."
            )
        except Exception as e:
            messagebox.showerror(
                "Unexpected Error",
                f"An unexpected error occurred while trying to connect to {ip_address}\n\n"
                f"Error: {str(e)}\n\n"
                f"Please check your network connection and SMB client configuration."
            )
    
    def _format_server_details(self, server: Dict[str, Any]) -> str:
        """Format server details for display with accessible shares list."""
        # Extract share information
        accessible_list = server.get('accessible_shares_list', '')
        accessible_count = server.get('accessible_shares', 0)
        total_shares = server.get('total_shares', accessible_count)
        
        # Format accessible shares list
        if accessible_list and accessible_list.strip():
            shares = [share.strip() for share in accessible_list.split(',') if share.strip()]
            if shares:
                share_list_text = '\n'.join([f'   • {share}' for share in shares])
            else:
                share_list_text = '   • None accessible'
        else:
            share_list_text = '   • None accessible'
        
        details = f"""📋 SMB Server Details
        
🖥 Basic Information:
   IP Address: {server.get('ip_address', 'Unknown')}
   Country: {server.get('country', 'Unknown')} ({server.get('country_code', 'Unknown')})
   Authentication: {server.get('auth_method', 'Unknown')}
   
📊 Scan Information:
   First Seen: {server.get('first_seen', 'Unknown')}
   Last Seen: {server.get('last_seen', 'Unknown')}
   Scan Count: {server.get('scan_count', 0)}
   Status: {server.get('status', 'Unknown')}
   
📁 Share Access:
   Total Shares Discovered: {total_shares}
   Accessible Shares: {accessible_count}
   
   Accessible Share List:
{share_list_text}
   
🔒 Security Assessment:
   Vulnerabilities: {server.get('vulnerabilities', 0)}
   
📝 Additional Notes:
   This server was discovered through SMBSeek scanning and shows
   the authentication method and share accessibility results.
   
   For detailed vulnerability information and remediation steps,
   use the Vulnerability Report window.
   
   For complete share enumeration data, check the backend database
   or export the detailed scan results.
        """
        
        return details
    
    def _export_selected_servers(self) -> None:
        """Show export menu for selected servers."""
        selected_servers = self._get_selected_servers()
        if not selected_servers:
            messagebox.showwarning("No Selection", "Please select servers to export.")
            return
        
        self._show_export_menu_for_servers(selected_servers, "selected")
    
    def _get_selected_servers(self) -> List[Dict[str, Any]]:
        """Get data for currently selected servers."""
        selected_items = self.tree.selection()
        selected_ips = []
        for item in selected_items:
            values = self.tree.item(item)["values"]
            selected_ips.append(values[2])  # IP address is now at index 2 due to favorite and avoid columns
        
        selected_servers = [
            server for server in self.filtered_servers
            if server.get("ip_address") in selected_ips
        ]
        
        return selected_servers
    
    def _export_all_servers(self) -> None:
        """Show export menu for all filtered servers."""
        if not self.filtered_servers:
            messagebox.showwarning("No Data", "No servers to export.")
            return
        
        self._show_export_menu_for_servers(self.filtered_servers, "all")
    
    def _export_servers_to_csv(self, servers: List[Dict[str, Any]], export_type: str) -> None:
        """Export servers using centralized export engine."""
        self._export_servers(servers, export_type, 'csv')
    
    def _export_servers(self, servers: List[Dict[str, Any]], export_type: str, format_type: str = 'csv') -> None:
        """
        Export servers using centralized data export engine.
        
        Args:
            servers: List of server dictionaries to export
            export_type: Type of export ("selected" or "all")  
            format_type: Export format (csv, json, zip)
        """
        if not servers:
            messagebox.showwarning("No Data", "No servers to export.")
            return
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extensions = {'csv': '.csv', 'json': '.json', 'zip': '.zip'}
        filetypes_map = {
            'csv': [("CSV files", "*.csv"), ("All files", "*.*")],
            'json': [("JSON files", "*.json"), ("All files", "*.*")],
            'zip': [("ZIP files", "*.zip"), ("All files", "*.*")]
        }
        
        default_filename = f"smbseek_servers_{export_type}_{timestamp}{extensions[format_type]}"
        
        # Ask for save location
        filename = filedialog.asksaveasfilename(
            title=f"Export {export_type.title()} Servers ({format_type.upper()})",
            defaultextension=extensions[format_type],
            filetypes=filetypes_map[format_type],
            initialfile=default_filename
        )
        
        if not filename:
            return
        
        try:
            # Create progress dialog
            progress_window = tk.Toplevel(self.window)
            progress_window.title("Exporting...")
            progress_window.geometry("300x120")
            progress_window.transient(self.window)
            progress_window.grab_set()
            
            progress_label = tk.Label(progress_window, text="Preparing export...")
            progress_label.pack(pady=10)
            
            progress_bar = ttk.Progressbar(progress_window, length=250, mode='determinate')
            progress_bar.pack(pady=10)
            
            progress_window.update()
            
            # Prepare filters applied info - simplified for enhanced tracking
            filters_applied = {}
            if self.search_text.get():
                filters_applied['search'] = self.search_text.get()
            if self.date_filter.get() != "All":
                filters_applied['date_filter'] = self.date_filter.get()
            if self.shares_filter.get():
                filters_applied['shares_filter'] = "accessible_only"
            
            # Progress callback
            def update_progress(percentage, message):
                if percentage >= 0:
                    progress_bar['value'] = percentage
                    progress_label.config(text=message)
                    progress_window.update()
            
            # Use export engine
            export_engine = get_export_engine()
            result = export_engine.export_data(
                data=servers,
                data_type='servers',
                export_format=format_type,
                output_path=filename,
                include_metadata=True,
                filters_applied=filters_applied,
                progress_callback=update_progress
            )
            
            progress_window.destroy()
            
            if result['success']:
                file_size_mb = result['file_size'] / (1024 * 1024)
                messagebox.showinfo(
                    "Export Complete",
                    f"Successfully exported {result['records_exported']} servers\n"
                    f"Format: {result['format'].upper()}\n"
                    f"Size: {file_size_mb:.2f} MB\n"
                    f"File: {filename}"
                )
            else:
                messagebox.showerror("Export Error", "Export failed")
            
        except Exception as e:
            try:
                progress_window.destroy()
            except:
                pass
            messagebox.showerror(
                "Export Error",
                f"Failed to export servers:\n{str(e)}"
            )
    
    def _show_export_menu_for_servers(self, servers: List[Dict[str, Any]], export_type: str) -> None:
        """Show export format selection menu for specific servers."""
        if not servers:
            messagebox.showwarning("No Data", "No servers to export.")
            return
        
        menu = tk.Menu(self.window, tearoff=0)
        menu.add_command(
            label=f"Export {export_type.title()} as CSV", 
            command=lambda: self._export_servers(servers, export_type, 'csv')
        )
        menu.add_command(
            label=f"Export {export_type.title()} as JSON", 
            command=lambda: self._export_servers(servers, export_type, 'json')
        )
        menu.add_command(
            label=f"Export {export_type.title()} as ZIP (CSV+JSON)", 
            command=lambda: self._export_servers(servers, export_type, 'zip')
        )
        
        # Show menu at mouse position
        try:
            menu.post(self.window.winfo_pointerx(), self.window.winfo_pointery())
        except tk.TclError:
            menu.post(self.window.winfo_rootx() + 50, self.window.winfo_rooty() + 50)
    
    def _toggle_mode(self) -> None:
        """Toggle between simple and advanced mode."""
        self.is_advanced_mode = not self.is_advanced_mode
        self._update_mode_display()
    
    def _update_mode_display(self) -> None:
        """Update display based on current mode."""
        if self.is_advanced_mode:
            self.mode_button.configure(text="📊 Simple")
            self.filter_frame.pack(fill=tk.X, padx=10, pady=(0, 5), before=self.table_frame)
            self.advanced_filters_frame.pack(fill=tk.X, pady=(5, 0))
        else:
            self.mode_button.configure(text="🔧 Advanced")
            self.filter_frame.pack(fill=tk.X, padx=10, pady=(0, 5), before=self.table_frame)
            self.advanced_filters_frame.pack_forget()
    
    def _clear_search(self) -> None:
        """Clear search text."""
        self.search_text.set("")
        self._apply_filters()
    
    def _toggle_show_all_results(self) -> None:
        """Toggle between showing recent results and all results."""
        if self.date_filter.get() == "Since Last Scan":
            # Currently showing recent, switch to all
            self.date_filter.set("All")
            self.show_all_button.configure(text="📊 Show Recent Results")
        else:
            # Currently showing all, switch to recent
            if self.last_scan_time:
                self.date_filter.set("Since Last Scan")
                self.show_all_button.configure(text="📈 Show All Results")
        
        self._apply_filters()
    
    def _reset_filters(self) -> None:
        """Reset all filters to default values - simplified for enhanced tracking."""
        self.search_text.set("")
        self.date_filter.set("All")
        self.shares_filter.set(False)  # Fixed: BooleanVar uses False, not empty string
        self.favorites_only.set(False)
        self.avoid_only.set(False)
        self._apply_filters()
    
    def _refresh_data(self) -> None:
        """Refresh data from database."""
        self._load_data()
    
    def _close_window(self) -> None:
        """Close the server list window."""
        self.window.destroy()


def open_server_list_window(parent: tk.Widget, db_reader: DatabaseReader,
                           window_data: Dict[str, Any] = None, settings_manager = None) -> None:
    """
    Open server list browser window.

    Args:
        parent: Parent widget
        db_reader: Database reader instance
        window_data: Optional data for window initialization
        settings_manager: Optional settings manager for favorites functionality
    """
    ServerListWindow(parent, db_reader, window_data, settings_manager)