#!/usr/bin/env python3
"""
Proxmox VM Deployment Script with OVMF Firmware Support

This script automates the deployment of Proxmox VMs with custom OVMF firmware files.
It handles VM creation, disk import, and OVMF configuration.
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Optional


class ProxmoxVMDeployer:
    """Handle Proxmox VM deployment with OVMF firmware support."""
    
    def __init__(self):
        self.vm_name: Optional[str] = None
        self.vm_id: Optional[int] = None
        self.storage_name: Optional[str] = None
        self.node_name: Optional[str] = None
        self.qcow2_path: Optional[Path] = None
        self.ovmf_code_path: Optional[Path] = None
        self.ovmf_vars_path: Optional[Path] = None
        self.vm_config: Optional[Dict[str, Any]] = None
        self.is_remote: bool = False
        self.remote_host: Optional[str] = None
        self.remote_user: Optional[str] = None
        self.remote_password: Optional[str] = None
    
    def display_banner(self):
        """Display startup banner."""
        banner = """
******************************************************************************
*                                                                            *
*          SonicWall NSx Deployment Script for Proxmox                      *
*                                                                            *
*          Created by Wynand van Nispen (wvannipen@sonicwall.com)          *
*          Version: 3.0                                                     *
*                                                                            *
******************************************************************************
        """
        print(banner)
    
    def prompt_deployment_type(self):
        """Ask user if deployment is local or remote."""
        print("\n" + "="*60)
        print("Deployment Type Selection")
        print("="*60)
        
        while True:
            choice = input("\nIs this a LOCAL or REMOTE deployment? (local/remote): ").strip().lower()
            
            if choice in ['local', 'l']:
                self.is_remote = False
                print("✓ Local deployment selected")
                break
            elif choice in ['remote', 'r']:
                self.is_remote = True
                print("✓ Remote deployment selected")
                self.prompt_remote_details()
                break
            else:
                print("Invalid choice. Please enter 'local' or 'remote'")
    
    def prompt_remote_details(self):
        """Prompt for remote Proxmox server details."""
        print("\n" + "-"*60)
        print("Remote Proxmox Server Details")
        print("-"*60)
        
        # Get IP address
        while True:
            self.remote_host = input("\nEnter Proxmox server IP address: ").strip()
            if self.remote_host:
                break
            print("IP address cannot be empty!")
        
        # Get username (default to root)
        username_input = input("Enter username [root]: ").strip()
        self.remote_user = username_input if username_input else "root"
        
        # Get password
        import getpass
        while True:
            self.remote_password = getpass.getpass("Enter password: ")
            if self.remote_password:
                break
            print("Password cannot be empty!")
        
        print("\n" + "-"*60)
        print(f"Remote Host: {self.remote_host}")
        print(f"Username: {self.remote_user}")
        print("-"*60)
        
        # Test connection
        if not self.test_remote_connection():
            print("\n❌ Unable to connect to remote server. Exiting.")
            sys.exit(1)
    
    def test_remote_connection(self) -> bool:
        """Test SSH connection to remote Proxmox server."""
        print("\n🔌 Testing connection to remote server...")
        
        # Use sshpass for password authentication
        cmd = [
            'sshpass', '-p', self.remote_password,
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'ConnectTimeout=10',
            f'{self.remote_user}@{self.remote_host}',
            'echo "Connection successful"'
        ]
        
        try:
            result = self.run_command(cmd, capture_output=True, text=True, check=True, timeout=15)
            if "Connection successful" in result.stdout:
                print("✓ Successfully connected to remote server")
                return True
            else:
                print("❌ Connection test failed")
                return False
        except subprocess.TimeoutExpired:
            print("❌ Connection timeout - server not reachable")
            return False
        except subprocess.CalledProcessError as e:
            print(f"❌ Connection failed: {e.stderr}")
            return False
        except FileNotFoundError:
            print("❌ Error: 'sshpass' not found. Please install it:")
            print("   Ubuntu/Debian: sudo apt-get install sshpass")
            print("   RHEL/CentOS: sudo yum install sshpass")
            return False
    
    def upload_files_to_remote(self) -> bool:
        """Upload required files to remote Proxmox server."""
        print("\n📤 Uploading files to remote server...")
        
        remote_tmp_dir = f"/tmp/proxmox_deploy_{self.vm_id}"
        
        # Create remote directory
        cmd_mkdir = [
            'sshpass', '-p', self.remote_password,
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            f'{self.remote_user}@{self.remote_host}',
            f'mkdir -p {remote_tmp_dir}'
        ]
        
        try:
            subprocess.run(cmd_mkdir, capture_output=True, text=True, check=True)
            print(f"✓ Created remote directory: {remote_tmp_dir}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to create remote directory: {e.stderr}")
            return False
        
        # Upload files using scp
        files_to_upload = [
            (self.qcow2_path, f"{remote_tmp_dir}/disk.qcow2"),
            (self.ovmf_code_path, f"{remote_tmp_dir}/OVMF_CODE.sw.fd"),
            (self.ovmf_vars_path, f"{remote_tmp_dir}/OVMF_VARS.sw.fd")
        ]
        
        for local_file, remote_file in files_to_upload:
            print(f"  Uploading {local_file.name}...")
            cmd_scp = [
                'sshpass', '-p', self.remote_password,
                'scp',
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'UserKnownHostsFile=/dev/null',
                str(local_file),
                f'{self.remote_user}@{self.remote_host}:{remote_file}'
            ]
            
            try:
                subprocess.run(cmd_scp, capture_output=True, text=True, check=True)
                print(f"  ✓ Uploaded {local_file.name}")
            except subprocess.CalledProcessError as e:
                print(f"  ❌ Failed to upload {local_file.name}: {e.stderr}")
                return False
        
        print("✓ All files uploaded successfully")
        
        # Update paths to remote locations
        self.qcow2_path = Path(f"{remote_tmp_dir}/disk.qcow2")
        self.ovmf_code_path = Path(f"{remote_tmp_dir}/OVMF_CODE.sw.fd")
        self.ovmf_vars_path = Path(f"{remote_tmp_dir}/OVMF_VARS.sw.fd")
        
        return True
    
    def execute_remote_command(self, command: list, description: str = "") -> subprocess.CompletedProcess:
        """Execute a command on the remote Proxmox server."""
        if description:
            print(f"  Remote: {description}")
        
        # Convert command list to string for remote execution
        cmd_string = ' '.join(str(c) for c in command)
        
        ssh_cmd = [
            'sshpass', '-p', self.remote_password,
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            f'{self.remote_user}@{self.remote_host}',
            cmd_string
        ]
        
        return subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
    
    def cleanup_remote_files(self):
        """Clean up temporary files on remote server."""
        if self.is_remote and self.vm_id:
            print("\n🧹 Cleaning up temporary files on remote server...")
            try:
                cmd = [
                    'sshpass', '-p', self.remote_password,
                    'ssh',
                    '-o', 'StrictHostKeyChecking=no',
                    '-o', 'UserKnownHostsFile=/dev/null',
                    f'{self.remote_user}@{self.remote_host}',
                    f'rm -rf /tmp/proxmox_deploy_{self.vm_id}'
                ]
                self.run_command(cmd, capture_output=True, text=True, check=True)
                print("✓ Temporary files cleaned up")
            except:
                print("⚠️  Warning: Could not clean up temporary files")
    
    def run_command(self, cmd: list, **kwargs) -> subprocess.CompletedProcess:
        """Execute a command locally or remotely based on deployment type."""
        if self.is_remote:
            return self.execute_remote_command(cmd, **kwargs)
        else:
            return self.run_command(cmd, **kwargs)
        
    def get_node_name(self) -> str:
        """Get the Proxmox node name."""
        try:
            result = self.run_command(['hostname'], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Error getting node name: {e}")
            sys.exit(1)
    
    def validate_files(self, qcow2: str, ovmf_code: str, ovmf_vars: str) -> bool:
        """Validate that all required files exist."""
        files = {
            'QCOW2 disk image': qcow2,
            'OVMF_CODE file': ovmf_code,
            'OVMF_VARS file': ovmf_vars
        }
        
        all_valid = True
        for file_type, file_path in files.items():
            if not os.path.exists(file_path):
                print(f"❌ Error: {file_type} not found: {file_path}")
                all_valid = False
            else:
                print(f"✓ Found {file_type}: {file_path}")
        
        return all_valid
    
    def prompt_user_inputs(self):
        """Prompt user for VM configuration parameters."""
        print("\n" + "="*60)
        print("Proxmox VM Deployment - Configuration")
        print("="*60)
        
        # VM Name
        while True:
            self.vm_name = input("\nEnter VM name: ").strip()
            if self.vm_name:
                break
            print("VM name cannot be empty!")
        
        # VM ID
        while True:
            try:
                vm_id_input = input("Enter VM ID (e.g., 100): ").strip()
                self.vm_id = int(vm_id_input)
                if self.vm_id > 0:
                    break
                print("VM ID must be a positive number!")
            except ValueError:
                print("Invalid input! Please enter a numeric VM ID.")
        
        # Storage Name
        while True:
            self.storage_name = input("Enter storage name (e.g., local-lvm): ").strip()
            if self.storage_name:
                break
            print("Storage name cannot be empty!")
        
        print("\n" + "-"*60)
        print("Advanced VM Configuration")
        print("-"*60)
        
        # Memory
        memory = self._get_input_with_default(
            "Enter RAM in MB",
            "4096",
            int
        )
        
        # CPU Cores
        cores = self._get_input_with_default(
            "Enter number of CPU cores",
            "2",
            int
        )
        
        # CPU Sockets
        sockets = self._get_input_with_default(
            "Enter number of CPU sockets",
            "1",
            int
        )
        
        # CPU Type
        cpu_type = self._get_input_with_default(
            "Enter CPU type (host/x86-64-v2-AES/kvm64)",
            "host",
            str
        )
        
        # OS Type
        print("\nOS Types: l26 (Linux 2.6+), win11 (Windows 11), win10 (Windows 10), other")
        ostype = self._get_input_with_default(
            "Enter OS type",
            "l26",
            str
        )
        
        # SCSI Controller
        scsihw = self._get_input_with_default(
            "Enter SCSI controller (virtio-scsi-pci/virtio-scsi-single)",
            "virtio-scsi-pci",
            str
        )
        
        # Network Bridge
        bridge = self._get_input_with_default(
            "Enter network bridge",
            "vmbr0",
            str
        )
        
        # QEMU Guest Agent
        agent_input = self._get_input_with_default(
            "Enable QEMU guest agent? (yes/no)",
            "yes",
            str
        )
        agent = "1" if agent_input.lower() in ['yes', 'y', '1'] else "0"
        
        # Machine Type
        machine = self._get_input_with_default(
            "Enter machine type (q35/pc)",
            "q35",
            str
        )
        
        # NUMA
        numa = self._get_input_with_default(
            "Enable NUMA (0=disabled, 1=enabled)",
            "0",
            str
        )
        
        # Build configuration dictionary
        # Note: efidisk0 will be added separately after VM creation
        self.vm_config = {
            "bios": "seabios",
            "cores": cores,
            "cpu": cpu_type,
            "ide2": "none,media=cdrom",
            "machine": machine,
            "memory": memory,
            "name": self.vm_name,
            "net0": f"virtio,bridge={bridge}",
            "net1": f"virtio,bridge={bridge}",
            "numa": numa,
            "ostype": ostype,
            "scsihw": scsihw,
            "serial0": "socket",
            "sockets": sockets
        }
        
        # Add agent only if enabled
        if agent == "1":
            self.vm_config["agent"] = agent
        
        # Display configuration summary
        print("\n" + "="*60)
        print("Configuration Summary:")
        print("="*60)
        print(f"VM Name:        {self.vm_name}")
        print(f"VM ID:          {self.vm_id}")
        print(f"Storage:        {self.storage_name}")
        print(f"Memory:         {memory} MB")
        print(f"CPU:            {cores} cores, {sockets} socket(s), type: {cpu_type}")
        print(f"OS Type:        {ostype}")
        print(f"SCSI HW:        {scsihw}")
        print(f"Network 0:      {bridge} (virtio)")
        print(f"Network 1:      {bridge} (virtio, no firewall)")
        print(f"Guest Agent:    {'Enabled' if agent == '1' else 'Disabled'}")
        print(f"Machine:        {machine}")
        print(f"NUMA:           {'Enabled' if numa == '1' else 'Disabled'}")
        print(f"BIOS:           SeaBIOS (with custom OVMF firmware)")
        print(f"Serial:         Enabled (socket)")
        print(f"EFI Disk:       Will be created (1M, pre-enrolled-keys)")
        print(f"IDE2:           CD-ROM (none)")
        print("="*60)
        
        # Save configuration to file for reference
        config_file = Path(f'/tmp/vm_{self.vm_id}_config.json')
        with open(config_file, 'w') as f:
            json.dump(self.vm_config, f, indent=2)
        print(f"\n💾 Configuration saved to: {config_file}")
        
        confirm = input("\nProceed with deployment? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("Deployment cancelled.")
            sys.exit(0)
    
    def _get_input_with_default(self, prompt: str, default: str, value_type):
        """Get user input with a default value."""
        user_input = input(f"{prompt} [{default}]: ").strip()
        if not user_input:
            return value_type(default)
        try:
            return value_type(user_input)
        except ValueError:
            print(f"Invalid input, using default: {default}")
            return value_type(default)
    
    def create_vm(self) -> bool:
        """Create the Proxmox VM based on configuration."""
        print("\n📝 Creating Proxmox VM...")
        
        # Build the qm create command
        cmd = ['qm', 'create', str(self.vm_id)]
        
        # Add name
        cmd.extend(['--name', self.vm_name])
        
        # Parse config and add parameters
        for key, value in self.vm_config.items():
            if key in ['args']:  # Skip args as we'll add it manually later
                continue
            
            if isinstance(value, bool):
                value = '1' if value else '0'
            elif isinstance(value, (dict, list)):
                value = json.dumps(value)
            else:
                value = str(value)
            
            cmd.append(f'--{key}')
            cmd.append(value)
        
        try:
            result = self.run_command(cmd, capture_output=True, text=True, check=True)
            print(f"✓ VM {self.vm_id} created successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error creating VM: {e}")
            print(f"STDOUT: {e.stdout}")
            print(f"STDERR: {e.stderr}")
            return False
    
    def add_efidisk(self) -> bool:
        """Add EFI disk to the VM after creation."""
        print(f"\n💾 Adding EFI disk...")
        
        cmd = [
            'qm', 'set',
            str(self.vm_id),
            '--efidisk0',
            f"{self.storage_name}:1,efitype=4m,pre-enrolled-keys=1"
        ]
        
        try:
            result = self.run_command(cmd, capture_output=True, text=True, check=True)
            print(f"✓ EFI disk added (1M, pre-enrolled-keys)")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error adding EFI disk: {e}")
            print(f"STDERR: {e.stderr}")
            return False
    
    def import_disk(self) -> bool:
        """Import the QCOW2 disk image to the VM."""
        print(f"\n💾 Importing disk image to storage '{self.storage_name}'...")
        
        cmd = [
            'qm', 'importdisk',
            str(self.vm_id),
            str(self.qcow2_path),
            self.storage_name
        ]
        
        try:
            result = self.run_command(cmd, capture_output=True, text=True, check=True)
            print("✓ Disk imported successfully")
            output = result.stdout.strip()
            print(f"  Output: {output}")
            
            # Parse output to find the disk name
            # Output format is typically: "Successfully imported disk as 'unused0:storage:vm-XXX-disk-1'"
            # or "Successfully imported disk as 'storage:vm-XXX-disk-1'"
            if 'unused0' in output.lower() or 'unused' in output.lower():
                print("  Note: Disk imported as unused, will be attached in next step")
            
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error importing disk: {e}")
            print(f"STDERR: {e.stderr}")
            return False
    
    def attach_disk_and_set_boot(self) -> bool:
        """Attach the imported disk to virtio0 and configure boot order."""
        print(f"\n🔗 Attaching imported disk to VM and configuring boot...")
        
        # After qm importdisk, the disk is created as "unused0"
        # We need to attach it to virtio0
        cmd_attach = [
            'qm', 'set',
            str(self.vm_id),
            '--virtio0',
            'unused0:0,iothread=1'
        ]
        
        try:
            result = self.run_command(cmd_attach, capture_output=True, text=True, check=True)
            print(f"✓ Imported disk attached to virtio0 with iothread")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error attaching disk: {e}")
            print(f"STDERR: {e.stderr}")
            print(f"\nTrying alternative method...")
            
            # Alternative: specify full disk path
            cmd_attach_alt = [
                'qm', 'set',
                str(self.vm_id),
                '--virtio0',
                f"{self.storage_name}:vm-{self.vm_id}-disk-1,iothread=1"
            ]
            
            try:
                result = self.run_command(cmd_attach_alt, capture_output=True, text=True, check=True)
                print(f"✓ Disk attached using full path")
            except subprocess.CalledProcessError as e2:
                print(f"❌ Alternative method also failed: {e2}")
                print(f"STDERR: {e2.stderr}")
                return False
        
        # Set boot order to virtio0
        cmd_boot = [
            'qm', 'set',
            str(self.vm_id),
            '--boot',
            'order=virtio0'
        ]
        
        try:
            result = self.run_command(cmd_boot, capture_output=True, text=True, check=True)
            print(f"✓ Boot order set to virtio0")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error setting boot order: {e}")
            print(f"STDERR: {e.stderr}")
            return False
    
    def copy_ovmf_files(self) -> bool:
        """Copy OVMF firmware files to /usr/share/pve-edk2-firmware/{vm_id}/."""
        print("\n📋 Copying OVMF firmware files...")
        
        # Create VM-specific directory under pve-edk2-firmware
        ovmf_dir = f'/usr/share/pve-edk2-firmware/{self.vm_id}'
        
        if self.is_remote:
            # Remote: files are already in /tmp, use cp commands via SSH
            try:
                # Create directory
                self.run_command(['mkdir', '-p', ovmf_dir], capture_output=True, text=True, check=True)
                print(f"✓ Created directory: {ovmf_dir}")
                
                # Copy OVMF_CODE
                self.run_command(['cp', str(self.ovmf_code_path), f"{ovmf_dir}/OVMF_CODE.sw.fd"], 
                               capture_output=True, text=True, check=True)
                print(f"✓ Copied OVMF_CODE.sw.fd to {ovmf_dir}")
                
                # Copy OVMF_VARS
                self.run_command(['cp', str(self.ovmf_vars_path), f"{ovmf_dir}/OVMF_VARS.sw.fd"], 
                               capture_output=True, text=True, check=True)
                print(f"✓ Copied OVMF_VARS.sw.fd to {ovmf_dir}")
                
                return True
            except Exception as e:
                print(f"❌ Error copying OVMF files: {e}")
                return False
        else:
            # Local: use Python file operations
            ovmf_dir_path = Path(ovmf_dir)
            try:
                ovmf_dir_path.mkdir(parents=True, exist_ok=True)
                print(f"✓ Created directory: {ovmf_dir}")
            except PermissionError:
                print("❌ Error: Permission denied. Please run this script with sudo.")
                return False
            
            # Copy OVMF_CODE file
            try:
                dest_code = ovmf_dir_path / 'OVMF_CODE.sw.fd'
                shutil.copy2(self.ovmf_code_path, dest_code)
                print(f"✓ Copied {self.ovmf_code_path.name} to {dest_code}")
            except Exception as e:
                print(f"❌ Error copying OVMF_CODE file: {e}")
                return False
            
            # Copy OVMF_VARS file
            try:
                dest_vars = ovmf_dir_path / 'OVMF_VARS.sw.fd'
                shutil.copy2(self.ovmf_vars_path, dest_vars)
                print(f"✓ Copied {self.ovmf_vars_path.name} to {dest_vars}")
            except Exception as e:
                print(f"❌ Error copying OVMF_VARS file: {e}")
                return False
            
            return True
    
    def add_args_to_config(self) -> bool:
        """Add OVMF args line to the VM configuration file."""
        print("\n⚙️  Adding OVMF args to VM configuration...")
        
        config_file_path = f'/etc/pve/nodes/{self.node_name}/qemu-server/{self.vm_id}.conf'
        
        # Use VM ID-specific path matching the working config structure
        args_line = f"args: -drive 'if=pflash,unit=0,format=raw,readonly=on,file=/usr/share/pve-edk2-firmware/{self.vm_id}/OVMF_CODE.sw.fd' -drive 'if=pflash,unit=1,format=raw,file=/usr/share/pve-edk2-firmware/{self.vm_id}/OVMF_VARS.sw.fd'"
        
        if self.is_remote:
            # Remote: use sed command to add args line
            try:
                # Use sed to insert args line at the beginning of the file
                sed_cmd = f"sed -i '1i{args_line}' {config_file_path}"
                self.run_command(['bash', '-c', sed_cmd], capture_output=True, text=True, check=True)
                print(f"✓ Added OVMF args to {config_file_path}")
                print(f"  Path: /usr/share/pve-edk2-firmware/{self.vm_id}/")
                return True
            except Exception as e:
                print(f"❌ Error modifying config file: {e}")
                return False
        else:
            # Local: use Python file operations
            config_file = Path(config_file_path)
            
            if not config_file.exists():
                print(f"❌ Error: Config file not found: {config_file}")
                return False
            
            try:
                # Read existing config
                with open(config_file, 'r') as f:
                    lines = f.readlines()
                
                # Check if args already exists
                has_args = any(line.strip().startswith('args:') for line in lines)
                
                if has_args:
                    print("⚠️  Warning: 'args' line already exists in config. Replacing it...")
                    lines = [line for line in lines if not line.strip().startswith('args:')]
                
                # Add args line at the top
                lines.insert(0, args_line + '\n')
                
                # Write back to file
                with open(config_file, 'w') as f:
                    f.writelines(lines)
                
                print(f"✓ Added OVMF args to {config_file}")
                print(f"  Path: /usr/share/pve-edk2-firmware/{self.vm_id}/")
                return True
                
            except PermissionError:
                print("❌ Error: Permission denied. Please run this script with sudo.")
                return False
            except Exception as e:
                print(f"❌ Error modifying config file: {e}")
                return False
    
    def display_banner(self):
        """Display startup banner."""
        banner = """
******************************************************************************
*                                                                            *
*          SonicWall NSx Deployment Script for Proxmox                      *
*                                                                            *
*          Created by Wynand van Nispen (wvannipen@sonicwall.com)          *
*          Version: 3.0                                                     *
*                                                                            *
******************************************************************************
        """
        print(banner)
    
    def deploy(self, qcow2: str, ovmf_code: str, ovmf_vars: str):
        """Main deployment workflow."""
        # Display banner
        self.display_banner()
        
        # Ask for deployment type (local or remote)
        self.prompt_deployment_type()
        
        print("\n" + "="*60)
        print("Proxmox VM Deployment Script with OVMF Support")
        print("="*60)
        
        # Validate files
        if not self.validate_files(qcow2, ovmf_code, ovmf_vars):
            print("\n❌ File validation failed. Exiting.")
            sys.exit(1)
        
        # Store file paths
        self.qcow2_path = Path(qcow2)
        self.ovmf_code_path = Path(ovmf_code)
        self.ovmf_vars_path = Path(ovmf_vars)
        
        # Get user inputs and build configuration (need VM ID before uploading)
        self.prompt_user_inputs()
        
        # If remote deployment, upload files first
        if self.is_remote:
            if not self.upload_files_to_remote():
                print("\n❌ File upload failed. Exiting.")
                sys.exit(1)
        
        # Get node name
        self.node_name = self.get_node_name()
        print(f"\n✓ Proxmox node: {self.node_name}")
        
        # Check if running as root (only for local deployment)
        if not self.is_remote and os.geteuid() != 0:
            print("\n⚠️  Warning: This script requires root privileges.")
            print("Please run with sudo or as root user.")
            sys.exit(1)
        
        # Deployment steps
        print("\n" + "="*60)
        print("Starting Deployment...")
        print("="*60)
        
        # Step 1: Create VM
        if not self.create_vm():
            print("\n❌ VM creation failed. Aborting deployment.")
            sys.exit(1)
        
        # Step 2: Add EFI disk
        if not self.add_efidisk():
            print("\n❌ EFI disk creation failed. Aborting deployment.")
            sys.exit(1)
        
        # Step 3: Import disk
        if not self.import_disk():
            print("\n❌ Disk import failed. Aborting deployment.")
            sys.exit(1)
        
        # Step 4: Attach disk and set boot order
        if not self.attach_disk_and_set_boot():
            print("\n❌ Disk attachment failed. Aborting deployment.")
            sys.exit(1)
        
        # Step 5: Copy OVMF files
        if not self.copy_ovmf_files():
            print("\n❌ OVMF file copy failed. Aborting deployment.")
            sys.exit(1)
        
        # Step 6: Add args to config
        if not self.add_args_to_config():
            print("\n❌ Config modification failed. Aborting deployment.")
            sys.exit(1)
        
        # Success!
        print("\n" + "="*60)
        print("✅ VM Deployment Completed Successfully!")
        print("="*60)
        print(f"Deployment Type: {'Remote' if self.is_remote else 'Local'}")
        if self.is_remote:
            print(f"Remote Host: {self.remote_host}")
        print(f"VM Name: {self.vm_name}")
        print(f"VM ID: {self.vm_id}")
        print(f"Node: {self.node_name}")
        print(f"Storage: {self.storage_name}")
        print(f"Disk: Attached to virtio0 (with iothread) and configured as boot device")
        print(f"Network: Two adapters on {self.storage_name}")
        print(f"  - net0: Standard virtio adapter")
        print(f"  - net1: Virtio adapter (no firewall)")
        print(f"Serial: Enabled for console access")
        print(f"OVMF: Firmware files in /usr/share/pve-edk2-firmware/{self.vm_id}/")
        print(f"\nConfiguration file saved: /tmp/vm_{self.vm_id}_config.json")
        print("\nYour VM is ready to start:")
        if self.is_remote:
            print(f"  ssh {self.remote_user}@{self.remote_host} 'qm start {self.vm_id}'")
            print(f"\nAccess the serial console:")
            print(f"  ssh {self.remote_user}@{self.remote_host} 'qm terminal {self.vm_id}'")
        else:
            print(f"  qm start {self.vm_id}")
            print(f"\nAccess the serial console:")
            print(f"  qm terminal {self.vm_id}")
        print("="*60)
        
        # Clean up remote files if applicable
        self.cleanup_remote_files()


def main():
    """Main entry point."""
    if len(sys.argv) != 4:
        print("Usage: python3 proxmox_vm_deploy.py <qcow2_file> <ovmf_code_file> <ovmf_vars_file>")
        print("\nExample:")
        print("  sudo python3 proxmox_vm_deploy.py disk.qcow2 OVMF_CODE.sw.fd OVMF_VARS.sw.fd")
        print("\nThe script will prompt you for:")
        print("  - VM name")
        print("  - VM ID (machine ID number)")
        print("  - Storage name")
        print("  - VM configuration parameters (memory, CPU, etc.)")
        sys.exit(1)
    
    qcow2_file = sys.argv[1]
    ovmf_code = sys.argv[2]
    ovmf_vars = sys.argv[3]
    
    deployer = ProxmoxVMDeployer()
    deployer.deploy(qcow2_file, ovmf_code, ovmf_vars)


if __name__ == '__main__':
    main()
