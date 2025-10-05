# SMBSeek Migration Checklist

## Pre-Migration Assessment ✓

### Current Environment Status
- **Python Version**: 3.13.3 (venv activated) ✓
- **Dependencies Installed**: shodan 1.31.0, smbprotocol 1.15.0, pyspnego 0.11.2 ✓
- **smbclient Available**: Version 4.21.4-Ubuntu ✓
- **Config File**: config.json with valid Shodan API key ✓
- **Exclusion List**: exclusion_list.txt present ✓
- **Data Files**: Recent scan results available ✓

## Migration Steps

### 1. Backup Current Installation
```bash
# Create backup directory
mkdir -p ~/smbseek_backup_$(date +%Y%m%d)

# Backup entire installation
cp -r /home/kevin/git/smbseek ~/smbseek_backup_$(date +%Y%m%d)/

# Backup just essential files
tar -czf ~/smbseek_essential_$(date +%Y%m%d).tar.gz \
    config.json exclusion_list.txt \
    *.csv *.json \
    smbscan.py failure_analyzer.py smb_peep.py
```

### 2. New Environment Setup

#### Python Environment
```bash
# Create new virtual environment
python3 -m venv smbseek_env
source smbseek_env/bin/activate

# Install dependencies
pip install shodan smbprotocol pyspnego
```

#### System Dependencies
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install smbclient

# CentOS/RHEL/Fedora
sudo dnf install samba-client

# macOS
brew install samba
```

### 3. Transfer Configuration

#### Core Files to Transfer
- `config.json` - Shodan API key and settings
- `exclusion_list.txt` - Organization exclusion rules
- `smbscan.py` - Main scanner tool
- `failure_analyzer.py` - Failure analysis tool  
- `smb_peep.py` - Share access verification tool
- `README.md` - Documentation

#### Data Files (Optional)
- `ip_record.csv` - Successful connection results
- `failed_record.csv` - Failed connection logs
- `failure_analysis_*.json` - Analysis reports
- `smb_peep_*.json` - Share access test results

### 4. Configuration Validation

#### Test Configuration
```bash
# Verify Python dependencies
python3 -c "import shodan, smbprotocol, spnego; print('Dependencies OK')"

# Test smbclient
smbclient --version

# Validate config.json format
python3 -c "import json; json.load(open('config.json')); print('Config valid')"
```

#### Test Shodan API
```bash
# Quick API test (replace with actual key)
python3 -c "
import shodan
api = shodan.Shodan('YOUR_API_KEY')
try:
    info = api.info()
    print(f'API working. Credits: {info.get(\"query_credits\", \"unknown\")}')
except Exception as e:
    print(f'API error: {e}')
"
```

### 5. Functionality Testing

#### Basic Scanner Test
```bash
# Test with limited scope
python3 smbscan.py -c US -q --help

# Small test scan (if permitted)
python3 smbscan.py -c US -n -o migration_test.csv
```

#### Tool Integration Test
```bash
# Test failure analyzer (if you have failed_record.csv)
python3 failure_analyzer.py failed_record.csv

# Test share peeper (if you have ip_record.csv)
python3 smb_peep.py ip_record.csv
```

### 6. Migration Verification

#### Environment Check
- [ ] Python 3.6+ installed and working
- [ ] Virtual environment activated  
- [ ] All Python dependencies installed
- [ ] smbclient available and working
- [ ] Config file with valid API key
- [ ] Exclusion list loaded
- [ ] All three tools (smbscan.py, failure_analyzer.py, smb_peep.py) present

#### Functionality Check
- [ ] Shodan API connection successful
- [ ] SMBScan help command works
- [ ] Config.json loads without errors
- [ ] Sample scan completes (if testing permitted)
- [ ] CSV output format correct
- [ ] Failure analyzer processes existing data
- [ ] Share peeper validates existing results

## Security Considerations

### API Key Protection
- [ ] Shodan API key not exposed in version control
- [ ] Config.json has proper file permissions (600)
- [ ] Backup files stored securely

### Network Safety
- [ ] Understand target network ownership
- [ ] Rate limiting configured appropriately
- [ ] Exclusion lists updated for your environment
- [ ] Testing performed only on authorized networks

## Troubleshooting

### Common Issues
1. **Python dependency conflicts**: Use clean virtual environment
2. **smbclient missing**: Install samba-client package
3. **API key errors**: Verify key format and credits
4. **Permission errors**: Check file permissions and ownership
5. **CSV format issues**: Ensure headers match expected format

### Quick Fixes
```bash
# Reset virtual environment
rm -rf venv && python3 -m venv venv && source venv/bin/activate
pip install shodan smbprotocol pyspnego

# Fix file permissions
chmod 600 config.json
chmod +x *.py

# Test minimal functionality
python3 -c "import json; print(json.load(open('config.json'))['shodan']['api_key'][:10] + '...')"
```

## Migration Complete

### Final Validation
- [ ] All tools executable and functional
- [ ] Configuration loaded successfully
- [ ] Sample operations complete without errors
- [ ] Data files accessible and parseable
- [ ] Documentation accessible

### Next Steps
1. Update any automation scripts with new paths
2. Schedule regular backup of scan results
3. Review and update exclusion lists for new environment
4. Test full workflow: scan → analyze → verify
5. Document any environment-specific configurations

---

**Migration Date**: $(date)  
**Source Environment**: /home/kevin/git/smbseek  
**Target Environment**: [To be filled during migration]  
**Validated By**: [To be filled during migration]