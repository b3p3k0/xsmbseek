"""
Server Detail Popup Operations

Handles server detail popup windows and exploration functionality.
Self-contained UI components with passed data dependencies.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import platform
from typing import Dict, Any


def show_server_detail_popup(parent_window, server_data, theme):
    """
    Show server detail popup window.

    Args:
        parent_window: Parent window for transient behavior
        server_data: Server dictionary with all fields
        theme: Theme object for styling
    """
    # Create popup window
    detail_window = tk.Toplevel(parent_window)
    detail_window.title(f"Server Details - {server_data.get('ip_address', 'Unknown')}")
    detail_window.geometry("700x700")
    detail_window.transient(parent_window)

    theme.apply_to_widget(detail_window, "main_window")

    # Create scrollable text area
    text_frame = tk.Frame(detail_window)
    text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    text_widget = tk.Text(text_frame, wrap=tk.WORD, state=tk.DISABLED)
    scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
    text_widget.configure(yscrollcommand=scrollbar.set)

    text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Format server details
    details = _format_server_details(server_data)

    # Insert details
    text_widget.configure(state=tk.NORMAL)
    text_widget.insert(tk.END, details)
    text_widget.configure(state=tk.DISABLED)

    # Button frame for Explore and Close buttons
    button_frame = tk.Frame(detail_window)
    theme.apply_to_widget(button_frame, "main_window")
    button_frame.pack(pady=(0, 10))

    # Explore button
    explore_button = tk.Button(
        button_frame,
        text="Explore",
        command=lambda: explore_server(server_data)
    )
    theme.apply_to_widget(explore_button, "button_secondary")
    explore_button.pack(side=tk.LEFT, padx=(0, 10))

    # Close button
    close_button = tk.Button(
        button_frame,
        text="Close",
        command=detail_window.destroy
    )
    theme.apply_to_widget(close_button, "button_primary")
    close_button.pack(side=tk.LEFT)

    # Ensure window is fully rendered before setting grab
    detail_window.update_idletasks()
    detail_window.grab_set()


def explore_server(server_data):
    """
    Open server in system file explorer via SMB/CIFS protocol.

    Args:
        server_data: Server dictionary containing IP address and authentication info
    """
    ip_address = server_data.get('ip_address')
    auth_method = server_data.get('auth_method', 'Unknown')

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


def _format_server_details(server: Dict[str, Any]) -> str:
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