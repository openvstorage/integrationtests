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
Virtual Disk testsuite
"""

import os
from ci.tests.general.general import General
from ci.tests.general.general_vdisk import GeneralVDisk
from ci.tests.general.general_vpool import GeneralVPool
from ci.tests.general.logHandler import LogHandler
from ovs.lib.scheduledtask import ScheduledTaskController


class TestVDisk(object):
    """
    Virtual Disk testsuite
    """
    logger = LogHandler.get('vdisks', name='vdisk')
    logger.logger.propagate = False

    vpool_name = General.get_config().get("vpool", "name")
    assert vpool_name, 'vPool name required in autotest.cfg file'
    tests_to_run = General.get_tests_to_run(General.get_test_level())

    #########
    # TESTS #
    #########

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
        vdisk = GeneralVDisk.create_volume(size=2,
                                           vpool=vpool,
                                           name='ovs-3700-disk',
                                           loop_device=loop,
                                           wait=True)

        count = 2
        GeneralVDisk.create_snapshot(vdisk=vdisk,
                                     snapshot_name='snap0')
        for x in xrange(count):
            GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, vdisk.name, x),
                                            size=512)

        GeneralVDisk.create_snapshot(vdisk=vdisk,
                                     snapshot_name='snap1')
        for x in xrange(count):
            GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, vdisk.name, x),
                                            size=512)

        GeneralVDisk.delete_snapshot(disk=vdisk,
                                     snapshot_name='snap1')

        for x in xrange(count):
            GeneralVDisk.generate_hash_file(full_name='/mnt/{0}/{1}_{2}.txt'.format(loop, vdisk.name, x),
                                            size=512)
        GeneralVDisk.create_snapshot(vdisk=vdisk,
                                     snapshot_name='snap2')

        pre_scrubber_logsize = _get_scrubber_log_size()
        ScheduledTaskController.gather_scrub_work()
        post_scrubber_logsize = _get_scrubber_log_size()

        GeneralVDisk.delete_volume(vdisk=vdisk,
                                   vpool=vpool,
                                   loop_device=loop)

        assert post_scrubber_logsize > pre_scrubber_logsize, "Scrubber actions where not logged!"
