# xsmbseek - GUI Frontend for SMBSeek Security Toolkit

**A cross-platform graphical interface for the SMBSeek security toolkit**

xsmbseek provides a user-friendly GUI frontend that integrates with the SMBSeek security assessment toolkit as an external configurable dependency.

##  Quick Start

### Prerequisites
- Python 3.6+
- tkinter (usually included with Python)
- SMBSeek toolkit (https://github.com/b3p3k0/smbseek)

### Installation

1. **Clone xsmbseek:**
   ```bash
   git clone https://github.com/b3p3k0/xsmbseek.git
   cd xsmbseek
   ```

2. **Install SMBSeek (required external dependency):**
   ```bash
   # Clone SMBSeek as a sibling directory (recommended)
   cd ..
   git clone https://github.com/b3p3k0/smbseek.git
   cd smbseek
   pip install -r requirements.txt
   cp conf/config.json.example conf/config.json
   # Edit conf/config.json and add your Shodan API key
   cd ../xsmbseek
   ```

3. **Run xsmbseek:**
   ```bash
   ./xsmbseek
   ```

   **Note:** If SMBSeek is installed elsewhere, specify the path:
   ```bash
   ./xsmbseek --smbseek-path /path/to/smbseek
   ```

### First Run
xsmbseek will automatically detect SMBSeek in common locations:
1. `./smbseek` (current directory)
2. `../smbseek` (sibling directory - recommended)
3. System PATH

If SMBSeek is not found automatically, xsmbseek will show a setup dialog to help you configure the correct path.

##  Usage

### Basic Commands
```bash
# Launch GUI (shows setup dialog if SMBSeek not found)
./xsmbseek

# Specify custom SMBSeek installation path
./xsmbseek --smbseek-path /path/to/smbseek

# Use custom configuration file
./xsmbseek --config my-config.json

# Development mode with mock data (no SMBSeek required)
./xsmbseek --mock

# Custom database location
./xsmbseek --database-path /path/to/database.db
```

### Configuration Management
xsmbseek uses a dual configuration system:
- **xsmbseek-config.json**: GUI settings, SMBSeek path, database path
- **SMBSeek configuration**: Handled by SMBSeek itself (`smbseek/conf/config.json`)

##  Architecture

### Project Structure
```
xsmbseek/                      # xsmbseek GUI frontend
├── xsmbseek                   # Executable GUI frontend
├── xsmbseek-config.json       # GUI configuration
├── gui/                       # GUI components
│   ├── components/            # Widgets and windows
│   └── utils/                 # GUI utilities
└── docs/                      # Documentation

../smbseek/                    # SMBSeek toolkit (external dependency)
├── smbseek.py                 # SMBSeek main executable
├── conf/                      # SMBSeek configuration
├── shared/                    # SMBSeek core modules
└── tools/                     # SMBSeek legacy tools
```

### Key Features
- **External Dependency Integration**: Treats SMBSeek as configurable external tool
- **Path Flexibility**: User-configurable SMBSeek installation location
- **Dual Configuration**: Separate settings for GUI and security tools
- **Mock Mode**: Development mode without SMBSeek dependency
- **Cross-Platform**: Works on Linux, macOS, and Windows

##  Development

### Testing
```bash
# Run basic functionality tests
python3 simple_test.py

# Test all CLI arguments
./xsmbseek --help
./xsmbseek --version

# Test mock mode (no SMBSeek required)
./xsmbseek --mock
```

### Development Mode
```bash
# Mock mode for GUI development
./xsmbseek --mock --config dev-config.json

# Test with different SMBSeek paths
./xsmbseek --smbseek-path /opt/smbseek --mock
```

##  Human Testing

See [`docs/HUMAN_TESTING_GUIDE.md`](docs/HUMAN_TESTING_GUIDE.md) for comprehensive testing instructions including:
- Brand new user journey
- Configuration management testing
- Error handling and recovery
- Integration testing with SMBSeek

##  Documentation

- **CLAUDE.md**: Development guidance for AI assistants
- **docs/HUMAN_TESTING_GUIDE.md**: Step-by-step testing instructions
- **SMBSeek Documentation**: See the SMBSeek repository for security tool documentation

##  Security

xsmbseek is a frontend for security assessment tools. It maintains the same ethical and security principles as SMBSeek:

- **Defensive Purpose Only**: For authorized security assessment
- **No Offensive Capabilities**: Read-only operations only
- **Rate Limiting**: Prevents aggressive scanning behavior
- **Audit Logging**: Comprehensive operation tracking

##  Contributing

1. Fork the repository
2. Create a feature branch
3. Test thoroughly using the human testing guide
4. Submit a pull request

##  License

This project follows the same license terms as specified in the LICENSE file.

##  Disclaimer

This tool is provided for educational and defensive security purposes only. Users are responsible for ensuring their use complies with all applicable laws and regulations.

---

For SMBSeek (the underlying security toolkit), visit: https://github.com/b3p3k0/smbseek