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
Init for Management Center testsuite
"""

from ci.tests.general.general_mgmtcenter import GeneralManagementCenter


def setup():
    """
    Setup for ManagementCenter package, will be executed when any test in this package is being executed
    Make necessary changes before being able to run the tests
    :return: None
    """
    GeneralManagementCenter.create_generic_mgmt_center()


def teardown():
    """
    Teardown for ManagementCenter package, will be executed when all started tests in this package have ended
    Removal actions of possible things left over after the test-run
    :return: None
    """
    for mgmt_center in GeneralManagementCenter.get_mgmt_centers():
        GeneralManagementCenter.remove_mgmt_center(mgmt_center)
