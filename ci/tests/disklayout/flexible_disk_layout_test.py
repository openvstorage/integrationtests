# Copyright 2016 iNuron NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
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
from ci.tests.general.general import General
from ci.tests.general.general_disk import GeneralDisk
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ci.tests.general.general_vdisk import GeneralVDisk
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
    continue_testing = ContinueTesting()

    logger = logging.getLogger('test_flexible_disk_layout')

    #########
    # TESTS #
    #########

    @staticmethod
    def fdl_0001_match_model_with_reality_test():
        """
        FDL-0001 - disks in ovs model should match actual physical disk configuration
        """
        if TestFlexibleDiskLayout.continue_testing.state is False:
            raise SkipTest('Test suite signaled to stop')
        GeneralStorageRouter.sync_with_reality()

        physical_disks = dict()
        modelled_disks = dict()
        loops = dict()

        TestFlexibleDiskLayout.logger.setLevel('INFO')
        storagerouters = GeneralStorageRouter.get_storage_routers()
        for storagerouter in storagerouters:
            root_client = SSHClient(storagerouter, username='root')
            hdds, ssds = GeneralDisk.get_physical_disks(client=root_client)
            physical_disks[storagerouter.guid] = hdds
            physical_disks[storagerouter.guid].update(ssds)
            loop_devices = General.get_loop_devices(client=root_client)
            loops[storagerouter.guid] = loop_devices

        disks = GeneralDisk.get_disks()
        for disk in disks:
            if disk.storagerouter_guid not in modelled_disks:
                modelled_disks[disk.storagerouter_guid] = dict()
            if disk.name not in loops[disk.storagerouter_guid]:
                modelled_disks[disk.storagerouter_guid][disk.name] = {'is_ssd': disk.is_ssd}

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
        if TestFlexibleDiskLayout.continue_testing.state is False:
            raise SkipTest('Test suite signaled to stop')

        my_sr = GeneralStorageRouter.get_local_storagerouter()

        unused_disks = GeneralDisk.get_unused_disks()
        if not unused_disks:
            raise SkipTest("At least one unused disk should be available for partition testing")

        hdds = dict()
        ssds = dict()
        mdisks = GeneralDisk.get_disks()
        for disk in mdisks:
            if disk.storagerouter_guid == my_sr.guid:
                if disk.is_ssd:
                    ssds['/dev/' + disk.name] = disk
                else:
                    hdds['/dev/' + disk.name] = disk

        all_disks = dict(ssds)
        all_disks.update(hdds)
        print all_disks
        print all_disks.keys()

        # check no partitions are modelled for unused disks
        partitions = GeneralDisk.get_disk_partitions()
        partitions_detected = False
        disk_guid = ''
        for path in unused_disks:
            # @TODO: remove the if when ticket OVS-4503 is solved
            if path in all_disks:
                disk_guid = all_disks[path].guid
                for partition in partitions:
                    if partition.disk_guid == disk_guid:
                        partitions_detected = True
        assert partitions_detected is False, 'Existing partitions detected on unused disks!'

        # try partition a disk using it's full reported size
        disk = all_disks[unused_disks[0]]
        GeneralDisk.configure_disk(storagerouter=my_sr,
                                   disk=disk,
                                   offset=0,
                                   size=int(disk.size),
                                   roles=['DB'])

        # lookup partition in model
        mountpoint = None
        partitions = GeneralDisk.get_disk_partitions()
        for partition in partitions:
            if partition.disk_guid == disk.guid and 'DB' in partition.roles:
                mountpoint = partition.mountpoint
                break

        assert mountpoint, 'New partition was not detected in model'

        # cleanup disk partition
        cmd = 'umount {0}; rmdir {0}'.format(mountpoint)
        General.execute_command_on_node(my_sr.ip, cmd)

        cmd = 'parted -s {0} rm 1'.format(disk.path)
        General.execute_command_on_node(my_sr.ip, cmd)

        # wipe partition table to be able to reuse this disk in another test
        GeneralVDisk.write_to_volume(location=disk.path,
                                     count=64,
                                     bs='1M',
                                     input_type='zero')
        GeneralStorageRouter.sync_with_reality()

        # verify partition no longer exists in ovs model
        is_partition_removed = True
        partitions = GeneralDisk.get_disk_partitions()
        for partition in partitions:
            if partition.disk_guid == disk_guid and 'DB' in partition.roles:
                is_partition_removed = False
                break

        assert is_partition_removed is True,\
            'New partition was not deleted successfully from system/model!'
