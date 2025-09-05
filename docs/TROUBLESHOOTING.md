# xsmbseek Troubleshooting Guide

This guide covers common issues and solutions for the xsmbseek GUI frontend.

## Settings Manager Issues

### "errno 17 file exists" Error

**Symptoms**: Application fails to start with error like:
```
Failed to init settings manager errno 17 file exists /path/to/xsmbseek-config.json
RuntimeError: Failed to initialize settings manager: [Errno 17] File exists
```

**Root Cause**: This error occurred in earlier versions when the settings manager was incorrectly passed a file path instead of a directory path.

**Solution**: 
1. **Update to latest version** - This issue has been fixed in the current version
2. **If issue persists**:
   ```bash
   # Check if ~/.smbseek exists as a file (should be directory)
   ls -la ~/.smbseek
   
   # If it's a file, rename it and restart
   mv ~/.smbseek ~/.smbseek.backup
   ./xsmbseek
   ```

**Technical Details**: The settings manager expects a directory path to store GUI preferences, but was being passed the path to `xsmbseek-config.json` file. The fix ensures settings are stored in `~/.smbseek/gui_settings.json` while app configuration remains in `xsmbseek-config.json`.

---

### Settings Not Persisting

**Symptoms**: Configuration changes don't save between application sessions

**Causes & Solutions**:

1. **Permissions Issue**:
   ```bash
   # Check permissions
   ls -la ~/.smbseek/
   
   # Ensure write access
   chmod 755 ~/.smbseek/
   chmod 644 ~/.smbseek/gui_settings.json
   ```

2. **Corrupted Settings File**:
   ```bash
   # Reset settings (will recreate with defaults)
   rm -rf ~/.smbseek/
   ./xsmbseek  # Will recreate directory
   ```

3. **Disk Space Issue**:
   ```bash
   # Check available disk space
   df -h ~
   
   # Clean up if needed
   du -sh ~/.smbseek/
   ```

---

### Multiple Configuration Systems

**Understanding the Architecture**:

xsmbseek uses two separate configuration systems:

1. **Application Configuration**: `xsmbseek-config.json`
   - **Location**: Same directory as xsmbseek executable
   - **Contains**: SMBSeek installation path, database path
   - **Managed by**: Application configuration dialog (⚙ Config button)
   - **Purpose**: Core application settings and SMBSeek integration

2. **User Preferences**: `~/.smbseek/gui_settings.json` 
   - **Location**: User's home directory (`~/.smbseek/`)
   - **Contains**: GUI themes, window positions, user preferences
   - **Managed by**: Automatically by application
   - **Purpose**: GUI state and user interface preferences

**Why Two Systems?**:
- **Portability**: App config travels with the application
- **User Privacy**: User preferences stay in user directory
- **Modularity**: Each system has focused responsibilities
- **Multi-User**: Different users can have different GUI preferences

---

## Configuration Dialog Issues

### Config Button Shows Placeholder Message

**Symptoms**: Clicking "⚙ Config" shows message about "will be implemented in upcoming phases"

**Cause**: This was a bug where the config button wasn't properly routed to the configuration dialog.

**Solution**: Update to the latest version where this has been fixed. The config button should now open:
- SMBSeek installation path field
- Database path field  
- "SMBSeek Config Editor" button

---

### SMBSeek Config Editor Opens Wrong Path

**Symptoms**: Config editor tries to open `../backend/conf/config.json` instead of the correct SMBSeek config file

**Cause**: Hardcoded references to deprecated `../backend/` directory path.

**Solution**: 
1. **Update to latest version** - Fixed to use dynamic path resolution
2. **Manually verify SMBSeek path** in app configuration dialog
3. **Check that SMBSeek config file exists**: `{smbseek_path}/conf/config.json`

---

## SMBSeek Integration Issues

### SMBSeek Installation Not Found

**Symptoms**: Error about SMBSeek directory or `smbseek.py` not found

**Solutions**:
1. **Install SMBSeek**:
   ```bash
   git clone https://github.com/b3p3k0/smbseek.git
   cd smbseek
   pip install -r requirements.txt
   ```

2. **Configure Path** in xsmbseek:
   - Launch xsmbseek
   - Click "⚙ Config"  
   - Set correct SMBSeek installation path
   - Click "Save"

3. **Verify Installation**:
   ```bash
   cd /path/to/smbseek
   python smbseek.py --version  # Should show version
   ```

---

### Database Issues

**Symptoms**: Database errors, missing database file, or permission issues

**Solutions**:

1. **Database Path Configuration**:
   - Click "⚙ Config" in xsmbseek
   - Verify database path is correct
   - Default: `{smbseek_path}/smbseek.db`

2. **Database Permissions**:
   ```bash
   # Check database file permissions
   ls -la /path/to/smbseek.db
   
   # Fix permissions if needed
   chmod 644 /path/to/smbseek.db
   ```

3. **Create New Database**:
   ```bash
   # If database is corrupted, run a scan to recreate it
   cd /path/to/smbseek
   python smbseek.py discover --country US  # Creates new database
   ```

---

## GUI Issues

### Application Won't Start

**Debug Steps**:
1. **Check Python Version**: `python3 --version` (need 3.6+)
2. **Check Dependencies**: `python3 -c "import tkinter; print('OK')"`
3. **Check File Permissions**: `ls -la ./xsmbseek`
4. **Run with Verbose Output**: `./xsmbseek --mock` (for testing)

**Common Fixes**:
- Install tkinter: `sudo apt install python3-tk` (Linux)
- Make executable: `chmod +x ./xsmbseek`
- Update Python: Ensure Python 3.6+ is installed

---

### Mock Mode Issues

**Usage**: `./xsmbseek --mock`

**Purpose**: Allows testing GUI without SMBSeek installation

**Troubleshooting**:
- Mock mode should start even without SMBSeek installed
- If mock mode fails, check basic Python/tkinter installation
- Mock mode uses simulated data for all operations

---

## Getting Help

### Debug Information to Collect

When reporting issues, please include:

1. **System Information**:
   ```bash
   uname -a  # OS version
   python3 --version  # Python version
   ls -la ./xsmbseek  # Executable permissions
   ```

2. **Configuration Information**:
   ```bash
   cat xsmbseek-config.json  # App config (remove sensitive data)
   ls -la ~/.smbseek/  # Settings directory
   ```

3. **Error Output**:
   ```bash
   ./xsmbseek --mock 2>&1 | tee xsmbseek-error.log
   ```

### Support Channels

- **GitHub Issues**: Report bugs and feature requests
- **Documentation**: Check `docs/USER_GUIDE.md` for usage instructions
- **SMBSeek Issues**: For backend SMBSeek issues, check the SMBSeek repository

---

## Advanced Troubleshooting

### Reset All Configuration

**Complete Reset** (loses all settings):
```bash
# Backup current config
cp xsmbseek-config.json xsmbseek-config.json.backup
cp -r ~/.smbseek ~/.smbseek.backup

# Reset everything
rm xsmbseek-config.json
rm -rf ~/.smbseek

# Restart application (will recreate with defaults)
./xsmbseek
```

### Manual Configuration Editing

**App Configuration** (`xsmbseek-config.json`):
```json
{
  "smbseek": {
    "path": "./smbseek",
    "database_path": null
  },
  "gui": {
    "theme": "default",
    "window_geometry": "800x700",
    "interface_mode": "simple"
  }
}
```

**User Preferences** (`~/.smbseek/gui_settings.json`):
```json
{
  "interface": {
    "mode": "simple",
    "theme": "light",
    "auto_refresh": true
  },
  "backend": {
    "backend_path": "./smbseek",
    "database_path": "./smbseek/smbseek.db"
  }
}
```

---

*Last Updated: September 2024*
*For the latest troubleshooting information, check the project documentation.*