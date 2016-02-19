# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Flexible disk layout testsuite
"""

import logging
from ci.tests.general.connection import Connection
from ci.tests.general.general import General
from ci.tests.general.general_disk import GeneralDisk
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from nose.plugins.skip import SkipTest
from ovs.extensions.generic.sshclient import SSHClient


class ContinueTesting(object):
    """
    Class indicating whether the tests should go on
    """
    def __init__(self):
        self.state = True
        pass

    def set_state(self, state):
        """
        Update the state
        :param state: New state to set
        :return: None
        """
        self.state = state


class TestFlexibleDiskLayout(object):
    """
    Flexible disk layout testsuite
    """
    tests_to_run = General.get_tests_to_run(General.get_test_level())
    continue_testing = ContinueTesting()

    logger = logging.getLogger('test_flexible_disk_layout')

    ######################
    # SETUP AND TEARDOWN #
    ######################

    @staticmethod
    def setup():
        """
        Make necessary changes before being able to run the tests
        :return: None
        """
        pass

    @staticmethod
    def teardown():
        """
        Removal actions of possible things left over after the test-run
        :return: None
        """
        pass

    #########
    # TESTS #
    #########

    @staticmethod
    def fdl_0001_match_model_with_reality_test():
        """
        FDL-0001 - disks in ovs model should match actual physical disk configuration
        """
        General.check_prereqs(testcase_number=1,
                              tests_to_run=TestFlexibleDiskLayout.tests_to_run)
        if TestFlexibleDiskLayout.continue_testing.state is False:
            raise SkipTest()

        GeneralStorageRouter.sync_with_reality()

        physical_disks = dict()
        modelled_disks = dict()
        loops = dict()

        api = Connection()

        TestFlexibleDiskLayout.logger.setLevel('INFO')
        storagerouters = GeneralStorageRouter.get_storage_routers()
        for storagerouter in storagerouters:
            root_client = SSHClient(storagerouter, username='root')
            hdds, ssds = GeneralDisk.get_physical_disks(client=root_client)
            physical_disks[storagerouter.guid] = hdds
            physical_disks[storagerouter.guid].update(ssds)
            loop_devices = General.get_loop_devices(client=root_client)
            loops[storagerouter.guid] = loop_devices

        data = api.list('disks')
        for guid in data:
            disk = api.fetch('disks', guid)
            if not disk['storagerouter_guid'] in modelled_disks:
                modelled_disks[disk['storagerouter_guid']] = dict()
            if not disk['name'] in loops[disk['storagerouter_guid']]:
                modelled_disks[disk['storagerouter_guid']][disk['name']] = {'is_ssd': disk['is_ssd']}

        TestFlexibleDiskLayout.logger.info('PDISKS: {0}'.format(physical_disks))
        TestFlexibleDiskLayout.logger.info('MDISKS: {0}'.format(modelled_disks))

        assert len(modelled_disks.keys()) == len(physical_disks.keys()),\
            "Nr of modelled/physical disks is NOT equal!:\n PDISKS: {0}\nMDISKS: {1}".format(modelled_disks,
                                                                                             physical_disks)

        for guid in physical_disks.keys():
            assert len(physical_disks[guid]) == len(modelled_disks[guid]),\
                "Nr of modelled/physical disks differs for storagerouter {0}:\n{1}\n{2}".format(guid,
                                                                                                physical_disks[guid],
                                                                                                modelled_disks[guid])

        # basic check on hdd/ssd
        for guid in physical_disks.keys():
            mdisks = modelled_disks[guid]
            pdisks = physical_disks[guid]
            for key in mdisks.iterkeys():
                assert mdisks[key]['is_ssd'] == pdisks[key]['is_ssd'],\
                    "Disk incorrectly modelled for storagerouter {0}\n,mdisk:{1}\n,pdisk:{2}".format(guid,
                                                                                                     mdisks[key],
                                                                                                     pdisks[key])

    @staticmethod
    def fdl_0002_add_remove_partition_with_role_and_crosscheck_model_test():
        """
        FDL-0002 - create/remove disk partition using full disk and verify ovs model
        - look for an unused disk
        - add a partition using full disk and assign a DB role to the partition
        - validate ovs model is correctly updated with DB role
        - cleanup that partition
        - verify ovs model is correctly updated
        """
        General.check_prereqs(testcase_number=2,
                              tests_to_run=TestFlexibleDiskLayout.tests_to_run)
        if TestFlexibleDiskLayout.continue_testing.state is False:
            raise SkipTest()

        my_sr = GeneralStorageRouter.get_local_storagerouter()

        unused_disks = GeneralDisk.get_unused_disks()
        if not unused_disks:
            raise SkipTest("At least one unused disk should be available for partition testing")

        api = Connection()

        hdds = dict()
        ssds = dict()
        mdisks = api.list('disks')
        for guid in mdisks:
            disk = api.fetch('disks', guid)
            if disk['storagerouter_guid'] == my_sr.guid:
                if disk['is_ssd']:
                    ssds['/dev/' + disk['name']] = disk
                else:
                    hdds['/dev/' + disk['name']] = disk

        all_disks = dict(ssds)
        all_disks.update(hdds)
        print all_disks
        print all_disks.keys()

        # check no partitions are modelled for unused disks
        partitions = api.list('diskpartitions')
        partitions_detected = False
        disk_guid = ''
        for path in unused_disks:
            disk_guid = all_disks[path]
            for partition_guid in partitions:
                partition = api.fetch('diskpartitions', partition_guid)
                if partition['disk_guid'] == disk_guid:
                    partitions_detected = True
        assert partitions_detected is False, 'Existing partitions detected on unused disks!'

        # try partition a disk using it's full reported size
        disk = all_disks[unused_disks[0]]
        GeneralDisk.configure_disk(storagerouter_guid=my_sr.guid,
                                   disk_guid=disk['guid'],
                                   partition_guid=None,
                                   offset=0,
                                   size=int(disk['size']),
                                   roles=['DB'])

        # lookup partition in model
        mountpoint = None
        partitions = api.list('diskpartitions')
        for partition_guid in partitions:
            partition = api.fetch('diskpartitions', partition_guid)
            if partition['disk_guid'] == disk['guid'] and 'DB' in str(partition['roles']):
                mountpoint = partition['mountpoint']
                break

        assert mountpoint, 'New partition was not detected in model'

        # cleanup disk partition
        cmd = 'umount {0}; rmdir {0}'.format(mountpoint)
        General.execute_command_on_node(my_sr.ip, cmd)

        cmd = 'parted -s {0} rm 1'.format(disk['path'])
        General.execute_command_on_node(my_sr.ip, cmd)

        # wipe partition table to be able to reuse this disk in another test
        cmd = 'dd if=/dev/zero of={0} bs=1M count=64'.format(disk['path'])
        General.execute_command_on_node(my_sr.ip, cmd)

        GeneralStorageRouter.sync_with_reality()

        # verify partition no longer exists in ovs model
        is_partition_removed = True
        partition = dict()
        partitions = api.list('diskpartitions')
        for partition_guid in partitions:
            partition = api.fetch('diskpartitions', partition_guid)
            if partition['disk_guid'] == disk_guid and 'DB' in partition['roles']:
                is_partition_removed = False
                break

        assert is_partition_removed,\
            'New partition was not deleted successfully from system/model!\n{0}'.format(partition)
