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
Init for Arakoon testsuite
"""

from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_arakoon import GeneralArakoon
from ci.tests.general.general_backend import GeneralBackend
from ci.tests.general.general_disk import GeneralDisk
from ci.tests.general.general_service import GeneralService
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ovs.extensions.db.etcd.configuration import EtcdConfiguration
from ovs.extensions.generic.sshclient import SSHClient

TEST_CLEANUP = ['/var/tmp/arakoon/OVS*', '/etc/init/ovs-arakoon-OVS_*',
                '/var/log/arakoon/ar_00*', '/var/log/arakoon/OVS_*',
                '/var/tmp/arakoon/ar_00*']
KEY_CLEANUP = ['ar_0001',
               'OVS_3671-single-node-cluster',
               'OVS_3671-multi-node-cluster']


def setup():
    """
    Setup for Arakoon package, will be executed when any test in this package is being executed
    Make necessary changes before being able to run the tests
    :return: None
    """
    autotest_config = General.get_config()
    backend_name = autotest_config.get('backend', 'name')
    assert backend_name, 'Please fill out a backend name in the autotest.cfg file'
    backend = GeneralBackend.get_by_name(backend_name)
    if backend is not None:
        GeneralAlba.remove_alba_backend(backend.alba_backend)

    for storagerouter in GeneralStorageRouter.get_masters():
        root_client = SSHClient(storagerouter, username='root')
        if GeneralService.get_service_status(name='ovs-scheduled-tasks',
                                             client=root_client) is True:
            GeneralService.stop_service(name='ovs-scheduled-tasks',
                                        client=root_client)

    storagerouters = GeneralStorageRouter.get_storage_routers()
    for sr in storagerouters:
        root_client = SSHClient(sr, username='root')
        GeneralDisk.add_db_role(sr)

        for location in TEST_CLEANUP:
            root_client.run('rm -rf {0}'.format(location))

    GeneralAlba.add_alba_backend(backend_name)
    GeneralArakoon.voldrv_arakoon_checkup()


def teardown():
    """
    Teardown for Arakoon package, will be executed when all started tests in this package have ended
    Removal actions of possible things left over after the test-run
    :return: None
    """
    autotest_config = General.get_config()
    backend_name = autotest_config.get('backend', 'name')
    backend = GeneralBackend.get_by_name(backend_name)
    if backend is not None:
        GeneralAlba.remove_alba_backend(backend.alba_backend)

    for storagerouter in GeneralStorageRouter.get_masters():
        root_client = SSHClient(storagerouter, username='root')
        if GeneralService.get_service_status(name='ovs-scheduled-tasks',
                                             client=root_client) is False:
            GeneralService.start_service(name='ovs-scheduled-tasks',
                                         client=root_client)

        for location in TEST_CLEANUP:
            root_client.run('rm -rf {0}'.format(location))

    for key in KEY_CLEANUP:
        if EtcdConfiguration.exists('{0}/{1}'.format(GeneralArakoon.ETCD_CONFIG_ROOT, key), raw = True):
            EtcdConfiguration.delete('{0}/{1}'.format(GeneralArakoon.ETCD_CONFIG_ROOT, key))
