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
import json
from ci.api_lib.helpers.api import OVSClient
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.main import CONFIG_LOC
from ci.main import SETTINGS_LOC

class CIConstants(object):
    """
    Collection of multiple constants and constant related instances
    """
    FIO_BIN = {'url': 'http://www.include.gr/fio.bin.latest', 'location': '/tmp/fio.bin.latest'}
    FIO_BIN_EE = {'url': 'http://www.include.gr/fio.bin.latest.ee', 'location': '/tmp/fio.bin.latest'}

    REQUIRED_PACKAGES_HYPERVISOR = ['qemu-kvm', 'libvirt0', 'python-libvirt', 'virtinst']
    REQUIRED_PACKAGE_CLOUD_INIT = ['genisoimage']

    with open(CONFIG_LOC, 'r') as JSON_CONFIG:
        SETUP_CFG = json.load(JSON_CONFIG)

    with open(SETTINGS_LOC, 'r') as JSON_SETTINGS:
        SETTINGS = json.load(JSON_SETTINGS)

    DATA_TEST_CASES = [(0, 100), (30, 70), (40, 60), (50, 50), (70, 30), (100, 0)]  # read write patterns to test (read, write)

    CLOUD_INIT_DATA = {
        'script_loc': 'https://raw.githubusercontent.com/kinvaris/cloud-init/master/create-config-drive',
        'script_dest': '/tmp/cloud_init_script.sh',
        'user-data_loc': '/tmp/user-data-migrate-test',
        'config_dest': '/tmp/cloud-init-config-migrate-test'
    }

    # collect details about parent hypervisor
    PARENT_HYPERVISOR_INFO = SETUP_CFG['ci'].get('hypervisor')

    # hypervisor details
    HYPERVISOR_TYPE = SETUP_CFG['ci']['local_hypervisor']['type']
    HYPERVISOR_USER = SETUP_CFG['ci']['local_hypervisor']['user']
    HYPERVISOR_PASSWORD = SETUP_CFG['ci']['local_hypervisor']['password']

    HYPERVISOR_INFO = {'type': HYPERVISOR_TYPE,
                       'user': HYPERVISOR_USER,
                       'password': HYPERVISOR_PASSWORD}

    VM_USERNAME = 'root'  # vm credentials & details
    VM_PASSWORD = 'rooter'
    VM_VCPUS = 4
    VM_VRAM = 1024  # In MB
    VM_OS_TYPE = 'ubuntu16.04'

    VM_WAIT_TIME = 300  # wait time before timing out on the vm install in seconds

    VDISK_THREAD_LIMIT = 5  # Each monitor thread queries x amount of vdisks
    FIO_VDISK_LIMIT = 50  # Each fio uses x disks

    IO_REFRESH_RATE = 5  # Refresh rate used for polling IO
    AMOUNT_TO_WRITE = 1 * 1024 ** 3  # Amount of data to RW to produce IO

    @classmethod
    def get_api_instance(cls):
        """
        Fetches the api instance using the constants provided by the configuration files
        :return: ovsclient instance
        :rtype: ci.api_lib.helpers.api.OVSClient
        """
        return OVSClient(cls.SETUP_CFG['ci']['grid_ip'],
                         cls.SETUP_CFG['ci']['user']['api']['username'],
                         cls.SETUP_CFG['ci']['user']['api']['password'])

    @classmethod
    def get_parent_hypervisor_instance(cls):
        """
        Fetches the parent hypervisor instance
        :return: 
        """
        return HypervisorFactory.get(cls.PARENT_HYPERVISOR_INFO['ip'],
                                     cls.PARENT_HYPERVISOR_INFO['user'],
                                     cls.PARENT_HYPERVISOR_INFO['password'],
                                     cls.PARENT_HYPERVISOR_INFO['type'])

    @classmethod
    def get_storagerouters_for_ha(cls):
        """
        Gets storagerouters based on roles
        :return: 
        """
        voldr_str_1 = None  # Will act as volumedriver node
        voldr_str_2 = None  # Will act as volumedriver node
        compute_str = None  # Will act as compute node
        for node_ip, node_details in cls.PARENT_HYPERVISOR_INFO['vms'].iteritems():
            if node_details['role'] == "VOLDRV":
                if voldr_str_1 is None:
                    voldr_str_1 = StoragerouterHelper.get_storagerouter_by_ip(node_ip)
                elif voldr_str_2 is None:
                    voldr_str_2 = StoragerouterHelper.get_storagerouter_by_ip(node_ip)
            elif node_details['role'] == "COMPUTE" and compute_str is None:
                compute_str = StoragerouterHelper.get_storagerouter_by_ip(node_ip)
        return voldr_str_1, voldr_str_2, compute_str

    @classmethod
    def get_images(cls):
        """
        Gets images specified in the settings.json
        :return: 
        """
        return cls.SETTINGS['images']

