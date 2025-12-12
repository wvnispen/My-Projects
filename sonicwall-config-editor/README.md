# SonicWall Config Editor

A Python application for parsing and editing SonicWall firewall configuration files in `.exp` format.

## Features

- **Configuration Parsing**: Parse complete SonicWall `.exp` configuration files
- **Security Zones**: View and manage security zone configurations
- **Address Objects**: Create, edit, and delete address objects and groups
- **Service Groups**: Manage service definitions and service groups
- **Interfaces**: Configure physical and logical interfaces
- **VLANs**: VLAN configuration and management
- **Export**: Save modified configurations back to `.exp` format

## Requirements

```
Python 3.8+
```

## Installation

```bash
git clone https://github.com/wvnispen/projects.git
cd projects/sonicwall-config-editor
pip install -r requirements.txt
```

## Usage

```bash
python config_editor.py --input firewall_config.exp
```

## Supported Configuration Sections

- Security Zones
- Address Objects & Groups
- Service Objects & Groups
- Interface Configuration
- VLAN Configuration
- NAT Policies
- Access Rules

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This tool is provided as-is for educational and administrative purposes. Always backup your configuration files before making changes. Not officially affiliated with or endorsed by SonicWall.

## License

MIT License - See [LICENSE](../LICENSE) for details.
