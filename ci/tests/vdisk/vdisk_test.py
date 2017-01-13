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
Virtual Disk testsuite
"""

from ci.tests.general.general import General
from ci.tests.general.general_vdisk import GeneralVDisk
from ci.tests.general.general_vpool import GeneralVPool
from ci.tests.general.logHandler import LogHandler
from ovs.dal.hybrids.vdisk import VDisk


class TestVDisk(object):
    """
    Virtual Disk testsuite
    """
    logger = LogHandler.get('vdisks', name='vdisk')

    vpool_name = General.get_config().get("vpool", "name")
    assert vpool_name, 'vPool name required in autotest.cfg file'

    @staticmethod
    def ovs_3791_validate_backend_sync_test():
        """
        Validate vdisk backend sync method
        """
        disk_name = 'ovs-3791-disk'
        loop = 'loop0'
        vpool = GeneralVPool.get_vpool_by_name(TestVDisk.vpool_name)
        vdisk = GeneralVDisk.create_volume(size=2, vpool=vpool, name=disk_name, loop_device=loop, wait=True)

        _, snap_id1 = GeneralVDisk.create_snapshot(vdisk=vdisk, snapshot_name='snap0')
        GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, vdisk.name, '1'), size=512)
        _, snap_id2 = GeneralVDisk.create_snapshot(vdisk=vdisk, snapshot_name='snap1')
        GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, vdisk.name, '2'), size=512)

        tlog_name = GeneralVDisk.schedule_backend_sync(vdisk)
        assert tlog_name[:5] == 'tlog_' and len(tlog_name) == 41,\
            'Unexpected result: {0} does not match tlog type'.format(tlog_name)

        timeout = 300
        status = False
        while timeout > 0:
            status = GeneralVDisk.is_volume_synced_up_to_snapshot(vdisk=vdisk, snapshot_id=snap_id2)
            TestVDisk.logger.info('sync up to snapshot: {0}'.format(status))
            if status is True:
                break
            timeout -= 1
        assert status is True, 'Snapshot not synced to backend within 5 minutes'

        status = False
        timeout = 300
        while timeout > 0:
            status = GeneralVDisk.is_volume_synced_up_to_tlog(vdisk=vdisk, tlog_name=tlog_name)
            TestVDisk.logger.info('sync up to tlog: {0}'.format(status))
            if status is True:
                break
            timeout -= 1
        assert status is True, 'Tlog not synced to backend within 5 minutes'

        GeneralVDisk.delete_volume(vdisk, vpool, loop)

    @staticmethod
    def validate_clone_disk_test():
        """
        Validate vdisk clone method
        """
        disk_name = 'clone-disk'
        clone_disk_name = 'new-cloned-disk'
        test_file_name = 'file-contents'
        test_file_size = 5000
        loop = 'loop0'
        clone_loop = 'loop1'

        vpool = GeneralVPool.get_vpool_by_name(TestVDisk.vpool_name)
        vdisk = GeneralVDisk.create_volume(size=50, vpool=vpool, name=disk_name, loop_device=loop, wait=True)

        TestVDisk.logger.info('clone_disk_test - create initial snapshot')
        GeneralVDisk.create_snapshot(vdisk=vdisk, snapshot_name='snap0')

        TestVDisk.logger.info('clone_disk_test - create 1st {0} GB test file'.format(test_file_size / 1000.0))
        GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, test_file_name, '1'),
                                        size=test_file_size)

        TestVDisk.logger.info('clone_disk_test - create 2nd {0} GB test file'.format(test_file_size / 1000.0))
        GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, test_file_name, '2'),
                                        size=test_file_size)

        GeneralVDisk.logger.info(General.execute_command('sync'))

        TestVDisk.logger.info('clone_disk_test - cloning disk')
        cloned_vdisk = GeneralVDisk.clone_volume(vdisk, clone_disk_name)
        TestVDisk.logger.info('clone_disk_test - cloned disk')

        GeneralVDisk.connect_volume(vpool, name=clone_disk_name, loop_device=clone_loop)

        md5_sum_1 = General.execute_command('md5sum /mnt/{0}/{1}_{2}.txt'.format(loop, test_file_name, '1'))[0].split('  ')[0]
        md5_sum_2 = General.execute_command('md5sum /mnt/{0}/{1}_{2}.txt'.format(loop, test_file_name, '2'))[0].split('  ')[0]
        md5_clone_1 = General.execute_command('md5sum /mnt/{0}/{1}_{2}.txt'.format(clone_loop, test_file_name, '1'))[0].split('  ')[0]
        md5_clone_2 = General.execute_command('md5sum /mnt/{0}/{1}_{2}.txt'.format(clone_loop, test_file_name, '2'))[0].split('  ')[0]

        GeneralVDisk.disconnect_volume(loop_device=clone_loop)
        GeneralVDisk.delete_volume(VDisk(cloned_vdisk['vdisk_guid']), vpool, wait=True)
        GeneralVDisk.delete_volume(vdisk, vpool, loop, wait=True)

        assert md5_sum_1 == md5_clone_1,\
            'file contents for /mnt/{0}/{1}_{2}.txt is not identical on source and clone!'.format(loop, vdisk.name, '1')
        assert md5_sum_2 == md5_clone_2,\
            'file contents for /mnt/{0}/{1}_{2}.txt is not identical on source and clone!'.format(loop, vdisk.name, '2')
