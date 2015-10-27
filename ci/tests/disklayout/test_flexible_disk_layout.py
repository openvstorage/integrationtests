# Copyright 2014 Open vStorage NV
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

import logging
from ci.tests.general import general
from ci.tests.api.connection import Connection

from nose.plugins.skip import SkipTest

from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.generic.system import System
from ovs.lib.disk import DiskController
from ovs.lib.storagerouter import StorageRouterController

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


def test_fdl_0000():
    """
    FDL-0000 - prerequisite tests for complete test suite
    """
    __continue_testing.state = True


def test_fdl_0001():
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
        if not modelled_disks.has_key(disk['storagerouter_guid']):
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


def test_fdl_0002():
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
                ssds[disk['path']] = disk
            else:
                hdds[disk['path']] = disk

    all_disks = dict(ssds)
    all_disks.update(hdds)
    print all_disks

    # check no partitions are modelled for unused disks
    partitions = api.list('diskpartitions')
    no_partitions = True
    for path in unused_disks:
        disk_guid = all_disks[path]
        for partition_guid in partitions:
            partition = api.fetch('diskpartitions', partition_guid)
            if partition['disk_guid'] == disk_guid:
                print partition['mountpoint'], partition['folder']
                no_partitions = False
    assert no_partitions is True, 'Existing partitions detected on unused disks!'

    # try partition a disk using it's full reported size
    disk = all_disks[unused_disks[0]]
    partition = None
    offset = 0
    size = int(disk['size'])
    roles = ['DB']
    StorageRouterController.configure_disk(my_sr.guid, disk['guid'], partition, offset, size, roles)

    # lookup partition in model
    print disk
    print disk_guid
    mountpoint = None
    partitions = api.list('diskpartitions')
    for partition_guid in partitions:
        partition = api.fetch('diskpartitions', partition_guid)
        print partition_guid, partition['roles'], partition['disk_guid']
        if partition['disk_guid'] == disk['guid'] and 'DB' in str(partition['roles']):
            mountpoint = partition['mountpoint']
            print partition
            break

    assert mountpoint, 'New partition was not detected in model'

    # cleanup disk partition
    cmd = 'umount {0}; rmdir {0}'.format(mountpoint)
    general.execute_command_on_node('10.100.131.61', cmd)

    cmd = 'parted -s {0} rm 1'.format(disk['path'])
    general.execute_command_on_node('10.100.131.61', cmd)

    # wipe partition table to be able to reuse this disk in another test
    cmd = 'dd if=/dev/zero of={0} bs=1M count=64'.format(disk['path'])
    general.execute_command_on_node('10.100.131.61', cmd)

    DiskController.sync_with_reality()

    # verify partition no longer exists in ovs model
    new_partition_detected = False
    partition = dict()
    partitions = api.list('diskpartitions')
    for partition_guid in partitions:
        partition = api.fetch('diskpartitions', partition_guid)
        if partition['disk_guid'] == disk_guid and 'DB' in partition['roles']:
            new_partition_detected = True
            break

    assert not new_partition_detected,\
        'New partition was not deleted successfully from system/model!\n{0}'.format(partition)
