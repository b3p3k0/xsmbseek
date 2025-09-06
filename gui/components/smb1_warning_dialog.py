"""
SMB1 Warning Dialog

Modal dialog for SMB1 discovery mode consent as per security audit recommendations.
Provides explicit user acknowledgment of SMB1 risks with mandatory consent checkbox.

Design Decision: Separate modal dialog ensures users cannot accidentally enable
SMB1 mode without understanding the security implications.
"""

import tkinter as tk
from tkinter import ttk
import os
import sys
from pathlib import Path
from typing import Optional

# Add utils to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))

from style import get_theme


class SMB1WarningDialog:
    """
    Modal warning dialog for SMB1 discovery mode consent.
    
    Implements audit security requirement: SMB1 mode requires explicit 
    acknowledgment with "I understand" checkbox before proceeding.
    
    Features:
    - Clear risk explanation
    - Mandatory consent checkbox
    - Modal behavior with proper focus management
    - Cannot proceed without explicit acknowledgment
    """
    
    def __init__(self, parent: tk.Widget):
        """
        Initialize SMB1 warning dialog.
        
        Args:
            parent: Parent widget for modal behavior
        """
        self.parent = parent
        self.theme = get_theme()
        
        # Dialog result
        self.result = False
        self.consent_given = False
        
        # UI components
        self.dialog = None
        self.consent_var = tk.BooleanVar()
        self.consent_checkbox = None
        self.proceed_button = None
        
        self._create_dialog()
    
    def _create_dialog(self) -> None:
        """Create the SMB1 warning dialog."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("⚠️ SMB1 Discovery Mode Warning")
        self.dialog.geometry("600x500")
        self.dialog.minsize(500, 450)
        
        # Apply theme
        self.theme.apply_to_widget(self.dialog, "main_window")
        
        # Make modal and bring to front
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.focus_set()
        
        # Center dialog
        self._center_dialog()
        
        # Build UI
        self._create_warning_header()
        self._create_risk_explanation()
        self._create_safety_measures()
        self._create_consent_section()
        self._create_button_panel()
        
        # Setup event handlers
        self._setup_event_handlers()
        
        # Initial button state
        self._update_proceed_button_state()
    
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
    
    def _create_warning_header(self) -> None:
        """Create warning header with alert styling."""
        header_frame = tk.Frame(self.dialog)
        header_frame.configure(bg='#fff3cd', relief='solid', borderwidth=1)  # Warning yellow background
        header_frame.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        # Warning icon and title
        title_frame = tk.Frame(header_frame, bg='#fff3cd')
        title_frame.pack(pady=10)
        
        warning_label = tk.Label(
            title_frame,
            text="⚠️ SECURITY WARNING ⚠️",
            font=self.theme.fonts["heading"],
            fg='#856404',  # Dark yellow text
            bg='#fff3cd'
        )
        warning_label.pack()
        
        subtitle_label = tk.Label(
            title_frame,
            text="SMB1 Discovery Mode",
            font=self.theme.fonts["subheading"],
            fg='#856404',
            bg='#fff3cd'
        )
        subtitle_label.pack(pady=(5, 0))
    
    def _create_risk_explanation(self) -> None:
        """Create risk explanation section."""
        risk_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(risk_frame, "card")
        risk_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 5))
        
        # Section title
        risk_title = self.theme.create_styled_label(
            risk_frame,
            "🛑 Security Risks",
            "heading",
            fg='#dc3545'  # Red color for risks
        )
        risk_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Risk explanation text
        risk_text = """SMB1 is a legacy protocol with known security vulnerabilities:

• Susceptible to remote code execution attacks
• Lacks modern encryption and authentication protections
• Used in WannaCry and NotPetya ransomware attacks
• Deprecated by Microsoft and security organizations worldwide

SMB1 Discovery Mode is provided only for compatibility with legacy systems that cannot be upgraded."""
        
        risk_label = self.theme.create_styled_label(
            risk_frame,
            risk_text,
            "body",
            justify="left"
        )
        risk_label.pack(anchor="w", padx=15, pady=(0, 10), fill=tk.X)
    
    def _create_safety_measures(self) -> None:
        """Create safety measures section."""
        safety_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(safety_frame, "card")
        safety_frame.pack(fill=tk.X, padx=15, pady=(0, 5))
        
        # Section title
        safety_title = self.theme.create_styled_label(
            safety_frame,
            "🔒 Safety Measures Applied",
            "heading",
            fg='#28a745'  # Green color for safety
        )
        safety_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Safety measures text
        safety_text = """When SMB1 Discovery Mode is enabled, these protections are enforced:

✓ Anonymous authentication ONLY (no credential exposure)
✓ Discovery operations ONLY (no file access or modifications)
✓ Single run mode (automatically disabled after scan)
✓ Strict timeouts and connection limits
✓ Enhanced logging and monitoring
✓ Process isolation and sandboxing"""
        
        safety_label = self.theme.create_styled_label(
            safety_frame,
            safety_text,
            "body",
            justify="left"
        )
        safety_label.pack(anchor="w", padx=15, pady=(0, 10), fill=tk.X)
    
    def _create_consent_section(self) -> None:
        """Create consent checkbox section."""
        consent_frame = tk.Frame(self.dialog)
        consent_frame.configure(bg='#f8f9fa', relief='solid', borderwidth=1)
        consent_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        # Consent checkbox with clear text
        self.consent_checkbox = tk.Checkbutton(
            consent_frame,
            variable=self.consent_var,
            text="I understand the security risks and accept responsibility for enabling SMB1 discovery",
            font=self.theme.fonts["body"],
            wraplength=550,
            bg='#f8f9fa',
            command=self._update_proceed_button_state
        )
        self.consent_checkbox.pack(padx=15, pady=15, anchor="w")
    
    def _create_button_panel(self) -> None:
        """Create dialog button panel."""
        button_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(button_frame, "main_window")
        button_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        # Cancel button (left)
        cancel_button = tk.Button(
            button_frame,
            text="Cancel",
            command=self._cancel
        )
        self.theme.apply_to_widget(cancel_button, "button_secondary")
        cancel_button.pack(side=tk.LEFT)
        
        # Proceed button (right) - initially disabled
        self.proceed_button = tk.Button(
            button_frame,
            text="⚠️ Enable SMB1 Mode",
            command=self._proceed,
            state=tk.DISABLED
        )
        self.theme.apply_to_widget(self.proceed_button, "button_danger")
        self.proceed_button.pack(side=tk.RIGHT)
    
    def _setup_event_handlers(self) -> None:
        """Setup event handlers."""
        self.dialog.protocol("WM_DELETE_WINDOW", self._cancel)
        
        # Keyboard shortcuts
        self.dialog.bind("<Escape>", lambda e: self._cancel())
        
        # Focus management
        self.dialog.focus_set()
    
    def _update_proceed_button_state(self) -> None:
        """Update proceed button state based on consent checkbox."""
        if self.consent_var.get():
            self.proceed_button.config(state=tk.NORMAL)
            # Change to warning style when enabled
            self.proceed_button.config(bg='#ffc107', fg='#212529')
        else:
            self.proceed_button.config(state=tk.DISABLED)
            # Disabled style
            self.proceed_button.config(bg='#e9ecef', fg='#6c757d')
    
    def _proceed(self) -> None:
        """User has given consent - enable SMB1 mode."""
        if not self.consent_var.get():
            return  # Should not happen due to button state management
        
        self.result = True
        self.consent_given = True
        self.dialog.destroy()
    
    def _cancel(self) -> None:
        """Cancel SMB1 mode - return to safe defaults."""
        self.result = False
        self.consent_given = False
        self.dialog.destroy()
    
    def show(self) -> bool:
        """
        Show dialog and wait for result.
        
        Returns:
            True if user consented to SMB1 mode, False otherwise
        """
        # Wait for dialog to close
        self.parent.wait_window(self.dialog)
        return self.result


def show_smb1_warning_dialog(parent: tk.Widget) -> bool:
    """
    Show SMB1 warning dialog and get user consent.
    
    This function implements the audit requirement for explicit SMB1 consent.
    Must be called before enabling SMB1 discovery mode.
    
    Args:
        parent: Parent widget for modal behavior
        
    Returns:
        True if user gave explicit consent for SMB1 mode, False otherwise
    """
    dialog = SMB1WarningDialog(parent)
    return dialog.show()


# Test function for development
def test_smb1_warning_dialog():
    """Test the SMB1 warning dialog."""
    root = tk.Tk()
    root.geometry("400x300")
    root.title("Test Parent Window")
    
    def test_dialog():
        result = show_smb1_warning_dialog(root)
        print(f"SMB1 consent result: {result}")
    
    test_button = tk.Button(root, text="Test SMB1 Warning", command=test_dialog)
    test_button.pack(pady=50)
    
    root.mainloop()


if __name__ == "__main__":
    test_smb1_warning_dialog()