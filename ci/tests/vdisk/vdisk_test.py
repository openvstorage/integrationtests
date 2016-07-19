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

import os
from ci.tests.general.general import General
from ci.tests.general.general_vdisk import GeneralVDisk
from ci.tests.general.general_vpool import GeneralVPool
from ci.tests.general.logHandler import LogHandler
from ovs.dal.hybrids.vdisk import VDisk
from ovs.lib.scheduledtask import ScheduledTaskController


class TestVDisk(object):
    """
    Virtual Disk testsuite
    """
    logger = LogHandler.get('vdisks', name='vdisk')

    vpool_name = General.get_config().get("vpool", "name")
    assert vpool_name, 'vPool name required in autotest.cfg file'

    @staticmethod
    def ovs_3700_validate_test():
        """
        Validate something test
        """
        def _get_scrubber_log_size():
            scrubber_log_name = '/var/log/upstart/ovs-scrubber.log'
            if os.path.exists(scrubber_log_name):
                return os.stat(scrubber_log_name).st_size
            return 0

        loop = 'loop0'
        vpool = GeneralVPool.get_vpool_by_name(TestVDisk.vpool_name)
        vdisk = GeneralVDisk.create_volume(size=2, vpool=vpool, name='ovs-3700-disk', loop_device=loop, wait=True)

        GeneralVDisk.create_snapshot(vdisk=vdisk, snapshot_name='snap0')
        GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, vdisk.name, '1'), size=512)

        GeneralVDisk.create_snapshot(vdisk=vdisk, snapshot_name='snap1')
        GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, vdisk.name, '2'), size=512)

        GeneralVDisk.delete_snapshot(disk=vdisk, snapshot_name='snap1')

        GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, vdisk.name, '3'), size=512)
        GeneralVDisk.create_snapshot(vdisk=vdisk, snapshot_name='snap2')

        pre_scrubber_logsize = _get_scrubber_log_size()
        ScheduledTaskController.gather_scrub_work()
        post_scrubber_logsize = _get_scrubber_log_size()

        GeneralVDisk.delete_volume(vdisk=vdisk, vpool=vpool, loop_device=loop)

        assert post_scrubber_logsize > pre_scrubber_logsize, "Scrubber actions were not logged!"

    @staticmethod
    def ovs_3756_metadata_size_test():
        """
        Validate get/set metadata cache size for a vdisk
        """
        disk_name = 'ovs-3756-disk'
        loop = 'loop0'
        vpool = GeneralVPool.get_vpool_by_name(TestVDisk.vpool_name)
        # vdisk_size in GiB
        vdisk_size = 2
        vdisk = GeneralVDisk.create_volume(size=vdisk_size, vpool=vpool, name=disk_name, loop_device=loop, wait=True)

        metadata_page_capacity = 256
        # 8 bytes non-dedup'ed, 24 bytes for the dedup'ed flavour
        individual_page_entry = 24
        metadata_cache_page_size = metadata_page_capacity * individual_page_entry
        # metadata_cache_capacity depending on volume_size
        # 100GiB -> 102400
        # 2GiB -> 2048
        metadata_cache_capacity = vdisk_size * 1024
        default_metadata_cache_size = metadata_cache_capacity * metadata_cache_page_size

        def _validate_setting_cache_value(value_to_verify):
            disk_config_params = GeneralVDisk.get_config_params(vdisk)
            disk_config_params['metadata_cache_size'] = value_to_verify

            GeneralVDisk.set_config_params(vdisk, {'new_config_params': disk_config_params})
            disk_config_params = GeneralVDisk.get_config_params(vdisk)
            actual_value = disk_config_params['metadata_cache_size']
            assert actual_value == value_to_verify,\
                'Value after set/get differs, actual: {0}, expected: {1}'.format(actual_value, value_to_verify)

        config_params = GeneralVDisk.get_config_params(vdisk)

        # validate default metadata cache as it was not set explicitly
        default_implicit_value = config_params['metadata_cache_size']
        assert default_implicit_value == default_metadata_cache_size,\
            'Expected default cache size: {0}, got {1}'.format(default_metadata_cache_size, default_implicit_value)

        # verify set/get of specific value - larger than default
        _validate_setting_cache_value(10000 * metadata_cache_page_size)

        # verify set/get of specific value - default value
        _validate_setting_cache_value(default_metadata_cache_size)

        # verify set/get of specific value - smaller than default value
        _validate_setting_cache_value(100 * metadata_cache_page_size)

        GeneralVDisk.delete_volume(vdisk=vdisk, vpool=vpool, loop_device=loop, wait=True)

    @staticmethod
    def ovs_3791_validate_backend_sync_test():
        """
        Validate vdisk backend sync method
        """
        disk_name = 'ovs-3791-disk'
        loop = 'loop0'
        vpool = GeneralVPool.get_vpool_by_name(TestVDisk.vpool_name)
        vdisk = GeneralVDisk.create_volume(size=2, vpool=vpool, name=disk_name, loop_device=loop, wait=True)

        GeneralVDisk.create_snapshot(vdisk=vdisk, snapshot_name='snap0')
        GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, vdisk.name, '1'), size=512)
        GeneralVDisk.create_snapshot(vdisk=vdisk, snapshot_name='snap1')
        GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, vdisk.name, '2'), size=512)

        tlog_name = GeneralVDisk.schedule_backend_sync(vdisk)
        assert tlog_name[:5] == 'tlog_' and len(tlog_name) == 41,\
            'Unexpected result: {0} does not match tlog type'.format(tlog_name)

        timeout = 300
        status = False
        while timeout > 0:
            status = GeneralVDisk.is_volume_synced_up_to_snapshot(vdisk=vdisk, snapshot_id='snap1')
            print 'sync up to snapshot: {0}'.format(status)
            if status is True:
                break
            timeout -= 1
        assert status is True, 'Snapshot not synced to backend within 5 minutes'

        status = False
        timeout = 300
        while timeout > 0:
            status = GeneralVDisk.is_volume_synced_up_to_tlog(vdisk=vdisk, tlog_name=tlog_name)
            print 'sync up to tlog: {0}'.format(status)
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
        test_file_size = 15000
        loop = 'loop0'
        clone_loop = 'loop1'

        vpool = GeneralVPool.get_vpool_by_name(TestVDisk.vpool_name)
        vdisk = GeneralVDisk.create_volume(size=50, vpool=vpool, name=disk_name, loop_device=loop, wait=True)

        TestVDisk.logger.info('clone_disk_test - create initial snapshot')
        GeneralVDisk.create_snapshot(vdisk=vdisk, snapshot_name='snap0')

        TestVDisk.logger.info('clone_disk_test - create 1st {0} GB test file'.format(test_file_size / 1000.0))
        GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, test_file_name, '1'), size=test_file_size)

        TestVDisk.logger.info('clone_disk_test - create 2nd {0} GB test file'.format(test_file_size / 1000.0))
        GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, test_file_name, '2'), size=test_file_size)

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
        GeneralVDisk.delete_volume(VDisk(cloned_vdisk['diskguid']), vpool, wait=True)
        GeneralVDisk.delete_volume(vdisk, vpool, loop, wait=True)

        assert md5_sum_1 == md5_clone_1,\
            'file contents for /mnt/{0}/{1}_{2}.txt is not identical on source and clone!'.format(loop, vdisk.name, '1')
        assert md5_sum_2 == md5_clone_2,\
            'file contents for /mnt/{0}/{1}_{2}.txt is not identical on source and clone!'.format(loop, vdisk.name, '2')
