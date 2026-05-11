# Remote Deployment Feature - v3.0

## 🌐 New in Version 3.0

The SonicWall NSx Deployment Script now supports **remote deployment** to Proxmox hosts over SSH!

## ✨ Key Features

### Updated Banner
```
******************************************************************************
*                                                                            *
*          SonicWall NSx Deployment Script for Proxmox                      *
*                                                                            *
*          Created by Wynand van Nispen (wvannipen@sonicwall.com)          *
*          Version: 3.0                                                     *
*                                                                            *
******************************************************************************
```

### Deployment Modes

1. **Local Deployment**: Run directly on the Proxmox host
2. **Remote Deployment**: Deploy to a remote Proxmox host via SSH

## 🚀 Usage

### Local Deployment

```bash
# Run on Proxmox host directly
sudo python3 proxmox_vm_deploy.py NSx270.qcow2 OVMF_CODE.sw.fd OVMF_VARS.sw.fd

# Select deployment type
Is this a LOCAL or REMOTE deployment? (local/remote): local
✓ Local deployment selected
```

### Remote Deployment

```bash
# Run from your workstation
python3 proxmox_vm_deploy.py NSx270.qcow2 OVMF_CODE.sw.fd OVMF_VARS.sw.fd

# Select deployment type
Is this a LOCAL or REMOTE deployment? (local/remote): remote
✓ Remote deployment selected

# Enter remote Proxmox details
Enter Proxmox server IP address: 192.168.1.100
Enter username [root]: root
Enter password: ********

🔌 Testing connection to remote server...
✓ Successfully connected to remote server

# Files will be uploaded automatically
📤 Uploading files to remote server...
  Uploading NSx270.qcow2...
  ✓ Uploaded NSx270.qcow2
  Uploading OVMF_CODE.sw.fd...
  ✓ Uploaded OVMF_CODE.sw.fd
  Uploading OVMF_VARS.sw.fd...
  ✓ Uploaded OVMF_VARS.sw.fd
✓ All files uploaded successfully
```

## 📋 Requirements

### For Local Deployment
- Root/sudo access on Proxmox host
- Python 3.6+

### For Remote Deployment
- `sshpass` installed on local machine
- SSH access to remote Proxmox host
- Root credentials for remote host
- Network connectivity to Proxmox host

### Installing sshpass

**Ubuntu/Debian:**
```bash
sudo apt-get install sshpass
```

**RHEL/CentOS:**
```bash
sudo yum install sshpass
```

**macOS:**
```bash
brew install sshpass
```

## 🔐 Remote Deployment Workflow

```
1. User selects "remote" deployment
   └── Prompts for IP, username, password

2. Test SSH connection
   └── Verifies credentials and connectivity

3. Prompt for VM configuration
   └── Name, ID, storage, CPU, RAM, etc.

4. Upload files to remote host
   ├── QCOW2 disk image
   ├── OVMF_CODE.sw.fd
   └── OVMF_VARS.sw.fd
   └── Files stored in /tmp/proxmox_deploy_{vm_id}/

5. Execute deployment on remote host
   ├── Create VM
   ├── Add EFI disk
   ├── Import disk
   ├── Attach disk
   ├── Copy OVMF files
   └── Configure args

6. Clean up temporary files
   └── Removes /tmp/proxmox_deploy_{vm_id}/

7. Display success message with remote commands
```

## 🎯 Example Sessions

### Complete Local Deployment
```bash
$ sudo python3 proxmox_vm_deploy.py NSx270.qcow2 OVMF_CODE.sw.fd OVMF_VARS.sw.fd

******************************************************************************
*                                                                            *
*          SonicWall NSx Deployment Script for Proxmox                      *
*                                                                            *
*          Created by Wynand van Nispen (wvannipen@sonicwall.com)          *
*          Version: 3.0                                                     *
*                                                                            *
******************************************************************************

============================================================
Deployment Type Selection
============================================================

Is this a LOCAL or REMOTE deployment? (local/remote): local
✓ Local deployment selected

[Rest of deployment continues as normal...]
```

### Complete Remote Deployment
```bash
$ python3 proxmox_vm_deploy.py NSx270.qcow2 OVMF_CODE.sw.fd OVMF_VARS.sw.fd

******************************************************************************
*                                                                            *
*          SonicWall NSx Deployment Script for Proxmox                      *
*                                                                            *
*          Created by Wynand van Nispen (wvannipen@sonicwall.com)          *
*          Version: 3.0                                                     *
*                                                                            *
******************************************************************************

============================================================
Deployment Type Selection
============================================================

Is this a LOCAL or REMOTE deployment? (local/remote): remote
✓ Remote deployment selected

------------------------------------------------------------
Remote Proxmox Server Details
------------------------------------------------------------

Enter Proxmox server IP address: 192.168.1.100
Enter username [root]: root
Enter password: 
------------------------------------------------------------
Remote Host: 192.168.1.100
Username: root
------------------------------------------------------------

🔌 Testing connection to remote server...
✓ Successfully connected to remote server

[... configuration prompts ...]

📤 Uploading files to remote server...
✓ Created remote directory: /tmp/proxmox_deploy_100
  Uploading NSx270.qcow2...
  ✓ Uploaded NSx270.qcow2
  Uploading OVMF_CODE.sw.fd...
  ✓ Uploaded OVMF_CODE.sw.fd
  Uploading OVMF_VARS.sw.fd...
  ✓ Uploaded OVMF_VARS.sw.fd
✓ All files uploaded successfully

[... deployment continues ...]

============================================================
✅ VM Deployment Completed Successfully!
============================================================
Deployment Type: Remote
Remote Host: 192.168.1.100
VM Name: nsx-fw-01
VM ID: 100
Node: pve
Storage: local-lvm
[... rest of details ...]

Your VM is ready to start:
  ssh root@192.168.1.100 'qm start 100'

Access the serial console:
  ssh root@192.168.1.100 'qm terminal 100'
============================================================

🧹 Cleaning up temporary files on remote server...
✓ Temporary files cleaned up
```

## 🔧 Technical Details

### SSH Connection
- Uses `sshpass` for password authentication
- Disables strict host key checking (for automation)
- 10-second connection timeout
- Automatically tests connection before proceeding

### File Transfer
- Uses `scp` for secure file transfer
- Files uploaded to `/tmp/proxmox_deploy_{vm_id}/`
- Temporary directory automatically cleaned up after deployment
- Large files (QCOW2) transferred efficiently

### Command Execution
- All `qm` commands executed via SSH
- File operations (`cp`, `mkdir`) executed remotely
- Config file modifications use `sed` on remote host
- Error handling for network issues

### Security
- Password not stored in logs
- Uses `getpass` for secure password input
- Connection details displayed but not logged
- Temporary files cleaned up automatically

## ⚙️ Architecture

### Local Mode
```
Script (Local) → Proxmox Commands (Local) → VM Created (Local)
```

### Remote Mode
```
Script (Local) → SSH/SCP → Proxmox Host (Remote) → VM Created (Remote)
                    ↓
              File Upload
```

## 🎛️ Configuration

### run_command() Method
Automatically routes commands based on deployment type:

```python
def run_command(self, cmd: list, **kwargs):
    """Execute locally or remotely."""
    if self.is_remote:
        return self.execute_remote_command(cmd, **kwargs)
    else:
        return subprocess.run(cmd, **kwargs)
```

### Remote File Operations
Special handling for file operations:
- `copy_ovmf_files()`: Uses `cp` command remotely
- `add_args_to_config()`: Uses `sed` command remotely
- All paths automatically adjusted for remote execution

## 🐛 Troubleshooting

### sshpass not found
```
❌ Error: 'sshpass' not found. Please install it:
   Ubuntu/Debian: sudo apt-get install sshpass
   RHEL/CentOS: sudo yum install sshpass
```

**Solution**: Install sshpass on your local machine

### Connection timeout
```
❌ Connection timeout - server not reachable
```

**Solutions**:
- Verify IP address is correct
- Check network connectivity: `ping 192.168.1.100`
- Verify SSH service is running on Proxmox
- Check firewall rules

### Authentication failed
```
❌ Connection failed: Permission denied
```

**Solutions**:
- Verify username (typically `root` for Proxmox)
- Check password is correct
- Ensure root login is enabled in SSH config
- Try SSH manually first: `ssh root@192.168.1.100`

### File upload failed
```
❌ Failed to upload NSx270.qcow2
```

**Solutions**:
- Check available disk space on remote host
- Verify network stability
- Check file permissions on source files
- Try uploading manually with scp first

## 🔒 Security Considerations

### Password Safety
- Password entered via `getpass` (not echoed to screen)
- Not stored in any logs or files
- Only used for SSH authentication
- Cleared from memory after use

### SSH Security
- Consider using SSH keys instead of passwords
- Disable root login after initial setup
- Use firewall rules to limit SSH access
- Monitor SSH logs for unauthorized access

### Network Security
- Use VPN for remote deployment over internet
- Restrict SSH to trusted networks
- Use strong passwords
- Enable fail2ban on Proxmox host

## 📊 Comparison: Local vs Remote

| Feature | Local | Remote |
|---------|-------|--------|
| **Location** | On Proxmox host | From workstation |
| **Requirements** | sudo/root | sshpass, network |
| **File Transfer** | Local copy | SCP upload |
| **Speed** | Fast | Network dependent |
| **Use Case** | Direct access | Remote management |
| **Cleanup** | Immediate | Automatic remote |

## 💡 Use Cases

### Local Deployment
- Running directly on Proxmox console
- No network overhead needed
- Maximum speed
- Troubleshooting on-site

### Remote Deployment
- Deploy from workstation to lab Proxmox
- Manage multiple Proxmox hosts from one location
- Automated deployments in CI/CD pipelines
- Remote site deployments

## 🎓 Best Practices

1. **Test locally first** - Verify deployment works locally before trying remote
2. **Use SSH keys** - More secure than passwords for production
3. **Check connectivity** - Verify network before starting large uploads
4. **Monitor logs** - Watch SSH logs on Proxmox during deployment
5. **Clean credentials** - Don't store passwords in scripts or history

## ✅ Version 3.0 Changes

- ✅ Added deployment type selection (local/remote)
- ✅ Implemented SSH-based remote deployment
- ✅ Automatic file upload via SCP
- ✅ Remote command execution for all VM operations
- ✅ Temporary file cleanup on remote host
- ✅ Updated banner with asterisks
- ✅ Version number updated to 3.0
- ✅ Enhanced success messages for remote mode

## 🚀 Ready to Deploy!

Whether you're deploying locally on a Proxmox host or remotely from your workstation, the script handles it all automatically!

```bash
# Just run the script and choose your deployment type
python3 proxmox_vm_deploy.py NSx270.qcow2 OVMF_CODE.sw.fd OVMF_VARS.sw.fd
```

---

**Version**: 3.0  
**Feature**: Remote Deployment via SSH  
**Status**: ✅ Production Ready
