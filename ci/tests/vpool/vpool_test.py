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
vPool testsuite
"""

import re
import time
from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_disk import GeneralDisk
from ci.tests.general.general_hypervisor import GeneralHypervisor
from ci.tests.general.general_service import GeneralService
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ci.tests.general.general_vdisk import GeneralVDisk
from ci.tests.general.general_vpool import GeneralVPool

from ovs.extensions.generic.sshclient import SSHClient


class TestVPool(object):
    """
    vPool testsuite
    """
    #########
    # TESTS #
    #########

    @staticmethod
    def add_remove_alba_vpool_test():
        """
        Create a vPool using default values (from autotest.cfg)
        If a vPool with name already exists, remove it and create a new vPool
        Validate the newly created vPool is correctly running
        Remove the newly created vPool and validate everything related to the vPool has been cleaned up
        """
        # Raise if vPool already exists
        vpool_name = 'add-delete-alba-vpool'
        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        if vpool is not None:
            raise RuntimeError('vPool with name "{0}" still exists'.format(vpool_name))

        # Add vPool and validate health
        vpool, vpool_params = GeneralVPool.add_vpool(vpool_parameters={'vpool_name': vpool_name,
                                                                       'preset': GeneralAlba.ONE_DISK_PRESET})
        assert vpool is not None, 'vPool {0} was not created'.format(vpool_name)
        GeneralVPool.validate_vpool_sanity(expected_settings=vpool_params)

        # Retrieve vPool information before removal
        guid = vpool.guid
        name = vpool.name
        files = GeneralVPool.get_related_files(vpool)
        directories = GeneralVPool.get_related_directories(vpool)
        storagerouters = [sd.storagerouter for sd in vpool.storagedrivers]

        # Remove vPool and validate removal
        GeneralVPool.remove_vpool(vpool=vpool)
        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        assert vpool is None, 'vPool {0} was not deleted'.format(vpool_name)
        GeneralVPool.check_vpool_cleanup(vpool_info={'guid': guid,
                                                     'name': name,
                                                     'type': 'alba',
                                                     'files': files,
                                                     'directories': directories},
                                         storagerouters=storagerouters)

    @staticmethod
    def ovs_2263_verify_alba_namespace_cleanup_test():
        """
        Verify ALBA namespace cleanup
        Create an amount of namespaces in ALBA
        Create a vPool and create some volumes
        Verify the amount of namespaces before and after vPool creation
        Remove the vPool and the manually created namespaces
        Verify the amount of namespaces before and after vPool deletion
        """

        # Create some namespaces in alba
        no_namespaces = 3
        backend_name = General.get_config().get('backend', 'name')
        alba_backend = GeneralAlba.get_by_name(name=backend_name)
        namespace_name = 'autotest-ns_'
        namespace_name_regex = re.compile('^autotest-ns_\d$')
        for nmspc_index in range(no_namespaces):
            GeneralAlba.execute_alba_cli_action(alba_backend, 'create-namespace', ['{0}{1}'.format(namespace_name, nmspc_index), 'default'], False)
        result = GeneralAlba.list_alba_namespaces(alba_backend=alba_backend,
                                                  name=namespace_name_regex)
        assert len(result) == no_namespaces,\
            "Expected {0} namespaces present on the {1} backend, found {2}".format(no_namespaces, backend_name,
                                                                                   len(result))

        # Create a vPool and create volumes on it
        vpool, vpool_params = GeneralVPool.add_vpool(vpool_parameters={'preset': GeneralAlba.ONE_DISK_PRESET})
        GeneralVPool.validate_vpool_sanity(expected_settings=vpool_params)
        root_client = SSHClient(GeneralStorageRouter.get_local_storagerouter(), username='root')
        if GeneralHypervisor.get_hypervisor_type() == 'VMWARE':
            GeneralVPool.mount_vpool(vpool=vpool,
                                     root_client=root_client)

        vdisks = []
        for disk_index in range(no_namespaces):
            vdisks.append(GeneralVDisk.create_volume(size=10,
                                                     vpool=vpool,
                                                     root_client=root_client))
        result = GeneralAlba.list_alba_namespaces(alba_backend=alba_backend)
        assert len(result) == 2 * no_namespaces + 1,\
            "Expected {0} namespaces present on the {1} backend, found {2}".format(2 * no_namespaces + 1, backend_name, len(result))

        # Remove files and vPool
        for vdisk in vdisks:
            GeneralVDisk.delete_volume(vdisk=vdisk,
                                       vpool=vpool,
                                       root_client=root_client)

        if GeneralHypervisor.get_hypervisor_type() == 'VMWARE':
            GeneralVPool.unmount_vpool(vpool=vpool,
                                       root_client=root_client)

        GeneralVPool.remove_vpool(vpool)

        # Verify amount of namespaces
        result = GeneralAlba.list_alba_namespaces(alba_backend=alba_backend,
                                                  name=namespace_name_regex)
        assert len(result) == no_namespaces,\
            "Expected {0} namespaces present on the {1} backend, found {2}".format(no_namespaces, backend_name,
                                                                                   len(result))
        for namespace in result:
            GeneralAlba.execute_alba_cli_action(alba_backend, 'delete-namespace', [namespace['name']], False)
        result = GeneralAlba.list_alba_namespaces(alba_backend=alba_backend,
                                                  name=namespace_name_regex)
        assert len(result) == 0,\
            "Expected no namespaces present on the {1} backend, found {2}".format(no_namespaces, backend_name,
                                                                                  len(result))
