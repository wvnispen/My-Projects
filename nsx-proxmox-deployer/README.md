# NSx Proxmox Deployer

Automated deployment scripts for SonicWall NSx virtual firewall appliances on Proxmox VE with custom OVMF firmware support.

## Features

- **Automated VM Creation**: Streamlined deployment of SonicWall NSx virtual firewalls
- **Custom OVMF Firmware**: Support for custom UEFI firmware with SonicWall certificates for Secure Boot
- **Local & Remote Deployment**: Scripts for both local Proxmox hosts and remote API-based deployment
- **Network Configuration**: Automatic network bridge and interface mapping
- **Resource Sizing**: Configurable CPU, memory, and storage allocation

## Requirements

- Proxmox VE 7.x or 8.x
- SonicWall NSx OVA/VMDK image
- Custom OVMF firmware (for Secure Boot functionality)
- Python 3.8+ (for remote deployment scripts)

## Installation

```bash
git clone https://github.com/wvnispen/projects.git
cd projects/nsx-proxmox-deployer
```

## Usage

### Local Deployment

```bash
./deploy-nsx-local.sh --image /path/to/nsx.ova --vmid 100 --name "NSx-Firewall"
```

### Remote Deployment (via API)

```bash
python deploy_nsx_remote.py \
    --host proxmox.local \
    --node pve \
    --vmid 100 \
    --image /path/to/nsx.ova
```

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `--vmid` | Proxmox VM ID | Auto-assign |
| `--name` | VM display name | NSx-Firewall |
| `--memory` | RAM in MB | 4096 |
| `--cores` | CPU cores | 2 |
| `--storage` | Storage target | local-lvm |
| `--bridge` | Network bridge | vmbr0 |

## Custom OVMF Firmware

For SonicWall Secure Boot functionality, you'll need to use the custom OVMF firmware with embedded SonicWall certificates. Place the firmware files in:

```
/usr/share/pve-edk2-firmware/OVMF_CODE_sonicwall.fd
/usr/share/pve-edk2-firmware/OVMF_VARS_sonicwall.fd
```

## Notes

- Ensure sufficient resources on your Proxmox host
- Network bridges must be configured before deployment
- The NSx appliance requires specific licensing from SonicWall

## License

MIT License - See [LICENSE](../LICENSE) for details.
