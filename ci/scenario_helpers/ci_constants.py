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
from ci.api_lib.helpers.ci_constants import CIConstants as _CIConstants


class CIConstants(_CIConstants):
    """
    Collection of multiple constants and constant related instances
    """
    SETTINGS_LOC = "/opt/OpenvStorage/ci/config/settings.json"

    FIO_BIN = {'url': 'http://www.include.gr/fio.bin.latest', 'location': '/tmp/fio.bin.latest'}
    FIO_BIN_EE = {'url': 'http://www.include.gr/fio.bin.latest.ee', 'location': '/tmp/fio.bin.latest'}

    DATA_TEST_CASES = [(0, 100), (30, 70), (40, 60), (50, 50), (70, 30), (100, 0)]  # read write patterns to test (read, write)

    CLOUD_INIT_DATA = {
        'script_loc': 'http://fileserver.cloudfounders.com/QA/cloud-init/create-config-drive',
        'script_dest': '/tmp/cloud_init_script.sh',
        'user-data_loc': '/tmp/user-data-migrate-test',
        'config_dest': '/tmp/cloud-init-config-migrate-test'}

    # hypervisor details
    VM_USERNAME = 'root'  # vm credentials & details
    VM_PASSWORD = 'rooter'
    VM_VCPUS = 4
    VM_VRAM = 1024  # In MB
    VM_OS_TYPE = 'ubuntu16.04'
    VM_CREATION_TIMEOUT = 12 * 60

    VM_WAIT_TIME = 300  # wait time before timing out on the vm install in seconds

    VDISK_THREAD_LIMIT = 5  # Each monitor thread queries x amount of vdisks
    FIO_VDISK_LIMIT = 50  # Each fio uses x disks

    IO_REFRESH_RATE = 5  # Refresh rate used for polling IO
    AMOUNT_TO_WRITE = 1 * 1024 ** 3  # Amount of data to RW to produce IO

    HA_TIMEOUT = 300

    @classmethod
    def get_shell_user(cls):
        """
        Gets the user configured within the setup
        :return: dict with the users credentials
        :rtype: dict
        """
        return {'username': cls.SETUP_CFG['ci']['user']['shell']['username'],
                'password': cls.SETUP_CFG['ci']['user']['shell']['password']}

    @classmethod
    def get_images(cls):
        """
        Gets images specified in the settings.json
        :return: 
        """
        return cls.SETTINGS['images']

    with open(SETTINGS_LOC, 'r') as JSON_SETTINGS:
        SETTINGS = json.load(JSON_SETTINGS)
