# Copyright 2015 iNuron NV
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


from ci.tests.general import general
from ci.tests.general.general import test_config

from ovs.dal.lists.vdisklist import VDiskList
from ovs.lib.vdisk import VDiskController

import random
import string
import time


def create(name, size, loop_device=None):
    cmd = "truncate -s {0}MB /mnt/{1}/{2}.raw".format(int(size), test_config.get('vpool', 'vpool_name'), name)
    general.execute_command(cmd, shell=True)

    if loop_device:
        cmd = """losetup /dev/{0} /mnt/{1}/{2}
mkdir /mnt/{0}
parted /dev/{0} mklabel gpt
parted -a optimal /dev/{0} mkpart primary ext4 0% 100%
partprobe
mkfs.ext4 /dev/{0}
mount -t ext4 /dev/{0} /mnt/{0}
""".format(loop_device, test_config.get('vpool', 'vpool_name'), name)
    general.execute_command(cmd, shell=True)


def delete(name, loop_device=None):
    if loop_device:
        cmd = """umount /dev/{0}
losetup -d /dev/{0}
rm /mnt/{1}/{2}.raw
rmdir /mnt/{0}
""".format(loop_device, test_config.get('vpool', 'vpool_name'), name)
    general.execute_command(cmd, shell=True)


def create_snapshot(disk_name, snapshot_name):
    disk_guid = VDiskList.get_vdisk_by_name(disk_name)[0].guid
    timestamp = str(int(float(time.time())))
    metadata = {'label': snapshot_name,
                'is_consistent': False,
                'timestamp': timestamp,
                'machineguid': '',
                'is_automatic': True,
                'is_sticky': False}
    VDiskController.create_snapshot(disk_guid, metadata, snapshot_name)


def delete_snapshot(disk_name, snapshot_name):
    disk_guid = VDiskList.get_vdisk_by_name(disk_name)[0].guid
    VDiskController.delete_snapshot(disk_guid, snapshot_name)


def generate_hash_file(full_name, size):
    cmd = 'truncate -s {0} {1}'.format(size, full_name)
    general.execute_command(cmd)
    hash = ''.join(random.choice(string.ascii_letters + string.digits) for _ in xrange(1024))
    with open(full_name, 'wb') as datafile:
        for x in xrange(size * 1024):
            datafile.write(hash)
