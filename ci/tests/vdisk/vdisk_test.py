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

from ci import autotests
from ci.tests.general.general import test_config
from ci.tests.general import general
from ci.tests.general.logHandler import LogHandler
from ci.tests.vdisk import vdisk_generic
from ci.tests.vpool import vpool_generic as vpool_generic

from ovs.dal.lists.vdisklist import VDiskList
from ovs.lib.scheduledtask import ScheduledTaskController

import os
import time

logger = LogHandler.get('vdisks', name='vdisk')
logger.logger.propagate = False

testsToRun = general.get_tests_to_run(autotests.get_test_level())


def setup():
    vpool_generic.add_alba_backend()
    vpool_generic.add_vpool()


def teardown():
    vpool_generic.remove_vpool()
    vpool_generic.remove_alba_backend()


def ovs_3700_validate_test():
    def get_scrubber_log_size():
        scrubber_log_name = '/var/log/upstart/ovs-scrubber.log'
        if os.path.exists(scrubber_log_name):
            return os.stat(scrubber_log_name).st_size
        return 0

    disk_name = "ovs-3700-disk"
    loop_device = 'loop0'

    vdisk_generic.create(disk_name, 2048, loop_device)

    print general.execute_command('ls -la /mnt/{0}'.format(test_config.get('vpool', 'vpool_name')))
    print general.execute_command('mount')

    # wait for disk to appear in model
    timeout = 10
    while not timeout:
        if not VDiskList.get_vdisk_by_name(disk_name):
            time.sleep(5)
        else:
            break

    count = 2
    vdisk_generic.create_snapshot(disk_name, 'snap0')
    for x in xrange(count):
        vdisk_generic.generate_hash_file('/mnt/{0}/{1}_{2}.txt'.format(loop_device, disk_name, x), 512)
    vdisk_generic.create_snapshot(disk_name, 'snap1')
    for x in xrange(count):
        vdisk_generic.generate_hash_file('/mnt/{0}/{1}_{2}.txt'.format(loop_device, disk_name, x), 512)
    vdisk_generic.delete_snapshot(disk_name, 'snap1')
    for x in xrange(count):
        vdisk_generic.generate_hash_file('/mnt/{0}/{1}_{2}.txt'.format(loop_device, disk_name, x), 512)
    vdisk_generic.create_snapshot(disk_name, 'snap2')

    pre_scrubber_logsize = get_scrubber_log_size()
    ScheduledTaskController.gather_scrub_work()
    post_scrubber_logsize = get_scrubber_log_size()

    vdisk_generic.delete(disk_name, loop_device)

    assert post_scrubber_logsize > pre_scrubber_logsize, "Scrubber actions where not logged!"
