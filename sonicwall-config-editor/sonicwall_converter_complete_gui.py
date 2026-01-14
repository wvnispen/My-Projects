#!/usr/bin/env python3
"""
SonicWall Configuration Converter - Complete Advanced GUI
Version 4.0 - Fixed field mappings for SonicOS 8.x .exp files

Full-featured interface for viewing and editing SonicWall configurations
Includes: Zones, Address Objects, Address Groups, Service Objects, Service Groups

Key fixes in v4.0:
- Address Objects: Fixed field mappings (addrObjIp1_, addrObjIp2_ instead of IpBegin/IpEnd/Mask)
- Service Objects: Fixed field mappings (svcObjIpType_, svcObjPort1_, svcObjPort2_)
- Display names now properly shown throughout the interface
- Type descriptions shown instead of raw type numbers
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import base64
import urllib.parse
import json
from pathlib import Path
from collections import defaultdict
import re


class ConfigEditor:
    """Base class for configuration editors."""
    
    def __init__(self, parent, title, config_data):
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.geometry("1000x650")
        self.config_data = config_data
        self.modified = False
        
    def mark_modified(self):
        """Mark the configuration as modified."""
        self.modified = True
        if "- Modified" not in self.window.title():
            self.window.title(self.window.title() + " - Modified")


class ZoneEditor(ConfigEditor):
    """Editor for security zones."""
    
    ZONE_TYPES = {
        '0': 'Untrusted (WAN)',
        '1': 'Trusted (LAN)',
        '2': 'Public (DMZ)',
        '4': 'Wireless (WLAN)',
        '5': 'Encrypted (VPN)',
        '6': 'Multicast',
        '8': 'SSL VPN',
        '9': 'Management'
    }
    
    def __init__(self, parent, config):
        super().__init__(parent, "Security Zones Editor", config)
        self.zones = self.extract_zones()
        self.create_widgets()
        self.load_zones()
    
    def extract_zones(self):
        """Extract zones from config."""
        zones = {}
        indices = set()
        
        for key in self.config_data.keys():
            if key.startswith('zoneObjId_'):
                idx = key.split('_')[1]
                indices.add(idx)
        
        for idx in sorted(indices, key=lambda x: int(x) if x.isdigit() else 0):
            zone = {
                'index': idx,
                'id': self.config_data.get(f'zoneObjId_{idx}', ''),
                'type': self.config_data.get(f'zoneObjZoneType_{idx}', ''),
                'security_level': self.config_data.get(f'zoneObjSecLevel_{idx}', ''),
            }
            if zone['id']:
                zones[idx] = zone
        
        return zones
    
    def create_widgets(self):
        """Create editor widgets."""
        # Toolbar
        toolbar = ttk.Frame(self.window)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Add New", command=self.add_zone).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Edit Selected", command=self.edit_zone).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Delete Selected", command=self.delete_zone).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Save Changes", command=self.save_changes).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Close", command=self.window.destroy).pack(side=tk.RIGHT, padx=2)
        
        # Info
        info_frame = ttk.Frame(self.window, padding="5")
        info_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(info_frame, text="⚠️ Warning: Deleting zones may affect firewall rules and policies!", 
                 foreground="red").pack()
        
        # Treeview
        tree_frame = ttk.Frame(self.window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('Name', 'Type', 'Security Level')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings',
                                  yscrollcommand=vsb.set)
        
        vsb.config(command=self.tree.yview)
        
        self.tree.heading('#0', text='Index')
        self.tree.heading('Name', text='Zone Name')
        self.tree.heading('Type', text='Zone Type')
        self.tree.heading('Security Level', text='Security Level')
        
        self.tree.column('#0', width=60)
        self.tree.column('Name', width=150)
        self.tree.column('Type', width=200)
        self.tree.column('Security Level', width=120)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind('<Double-1>', lambda e: self.edit_zone())
    
    def load_zones(self):
        """Load zones into treeview."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for idx, zone in sorted(self.zones.items()):
            zone_type_desc = self.ZONE_TYPES.get(zone['type'], f"Type {zone['type']}")
            self.tree.insert('', 'end', text=idx,
                           values=(zone['id'], zone_type_desc, zone['security_level']))
    
    def add_zone(self):
        """Add a new zone."""
        dialog = ZoneDialog(self.window, "Add Security Zone", None)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            max_idx = max([int(k) for k in self.zones.keys() if k.isdigit()] + [0])
            new_idx = str(max_idx + 1)
            
            self.zones[new_idx] = {
                'index': new_idx,
                'id': dialog.result['name'],
                'type': dialog.result['type'],
                'security_level': dialog.result['security_level'],
            }
            
            self.load_zones()
            self.mark_modified()
    
    def edit_zone(self):
        """Edit selected zone."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a zone to edit")
            return
        
        idx = self.tree.item(selection[0])['text']
        zone = self.zones[idx]
        
        dialog = ZoneDialog(self.window, "Edit Security Zone", zone)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            self.zones[idx].update({
                'id': dialog.result['name'],
                'type': dialog.result['type'],
                'security_level': dialog.result['security_level'],
            })
            
            self.load_zones()
            self.mark_modified()
    
    def delete_zone(self):
        """Delete selected zone."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a zone to delete")
            return
        
        idx = self.tree.item(selection[0])['text']
        zone = self.zones[idx]
        
        # Check if zone is used in address objects
        used_in_addresses = [k for k, v in self.config_data.items() 
                            if k.startswith('addrObjZone_') and v == zone['id']]
        
        if used_in_addresses:
            count = len(used_in_addresses)
            if not messagebox.askyesno("Zone In Use", 
                f"Warning: Zone '{zone['id']}' is used by {count} address object(s).\n\n" +
                "Deleting this zone may cause issues with firewall rules.\n\n" +
                "Are you sure you want to delete it?"):
                return
        
        if messagebox.askyesno("Confirm Delete", 
                              f"Delete zone '{zone['id']}'?\n\nThis cannot be undone."):
            del self.zones[idx]
            self.load_zones()
            self.mark_modified()
    
    def save_changes(self):
        """Save changes back to config."""
        for idx, zone in self.zones.items():
            self.config_data[f'zoneObjId_{idx}'] = zone['id']
            self.config_data[f'zoneObjZoneType_{idx}'] = zone['type']
            if zone.get('security_level'):
                self.config_data[f'zoneObjSecLevel_{idx}'] = zone['security_level']
        
        messagebox.showinfo("Success", "Security zones saved successfully!")
        self.modified = False
        self.window.title(self.window.title().replace(" - Modified", ""))


class ZoneDialog:
    """Dialog for adding/editing zones."""
    
    def __init__(self, parent, title, zone_data):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("450x250")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.result = None
        self.zone_data = zone_data or {}
        
        self.create_widgets()
        
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def create_widgets(self):
        """Create dialog widgets."""
        form_frame = ttk.Frame(self.dialog, padding="10")
        form_frame.pack(fill=tk.BOTH, expand=True)
        
        # Name
        ttk.Label(form_frame, text="Zone Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_var = tk.StringVar(value=self.zone_data.get('id', ''))
        ttk.Entry(form_frame, textvariable=self.name_var, width=35).grid(row=0, column=1, pady=5, sticky=tk.EW)
        
        # Type
        ttk.Label(form_frame, text="Zone Type:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.type_var = tk.StringVar(value=self.zone_data.get('type', '1'))
        type_combo = ttk.Combobox(form_frame, textvariable=self.type_var, width=33)
        type_combo['values'] = (
            '0 - Untrusted (WAN)',
            '1 - Trusted (LAN)',
            '2 - Public (DMZ)',
            '4 - Wireless (WLAN)',
            '5 - Encrypted (VPN)',
            '6 - Multicast',
            '8 - SSL VPN',
            '9 - Management'
        )
        type_combo.grid(row=1, column=1, pady=5, sticky=tk.EW)
        
        # Security Level
        ttk.Label(form_frame, text="Security Level:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.sec_level_var = tk.StringVar(value=self.zone_data.get('security_level', ''))
        ttk.Entry(form_frame, textvariable=self.sec_level_var, width=35).grid(row=2, column=1, pady=5, sticky=tk.EW)
        
        form_frame.columnconfigure(1, weight=1)
        
        # Buttons
        button_frame = ttk.Frame(self.dialog, padding="10")
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Save", command=self.save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT)
    
    def save(self):
        """Save the zone."""
        name = self.name_var.get().strip()
        
        if not name:
            messagebox.showerror("Validation Error", "Zone name is required")
            return
        
        type_val = self.type_var.get().split(' - ')[0] if ' - ' in self.type_var.get() else self.type_var.get()
        
        self.result = {
            'name': name,
            'type': type_val,
            'security_level': self.sec_level_var.get(),
        }
        
        self.dialog.destroy()


class AddressGroupEditor(ConfigEditor):
    """Editor for address object groups."""
    
    def __init__(self, parent, config):
        super().__init__(parent, "Address Groups Editor", config)
        self.groups = self.extract_address_groups()
        self.addresses = self.get_all_addresses()
        self.create_widgets()
        self.load_groups()
    
    def get_all_addresses(self):
        """Get list of all address objects for dropdown.
        
        Uses display name (addrObjIdDisp_) if available, otherwise internal name (addrObjId_).
        """
        addresses = []
        indices = set()
        
        for key in self.config_data.keys():
            if key.startswith('addrObjId_'):
                idx = key.split('_')[1]
                indices.add(idx)
        
        for idx in sorted(indices, key=lambda x: int(x) if x.isdigit() else 0):
            # Prefer display name over internal name
            addr_name = self.config_data.get(f'addrObjIdDisp_{idx}', '') or self.config_data.get(f'addrObjId_{idx}', '')
            if addr_name:
                addresses.append(addr_name)
        
        return sorted(addresses)
    
    def extract_address_groups(self):
        """Extract address groups from config.
        
        Address groups are stored as:
        - addrObjType_X=8 (type 8 = group)
        - Members in addro_atomToGrp_Y=<group_name> (index Y is the member, value is the group name)
        - Nested groups in addro_grpToGrp_Z=<group_name> (index Z is the nested group, value is parent group name)
        
        Note: Group memberships use internal names (addrObjId_), not display names.
        """
        groups = {}
        
        # First find all address objects of type 8 (groups)
        for key in self.config_data.keys():
            if key.startswith('addrObjType_'):
                idx = key.split('_')[1]
                obj_type = self.config_data.get(key, '')
                if obj_type == '8':  # Type 8 is an address group
                    internal_name = self.config_data.get(f'addrObjId_{idx}', '')
                    display_name = self.config_data.get(f'addrObjIdDisp_{idx}', '') or internal_name
                    if internal_name:
                        groups[idx] = {
                            'index': idx,
                            'id': internal_name,  # Internal name for group membership lookup
                            'display_name': display_name,  # Display name for UI
                            'members': [],
                        }
        
        # Now find members for each group
        for idx, group_data in groups.items():
            internal_name = group_data['id']
            members = []
            
            # Find all addro_atomToGrp entries where the VALUE equals this group's internal name
            # The KEY index tells us which address object is the member
            for key in self.config_data.keys():
                if key.startswith('addro_atomToGrp_'):
                    parent_group = self.config_data[key]
                    if parent_group == internal_name:
                        # The index is the member address object
                        member_idx = key.split('_')[-1]
                        # Use display name for members if available
                        member_name = self.config_data.get(f'addrObjIdDisp_{member_idx}', '') or \
                                    self.config_data.get(f'addrObjId_{member_idx}', '')
                        if member_name and member_name not in members:
                            members.append(member_name)
            
            # Also find nested groups via addro_grpToGrp
            # Same pattern: value = parent group, index = nested group
            for key in self.config_data.keys():
                if key.startswith('addro_grpToGrp_'):
                    parent_group = self.config_data[key]
                    if parent_group == internal_name:
                        # The index is the nested group
                        nested_idx = key.split('_')[-1]
                        # Use display name for nested groups if available
                        nested_name = self.config_data.get(f'addrObjIdDisp_{nested_idx}', '') or \
                                    self.config_data.get(f'addrObjId_{nested_idx}', '')
                        if nested_name and nested_name not in members and nested_name != internal_name:
                            members.append(nested_name)
            
            group_data['members'] = sorted(members)
        
        return groups
    
    def create_widgets(self):
        """Create editor widgets."""
        # Toolbar
        toolbar = ttk.Frame(self.window)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Add New", command=self.add_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Edit Selected", command=self.edit_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Delete Selected", command=self.delete_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Save Changes", command=self.save_changes).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Refresh Addresses", command=self.refresh_addresses).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Close", command=self.window.destroy).pack(side=tk.RIGHT, padx=2)
        
        # Search
        search_frame = ttk.Frame(self.window)
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=2)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self.filter_groups())
        ttk.Entry(search_frame, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=2)
        
        # Treeview
        tree_frame = ttk.Frame(self.window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('Group Name', 'Member Count', 'Members')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings',
                                  yscrollcommand=vsb.set)
        
        vsb.config(command=self.tree.yview)
        
        self.tree.heading('#0', text='Index')
        self.tree.heading('Group Name', text='Group Name')
        self.tree.heading('Member Count', text='Members')
        self.tree.heading('Members', text='Member Objects')
        
        self.tree.column('#0', width=60)
        self.tree.column('Group Name', width=200)
        self.tree.column('Member Count', width=80)
        self.tree.column('Members', width=600)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind('<Double-1>', lambda e: self.edit_group())
    
    def load_groups(self):
        """Load groups into treeview."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        search_term = self.search_var.get().lower()
        
        for idx, group in sorted(self.groups.items()):
            # Use display name for search and display
            display_name = group.get('display_name', group['id'])
            if search_term and search_term not in display_name.lower():
                continue
            
            members_str = ', '.join(group['members'][:5])
            if len(group['members']) > 5:
                extra_count = len(group['members']) - 5
                members_str += f' ... ({extra_count} more)'
            
            self.tree.insert('', 'end', text=idx,
                           values=(display_name, len(group['members']), members_str))
    
    def filter_groups(self):
        """Filter groups based on search term."""
        self.load_groups()
    
    def refresh_addresses(self):
        """Refresh the list of available addresses."""
        self.addresses = self.get_all_addresses()
        messagebox.showinfo("Refreshed", f"Address list refreshed. {len(self.addresses)} addresses available.")
    
    def add_group(self):
        """Add a new address group."""
        dialog = AddressGroupDialog(self.window, "Add Address Group", None, self.addresses)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            # Find next available address object index
            addr_indices = set()
            for key in self.config_data.keys():
                if key.startswith('addrObjId_'):
                    idx = key.split('_')[1]
                    if idx.isdigit():
                        addr_indices.add(int(idx))
            
            new_idx = str(max(addr_indices) + 1 if addr_indices else 0)
            
            # Create the address object entry for this group
            self.config_data[f'addrObjId_{new_idx}'] = dialog.result['name']
            self.config_data[f'addrObjType_{new_idx}'] = '8'  # Type 8 = group
            self.config_data[f'addrObjZone_{new_idx}'] = ''
            self.config_data[f'addrObjIp1_{new_idx}'] = '0.0.0.0'
            self.config_data[f'addrObjIp2_{new_idx}'] = '0.0.0.0'
            
            self.groups[new_idx] = {
                'index': new_idx,
                'id': dialog.result['name'],
                'members': dialog.result['members'],
            }
            
            self.load_groups()
            self.mark_modified()
    
    def edit_group(self):
        """Edit selected address group."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a group to edit")
            return
        
        idx = self.tree.item(selection[0])['text']
        group = self.groups[idx]
        
        dialog = AddressGroupDialog(self.window, "Edit Address Group", group, self.addresses)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            self.groups[idx].update({
                'id': dialog.result['name'],
                'members': dialog.result['members'],
            })
            
            self.load_groups()
            self.mark_modified()
    
    def delete_group(self):
        """Delete selected address group."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a group to delete")
            return
        
        idx = self.tree.item(selection[0])['text']
        group = self.groups[idx]
        
        if messagebox.askyesno("Confirm Delete", 
                              f"Delete address group '{group['id']}'?\n\nThis cannot be undone."):
            del self.groups[idx]
            self.load_groups()
            self.mark_modified()
    
    def save_changes(self):
        """Save changes back to config.
        
        Address groups in SonicWall are complex:
        1. Group objects are address objects with type 8
        2. Membership is stored in separate relationship parameters
        3. We need to preserve existing relationships and create new ones
        """
        # First, update all group names (they're address objects)
        for idx, group in self.groups.items():
            # Update the address object name
            self.config_data[f'addrObjId_{idx}'] = group['id']
            # Ensure it's marked as type 8 (group)
            self.config_data[f'addrObjType_{idx}'] = '8'
        
        # Now handle group membership via relationships
        # This is complex - we need to clear old relationships for these groups
        # and create new ones
        
        # Get list of all group names
        group_names = {group['id'] for group in self.groups.values()}
        
        # Clear old relationship entries for our groups
        keys_to_delete = []
        for key in list(self.config_data.keys()):
            if key.startswith('addro_atomToGrp_') or key.startswith('addro_grpToGrp_'):
                if self.config_data[key] in group_names:
                    keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del self.config_data[key]
        
        # Create new relationship entries
        # We need to find the next available index for relationships
        rel_indices = set()
        for key in self.config_data.keys():
            if key.startswith('addro_atomToGrp_') or key.startswith('addro_grpToGrp_'):
                idx = key.split('_')[-1]
                if idx.isdigit():
                    rel_indices.add(int(idx))
        
        next_rel_idx = max(rel_indices) + 1 if rel_indices else 0
        
        # For each group, create relationship entries for its members
        for group_idx, group in self.groups.items():
            group_name = group['id']
            
            for member_name in group['members']:
                # Find the address object index for this member
                member_idx = None
                for key in self.config_data.keys():
                    if key.startswith('addrObjId_'):
                        if self.config_data[key] == member_name:
                            member_idx = key.split('_')[1]
                            break
                
                if member_idx:
                    # Check if this member is itself a group (type 8)
                    member_type = self.config_data.get(f'addrObjType_{member_idx}', '')
                    if member_type == '8':
                        # It's a nested group
                        self.config_data[f'addro_grpToGrp_{next_rel_idx}'] = group_name
                    else:
                        # It's a regular address object
                        self.config_data[f'addro_atomToGrp_{next_rel_idx}'] = group_name
                    next_rel_idx += 1
        
        messagebox.showinfo("Success", "Address groups saved successfully!")
        self.modified = False
        self.window.title(self.window.title().replace(" - Modified", ""))


class AddressGroupDialog:
    """Dialog for adding/editing address groups."""
    
    def __init__(self, parent, title, group_data, available_addresses):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("700x550")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.result = None
        self.group_data = group_data or {}
        self.available_addresses = available_addresses
        self.selected_members = list(group_data.get('members', [])) if group_data else []
        
        self.create_widgets()
        
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def create_widgets(self):
        """Create dialog widgets."""
        # Group name
        name_frame = ttk.Frame(self.dialog, padding="10")
        name_frame.pack(fill=tk.X)
        
        ttk.Label(name_frame, text="Group Name:").pack(side=tk.LEFT, padx=5)
        self.name_var = tk.StringVar(value=self.group_data.get('id', ''))
        ttk.Entry(name_frame, textvariable=self.name_var, width=40).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Member management
        members_frame = ttk.LabelFrame(self.dialog, text="Group Members", padding="10")
        members_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Available addresses (left side)
        left_frame = ttk.Frame(members_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        ttk.Label(left_frame, text="Available Addresses:").pack()
        
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=2)
        ttk.Label(search_frame, text="Filter:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace('w', lambda *args: self.filter_available())
        ttk.Entry(search_frame, textvariable=self.filter_var, width=20).pack(side=tk.LEFT, padx=5)
        
        avail_scroll = ttk.Scrollbar(left_frame)
        avail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.available_list = tk.Listbox(left_frame, height=15, selectmode=tk.EXTENDED,
                                         yscrollcommand=avail_scroll.set)
        self.available_list.pack(fill=tk.BOTH, expand=True)
        avail_scroll.config(command=self.available_list.yview)
        
        # Buttons (middle)
        button_frame = ttk.Frame(members_frame)
        button_frame.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(button_frame, text="Add >>", command=self.add_members, width=10).pack(pady=5)
        ttk.Button(button_frame, text="<< Remove", command=self.remove_members, width=10).pack(pady=5)
        ttk.Button(button_frame, text="Add All >>", command=self.add_all, width=10).pack(pady=5)
        ttk.Button(button_frame, text="<< Remove All", command=self.remove_all, width=10).pack(pady=5)
        
        # Selected members (right side)
        right_frame = ttk.Frame(members_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        ttk.Label(right_frame, text="Group Members:").pack()
        
        member_scroll = ttk.Scrollbar(right_frame)
        member_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.members_list = tk.Listbox(right_frame, height=15, selectmode=tk.EXTENDED,
                                       yscrollcommand=member_scroll.set)
        self.members_list.pack(fill=tk.BOTH, expand=True)
        member_scroll.config(command=self.members_list.yview)
        
        # Populate lists
        self.populate_lists()
        
        # Buttons
        button_frame = ttk.Frame(self.dialog, padding="10")
        button_frame.pack(fill=tk.X)
        
        ttk.Label(button_frame, text=f"Total members: {len(self.selected_members)}").pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Save", command=self.save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT)
    
    def populate_lists(self):
        """Populate the available and selected lists."""
        self.available_list.delete(0, tk.END)
        self.members_list.delete(0, tk.END)
        
        # Available addresses (not in group)
        for addr in self.available_addresses:
            if addr not in self.selected_members:
                self.available_list.insert(tk.END, addr)
        
        # Selected members
        for member in self.selected_members:
            self.members_list.insert(tk.END, member)
    
    def filter_available(self):
        """Filter available addresses."""
        filter_text = self.filter_var.get().lower()
        
        self.available_list.delete(0, tk.END)
        for addr in self.available_addresses:
            if addr not in self.selected_members:
                if not filter_text or filter_text in addr.lower():
                    self.available_list.insert(tk.END, addr)
    
    def add_members(self):
        """Add selected addresses to group."""
        selections = self.available_list.curselection()
        for idx in reversed(selections):
            addr = self.available_list.get(idx)
            if addr not in self.selected_members:
                self.selected_members.append(addr)
        
        self.populate_lists()
    
    def remove_members(self):
        """Remove selected members from group."""
        selections = self.members_list.curselection()
        for idx in reversed(selections):
            member = self.members_list.get(idx)
            if member in self.selected_members:
                self.selected_members.remove(member)
        
        self.populate_lists()
    
    def add_all(self):
        """Add all available addresses to group."""
        for i in range(self.available_list.size()):
            addr = self.available_list.get(i)
            if addr not in self.selected_members:
                self.selected_members.append(addr)
        
        self.populate_lists()
    
    def remove_all(self):
        """Remove all members from group."""
        self.selected_members.clear()
        self.populate_lists()
    
    def save(self):
        """Save the address group."""
        name = self.name_var.get().strip()
        
        if not name:
            messagebox.showerror("Validation Error", "Group name is required")
            return
        
        if not self.selected_members:
            if not messagebox.askyesno("Empty Group", 
                "Group has no members. Save anyway?"):
                return
        
        self.result = {
            'name': name,
            'members': self.selected_members,
        }
        
        self.dialog.destroy()


class ServiceGroupEditor(ConfigEditor):
    """Editor for service object groups."""
    
    def __init__(self, parent, config):
        super().__init__(parent, "Service Groups Editor", config)
        self.groups = self.extract_service_groups()
        self.services = self.get_all_services()
        self.create_widgets()
        self.load_groups()
    
    def get_all_services(self):
        """Get list of all service objects for dropdown."""
        services = []
        indices = set()
        
        for key in self.config_data.keys():
            if key.startswith('svcObjId_'):
                idx = key.split('_')[1]
                indices.add(idx)
        
        for idx in sorted(indices, key=lambda x: int(x) if x.isdigit() else 0):
            svc_name = self.config_data.get(f'svcObjId_{idx}', '')
            if svc_name:
                services.append(svc_name)
        
        return sorted(services)
    
    def extract_service_groups(self):
        """Extract service groups from config.
        
        Service groups are stored as:
        - svcObjType_X=2 (type 2 = group)
        - Members in so_atomToGrp_Y=<group_name> (index Y is the member, value is the group name)
        - Nested groups in so_grpToGrp_Z=<group_name> (index Z is the nested group, value is parent group name)
        """
        groups = {}
        
        # First find all service objects of type 2 (groups)
        for key in self.config_data.keys():
            if key.startswith('svcObjType_'):
                idx = key.split('_')[1]
                obj_type = self.config_data.get(key, '')
                if obj_type == '2':  # Type 2 is a service group
                    group_name = self.config_data.get(f'svcObjId_{idx}', '')
                    if group_name:
                        groups[idx] = {
                            'index': idx,
                            'id': group_name,
                            'members': [],
                        }
        
        # Now find members for each group
        for idx, group_data in groups.items():
            group_name = group_data['id']
            members = []
            
            # Find all so_atomToGrp entries where the VALUE equals this group name
            # The KEY index tells us which service object is the member
            for key in self.config_data.keys():
                if key.startswith('so_atomToGrp_'):
                    parent_group = self.config_data[key]
                    if parent_group == group_name:
                        # The index is the member service object
                        member_idx = key.split('_')[-1]
                        member_name = self.config_data.get(f'svcObjId_{member_idx}', '')
                        if member_name and member_name not in members:
                            members.append(member_name)
            
            # Also find nested groups via so_grpToGrp
            # Same pattern: value = parent group, index = nested group
            for key in self.config_data.keys():
                if key.startswith('so_grpToGrp_'):
                    parent_group = self.config_data[key]
                    if parent_group == group_name:
                        # The index is the nested group
                        nested_idx = key.split('_')[-1]
                        nested_name = self.config_data.get(f'svcObjId_{nested_idx}', '')
                        if nested_name and nested_name not in members and nested_name != group_name:
                            members.append(nested_name)
            
            group_data['members'] = sorted(members)
        
        return groups
    
    def create_widgets(self):
        """Create editor widgets."""
        # Toolbar
        toolbar = ttk.Frame(self.window)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Add New", command=self.add_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Edit Selected", command=self.edit_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Delete Selected", command=self.delete_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Save Changes", command=self.save_changes).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Refresh Services", command=self.refresh_services).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Close", command=self.window.destroy).pack(side=tk.RIGHT, padx=2)
        
        # Search
        search_frame = ttk.Frame(self.window)
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=2)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self.filter_groups())
        ttk.Entry(search_frame, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=2)
        
        # Treeview
        tree_frame = ttk.Frame(self.window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('Group Name', 'Member Count', 'Members')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings',
                                  yscrollcommand=vsb.set)
        
        vsb.config(command=self.tree.yview)
        
        self.tree.heading('#0', text='Index')
        self.tree.heading('Group Name', text='Group Name')
        self.tree.heading('Member Count', text='Members')
        self.tree.heading('Members', text='Member Services')
        
        self.tree.column('#0', width=60)
        self.tree.column('Group Name', width=200)
        self.tree.column('Member Count', width=80)
        self.tree.column('Members', width=600)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind('<Double-1>', lambda e: self.edit_group())
    
    def load_groups(self):
        """Load groups into treeview."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        search_term = self.search_var.get().lower()
        
        for idx, group in sorted(self.groups.items()):
            if search_term and search_term not in group['id'].lower():
                continue
            
            members_str = ', '.join(group['members'][:5])
            if len(group['members']) > 5:
                extra_count = len(group['members']) - 5
                members_str += f' ... ({extra_count} more)'
            
            self.tree.insert('', 'end', text=idx,
                           values=(group['id'], len(group['members']), members_str))
    
    def filter_groups(self):
        """Filter groups based on search term."""
        self.load_groups()
    
    def refresh_services(self):
        """Refresh the list of available services."""
        self.services = self.get_all_services()
        messagebox.showinfo("Refreshed", f"Service list refreshed. {len(self.services)} services available.")
    
    def add_group(self):
        """Add a new service group."""
        dialog = ServiceGroupDialog(self.window, "Add Service Group", None, self.services)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            # Find next available service object index
            svc_indices = set()
            for key in self.config_data.keys():
                if key.startswith('svcObjId_'):
                    idx = key.split('_')[1]
                    if idx.isdigit():
                        svc_indices.add(int(idx))
            
            new_idx = str(max(svc_indices) + 1 if svc_indices else 0)
            
            # Create the service object entry for this group
            self.config_data[f'svcObjId_{new_idx}'] = dialog.result['name']
            self.config_data[f'svcObjType_{new_idx}'] = '2'  # Type 2 = group
            self.config_data[f'svcObjPort1_{new_idx}'] = '0'
            self.config_data[f'svcObjPort2_{new_idx}'] = '0'
            self.config_data[f'svcObjProtocol_{new_idx}'] = '0'
            
            self.groups[new_idx] = {
                'index': new_idx,
                'id': dialog.result['name'],
                'members': dialog.result['members'],
            }
            
            self.load_groups()
            self.mark_modified()
    
    def edit_group(self):
        """Edit selected service group."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a group to edit")
            return
        
        idx = self.tree.item(selection[0])['text']
        group = self.groups[idx]
        
        dialog = ServiceGroupDialog(self.window, "Edit Service Group", group, self.services)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            self.groups[idx].update({
                'id': dialog.result['name'],
                'members': dialog.result['members'],
            })
            
            self.load_groups()
            self.mark_modified()
    
    def delete_group(self):
        """Delete selected service group."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a group to delete")
            return
        
        idx = self.tree.item(selection[0])['text']
        group = self.groups[idx]
        
        if messagebox.askyesno("Confirm Delete", 
                              f"Delete service group '{group['id']}'?\n\nThis cannot be undone."):
            del self.groups[idx]
            self.load_groups()
            self.mark_modified()
    
    def save_changes(self):
        """Save changes back to config.
        
        Service groups in SonicWall are complex:
        1. Group objects are service objects with type 2
        2. Membership is stored in separate relationship parameters
        3. We need to preserve existing relationships and create new ones
        """
        # First, update all group names (they're service objects)
        for idx, group in self.groups.items():
            # Update the service object name
            self.config_data[f'svcObjId_{idx}'] = group['id']
            # Ensure it's marked as type 2 (group)
            self.config_data[f'svcObjType_{idx}'] = '2'
        
        # Now handle group membership via relationships
        # Get list of all group names
        group_names = {group['id'] for group in self.groups.values()}
        
        # Clear old relationship entries for our groups
        keys_to_delete = []
        for key in list(self.config_data.keys()):
            if key.startswith('so_atomToGrp_') or key.startswith('so_grpToGrp_'):
                if self.config_data[key] in group_names:
                    keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del self.config_data[key]
        
        # Create new relationship entries
        # Find the next available index for relationships
        rel_indices = set()
        for key in self.config_data.keys():
            if key.startswith('so_atomToGrp_') or key.startswith('so_grpToGrp_'):
                idx = key.split('_')[-1]
                if idx.isdigit():
                    rel_indices.add(int(idx))
        
        next_rel_idx = max(rel_indices) + 1 if rel_indices else 0
        
        # For each group, create relationship entries for its members
        for group_idx, group in self.groups.items():
            group_name = group['id']
            
            for member_name in group['members']:
                # Find the service object index for this member
                member_idx = None
                for key in self.config_data.keys():
                    if key.startswith('svcObjId_'):
                        if self.config_data[key] == member_name:
                            member_idx = key.split('_')[1]
                            break
                
                if member_idx:
                    # Check if this member is itself a group (type 2)
                    member_type = self.config_data.get(f'svcObjType_{member_idx}', '')
                    if member_type == '2':
                        # It's a nested group
                        self.config_data[f'so_grpToGrp_{next_rel_idx}'] = group_name
                    else:
                        # It's a regular service object
                        self.config_data[f'so_atomToGrp_{next_rel_idx}'] = group_name
                    next_rel_idx += 1
        
        messagebox.showinfo("Success", "Service groups saved successfully!")
        self.modified = False
        self.window.title(self.window.title().replace(" - Modified", ""))


class ServiceGroupDialog:
    """Dialog for adding/editing service groups - same structure as AddressGroupDialog."""
    
    def __init__(self, parent, title, group_data, available_services):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("700x550")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.result = None
        self.group_data = group_data or {}
        self.available_services = available_services
        self.selected_members = list(group_data.get('members', [])) if group_data else []
        
        self.create_widgets()
        
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def create_widgets(self):
        """Create dialog widgets."""
        # Group name
        name_frame = ttk.Frame(self.dialog, padding="10")
        name_frame.pack(fill=tk.X)
        
        ttk.Label(name_frame, text="Group Name:").pack(side=tk.LEFT, padx=5)
        self.name_var = tk.StringVar(value=self.group_data.get('id', ''))
        ttk.Entry(name_frame, textvariable=self.name_var, width=40).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Member management
        members_frame = ttk.LabelFrame(self.dialog, text="Group Members", padding="10")
        members_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Available services (left side)
        left_frame = ttk.Frame(members_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        ttk.Label(left_frame, text="Available Services:").pack()
        
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=2)
        ttk.Label(search_frame, text="Filter:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace('w', lambda *args: self.filter_available())
        ttk.Entry(search_frame, textvariable=self.filter_var, width=20).pack(side=tk.LEFT, padx=5)
        
        avail_scroll = ttk.Scrollbar(left_frame)
        avail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.available_list = tk.Listbox(left_frame, height=15, selectmode=tk.EXTENDED,
                                         yscrollcommand=avail_scroll.set)
        self.available_list.pack(fill=tk.BOTH, expand=True)
        avail_scroll.config(command=self.available_list.yview)
        
        # Buttons (middle)
        button_frame = ttk.Frame(members_frame)
        button_frame.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(button_frame, text="Add >>", command=self.add_members, width=10).pack(pady=5)
        ttk.Button(button_frame, text="<< Remove", command=self.remove_members, width=10).pack(pady=5)
        ttk.Button(button_frame, text="Add All >>", command=self.add_all, width=10).pack(pady=5)
        ttk.Button(button_frame, text="<< Remove All", command=self.remove_all, width=10).pack(pady=5)
        
        # Selected members (right side)
        right_frame = ttk.Frame(members_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        ttk.Label(right_frame, text="Group Members:").pack()
        
        member_scroll = ttk.Scrollbar(right_frame)
        member_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.members_list = tk.Listbox(right_frame, height=15, selectmode=tk.EXTENDED,
                                       yscrollcommand=member_scroll.set)
        self.members_list.pack(fill=tk.BOTH, expand=True)
        member_scroll.config(command=self.members_list.yview)
        
        # Populate lists
        self.populate_lists()
        
        # Buttons
        button_frame = ttk.Frame(self.dialog, padding="10")
        button_frame.pack(fill=tk.X)
        
        ttk.Label(button_frame, text=f"Total members: {len(self.selected_members)}").pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Save", command=self.save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT)
    
    def populate_lists(self):
        """Populate the available and selected lists."""
        self.available_list.delete(0, tk.END)
        self.members_list.delete(0, tk.END)
        
        for svc in self.available_services:
            if svc not in self.selected_members:
                self.available_list.insert(tk.END, svc)
        
        for member in self.selected_members:
            self.members_list.insert(tk.END, member)
    
    def filter_available(self):
        """Filter available services."""
        filter_text = self.filter_var.get().lower()
        
        self.available_list.delete(0, tk.END)
        for svc in self.available_services:
            if svc not in self.selected_members:
                if not filter_text or filter_text in svc.lower():
                    self.available_list.insert(tk.END, svc)
    
    def add_members(self):
        """Add selected services to group."""
        selections = self.available_list.curselection()
        for idx in reversed(selections):
            svc = self.available_list.get(idx)
            if svc not in self.selected_members:
                self.selected_members.append(svc)
        
        self.populate_lists()
    
    def remove_members(self):
        """Remove selected members from group."""
        selections = self.members_list.curselection()
        for idx in reversed(selections):
            member = self.members_list.get(idx)
            if member in self.selected_members:
                self.selected_members.remove(member)
        
        self.populate_lists()
    
    def add_all(self):
        """Add all available services to group."""
        for i in range(self.available_list.size()):
            svc = self.available_list.get(i)
            if svc not in self.selected_members:
                self.selected_members.append(svc)
        
        self.populate_lists()
    
    def remove_all(self):
        """Remove all members from group."""
        self.selected_members.clear()
        self.populate_lists()
    
    def save(self):
        """Save the service group."""
        name = self.name_var.get().strip()
        
        if not name:
            messagebox.showerror("Validation Error", "Group name is required")
            return
        
        if not self.selected_members:
            if not messagebox.askyesno("Empty Group", 
                "Group has no members. Save anyway?"):
                return
        
        self.result = {
            'name': name,
            'members': self.selected_members,
        }
        
        self.dialog.destroy()




class InterfaceEditor(ConfigEditor):
    """Editor for network interfaces."""
    
    def __init__(self, parent, config):
        super().__init__(parent, "Interface Editor", config)
        self.interfaces = self.extract_interfaces()
        self.create_widgets()
        self.load_interfaces()
    
    def extract_interfaces(self):
        """Extract interface configurations from config."""
        interfaces = {}
        indices = set()
        
        # Find all interface indices
        for key in self.config_data.keys():
            if key.startswith('iface_name_'):
                idx = key.split('_')[2]
                indices.add(idx)
        
        # Extract interface details
        for idx in sorted(indices, key=lambda x: int(x) if x.isdigit() else 999999):
            iface = {
                'index': idx,
                'name': self.config_data.get(f'iface_name_{idx}', ''),
                'ifnum': self.config_data.get(f'iface_ifnum_{idx}', ''),
                'comment': self.config_data.get(f'iface_comment_{idx}', ''),
                'zone': self.get_interface_zone(idx),
                'vlan_id': self.config_data.get(f'if_l2cfg_vlan_id_{idx}', ''),
            }
            if iface['name']:
                interfaces[idx] = iface
        
        return interfaces
    
    def get_interface_zone(self, idx):
        """Get zone name for interface."""
        # Match interface to zone by checking address objects
        ifnum = self.config_data.get(f'iface_ifnum_{idx}', '')
        if not ifnum:
            return ''
        
        # Find address objects with this interface's zone
        for key in self.config_data.keys():
            if key.startswith('addrObjZone_'):
                addr_idx = key.split('_')[1]
                # Check if this address belongs to this interface
                addr_name = self.config_data.get(f'addrObjId_{addr_idx}', '')
                iface_name = self.config_data.get(f'iface_name_{idx}', '')
                if iface_name and iface_name in addr_name:
                    return self.config_data.get(key, '')
        
        return ''
    
    def create_widgets(self):
        """Create editor widgets."""
        # Toolbar
        toolbar = ttk.Frame(self.window)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Edit Selected", command=self.edit_interface).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Close", command=self.window.destroy).pack(side=tk.RIGHT, padx=2)
        
        # Info label
        info_frame = ttk.Frame(self.window)
        info_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
        ttk.Label(info_frame, text="💡 Tip: Double-click an interface to edit its comment", 
                 foreground="blue").pack(side=tk.LEFT, padx=2)
        
        # Search
        search_frame = ttk.Frame(self.window)
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=2)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self.filter_interfaces())
        ttk.Entry(search_frame, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=2)
        
        # Treeview
        tree_frame = ttk.Frame(self.window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('Interface', 'Zone', 'VLAN ID', 'Comment')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings',
                                  yscrollcommand=vsb.set)
        
        vsb.config(command=self.tree.yview)
        
        self.tree.heading('#0', text='Index')
        self.tree.heading('Interface', text='Interface')
        self.tree.heading('Zone', text='Zone')
        self.tree.heading('VLAN ID', text='VLAN ID')
        self.tree.heading('Comment', text='Comment')
        
        self.tree.column('#0', width=60)
        self.tree.column('Interface', width=150)
        self.tree.column('Zone', width=100)
        self.tree.column('VLAN ID', width=100)
        self.tree.column('Comment', width=400)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind('<Double-1>', lambda e: self.edit_interface())
    
    def load_interfaces(self):
        """Load interfaces into treeview."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        search_term = self.search_var.get().lower()
        
        for idx, iface in sorted(self.interfaces.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999999):
            if search_term and search_term not in iface['name'].lower() and search_term not in iface['comment'].lower():
                continue
            
            # Format VLAN ID display
            vlan_display = iface['vlan_id'] if iface['vlan_id'] and iface['vlan_id'] not in ['0', '65535'] else ''
            
            self.tree.insert('', 'end', text=idx,
                           values=(iface['name'], iface['zone'], vlan_display, iface['comment']))
    
    def filter_interfaces(self):
        """Filter interfaces based on search term."""
        self.load_interfaces()
    
    def edit_interface(self):
        """Edit selected interface comment."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an interface to edit")
            return
        
        idx = self.tree.item(selection[0])['text']
        iface = self.interfaces[idx]
        
        dialog = InterfaceDialog(self.window, iface)
        if dialog.result:
            # Update config
            self.config_data[f'iface_comment_{idx}'] = dialog.result['comment']
            self.config_data[f'iface_comment6_{idx}'] = dialog.result['comment']  # IPv6 version
            
            # Update local copy
            self.interfaces[idx]['comment'] = dialog.result['comment']
            
            # Mark as modified
            self.mark_modified()
            
            # Refresh display
            self.load_interfaces()
            
            messagebox.showinfo("Success", "Interface comment updated. Click 'Save Changes' to apply.")
    
    def save_changes(self):
        """Save changes back to config."""
        if self.modified:
            self.mark_modified()
            messagebox.showinfo("Success", "Changes saved to configuration. Use 'Save as .exp' to export.")


class InterfaceDialog:
    """Dialog for editing interface properties."""
    
    def __init__(self, parent, iface=None):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Edit Interface")
        self.dialog.geometry("500x200")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Interface info (read-only)
        info_frame = ttk.LabelFrame(self.dialog, text="Interface Information", padding="10")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(info_frame, text=f"Interface: {iface['name']}").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Label(info_frame, text=f"Zone: {iface['zone']}").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        if iface['vlan_id'] and iface['vlan_id'] not in ['0', '65535']:
            ttk.Label(info_frame, text=f"VLAN ID: {iface['vlan_id']}").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        
        # Editable fields
        edit_frame = ttk.LabelFrame(self.dialog, text="Editable Properties", padding="10")
        edit_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        ttk.Label(edit_frame, text="Comment:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.comment_var = tk.StringVar(value=iface.get('comment', ''))
        comment_entry = ttk.Entry(edit_frame, textvariable=self.comment_var, width=50)
        comment_entry.grid(row=0, column=1, padx=5, pady=5)
        comment_entry.focus()
        
        # Buttons
        button_frame = ttk.Frame(self.dialog, padding="10")
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Save", command=self.save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT)
        
        # Center dialog
        self.dialog.update_idletasks()
        x = (parent.winfo_width() - self.dialog.winfo_width()) // 2 + parent.winfo_x()
        y = (parent.winfo_height() - self.dialog.winfo_height()) // 2 + parent.winfo_y()
        self.dialog.geometry(f"+{x}+{y}")
        
        # Wait for dialog
        self.dialog.wait_window()
    
    def save(self):
        """Save interface changes."""
        self.result = {
            'comment': self.comment_var.get().strip(),
        }
        self.dialog.destroy()


class VLANEditor(ConfigEditor):
    """Editor for VLAN configurations."""
    
    def __init__(self, parent, config):
        super().__init__(parent, "VLAN Editor", config)
        self.vlans = self.extract_vlans()
        self.create_widgets()
        self.load_vlans()
    
    def extract_vlans(self):
        """Extract VLAN configurations from config."""
        vlans = {}
        
        # Find all interfaces that are VLAN subinterfaces
        for key in self.config_data.keys():
            if key.startswith('iface_name_'):
                idx = key.split('_')[2]
                iface_name = self.config_data.get(key, '')
                
                # Check if it's a VLAN subinterface (format: X6:V10)
                if ':V' in iface_name or ':v' in iface_name.lower():
                    # Extract VLAN ID from interface name
                    try:
                        vlan_part = iface_name.split(':')[1]  # Get "V10" part
                        vlan_id = vlan_part[1:]  # Remove 'V' to get "10"
                    except:
                        vlan_id = 'Unknown'
                    
                    parent = iface_name.split(':')[0] if ':' in iface_name else ''
                    
                    vlans[idx] = {
                        'index': idx,
                        'vlan_id': vlan_id,
                        'interface': iface_name,
                        'parent': parent,
                        'ifnum': self.config_data.get(f'iface_ifnum_{idx}', ''),
                        'comment': self.config_data.get(f'iface_comment_{idx}', ''),
                    }
        
        return vlans
    
    def create_widgets(self):
        """Create editor widgets."""
        # Toolbar
        toolbar = ttk.Frame(self.window)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Close", command=self.window.destroy).pack(side=tk.RIGHT, padx=2)
        
        # Info label
        info_frame = ttk.Frame(self.window)
        info_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
        ttk.Label(info_frame, text="💡 Tip: VLANs are displayed from interfaces with VLAN IDs configured", 
                 foreground="blue").pack(side=tk.LEFT, padx=2)
        
        # Search
        search_frame = ttk.Frame(self.window)
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=2)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self.filter_vlans())
        ttk.Entry(search_frame, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=2)
        
        # Treeview
        tree_frame = ttk.Frame(self.window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('VLAN ID', 'Interface', 'Parent Interface', 'Comment')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings',
                                  yscrollcommand=vsb.set)
        
        vsb.config(command=self.tree.yview)
        
        self.tree.heading('#0', text='Index')
        self.tree.heading('VLAN ID', text='VLAN ID')
        self.tree.heading('Interface', text='Interface')
        self.tree.heading('Parent Interface', text='Parent')
        self.tree.heading('Comment', text='Comment')
        
        self.tree.column('#0', width=60)
        self.tree.column('VLAN ID', width=100)
        self.tree.column('Interface', width=200)
        self.tree.column('Parent Interface', width=150)
        self.tree.column('Comment', width=300)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
    
    def load_vlans(self):
        """Load VLANs into treeview."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        search_term = self.search_var.get().lower()
        
        for idx, vlan in sorted(self.vlans.items(), 
                               key=lambda x: int(x[1]['vlan_id']) if x[1]['vlan_id'].isdigit() else 999999):
            if search_term and search_term not in vlan['interface'].lower() and search_term not in vlan['vlan_id']:
                continue
            
            self.tree.insert('', 'end', text=idx,
                           values=(vlan['vlan_id'], vlan['interface'], vlan['parent'], vlan['comment']))
    
    def filter_vlans(self):
        """Filter VLANs based on search term."""
        self.load_vlans()


class AddressObjectEditor(ConfigEditor):
    """Editor for address objects."""
    
    def __init__(self, parent, config):
        super().__init__(parent, "Address Objects Editor", config)
        self.addresses = self.extract_address_objects()
        self.create_widgets()
        self.load_addresses()
        
    def extract_address_objects(self):
        """Extract address objects from config.
        
        SonicWall .exp file field mappings:
        - addrObjId_X: Internal name (used for references)
        - addrObjIdDisp_X: Display name (shown in GUI)
        - addrObjType_X: Object type (1=Host, 2=Range, 4=Network, 8=Group, 8192=FQDN)
        - addrObjZone_X: Zone assignment
        - addrObjIp1_X: Primary IP (host IP, network address, or range start)
        - addrObjIp2_X: Secondary IP (subnet mask for networks, or range end)
        """
        addresses = {}
        indices = set()
        
        for key in self.config_data.keys():
            if key.startswith('addrObjId_'):
                idx = key.split('_')[1]
                indices.add(idx)
        
        for idx in sorted(indices, key=lambda x: int(x) if x.isdigit() else 0):
            obj_type = self.config_data.get(f'addrObjType_{idx}', '')
            ip1 = self.config_data.get(f'addrObjIp1_{idx}', '')
            ip2 = self.config_data.get(f'addrObjIp2_{idx}', '')
            
            # For type 4 (Network), ip2 is the subnet mask
            # For type 2 (Range), ip2 is the end IP
            # For type 1 (Host), ip2 is typically 0.0.0.0
            if obj_type == '4':  # Network
                mask = ip2
                ip_end = ''
            elif obj_type == '2':  # Range
                mask = ''
                ip_end = ip2
            else:
                mask = ''
                ip_end = ip2
            
            addr = {
                'index': idx,
                'id': self.config_data.get(f'addrObjId_{idx}', ''),
                'display_name': self.config_data.get(f'addrObjIdDisp_{idx}', ''),
                'type': obj_type,
                'zone': self.config_data.get(f'addrObjZone_{idx}', ''),
                'ip1': ip1,  # Primary IP (host, network, or range start)
                'ip2': ip2,  # Raw value from config
                'ip_begin': ip1,  # For UI compatibility
                'ip_end': ip_end,  # Range end IP (if applicable)
                'mask': mask,  # Subnet mask (if applicable)
                'properties': self.config_data.get(f'addrObjProperties_{idx}', ''),
                'instance_id': self.config_data.get(f'addrObjInstanceId_{idx}', ''),
            }
            if addr['id'] or addr['display_name']:
                addresses[idx] = addr
        
        return addresses
    
    def create_widgets(self):
        """Create editor widgets."""
        # Toolbar
        toolbar = ttk.Frame(self.window)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Add New", command=self.add_address).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Edit Selected", command=self.edit_address).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Delete Selected", command=self.delete_address).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Save Changes", command=self.save_changes).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Close", command=self.window.destroy).pack(side=tk.RIGHT, padx=2)
        
        # Search bar
        search_frame = ttk.Frame(self.window)
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=2)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self.filter_addresses())
        ttk.Entry(search_frame, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=2)
        
        # Treeview for address list
        tree_frame = ttk.Frame(self.window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Treeview
        columns = ('Name', 'Zone', 'Type', 'IP Begin', 'IP End', 'Mask')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings',
                                  yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        # Column headings
        self.tree.heading('#0', text='Index')
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120)
        
        self.tree.column('#0', width=60)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Double-click to edit
        self.tree.bind('<Double-1>', lambda e: self.edit_address())
    
    def load_addresses(self):
        """Load addresses into treeview."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        search_term = self.search_var.get().lower()
        
        # Type descriptions for display
        type_names = {
            '1': 'Host',
            '2': 'Range',
            '4': 'Network',
            '8': 'Group',
            '8192': 'FQDN',
        }
        
        for idx, addr in sorted(self.addresses.items()):
            # Use display name if available, otherwise internal name
            display_name = addr.get('display_name') or addr.get('id', '')
            
            # Filter by search term
            if search_term and search_term not in display_name.lower() and search_term not in addr.get('ip1', '').lower():
                continue
            
            # Get type description
            type_val = addr.get('type', '')
            type_desc = type_names.get(type_val, f'Type {type_val}')
            
            # Format IP display based on type
            ip_display = addr.get('ip1', '')
            ip2_display = ''
            mask_display = ''
            
            if type_val == '4':  # Network - show mask
                mask_display = addr.get('ip2', '')
            elif type_val == '2':  # Range - show end IP
                ip2_display = addr.get('ip2', '')
            
            self.tree.insert('', 'end', text=idx,
                           values=(display_name, addr.get('zone', ''), type_desc,
                                 ip_display, ip2_display, mask_display))
    
    def filter_addresses(self):
        """Filter addresses based on search term."""
        self.load_addresses()
    
    def add_address(self):
        """Add a new address object."""
        dialog = AddressDialog(self.window, "Add Address Object", None)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            # Find next available index
            max_idx = max([int(k) for k in self.addresses.keys() if k.isdigit()] + [0])
            new_idx = str(max_idx + 1)
            
            obj_type = dialog.result['type']
            
            # Determine ip2 value based on type
            if obj_type == '4':  # Network
                ip2 = dialog.result['mask']
            elif obj_type == '2':  # Range
                ip2 = dialog.result['ip_end']
            else:  # Host
                ip2 = '0.0.0.0'
            
            self.addresses[new_idx] = {
                'index': new_idx,
                'id': dialog.result['name'],
                'display_name': dialog.result['name'],
                'type': obj_type,
                'zone': dialog.result['zone'],
                'ip1': dialog.result['ip_begin'],
                'ip2': ip2,
                'ip_begin': dialog.result['ip_begin'],
                'ip_end': dialog.result['ip_end'],
                'mask': dialog.result['mask'],
            }
            
            self.load_addresses()
            self.mark_modified()
    
    def edit_address(self):
        """Edit selected address object."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an address to edit")
            return
        
        idx = self.tree.item(selection[0])['text']
        addr = self.addresses[idx]
        
        dialog = AddressDialog(self.window, "Edit Address Object", addr)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            obj_type = dialog.result['type']
            
            # Determine ip2 value based on type
            if obj_type == '4':  # Network
                ip2 = dialog.result['mask']
            elif obj_type == '2':  # Range
                ip2 = dialog.result['ip_end']
            else:  # Host
                ip2 = '0.0.0.0'
            
            self.addresses[idx].update({
                'id': dialog.result['name'],
                'display_name': dialog.result['name'],
                'type': obj_type,
                'zone': dialog.result['zone'],
                'ip1': dialog.result['ip_begin'],
                'ip2': ip2,
                'ip_begin': dialog.result['ip_begin'],
                'ip_end': dialog.result['ip_end'],
                'mask': dialog.result['mask'],
            })
            
            self.load_addresses()
            self.mark_modified()
    
    def delete_address(self):
        """Delete selected address object."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an address to delete")
            return
        
        idx = self.tree.item(selection[0])['text']
        addr = self.addresses[idx]
        
        if messagebox.askyesno("Confirm Delete", 
                              f"Delete address object '{addr['id']}'?\n\nThis cannot be undone."):
            del self.addresses[idx]
            self.load_addresses()
            self.mark_modified()
    
    def save_changes(self):
        """Save changes back to config.
        
        Maps internal address object fields back to SonicWall .exp format:
        - addrObjId_X: Internal name
        - addrObjIdDisp_X: Display name
        - addrObjType_X: Object type
        - addrObjZone_X: Zone assignment
        - addrObjIp1_X: Primary IP
        - addrObjIp2_X: Secondary IP (mask or range end)
        """
        for idx, addr in self.addresses.items():
            self.config_data[f'addrObjId_{idx}'] = addr['id']
            self.config_data[f'addrObjIdDisp_{idx}'] = addr.get('display_name') or addr['id']
            self.config_data[f'addrObjType_{idx}'] = addr['type']
            self.config_data[f'addrObjZone_{idx}'] = addr['zone']
            self.config_data[f'addrObjIp1_{idx}'] = addr.get('ip1', '') or addr.get('ip_begin', '')
            
            # Set ip2 based on type
            obj_type = addr.get('type', '')
            if obj_type == '4':  # Network - ip2 is mask
                self.config_data[f'addrObjIp2_{idx}'] = addr.get('mask', '') or addr.get('ip2', '')
            elif obj_type == '2':  # Range - ip2 is end IP
                self.config_data[f'addrObjIp2_{idx}'] = addr.get('ip_end', '') or addr.get('ip2', '')
            else:  # Host or other - preserve ip2
                self.config_data[f'addrObjIp2_{idx}'] = addr.get('ip2', '0.0.0.0')
        
        messagebox.showinfo("Success", "Address objects saved successfully!")
        self.modified = False
        self.window.title(self.window.title().replace(" - Modified", ""))


class AddressDialog:
    """Dialog for adding/editing address objects."""
    
    def __init__(self, parent, title, address_data):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("500x350")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.result = None
        self.address_data = address_data or {}
        
        self.create_widgets()
        
        # Center dialog
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def create_widgets(self):
        """Create dialog widgets."""
        # Form fields
        form_frame = ttk.Frame(self.dialog, padding="10")
        form_frame.pack(fill=tk.BOTH, expand=True)
        
        row = 0
        
        # Name
        ttk.Label(form_frame, text="Name:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.name_var = tk.StringVar(value=self.address_data.get('id', ''))
        ttk.Entry(form_frame, textvariable=self.name_var, width=40).grid(row=row, column=1, pady=5, sticky=tk.EW)
        row += 1
        
        # Zone
        ttk.Label(form_frame, text="Zone:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.zone_var = tk.StringVar(value=self.address_data.get('zone', ''))
        zone_combo = ttk.Combobox(form_frame, textvariable=self.zone_var, width=38)
        zone_combo['values'] = ('LAN', 'WAN', 'DMZ', 'VPN', 'SSLVPN', 'WLAN', 'MGMT')
        zone_combo.grid(row=row, column=1, pady=5, sticky=tk.EW)
        row += 1
        
        # Type
        ttk.Label(form_frame, text="Type:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.type_var = tk.StringVar(value=self.address_data.get('type', '1'))
        type_combo = ttk.Combobox(form_frame, textvariable=self.type_var, width=38)
        type_combo['values'] = ('1 - Host', '4 - Network', '2 - Range', '8192 - FQDN')
        type_combo.grid(row=row, column=1, pady=5, sticky=tk.EW)
        row += 1
        
        # IP Begin
        ttk.Label(form_frame, text="IP Address / Begin:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.ip_begin_var = tk.StringVar(value=self.address_data.get('ip_begin', ''))
        ttk.Entry(form_frame, textvariable=self.ip_begin_var, width=40).grid(row=row, column=1, pady=5, sticky=tk.EW)
        row += 1
        
        # IP End
        ttk.Label(form_frame, text="IP End (for Range):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.ip_end_var = tk.StringVar(value=self.address_data.get('ip_end', ''))
        ttk.Entry(form_frame, textvariable=self.ip_end_var, width=40).grid(row=row, column=1, pady=5, sticky=tk.EW)
        row += 1
        
        # Netmask
        ttk.Label(form_frame, text="Netmask (for Network):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.mask_var = tk.StringVar(value=self.address_data.get('mask', ''))
        ttk.Entry(form_frame, textvariable=self.mask_var, width=40).grid(row=row, column=1, pady=5, sticky=tk.EW)
        row += 1
        
        form_frame.columnconfigure(1, weight=1)
        
        # Help text
        help_frame = ttk.LabelFrame(self.dialog, text="Quick Guide", padding="10")
        help_frame.pack(fill=tk.X, padx=10, pady=5)
        
        help_text = """Host: Single IP address (e.g., 192.168.1.100)
Network: Network with netmask (e.g., 192.168.1.0 / 255.255.255.0)
Range: IP range (e.g., 192.168.1.10 to 192.168.1.20)
FQDN: Fully qualified domain name (e.g., www.example.com)"""
        
        ttk.Label(help_frame, text=help_text, justify=tk.LEFT).pack()
        
        # Buttons
        button_frame = ttk.Frame(self.dialog, padding="10")
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Save", command=self.save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT)
    
    def save(self):
        """Save the address object."""
        name = self.name_var.get().strip()
        
        if not name:
            messagebox.showerror("Validation Error", "Name is required")
            return
        
        # Extract type number from combo selection
        type_val = self.type_var.get().split(' - ')[0] if ' - ' in self.type_var.get() else self.type_var.get()
        
        self.result = {
            'name': name,
            'zone': self.zone_var.get(),
            'type': type_val,
            'ip_begin': self.ip_begin_var.get(),
            'ip_end': self.ip_end_var.get(),
            'mask': self.mask_var.get(),
        }
        
        self.dialog.destroy()


class ServiceObjectEditor(ConfigEditor):
    """Editor for service objects."""
    
    def __init__(self, parent, config):
        super().__init__(parent, "Service Objects Editor", config)
        self.services = self.extract_service_objects()
        self.create_widgets()
        self.load_services()
    
    def extract_service_objects(self):
        """Extract service objects from config.
        
        SonicWall .exp file field mappings:
        - svcObjId_X: Service name
        - svcObjType_X: Object type (1=Service, 2=Group)
        - svcObjIpType_X: IP Protocol number (6=TCP, 17=UDP, etc.)
        - svcObjPort1_X: Start port
        - svcObjPort2_X: End port
        """
        services = {}
        indices = set()
        
        for key in self.config_data.keys():
            if key.startswith('svcObjId_'):
                idx = key.split('_')[1]
                indices.add(idx)
        
        # Protocol number to name mapping
        protocol_names = {
            '6': 'TCP',
            '17': 'UDP',
            '1': 'ICMP',
            '47': 'GRE',
            '50': 'ESP',
            '51': 'AH',
            '0': 'Any',
        }
        
        for idx in sorted(indices, key=lambda x: int(x) if x.isdigit() else 0):
            ip_type = self.config_data.get(f'svcObjIpType_{idx}', '')
            protocol_name = protocol_names.get(ip_type, f'Proto {ip_type}' if ip_type else '')
            
            svc = {
                'index': idx,
                'id': self.config_data.get(f'svcObjId_{idx}', ''),
                'type': self.config_data.get(f'svcObjType_{idx}', ''),
                'ip_type': ip_type,  # Raw protocol number
                'protocol': protocol_name,  # Human-readable protocol name
                'port1': self.config_data.get(f'svcObjPort1_{idx}', ''),
                'port2': self.config_data.get(f'svcObjPort2_{idx}', ''),
                'port_low': self.config_data.get(f'svcObjPort1_{idx}', ''),  # For compatibility
                'port_high': self.config_data.get(f'svcObjPort2_{idx}', ''),  # For compatibility
                'properties': self.config_data.get(f'svcObjProperties_{idx}', ''),
                'management': self.config_data.get(f'svcObjManagement_{idx}', ''),
            }
            if svc['id']:
                services[idx] = svc
        
        return services
    
    def create_widgets(self):
        """Create editor widgets."""
        # Toolbar
        toolbar = ttk.Frame(self.window)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Add New", command=self.add_service).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Edit Selected", command=self.edit_service).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Delete Selected", command=self.delete_service).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Save Changes", command=self.save_changes).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Close", command=self.window.destroy).pack(side=tk.RIGHT, padx=2)
        
        # Search bar
        search_frame = ttk.Frame(self.window)
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=2)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self.filter_services())
        ttk.Entry(search_frame, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=2)
        
        # Treeview
        tree_frame = ttk.Frame(self.window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        columns = ('Name', 'Protocol', 'Port Start', 'Port End', 'Type')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings',
                                  yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        self.tree.heading('#0', text='Index')
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120)
        
        self.tree.column('#0', width=60)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        self.tree.bind('<Double-1>', lambda e: self.edit_service())
    
    def load_services(self):
        """Load services into treeview."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        search_term = self.search_var.get().lower()
        
        # Type descriptions
        type_names = {
            '1': 'Service',
            '2': 'Group',
        }
        
        for idx, svc in sorted(self.services.items()):
            if search_term and search_term not in svc['id'].lower():
                continue
            
            # Get type description
            svc_type = svc.get('type', '')
            type_desc = type_names.get(svc_type, f'Type {svc_type}')
            
            # Format port display
            port1 = svc.get('port1', '') or svc.get('port_low', '')
            port2 = svc.get('port2', '') or svc.get('port_high', '')
            
            port_desc = f"{port1}"
            if port2 and port2 != port1:
                port_desc = f"{port1}-{port2}"
            
            self.tree.insert('', 'end', text=idx,
                           values=(svc['id'], svc.get('protocol', ''),
                                 port1, port2, type_desc))
    
    def filter_services(self):
        """Filter services based on search term."""
        self.load_services()
    
    def add_service(self):
        """Add a new service object."""
        dialog = ServiceDialog(self.window, "Add Service Object", None)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            max_idx = max([int(k) for k in self.services.keys() if k.isdigit()] + [0])
            new_idx = str(max_idx + 1)
            
            # Convert protocol name to number
            protocol_numbers = {
                'TCP': '6',
                'UDP': '17',
                'ICMP': '1',
                'GRE': '47',
                'ESP': '50',
                'AH': '51',
                'Any': '0',
            }
            ip_type = protocol_numbers.get(dialog.result['protocol'], '6')
            
            self.services[new_idx] = {
                'index': new_idx,
                'id': dialog.result['name'],
                'type': '1',  # Service type
                'ip_type': ip_type,
                'protocol': dialog.result['protocol'],
                'port1': dialog.result['port_low'],
                'port2': dialog.result['port_high'],
                'port_low': dialog.result['port_low'],
                'port_high': dialog.result['port_high'],
            }
            
            self.load_services()
            self.mark_modified()
    
    def edit_service(self):
        """Edit selected service object."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a service to edit")
            return
        
        idx = self.tree.item(selection[0])['text']
        svc = self.services[idx]
        
        dialog = ServiceDialog(self.window, "Edit Service Object", svc)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            # Convert protocol name to number
            protocol_numbers = {
                'TCP': '6',
                'UDP': '17',
                'ICMP': '1',
                'GRE': '47',
                'ESP': '50',
                'AH': '51',
                'Any': '0',
            }
            ip_type = protocol_numbers.get(dialog.result['protocol'], svc.get('ip_type', '6'))
            
            self.services[idx].update({
                'id': dialog.result['name'],
                'ip_type': ip_type,
                'protocol': dialog.result['protocol'],
                'port1': dialog.result['port_low'],
                'port2': dialog.result['port_high'],
                'port_low': dialog.result['port_low'],
                'port_high': dialog.result['port_high'],
            })
            
            self.load_services()
            self.mark_modified()
    
    def delete_service(self):
        """Delete selected service object."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a service to delete")
            return
        
        idx = self.tree.item(selection[0])['text']
        svc = self.services[idx]
        
        if messagebox.askyesno("Confirm Delete", 
                              f"Delete service object '{svc['id']}'?\n\nThis cannot be undone."):
            del self.services[idx]
            self.load_services()
            self.mark_modified()
    
    def save_changes(self):
        """Save changes back to config.
        
        Maps service object fields back to SonicWall .exp format:
        - svcObjId_X: Service name
        - svcObjType_X: Object type (1=Service, 2=Group)
        - svcObjIpType_X: IP Protocol number
        - svcObjPort1_X: Start port
        - svcObjPort2_X: End port
        """
        # Protocol name to number mapping
        protocol_numbers = {
            'TCP': '6',
            'UDP': '17',
            'ICMP': '1',
            'GRE': '47',
            'ESP': '50',
            'AH': '51',
            'Any': '0',
        }
        
        for idx, svc in self.services.items():
            self.config_data[f'svcObjId_{idx}'] = svc['id']
            
            # Convert protocol name back to number if needed
            protocol = svc.get('protocol', '')
            if protocol in protocol_numbers:
                ip_type = protocol_numbers[protocol]
            elif svc.get('ip_type'):
                ip_type = svc['ip_type']
            else:
                ip_type = '6'  # Default to TCP
            
            self.config_data[f'svcObjIpType_{idx}'] = ip_type
            self.config_data[f'svcObjPort1_{idx}'] = svc.get('port1', '') or svc.get('port_low', '')
            self.config_data[f'svcObjPort2_{idx}'] = svc.get('port2', '') or svc.get('port_high', '')
            self.config_data[f'svcObjType_{idx}'] = svc.get('type', '1')
        
        messagebox.showinfo("Success", "Service objects saved successfully!")
        self.modified = False
        self.window.title(self.window.title().replace(" - Modified", ""))


class ServiceDialog:
    """Dialog for adding/editing service objects."""
    
    def __init__(self, parent, title, service_data):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("450x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.result = None
        self.service_data = service_data or {}
        
        self.create_widgets()
        
        # Center dialog
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def create_widgets(self):
        """Create dialog widgets."""
        form_frame = ttk.Frame(self.dialog, padding="10")
        form_frame.pack(fill=tk.BOTH, expand=True)
        
        row = 0
        
        # Name
        ttk.Label(form_frame, text="Name:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.name_var = tk.StringVar(value=self.service_data.get('id', ''))
        ttk.Entry(form_frame, textvariable=self.name_var, width=35).grid(row=row, column=1, pady=5, sticky=tk.EW)
        row += 1
        
        # Protocol
        ttk.Label(form_frame, text="Protocol:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.protocol_var = tk.StringVar(value=self.service_data.get('protocol', 'TCP'))
        protocol_combo = ttk.Combobox(form_frame, textvariable=self.protocol_var, width=33)
        protocol_combo['values'] = ('TCP', 'UDP', 'ICMP', 'IP')
        protocol_combo.grid(row=row, column=1, pady=5, sticky=tk.EW)
        row += 1
        
        # Port Low
        ttk.Label(form_frame, text="Port (or Port Low):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.port_low_var = tk.StringVar(value=self.service_data.get('port_low', ''))
        ttk.Entry(form_frame, textvariable=self.port_low_var, width=35).grid(row=row, column=1, pady=5, sticky=tk.EW)
        row += 1
        
        # Port High
        ttk.Label(form_frame, text="Port High (optional):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.port_high_var = tk.StringVar(value=self.service_data.get('port_high', ''))
        ttk.Entry(form_frame, textvariable=self.port_high_var, width=35).grid(row=row, column=1, pady=5, sticky=tk.EW)
        row += 1
        
        form_frame.columnconfigure(1, weight=1)
        
        # Help
        help_frame = ttk.LabelFrame(self.dialog, text="Examples", padding="10")
        help_frame.pack(fill=tk.X, padx=10, pady=5)
        
        help_text = """Single port: Port = 80, Port High = (empty or same)
Port range: Port = 8000, Port High = 8999
Well-known: HTTP=80, HTTPS=443, SSH=22, DNS=53"""
        
        ttk.Label(help_frame, text=help_text, justify=tk.LEFT).pack()
        
        # Buttons
        button_frame = ttk.Frame(self.dialog, padding="10")
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Save", command=self.save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT)
    
    def save(self):
        """Save the service object."""
        name = self.name_var.get().strip()
        
        if not name:
            messagebox.showerror("Validation Error", "Name is required")
            return
        
        port_high = self.port_high_var.get().strip()
        if not port_high:
            port_high = self.port_low_var.get().strip()
        
        self.result = {
            'name': name,
            'protocol': self.protocol_var.get(),
            'port_low': self.port_low_var.get(),
            'port_high': port_high,
        }
        
        self.dialog.destroy()


class SonicWallConverterCompleteGUI:
    """Complete GUI with all configuration editors."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("SonicWall Configuration Converter - Complete Edition")
        self.root.geometry("950x750")
        
        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar()
        self.config = {}
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create all GUI widgets."""
        # Title
        title_frame = ttk.Frame(self.root, padding="10")
        title_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        title_label = ttk.Label(
            title_frame,
            text="SonicWall Configuration Converter - Complete Edition",
            font=('Arial', 14, 'bold')
        )
        title_label.grid(row=0, column=0, pady=5)
        
        subtitle_label = ttk.Label(
            title_frame,
            text="Full configuration editor with zones, objects, and groups",
            font=('Arial', 9)
        )
        subtitle_label.grid(row=1, column=0)
        
        # File operations
        file_frame = ttk.LabelFrame(self.root, text="File Operations", padding="10")
        file_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        ttk.Label(file_frame, text="Input File:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(file_frame, textvariable=self.input_file, width=60).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="Browse...", command=self.browse_input).grid(row=0, column=2, pady=2)
        
        ttk.Label(file_frame, text="Output File:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(file_frame, textvariable=self.output_file, width=60).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="Browse...", command=self.browse_output).grid(row=1, column=2, pady=2)
        
        # Basic operations
        basic_ops = ttk.LabelFrame(self.root, text="Basic Operations", padding="10")
        basic_ops.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        ttk.Button(basic_ops, text="Load & Decode .exp", command=self.load_and_decode, width=20).grid(row=0, column=0, padx=5, pady=2)
        ttk.Button(basic_ops, text="Save as .exp", command=self.save_as_exp, width=20).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(basic_ops, text="Save as Text", command=self.save_as_text, width=20).grid(row=0, column=2, padx=5, pady=2)
        ttk.Button(basic_ops, text="Analyze Config", command=self.analyze_config, width=20).grid(row=0, column=3, padx=5, pady=2)
        
        # Configuration editors
        editors_frame = ttk.LabelFrame(self.root, text="Configuration Editors", padding="10")
        editors_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        ttk.Label(editors_frame, text="Edit configuration objects and groups:").grid(row=0, column=0, columnspan=4, pady=5)
        
        # Row 1: Basic objects
        ttk.Button(editors_frame, text="🔒 Security Zones", command=self.open_zone_editor, width=22).grid(row=1, column=0, padx=3, pady=2)
        ttk.Button(editors_frame, text="📍 Address Objects", command=self.open_address_editor, width=22).grid(row=1, column=1, padx=3, pady=2)
        ttk.Button(editors_frame, text="🔌 Service Objects", command=self.open_service_editor, width=22).grid(row=1, column=2, padx=3, pady=2)
        
        # Row 2: Groups
        ttk.Button(editors_frame, text="📁 Address Groups", command=self.open_address_groups, width=22).grid(row=2, column=0, padx=3, pady=2)
        ttk.Button(editors_frame, text="📁 Service Groups", command=self.open_service_groups, width=22).grid(row=2, column=1, padx=3, pady=2)
        ttk.Button(editors_frame, text="🌐 Interfaces", command=self.open_interface_editor, width=22).grid(row=2, column=2, padx=3, pady=2)
        
        # Row 3: Network Configuration  
        ttk.Button(editors_frame, text="🏷️ VLANs", command=self.open_vlan_editor, width=22).grid(row=3, column=0, padx=3, pady=2)
        
        # Status area
        status_frame = ttk.LabelFrame(self.root, text="Status / Output", padding="10")
        status_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=5)
        
        self.output_text = scrolledtext.ScrolledText(status_frame, height=20, width=110)
        self.output_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(4, weight=1)
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)
        
        self.log("✓ Ready. Load a configuration file to begin editing.")
        self.log("💡 Tip: Use 'Refresh' buttons in group editors after adding new objects.")
    
    def log(self, message):
        """Add message to output area."""
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.root.update()
    
    def clear_log(self):
        """Clear the output area."""
        self.output_text.delete(1.0, tk.END)
    
    def browse_input(self):
        """Browse for input file."""
        filename = filedialog.askopenfilename(
            title="Select Input File",
            filetypes=[
                ("SonicWall Export", "*.exp"),
                ("Text Files", "*.txt"),
                ("All Files", "*.*")
            ]
        )
        if filename:
            self.input_file.set(filename)
            if filename.endswith('.exp'):
                self.output_file.set(filename.replace('.exp', '.txt'))
            elif filename.endswith('.txt'):
                self.output_file.set(filename.replace('.txt', '_new.exp'))
    
    def browse_output(self):
        """Browse for output file."""
        filename = filedialog.asksaveasfilename(
            title="Save Output File As",
            filetypes=[
                ("Text Files", "*.txt"),
                ("SonicWall Export", "*.exp"),
                ("All Files", "*.*")
            ]
        )
        if filename:
            self.output_file.set(filename)
    
    def decode_exp_file(self, exp_file_path):
        """Decode a SonicWall .exp file."""
        with open(exp_file_path, 'rb') as f:
            content = f.read()
        
        content_str = content.decode('utf-8', errors='ignore')
        
        if content_str.endswith('&&'):
            content_str = content_str[:-2] + '=='
        elif content_str.endswith('&'):
            content_str = content_str[:-1] + '='
        
        decoded = base64.b64decode(content_str)
        decoded_str = decoded.decode('utf-8', errors='ignore')
        
        params = urllib.parse.parse_qs(decoded_str, keep_blank_values=True)
        
        config = {}
        for key, value in params.items():
            config[key] = value[0] if len(value) == 1 else value
        
        return config
    
    def load_and_decode(self):
        """Load and decode a configuration file."""
        if not self.input_file.get():
            messagebox.showerror("Error", "Please select an input file")
            return
        
        self.clear_log()
        
        try:
            self.log(f"Loading: {self.input_file.get()}")
            self.config = self.decode_exp_file(self.input_file.get())
            
            self.log(f"\n✓ Configuration loaded successfully!")
            self.log(f"  Total parameters: {len(self.config)}")
            
            if 'shortProdName' in self.config:
                self.log(f"  Model: {self.config['shortProdName']}")
            if 'buildNum' in self.config:
                self.log(f"  Firmware: {self.config['buildNum']}")
            
            # Count objects
            zone_count = len([k for k in self.config if k.startswith('zoneObjId_')])
            addr_count = len([k for k in self.config if k.startswith('addrObjId_')])
            svc_count = len([k for k in self.config if k.startswith('svcObjId_')])
            addr_grp_count = len([k for k in self.config if k.startswith('addrGrpId_')])
            svc_grp_count = len([k for k in self.config if k.startswith('svcGrpId_')])
            
            self.log(f"\n  Security Zones: {zone_count}")
            self.log(f"  Address Objects: {addr_count}")
            self.log(f"  Service Objects: {svc_count}")
            self.log(f"  Address Groups: {addr_grp_count}")
            self.log(f"  Service Groups: {svc_grp_count}")
            
            self.log("\n✓ Ready to edit! Use the Configuration Editors above.")
            
        except Exception as e:
            self.log(f"\n✗ Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to load configuration:\n{str(e)}")
    
    def save_as_exp(self):
        """Save configuration as .exp file."""
        if not self.config:
            messagebox.showerror("Error", "No configuration loaded")
            return
        
        if not self.output_file.get():
            messagebox.showerror("Error", "Please specify an output file")
            return
        
        try:
            self.log(f"\nSaving to: {self.output_file.get()}")
            
            params = []
            for key, value in self.config.items():
                if isinstance(value, list):
                    for v in value:
                        params.append(f"{key}={v}")
                else:
                    params.append(f"{key}={value}")
            
            url_encoded = "&".join(params)
            b64_encoded = base64.b64encode(url_encoded.encode('utf-8')).decode('utf-8')
            
            if b64_encoded.endswith('=='):
                b64_encoded = b64_encoded[:-2] + '&&'
            elif b64_encoded.endswith('='):
                b64_encoded = b64_encoded[:-1] + '&'
            
            with open(self.output_file.get(), 'w', encoding='utf-8') as f:
                f.write(b64_encoded)
            
            self.log("✓ Configuration saved successfully!")
            messagebox.showinfo("Success", "Configuration saved as .exp file!")
            
        except Exception as e:
            self.log(f"✗ Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to save:\n{str(e)}")
    
    def save_as_text(self):
        """Save configuration as text file."""
        if not self.config:
            messagebox.showerror("Error", "No configuration loaded")
            return
        
        if not self.output_file.get():
            messagebox.showerror("Error", "Please specify an output file")
            return
        
        try:
            self.log(f"\nSaving to: {self.output_file.get()}")
            
            with open(self.output_file.get(), 'w', encoding='utf-8') as f:
                f.write("# SonicWall Configuration Export\n\n")
                for key in sorted(self.config.keys()):
                    value = self.config[key]
                    if isinstance(value, str):
                        value = value.replace('\n', '\\n').replace('\r', '\\r')
                    f.write(f"{key}={value}\n")
            
            self.log("✓ Configuration saved as text file!")
            messagebox.showinfo("Success", "Configuration saved!")
            
        except Exception as e:
            self.log(f"✗ Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to save:\n{str(e)}")
    
    def analyze_config(self):
        """Analyze the loaded configuration."""
        if not self.config:
            messagebox.showerror("Error", "No configuration loaded")
            return
        
        self.clear_log()
        self.log("Configuration Analysis")
        self.log("=" * 70)
        
        if 'shortProdName' in self.config:
            self.log(f"Model: {self.config['shortProdName']}")
        if 'buildNum' in self.config:
            self.log(f"Firmware: {self.config['buildNum']}")
        if 'checksum' in self.config:
            self.log(f"Checksum: {self.config['checksum']}")
        
        counts = {
            'Security Zones': len([k for k in self.config if k.startswith('zoneObjId_')]),
            'Address Objects': len([k for k in self.config if k.startswith('addrObjId_')]),
            'Service Objects': len([k for k in self.config if k.startswith('svcObjId_')]),
            'Address Groups': len([k for k in self.config if k.startswith('addrGrpId_')]),
            'Service Groups': len([k for k in self.config if k.startswith('svcGrpId_')]),
            'User Objects': len([k for k in self.config if k.startswith('userObjId_')]),
            'Schedules': len([k for k in self.config if k.startswith('sched_grpToGrp_')]),
        }
        
        self.log(f"\nObject Counts:")
        for name, count in counts.items():
            if count > 0:
                self.log(f"  {name}: {count}")
        
        self.log(f"\nTotal Configuration Parameters: {len(self.config)}")
    
    def open_zone_editor(self):
        """Open the security zones editor."""
        if not self.config:
            messagebox.showerror("Error", "Please load a configuration file first")
            return
        
        ZoneEditor(self.root, self.config)
    
    def open_address_editor(self):
        """Open the address objects editor."""
        if not self.config:
            messagebox.showerror("Error", "Please load a configuration file first")
            return
        
        AddressObjectEditor(self.root, self.config)
    
    def open_service_editor(self):
        """Open the service objects editor."""
        if not self.config:
            messagebox.showerror("Error", "Please load a configuration file first")
            return
        
        ServiceObjectEditor(self.root, self.config)
    
    def open_address_groups(self):
        """Open address groups editor."""
        if not self.config:
            messagebox.showerror("Error", "Please load a configuration file first")
            return
        
        AddressGroupEditor(self.root, self.config)
    
    def open_service_groups(self):
        """Open service groups editor."""
        if not self.config:
            messagebox.showerror("Error", "Please load a configuration file first")
            return
        
        ServiceGroupEditor(self.root, self.config)
    
    def open_interface_editor(self):
        """Open interface editor."""
        if not self.config:
            messagebox.showerror("Error", "Please load a configuration file first")
            return
        
        InterfaceEditor(self.root, self.config)
    
    def open_vlan_editor(self):
        """Open VLAN editor."""
        if not self.config:
            messagebox.showerror("Error", "Please load a configuration file first")
            return
        
        VLANEditor(self.root, self.config)


def main():
    """Main entry point for the application."""
    root = tk.Tk()
    app = SonicWallConverterCompleteGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
