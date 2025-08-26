"""
SMBSeek GUI - Settings Manager

Global settings management for SMBSeek GUI including user preferences,
interface modes, and persistent configuration storage.

Design Decision: Centralized settings management allows consistent behavior
across all application components and provides user preference persistence.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime


class SettingsManager:
    """
    Global settings manager for SMBSeek GUI.
    
    Handles user preferences, interface modes, window positions,
    and other persistent application settings.
    """
    
    def __init__(self, settings_dir: Optional[str] = None):
        """
        Initialize settings manager.
        
        Args:
            settings_dir: Directory to store settings files (default: ~/.smbseek)
        """
        # Default settings directory
        if settings_dir is None:
            home_dir = Path.home()
            self.settings_dir = home_dir / '.smbseek'
        else:
            self.settings_dir = Path(settings_dir)
        
        self.settings_file = self.settings_dir / 'gui_settings.json'
        
        # Ensure settings directory exists
        self.settings_dir.mkdir(exist_ok=True)
        
        # Default settings
        self.default_settings = {
            'interface': {
                'mode': 'simple',  # 'simple' or 'advanced'
                'theme': 'light',  # 'light' or 'dark' (future)
                'auto_refresh': True,
                'confirm_exits': True
            },
            'windows': {
                'main_window': {
                    'geometry': '800x700',
                    'position': 'center'
                },
                'server_list': {
                    'mode': 'simple',
                    'last_filters': {},
                    'column_widths': {}
                },
                'vulnerability_report': {
                    'mode': 'simple',
                    'last_filters': {},
                    'column_widths': {}
                },
                'config_editor': {
                    'mode': 'simple',
                    'last_section': 'scanning'
                }
            },
            'data': {
                'last_export_location': '',
                'last_import_location': '',
                'export_format_preference': 'csv',
                'import_mode_preference': 'merge'
            },
            'backend': {
                'mock_mode': False,
                'backend_path': '../backend',
                'config_path': '../backend/conf/config.json',
                'database_path': '../backend/smbseek.db',
                'last_database_path': '',
                'database_validated': False
            },
            'metadata': {
                'version': '1.0.0',
                'created': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat()
            }
        }
        
        # Current settings (loaded from file or defaults)
        self.settings = {}
        self._change_callbacks = []
        
        # Load settings from file
        self.load_settings()
    
    def load_settings(self) -> None:
        """Load settings from file or create defaults."""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    file_settings = json.load(f)
                
                # Merge with defaults (in case new settings were added)
                self.settings = self._merge_settings(self.default_settings, file_settings)
                
                # Update last_updated timestamp
                self.settings['metadata']['last_updated'] = datetime.now().isoformat()
                
            else:
                # Use defaults and save them
                self.settings = self.default_settings.copy()
                self.save_settings()
                
        except Exception as e:
            print(f"Warning: Failed to load settings: {e}")
            print("Using default settings")
            self.settings = self.default_settings.copy()
    
    def save_settings(self) -> bool:
        """
        Save current settings to file.
        
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            self.settings['metadata']['last_updated'] = datetime.now().isoformat()
            
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error: Failed to save settings: {e}")
            return False
    
    def get_setting(self, key_path: str, default: Any = None) -> Any:
        """
        Get setting value by dot-separated key path.
        
        Args:
            key_path: Dot-separated path like 'interface.mode' or 'windows.main_window.geometry'
            default: Default value if key not found
            
        Returns:
            Setting value or default
        """
        keys = key_path.split('.')
        current = self.settings
        
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default
    
    def set_setting(self, key_path: str, value: Any, save_immediately: bool = True) -> bool:
        """
        Set setting value by dot-separated key path.
        
        Args:
            key_path: Dot-separated path like 'interface.mode'
            value: Value to set
            save_immediately: Whether to save to file immediately
            
        Returns:
            True if set successfully, False otherwise
        """
        keys = key_path.split('.')
        current = self.settings
        
        try:
            # Navigate to parent of target key
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            
            # Set the final key
            old_value = current.get(keys[-1])
            current[keys[-1]] = value
            
            # Notify callbacks if value changed
            if old_value != value:
                self._notify_change_callbacks(key_path, old_value, value)
            
            # Save if requested
            if save_immediately:
                return self.save_settings()
            
            return True
            
        except Exception as e:
            print(f"Error: Failed to set setting {key_path}: {e}")
            return False
    
    def _merge_settings(self, defaults: Dict[str, Any], user_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge user settings with defaults, preserving structure.
        
        Args:
            defaults: Default settings structure
            user_settings: User settings to merge
            
        Returns:
            Merged settings dictionary
        """
        result = defaults.copy()
        
        for key, value in user_settings.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_settings(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def get_interface_mode(self) -> str:
        """Get current interface mode (simple/advanced)."""
        return self.get_setting('interface.mode', 'simple')
    
    def set_interface_mode(self, mode: str) -> bool:
        """
        Set interface mode globally.
        
        Args:
            mode: 'simple' or 'advanced'
            
        Returns:
            True if set successfully
        """
        if mode not in ['simple', 'advanced']:
            raise ValueError("Mode must be 'simple' or 'advanced'")
        
        return self.set_setting('interface.mode', mode)
    
    def toggle_interface_mode(self) -> str:
        """
        Toggle between simple and advanced modes.
        
        Returns:
            New mode after toggle
        """
        current_mode = self.get_interface_mode()
        new_mode = 'advanced' if current_mode == 'simple' else 'simple'
        self.set_interface_mode(new_mode)
        return new_mode
    
    def get_window_setting(self, window_name: str, setting_name: str, default: Any = None) -> Any:
        """
        Get window-specific setting.
        
        Args:
            window_name: Name of the window
            setting_name: Name of the setting
            default: Default value if not found
            
        Returns:
            Setting value or default
        """
        return self.get_setting(f'windows.{window_name}.{setting_name}', default)
    
    def set_window_setting(self, window_name: str, setting_name: str, value: Any) -> bool:
        """
        Set window-specific setting.
        
        Args:
            window_name: Name of the window
            setting_name: Name of the setting
            value: Value to set
            
        Returns:
            True if set successfully
        """
        return self.set_setting(f'windows.{window_name}.{setting_name}', value)
    
    def get_window_mode(self, window_name: str) -> str:
        """
        Get mode for specific window.
        
        Args:
            window_name: Name of the window
            
        Returns:
            Window mode ('simple' or 'advanced'), defaults to global mode
        """
        # Try window-specific mode first, then fall back to global mode
        window_mode = self.get_window_setting(window_name, 'mode')
        if window_mode:
            return window_mode
        else:
            return self.get_interface_mode()
    
    def set_window_mode(self, window_name: str, mode: str) -> bool:
        """
        Set mode for specific window.
        
        Args:
            window_name: Name of the window
            mode: 'simple' or 'advanced'
            
        Returns:
            True if set successfully
        """
        if mode not in ['simple', 'advanced']:
            raise ValueError("Mode must be 'simple' or 'advanced'")
        
        return self.set_window_setting(window_name, 'mode', mode)
    
    def reset_to_defaults(self, section: Optional[str] = None) -> bool:
        """
        Reset settings to defaults.
        
        Args:
            section: Optional section to reset (e.g., 'interface', 'windows')
                    If None, resets all settings
            
        Returns:
            True if reset successfully
        """
        try:
            if section:
                if section in self.default_settings:
                    self.settings[section] = self.default_settings[section].copy()
                else:
                    return False
            else:
                self.settings = self.default_settings.copy()
            
            return self.save_settings()
            
        except Exception as e:
            print(f"Error: Failed to reset settings: {e}")
            return False
    
    def export_settings(self, export_path: str) -> bool:
        """
        Export settings to file.
        
        Args:
            export_path: Path to export settings to
            
        Returns:
            True if exported successfully
        """
        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
            return True
            
        except Exception as e:
            print(f"Error: Failed to export settings: {e}")
            return False
    
    def import_settings(self, import_path: str, merge: bool = True) -> bool:
        """
        Import settings from file.
        
        Args:
            import_path: Path to import settings from
            merge: Whether to merge with current settings or replace entirely
            
        Returns:
            True if imported successfully
        """
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                imported_settings = json.load(f)
            
            if merge:
                self.settings = self._merge_settings(self.settings, imported_settings)
            else:
                # Validate imported settings have required structure
                if 'metadata' not in imported_settings:
                    imported_settings['metadata'] = self.default_settings['metadata'].copy()
                
                self.settings = imported_settings
            
            return self.save_settings()
            
        except Exception as e:
            print(f"Error: Failed to import settings: {e}")
            return False
    
    def register_change_callback(self, callback: Callable[[str, Any, Any], None]) -> None:
        """
        Register callback for setting changes.
        
        Args:
            callback: Function to call when settings change (key_path, old_value, new_value)
        """
        if callback not in self._change_callbacks:
            self._change_callbacks.append(callback)
    
    def unregister_change_callback(self, callback: Callable[[str, Any, Any], None]) -> None:
        """
        Unregister setting change callback.
        
        Args:
            callback: Callback function to remove
        """
        if callback in self._change_callbacks:
            self._change_callbacks.remove(callback)
    
    def get_database_path(self) -> str:
        """
        Get the database path to use for the current session.
        
        Returns:
            Database path (last used if available, otherwise default)
        """
        last_db = self.get_setting('backend.last_database_path', '')
        if last_db and os.path.exists(last_db):
            return last_db
        else:
            return self.get_setting('backend.database_path', '../backend/smbseek.db')
    
    def set_database_path(self, db_path: str, validate: bool = True) -> bool:
        """
        Set the current database path and optionally validate it.
        
        Args:
            db_path: Path to database file
            validate: Whether to validate the database file exists
            
        Returns:
            True if set successfully (and validated if requested)
        """
        if validate and not os.path.exists(db_path):
            return False
        
        # Set both current and last database paths
        success1 = self.set_setting('backend.database_path', db_path)
        success2 = self.set_setting('backend.last_database_path', db_path)
        success3 = self.set_setting('backend.database_validated', validate)
        
        return success1 and success2 and success3
    
    def is_database_validated(self) -> bool:
        """
        Check if current database path has been validated.
        
        Returns:
            True if database was validated
        """
        return self.get_setting('backend.database_validated', False)
    
    def clear_database_validation(self) -> None:
        """Clear database validation flag (used when database becomes invalid)."""
        self.set_setting('backend.database_validated', False)
    
    def get_backend_path(self) -> str:
        """
        Get the backend path to use for backend integration.
        
        Returns:
            Backend path (default: '../backend')
        """
        return self.get_setting('backend.backend_path', '../backend')
    
    def set_backend_path(self, backend_path: str, validate: bool = True) -> bool:
        """
        Set the backend path for backend integration.
        
        Args:
            backend_path: Path to backend directory
            validate: Whether to validate the backend path exists
            
        Returns:
            True if set successfully (and validated if requested)
        """
        if validate and not os.path.exists(backend_path):
            return False
        
        return self.set_setting('backend.backend_path', backend_path)
    
    def _notify_change_callbacks(self, key_path: str, old_value: Any, new_value: Any) -> None:
        """
        Notify registered callbacks of setting changes.
        
        Args:
            key_path: Path of changed setting
            old_value: Previous value
            new_value: New value
        """
        for callback in self._change_callbacks:
            try:
                callback(key_path, old_value, new_value)
            except Exception as e:
                print(f"Warning: Settings callback error: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get settings statistics and metadata.
        
        Returns:
            Dictionary with settings statistics
        """
        def count_settings(obj, depth=0):
            if isinstance(obj, dict):
                count = 0
                for value in obj.values():
                    count += count_settings(value, depth + 1)
                return count
            else:
                return 1
        
        return {
            'total_settings': count_settings(self.settings),
            'settings_file': str(self.settings_file),
            'settings_dir': str(self.settings_dir),
            'file_exists': self.settings_file.exists(),
            'file_size': self.settings_file.stat().st_size if self.settings_file.exists() else 0,
            'created': self.get_setting('metadata.created'),
            'last_updated': self.get_setting('metadata.last_updated'),
            'version': self.get_setting('metadata.version')
        }


# Global settings manager instance
_settings_manager = None


def get_settings_manager(settings_dir: Optional[str] = None) -> SettingsManager:
    """
    Get the global settings manager instance.
    
    Args:
        settings_dir: Directory for settings (only used on first call)
        
    Returns:
        SettingsManager instance
    """
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager(settings_dir)
    return _settings_manager