# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Non-Commercial License, Version 1.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/OVS_NON_COMMERCIAL
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

from nose.plugins.skip import SkipTest
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.generic.system import System
from ovs.lib.disk import DiskController
from ovs.lib.storagerouter import StorageRouterController

from ci.tests.general import general
from ci.tests.general.connection import Connection

log = logging.getLogger('test_flexible_disk_layout')
vpool_name = general.test_config.get("vpool", "vpool_name")
vpool_name = 'api-' + vpool_name


class ContinueTesting:
    def __init__(self):
        pass

__continue_testing = ContinueTesting()
__continue_testing.state = True


def setup():

    pass


def teardown():

    pass


def fdl_0000_disklayout_prerequisites_test():
    """
    FDL-0000 - prerequisite tests for complete test suite
    """
    __continue_testing.state = True
    pass


def fdl_0001_match_model_with_reality_test():
    """
    FDL-0001 - disks in ovs model should match actual physical disk configuration
    """
    if not __continue_testing.state:
        raise SkipTest()

    DiskController.sync_with_reality()

    physical_disks = dict()
    modelled_disks = dict()

    my_sr = System.get_my_storagerouter()

    api = Connection(my_sr.ip, general.test_config.get('main', 'username'),
                     general.test_config.get('main', 'password'))
    api.authenticate()

    log.setLevel('INFO')
    storagerouters = StorageRouterList.get_storagerouters()
    for storagerouter in storagerouters:
        hdds, ssds = general.get_physical_disks(storagerouter.ip)
        physical_disks[storagerouter.guid] = hdds
        physical_disks[storagerouter.guid].update(ssds)

    data = api.list('disks')
    for guid in data:
        disk = api.fetch('disks', guid)
        if not disk['storagerouter_guid'] in modelled_disks:
            modelled_disks[disk['storagerouter_guid']] = dict()
        modelled_disks[disk['storagerouter_guid']][disk['name']] = {'is_ssd': disk['is_ssd']}

    log.info('PDISKS: {0}'.format(physical_disks))
    log.info('MDISKS: {0}'.format(modelled_disks))

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


def fdl_0002_add_remove_partition_with_role_and_crosscheck_model_test():
    """
    FDL-0002 - create/remove disk partition using full disk and verify ovs model
    - look for an unused disk
    - add a partition using full disk and assign a DB role to the partition
    - validate ovs model is correctly updated with DB role
    - cleanup that partition
    - verify ovs model is correctly updated
    """

    if not __continue_testing.state:
        raise SkipTest()

    my_sr = System.get_my_storagerouter()

    unused_disks = general.get_unused_disks()
    if not unused_disks:
        raise SkipTest("At least one unused disk should be available for partition testing")

    api = Connection(my_sr.ip, general.test_config.get('main', 'username'),
                     general.test_config.get('main', 'password'))
    api.authenticate()

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
    partition = None
    offset = 0
    size = int(disk['size'])
    roles = ['DB']
    StorageRouterController.configure_disk(my_sr.guid, disk['guid'], partition, offset, size, roles)

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
    general.execute_command_on_node(my_sr.ip, cmd)

    cmd = 'parted -s {0} rm 1'.format(disk['path'])
    general.execute_command_on_node(my_sr.ip, cmd)

    # wipe partition table to be able to reuse this disk in another test
    cmd = 'dd if=/dev/zero of={0} bs=1M count=64'.format(disk['path'])
    general.execute_command_on_node(my_sr.ip, cmd)

    DiskController.sync_with_reality()

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
