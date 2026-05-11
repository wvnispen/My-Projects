# Proxmox Automation Scripts

A collection of scripts for Proxmox VE management, including VM deployment, migrations, and API interactions.

## Scripts

### VM Management

| Script | Description |
|--------|-------------|
| `create-vm.sh` | Create VMs with custom configurations |
| `clone-vm.py` | Clone VMs with automatic resource adjustment |
| `migrate-vm.py` | Migrate VMs between nodes or storage |
| `backup-vm.sh` | Automated backup with retention policies |

### API Utilities

| Script | Description |
|--------|-------------|
| `pve-api-client.py` | Python client for Proxmox API operations |
| `get-cluster-status.py` | Cluster health and resource overview |
| `bulk-operations.py` | Batch operations on multiple VMs |

### Migration Tools

| Script | Description |
|--------|-------------|
| `kvm-to-proxmox.sh` | Migrate VMs from KVM to Proxmox |
| `vmware-to-proxmox.py` | VMware to Proxmox migration |
| `custom-uefi-migrate.sh` | Migration with custom UEFI firmware |

## Requirements

- Proxmox VE 7.x or 8.x
- Python 3.8+
- `proxmoxer` Python library
- API token with appropriate permissions

## Installation

```bash
git clone https://github.com/wvnispen/projects.git
cd projects/proxmox-automation
pip install -r requirements.txt
```

## Configuration

Create a configuration file `config.yaml`:

```yaml
proxmox:
  host: "proxmox.local"
  port: 8006
  verify_ssl: false
  
auth:
  # Option 1: API Token (recommended)
  token_name: "automation@pve!automation"
  token_value: "your-token-here"
  
  # Option 2: Username/Password
  # username: "root@pam"
  # password: "your-password"

defaults:
  node: "pve"
  storage: "local-lvm"
  bridge: "vmbr0"
```

## Usage Examples

### Create a VM

```bash
python create-vm.py \
    --name "test-vm" \
    --cores 2 \
    --memory 4096 \
    --disk 32 \
    --iso "local:iso/ubuntu-22.04.iso"
```

### Clone with modifications

```bash
python clone-vm.py \
    --source 100 \
    --target-name "cloned-vm" \
    --memory 8192 \
    --full-clone
```

### Migrate from KVM

```bash
./kvm-to-proxmox.sh \
    --source-host kvm-server \
    --vm-name "legacy-vm" \
    --target-node pve \
    --target-storage local-lvm
```

## API Permissions

For Proxmox 8.x and later, ensure your API token has the required permissions:

```
Datastore.Allocate
Datastore.AllocateSpace
Sys.AccessNetwork  # Required for network operations in 8.x+
Sys.Audit
Sys.Modify
VM.Allocate
VM.Audit
VM.Clone
VM.Config.*
VM.Console
VM.Migrate
VM.Monitor
VM.PowerMgmt
```

## Notes

### Proxmox 8.x API Changes

Starting with Proxmox VE 8.x (specifically after 8.1.1), additional permissions are required:
- `Sys.AccessNetwork` is now required for network-related API calls
- Some endpoints have stricter permission checking

### Custom UEFI Firmware

For VMs requiring custom UEFI firmware (like SonicWall NSx):
1. Place custom firmware in `/usr/share/pve-edk2-firmware/`
2. Use the migration script with `--custom-uefi` flag
3. Update VM config to reference the custom firmware

## Contributing

Contributions welcome! Please submit a Pull Request.

## License

MIT License - See [LICENSE](../LICENSE) for details.
