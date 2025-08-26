# SMBSeek GUI Error Code Reference

This document provides a comprehensive reference for all error codes used in the SMBSeek GUI application. Error codes enable efficient troubleshooting and user support.

## Error Code Format

Error codes follow the format `[CATEGORY###]` where:
- **CATEGORY**: Two or three letter category prefix
- **###**: Three-digit sequential number within category

## Error Categories

### Database Errors (DB001-DB099)
File access and database connection errors.

| Code | Message | Cause | Resolution |
|------|---------|-------|------------|
| DB001 | Database file not found at {path} | File does not exist | Verify file path and ensure file exists |
| DB002 | Cannot read database file: {path} | Permission denied | Check file permissions and read access |
| DB003 | Cannot write to database file: {path} | Permission denied | Check file permissions and write access |
| DB010 | Database file is corrupted or invalid: {error} | File corruption | Use database backup or re-initialize |
| DB011 | Database connection failed: {error} | Connection issue | Ensure valid SQLite database not in use |
| DB012 | Database locked by another process | File lock | Close other applications using database |

### Validation Errors (VAL001-VAL099)
Schema and data validation errors.

| Code | Message | Cause | Resolution |
|------|---------|-------|------------|
| VAL001 | Database missing required core tables | Incomplete schema | Use complete SMBSeek database |
| VAL002 | Database schema incompatible | Wrong schema version | Import compatible SMBSeek database |
| VAL003 | Invalid table structure in {table}: {error} | Schema mismatch | Verify database from SMBSeek toolkit |
| VAL010 | No data found in database tables | Empty database | Use database with scan results |
| VAL011 | Data integrity check failed: {error} | Data corruption | Try using database backup |

### Import Process Errors (IMP001-IMP099)
Database import and migration errors.

| Code | Message | Cause | Resolution |
|------|---------|-------|------------|
| IMP001 | Database import failed during {stage}: {error} | Import failure | Check file integrity and retry |
| IMP002 | Import cancelled by user | User cancellation | Import stopped - no changes made |
| IMP003 | Import timeout after {duration} seconds | Large database | Import smaller database or increase timeout |

### Configuration Errors (CFG001-CFG099)
Configuration file and backend path errors.

| Code | Message | Cause | Resolution |
|------|---------|-------|------------|
| CFG001 | Configuration file not found: {path} | Missing config | Create configuration file or check path |
| CFG002 | Invalid configuration format: {error} | Syntax error | Check configuration file syntax |
| CFG010 | Backend path not found: {path} | Missing backend | Verify installation or use --backend-path |
| CFG011 | Backend executable not found: {path} | Missing executable | Ensure SMBSeek backend properly installed |

### User Interface Errors (UI001-UI099)
Dialog and component errors.

| Code | Message | Cause | Resolution |
|------|---------|-------|------------|
| UI001 | Failed to create dialog: {error} | UI failure | Restart application or check resources |
| UI002 | Theme loading failed: {error} | Theme issue | Application uses default styling |

### System Errors (SYS001-SYS099)
Threading and system resource errors.

| Code | Message | Cause | Resolution |
|------|---------|-------|------------|
| SYS001 | Background operation failed: {error} | Threading issue | Retry operation or restart application |
| SYS002 | Insufficient system resources: {error} | Low resources | Close other applications or free resources |

## Quick Error Lookup

### Common Database Import Errors

**"Error VAL001" - Missing Core Tables**
- **Cause**: Database doesn't have required `smb_servers` and `scan_sessions` tables
- **Fix**: Use a complete SMBSeek database file from actual scan results

**"Error DB001" - File Not Found**  
- **Cause**: Database file path is incorrect or file doesn't exist
- **Fix**: Verify the file path and ensure the database file exists

**"Error DB011" - Connection Failed**
- **Cause**: File is not a valid SQLite database or is corrupted
- **Fix**: Try a different database file or use a backup

**"Error IMP001" - Import Failed**
- **Cause**: Error during database import process
- **Fix**: Check file integrity and try again

### Backend Configuration Errors

**"Error CFG010" - Backend Path Not Found**
- **Cause**: Cannot find SMBSeek backend at specified path
- **Fix**: Use `--backend-path` argument or verify backend installation

**"Error CFG011" - Backend Executable Not Found**
- **Cause**: SMBSeek backend script is missing or not executable
- **Fix**: Ensure backend is properly installed and accessible

## Reporting Issues

When reporting issues, always include:
1. **Error Code**: The full error code (e.g., "VAL001")  
2. **Error Message**: Complete error message shown
3. **Context**: What you were trying to do when error occurred
4. **Database**: Information about the database file being used

Example:
```
Error: VAL001 - Database missing required core tables. Found: ['scan_sessions']
Context: Trying to import backend/smbseek.db 
Database: File exists, 400KB, modified yesterday
```

This format enables quick diagnosis and resolution of issues.