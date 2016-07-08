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
Init for Backend testsuite
"""

from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_disk import GeneralDisk
from ci.tests.general.general_storagerouter import GeneralStorageRouter


def setup():
    """
    Setup for Backend package, will be executed when any test in this package is being executed
    Make necessary changes before being able to run the tests
    :return: None
    """
    General.validate_required_config_settings(settings={'backend': ['name']})
    my_sr = GeneralStorageRouter.get_local_storagerouter()
    if GeneralStorageRouter.has_roles(storagerouter=my_sr, roles='DB') is False:
        GeneralDisk.add_db_role(my_sr)


def teardown():
    """
    Teardown for Backend package, will be executed when all started tests in this package have ended
    Removal actions of possible things left over after the test-run
    :return: None
    """
    alba_backend = GeneralAlba.get_by_name(General.get_config().get('backend', 'name'))
    if alba_backend is not None:
        GeneralAlba.unclaim_disks(alba_backend)
        GeneralAlba.remove_alba_backend(alba_backend)
