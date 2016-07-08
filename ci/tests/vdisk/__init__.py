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

"""
Init for vDisk testsuite
"""

from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_vdisk import GeneralVDisk
from ci.tests.general.general_vpool import GeneralVPool

from ovs.dal.lists.vdisklist import VDiskList


def setup():
    """
    Setup for VirtualDisk package, will be executed when any test in this package is being executed
    Make necessary changes before being able to run the tests
    :return: None
    """
    General.validate_required_config_settings(settings={'vpool': ['name'],
                                                        'backend': ['name']})
    GeneralAlba.prepare_alba_backend()
    _, vpool_params = GeneralVPool.add_vpool(vpool_parameters={'preset': GeneralAlba.ONE_DISK_PRESET})
    GeneralVPool.validate_vpool_sanity(expected_settings=vpool_params)


def teardown():
    """
    Teardown for VirtualDisk package, will be executed when all started tests in this package have ended
    Removal actions of possible things left over after the test-run
    :return: None
    """
    vpool_name = General.get_config().get("vpool", "name")
    vpool = GeneralVPool.get_vpool_by_name(vpool_name)

    for vd in VDiskList.get_vdisks():
        GeneralVDisk.delete_volume(vd, vpool, loop_device='loop0')

    if vpool is not None:
        GeneralVPool.remove_vpool(vpool)

    alba_backend = GeneralAlba.get_by_name(General.get_config().get('backend', 'name'))
    if alba_backend is not None:
        GeneralAlba.unclaim_disks_and_remove_alba_backend(alba_backend=alba_backend)
