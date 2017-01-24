# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.


class SdkOptionMapping(object):

    disk_options_mapping = {
        "mountpoint": {
            "option": "path",
            "values": None,
            "type": str
        },
        "pool": {
            "option": "pool",
            "values": None,
            "type": str
        },
        "vol": {
            "option": "vol",
            "values": None,
            "type": str
        },
        "device": {
            "option": "device",
            "values": ["cdrom", "disk", "lun", "sata", "floppy"],
            "default": "disk",
            "type": str
        },
        "boot_order": {
            "option": "boot_order",
            "values": None,
            "type": int
        },
        "bus": {
            "option": "bus",
            "values": ["ide", "sata", "iscsi", "sata", "usb", "virtio", "xen"],
            "default": "virtio",
            "type": str
        },
        "removable": {
            "option": "removable",
            "values": ["on", "off"],
            "type": str
        },
        "readonly": {
            "option": "readonly",
            "values": ["on", "off"],
            "type": str
        },
        "shareable": {
            "option": "shareable",
            "values": ["on", "off"],
            "type": str
        },
        "size": {
            "option": "size",
            "values": None,
            "type": float
        },
        "format": {
            "option": "format",
            "values": ["raw", "qcow2", "vmdk"],
            "default": "raw",
            "type": str
        },
        "sparse": {
            "option": "sparse",
            "values": ["yes", "no"],
            "default": "yes",
            "type": str
        },
    }
    network_option_mapping = {
        "bridge": {
            "option": "bridge",
            "values": None,
            "default": None,
            "type": str
        },
        "network": {
            "option": "network",
            "values": None,
            "default": None,
            "type": str
        },
        "model": {
            "option": "model",
            "values": ["e1000", "rtl8139", "virtio"],
            "default": "e1000",
            "type": str
        },
        "mac": {
            "option": "mac",
            "values": None,
            "default": "random",
            "type": str
        },
    }
