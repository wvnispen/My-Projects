#!/usr/bin/env python3
"""
SonicWall Configuration Converter - Complete Advanced GUI
Full-featured interface for viewing and editing SonicWall configurations
Includes: Zones, Address Objects, Address Groups, Service Objects, Service Groups
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
        """Get list of all address objects for dropdown."""
        addresses = []
        indices = set()
        
        for key in self.config_data.keys():
            if key.startswith('addrObjId_'):
                idx = key.split('_')[1]
                indices.add(idx)
        
        for idx in sorted(indices, key=lambda x: int(x) if x.isdigit() else 0):
            addr_name = self.config_data.get(f'addrObjId_{idx}', '')
            if addr_name:
                addresses.append(addr_name)
        
        return sorted(addresses)
    
    def extract_address_groups(self):
        """Extract address groups from config."""
        groups = {}
        indices = set()
        
        for key in self.config_data.keys():
            if key.startswith('addrGrpId_'):
                idx = key.split('_')[1]
                indices.add(idx)
        
        for idx in sorted(indices, key=lambda x: int(x) if x.isdigit() else 0):
            group_name = self.config_data.get(f'addrGrpId_{idx}', '')
            if group_name:
                # Extract members
                members = []
                member_key = f'addrGrpMembers_{idx}'
                if member_key in self.config_data:
                    members_str = self.config_data[member_key]
                    # Members are typically comma or space separated
                    if members_str:
                        members = [m.strip() for m in re.split(r'[,\s]+', members_str) if m.strip()]
                
                groups[idx] = {
                    'index': idx,
                    'id': group_name,
                    'members': members,
                }
        
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
            if search_term and search_term not in group['id'].lower():
                continue
            
            members_str = ', '.join(group['members'][:5])
            if len(group['members']) > 5:
                members_str += f' ... ({len(group['members']) - 5} more)'
            
            self.tree.insert('', 'end', text=idx,
                           values=(group['id'], len(group['members']), members_str))
    
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
            max_idx = max([int(k) for k in self.groups.keys() if k.isdigit()] + [0])
            new_idx = str(max_idx + 1)
            
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
        """Save changes back to config."""
        # Clear old group entries
        keys_to_delete = [k for k in self.config_data.keys() 
                         if k.startswith('addrGrpId_') or k.startswith('addrGrpMembers_')]
        for key in keys_to_delete:
            del self.config_data[key]
        
        # Save new groups
        for idx, group in self.groups.items():
            self.config_data[f'addrGrpId_{idx}'] = group['id']
            self.config_data[f'addrGrpMembers_{idx}'] = ','.join(group['members'])
        
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
        """Extract service groups from config."""
        groups = {}
        indices = set()
        
        for key in self.config_data.keys():
            if key.startswith('svcGrpId_'):
                idx = key.split('_')[1]
                indices.add(idx)
        
        for idx in sorted(indices, key=lambda x: int(x) if x.isdigit() else 0):
            group_name = self.config_data.get(f'svcGrpId_{idx}', '')
            if group_name:
                members = []
                member_key = f'svcGrpMembers_{idx}'
                if member_key in self.config_data:
                    members_str = self.config_data[member_key]
                    if members_str:
                        members = [m.strip() for m in re.split(r'[,\s]+', members_str) if m.strip()]
                
                groups[idx] = {
                    'index': idx,
                    'id': group_name,
                    'members': members,
                }
        
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
                members_str += f' ... ({len(group['members']) - 5} more)'
            
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
            max_idx = max([int(k) for k in self.groups.keys() if k.isdigit()] + [0])
            new_idx = str(max_idx + 1)
            
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
        """Save changes back to config."""
        # Clear old group entries
        keys_to_delete = [k for k in self.config_data.keys() 
                         if k.startswith('svcGrpId_') or k.startswith('svcGrpMembers_')]
        for key in keys_to_delete:
            del self.config_data[key]
        
        # Save new groups
        for idx, group in self.groups.items():
            self.config_data[f'svcGrpId_{idx}'] = group['id']
            self.config_data[f'svcGrpMembers_{idx}'] = ','.join(group['members'])
        
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


# Note: AddressObjectEditor and ServiceObjectEditor classes need to be included
# They are copied from the advanced GUI implementation above


class AddressObjectEditor(ConfigEditor):
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


def main():
    """Main entry point for the application."""
    root = tk.Tk()
    app = SonicWallConverterCompleteGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
