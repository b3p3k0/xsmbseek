# Human Testing Guide for xsmbseek

This guide provides step-by-step testing instructions for human testers to validate the xsmbseek GUI frontend after restructuring.

## Overview

xsmbseek is now a standalone GUI frontend that integrates with SMBSeek as an external configurable dependency. This guide tests all aspects of the new architecture.

## Prerequisites

- Linux system (Debian-based preferred: Ubuntu, Kali, etc.)
- Python 3.6+
- Git
- Internet connection (for SMBSeek installation)
- Terminal access

## Testing Scenarios

### Scenario 1: Brand New User Journey

This simulates a user cloning xsmbseek from GitHub for the first time.

#### Step 1.1: Initial Setup
```bash
# Simulate fresh clone
git status  # Should show clean working directory
ls -la      # Verify structure: xsmbseek, xsmbseek-config.json, gui/, docs/

# Test basic CLI functionality
./xsmbseek --help     # Should show usage information
./xsmbseek --version  # Should show "xsmbseek 1.0.0"
```

**Expected Results:**
- Help text shows "xsmbseek - GUI Frontend for SMBSeek Security Toolkit"
- Version shows "xsmbseek 1.0.0"
- No errors in output

#### Step 1.2: First Run (No SMBSeek)
```bash
# Run xsmbseek without SMBSeek installed
./xsmbseek
```

**Expected Behavior:**
1. GUI should launch
2. "SMBSeek Setup Required" dialog should appear
3. Dialog should contain:
   - Clear instructions for installing SMBSeek
   - "Open SMBSeek Repository" button
   - Path entry field with Browse button
   - OK/Cancel buttons

**Test Actions:**
- Click "Open SMBSeek Repository" → Should open https://github.com/b3p3k0/smbseek
- Try entering invalid path → Should show validation error
- Click Cancel → Application should exit cleanly

#### Step 1.3: Install SMBSeek
```bash
# Install SMBSeek as external dependency
git clone https://github.com/b3p3k0/smbseek.git
cd smbseek

# Follow SMBSeek installation
pip install -r requirements.txt
cp conf/config.json.example conf/config.json

# Test SMBSeek works
chmod +x smbseek.py
./smbseek.py --help

# Return to xsmbseek directory
cd ../
```

**Expected Results:**
- SMBSeek clones successfully
- Dependencies install without errors
- SMBSeek --help shows proper output
- Directory structure: `xsmbseek/` and `smbseek/` side by side

#### Step 1.4: First Successful Run
```bash
# Run xsmbseek with SMBSeek available
./xsmbseek
```

**Expected Behavior:**
1. GUI launches without setup dialog
2. Main dashboard appears
3. Window title shows "xsmbseek - SMBSeek GUI Frontend (smbseek)"
4. No error dialogs

**Visual Verification:**
- Dashboard loads with default widgets
- Interface is responsive
- No console errors
- Application can be closed cleanly

### Scenario 2: Configuration Management

Test the dual configuration system and path handling.

#### Step 2.1: CLI Path Override
```bash
# Test custom SMBSeek path
./xsmbseek --smbseek-path /nonexistent/path
```

**Expected Behavior:**
- Setup dialog appears asking for valid SMBSeek path
- Shows error about path not found
- Can browse to correct path

#### Step 2.2: Configuration Files
```bash
# Test configuration file handling
./xsmbseek --config test-config.json --smbseek-path ./smbseek
```

**Expected Results:**
- Creates test-config.json if it doesn't exist
- Application runs with custom config
- Configuration persists between runs

#### Step 2.3: Database Path Override
```bash
# Test custom database path
./xsmbseek --database-path ./custom-database.db
```

**Expected Results:**
- Application accepts custom database location
- Database operations work correctly
- No conflicts with SMBSeek's database

### Scenario 3: Mock Mode Testing

Test development mode without SMBSeek dependency.

#### Step 3.1: Mock Mode
```bash
# Test mock mode
./xsmbseek --mock
```

**Expected Behavior:**
1. Application starts immediately (no SMBSeek validation)
2. Window title includes "- Mock Mode"
3. Dashboard shows mock data
4. All GUI functions work without backend calls

#### Step 3.2: Mock Mode Development
```bash
# Test mock mode with config
./xsmbseek --mock --config dev-config.json
```

**Expected Results:**
- Mock mode works with custom configuration
- Development workflow is smooth
- No SMBSeek dependencies required

### Scenario 4: Error Handling & Recovery

Test error scenarios and recovery mechanisms.

#### Step 4.1: Invalid SMBSeek Installation
```bash
# Create fake SMBSeek directory without proper files
mkdir fake-smbseek
./xsmbseek --smbseek-path ./fake-smbseek
```

**Expected Behavior:**
- Validation fails with descriptive error
- Setup dialog offers to fix the problem
- User can browse to correct path

#### Step 4.2: Permission Issues
```bash
# Test permission handling
chmod -x smbseek/smbseek.py
./xsmbseek
```

**Expected Results:**
- Clear error message about permissions
- Helpful suggestions for resolution
- Graceful fallback to setup dialog

**Cleanup:**
```bash
chmod +x smbseek/smbseek.py  # Restore permissions
```

#### Step 4.3: Configuration Corruption
```bash
# Test corrupted configuration file
echo "invalid json content" > xsmbseek-config.json
./xsmbseek
```

**Expected Behavior:**
- Warning about corrupted config
- Falls back to defaults
- Application still functions

**Cleanup:**
```bash
git checkout xsmbseek-config.json  # Restore config
```

### Scenario 5: Cross-Platform Compatibility

#### Step 5.1: Working Directory Independence
```bash
# Test running from different directories
cd /tmp
/path/to/xsmbseek/xsmbseek --smbseek-path /path/to/smbseek
```

**Expected Results:**
- Application works regardless of current directory
- Paths resolve correctly
- No hardcoded path issues

#### Step 5.2: Path Types
```bash
# Test absolute and relative paths
./xsmbseek --smbseek-path /absolute/path/to/smbseek
./xsmbseek --smbseek-path ../relative/path/to/smbseek
./xsmbseek --smbseek-path ~/home/path/to/smbseek
```

**Expected Results:**
- All path types are handled correctly
- Path resolution is consistent
- No path-related errors

### Scenario 6: Integration Testing

Test interaction between xsmbseek and SMBSeek.

#### Step 6.1: SMBSeek Configuration Access
```bash
# Run xsmbseek and access SMBSeek config
./xsmbseek
# In GUI: Navigate to configuration editing
# Should be able to edit smbseek/conf/config.json
```

**Expected Behavior:**
- Can access SMBSeek's configuration through GUI
- Changes are saved to SMBSeek's config file
- No conflicts between configurations

#### Step 6.2: Database Sharing
```bash
# Test database sharing between CLI and GUI
cd smbseek
./smbseek.py db query --summary

# In another terminal
cd ../xsmbseek
./xsmbseek
# GUI should show same data as CLI query
```

**Expected Results:**
- Database data is shared correctly
- No locking conflicts
- GUI reflects CLI operations

## Test Results Documentation

For each test scenario, document:

1. **PASS/FAIL** status
2. **Actual behavior** vs expected
3. **Error messages** (if any) - exact text
4. **Performance observations** (startup time, responsiveness)
5. **UI/UX feedback** (clarity, ease of use)

## Common Issues to Watch For

### High Priority Issues
- Application crashes or hangs
- Data corruption or loss
- Security vulnerabilities
- Path resolution failures

### Medium Priority Issues
- UI responsiveness problems
- Confusing error messages
- Configuration persistence issues
- Cross-platform compatibility problems

### Low Priority Issues
- Minor UI inconsistencies
- Non-critical warning messages
- Performance optimizations
- Feature enhancement suggestions

## Reporting Issues

When reporting issues, include:

1. **Environment Details:**
   - Operating system and version
   - Python version
   - SMBSeek version (if applicable)

2. **Steps to Reproduce:**
   - Exact commands used
   - Configuration files involved
   - Expected vs actual behavior

3. **Error Information:**
   - Complete error messages
   - Console output
   - Log files (if any)

4. **Impact Assessment:**
   - How critical is this issue?
   - Does it block basic functionality?
   - Are there workarounds?

## Testing Completion Checklist

- [ ] All 6 scenarios completed
- [ ] Results documented for each test
- [ ] Any issues reported with details
- [ ] Performance characteristics noted
- [ ] User experience feedback provided
- [ ] Recommendations for improvements

## Next Steps

After completing human testing:

1. **Review Results:** Analyze all test outcomes
2. **Prioritize Issues:** Rank found issues by severity
3. **Plan Fixes:** Create action items for critical issues
4. **Update Documentation:** Reflect any changes needed
5. **Phase 3 Planning:** Prepare for configuration dialog implementation

---

**Note:** This testing focuses on the restructured architecture. GUI functionality testing (Phase 3) will come after the configuration dialog implementation is complete.