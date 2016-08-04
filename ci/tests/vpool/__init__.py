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
Init for vPool testsuite
"""

from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba


def setup():
    """
    Setup for vPool package, will be executed when any test in this package is being executed
    Make necessary changes before being able to run the tests
    :return: None
    """
    General.validate_required_config_settings(settings={'vpool': ['name', 'type', 'readcache_size', 'writecache_size', 'integrate_mgmt',
                                                                  'storage_ip', 'config_params', 'fragment_cache_on_read', 'fragment_cache_on_write'],
                                                        'backend': ['name']})
    GeneralAlba.prepare_alba_backend()


def teardown():
    """
    Teardown for vPool package, will be executed when all started tests in this package have ended
    Removal actions of possible things left over after the test-run
    :return: None
    """
    alba_backend = GeneralAlba.get_by_name(General.get_config().get('backend', 'name'))
    if alba_backend:
        GeneralAlba.unclaim_disks_and_remove_alba_backend(alba_backend=alba_backend)
