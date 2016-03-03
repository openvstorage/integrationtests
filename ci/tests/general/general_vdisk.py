# Copyright 2016 iNuron NV
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
A general class dedicated to vDisk logic
"""

import os
import time
import uuid
import random
import string
from ci.tests.general.connection import Connection
from ovs.dal.lists.vdisklist import VDiskList
from ovs.extensions.generic.sshclient import SSHClient
from subprocess import CalledProcessError


class GeneralVDisk(object):
    """
    A general class dedicated to vDisk logic
    """
    api = Connection()

    @staticmethod
    def get_vdisk_by_name(name):
        """
        Retrieve the DAL vDisk object based on its name
        :param name: Name of the virtual disk
        :return: vDisk DAL object
        """
        return VDiskList.get_vdisk_by_name(vdiskname=name)

    @staticmethod
    def get_vdisks():
        """
        Retrieve all Virtual Disks
        :return: Virtual Disk data-object list
        """
        return VDiskList.get_vdisks()

    @staticmethod
    def create_volume(size, vpool, name=None, loop_device=None, root_client=None, wait=True):
        """
        Create a volume
        :param size: Size of the volume (in GB)
        :param vpool: vPool to create a volume for
        :param name: Name for the volume
        :param loop_device: Loop device to use to mount volume on
        :param root_client: SSHClient object
        :param wait: Wait for the volume to be created on volumedriver and in model
        :return: Newly created Virtual Disk
        """
        location = GeneralVDisk.get_filesystem_location(vpool=vpool,
                                                        vdisk_name=name if name is not None else uuid.uuid4())
        if root_client is None:
            root_client = SSHClient('127.0.0.1', username='root')

        try:
            if loop_device is not None:
                root_client.run('umount /mnt/{0} | echo true'.format(loop_device))
                root_client.run('losetup -d /dev/{0} | echo true'.format(loop_device))
                root_client.run('truncate -s {0}G {1}'.format(size, location))
                root_client.run('losetup /dev/{0} {1}'.format(loop_device, location))
                root_client.dir_create('/mnt/{0}'.format(loop_device))
                root_client.run('parted /dev/{0} mklabel gpt'.format(loop_device))
                root_client.run('parted -a optimal /dev/{0} mkpart primary ext4 0% 100%'.format(loop_device))
                root_client.run('partprobe; echo true')
                root_client.run('mkfs.ext4 /dev/{0}'.format(loop_device))
                root_client.run('mount -t ext4 /dev/{0} /mnt/{0}'.format(loop_device))
        except CalledProcessError as cpe:
            cmd = """
                umount /mnt/{0};
                losetup -d /dev/{0};
                rm {1}""".format(loop_device, location)
            root_client.run(cmd)
            raise

        vdisk = None
        if wait is True:
            counter = 0
            timeout = 60
            volume_name = os.path.basename(location).replace('-flat.vmdk', '').replace('.raw', '')
            while True and counter < timeout:
                time.sleep(1)
                vdisks = GeneralVDisk.get_vdisk_by_name(name=volume_name)
                if vdisks is not None:
                    vdisk = vdisks[0]
                    break
                counter += 1
            if counter == timeout:
                raise RuntimeError('Disk {0} did not show up in model after {1} seconds'.format(volume_name, timeout))
        return vdisk

    @staticmethod
    def delete_volume(vdisk, vpool, loop_device=None, root_client=None, wait=True):
        """
        Delete a volume
        :param vdisk: Virtual disk to delete
        :param vpool: vPool which hosts the Virtual Disk
        :param loop_device: Loop device where volume is mounted on
        :param root_client: SSHClient object
        :param wait: Wait for the volume to be deleted from model
        :return: None
        """
        location = GeneralVDisk.get_filesystem_location(vpool=vpool,
                                                        vdisk_name=vdisk.name)
        if root_client is None:
            root_client = SSHClient('127.0.0.1', username='root')

        if loop_device is not None:
            root_client.run('umount /dev/{0}'.format(loop_device))
            root_client.run('losetup -d /dev/{0}'.format(loop_device))
            root_client.dir_delete('/mnt/{0}'.format(loop_device))
        root_client.file_delete(location)

        if wait is True:
            counter = 0
            timeout = 60
            volume_name = os.path.basename(location).replace('-flat.vmdk', '').replace('.raw', '')
            while True and counter < timeout:
                time.sleep(1)
                vdisks = GeneralVDisk.get_vdisk_by_name(name=volume_name)
                if vdisks is None:
                    break
                counter += 1
            if counter == timeout:
                raise RuntimeError('Disk {0} was not deleted from model after {1} seconds'.format(volume_name, timeout))

    @staticmethod
    def write_to_volume(vdisk=None, vpool=None, location=None, count=1024, bs='1M', input_type='random', root_client=None):
        """
        Write some data to a file
        :param vdisk: Virtual disk to write on
        :param vpool: vPool which hosts the Virtual Disk
        :param location: Absolute path to file
        :param count: amount of blocks to write
        :param bs: Size of the blocks to write
        :param input_type: Type of input (null, zero, random)
        :param root_client: SSHClient object
        :return: None
        """
        if location is None and (vdisk is None or vpool is None):
            raise ValueError('vDisk and vPool must be provided if no location has been provided')

        if location is None:
            location = GeneralVDisk.get_filesystem_location(vpool=vpool,
                                                            vdisk_name=vdisk.name)
        if root_client is None:
            root_client = SSHClient('127.0.0.1', username='root')

        if input_type not in ('null', 'zero', 'random'):
            raise ValueError('Invalid input type provided')
        if not root_client.file_exists(location):
            raise ValueError('File {0} does not exist on Storage Router {1}'.format(location, root_client.ip))
        if not isinstance(count, int) or count < 1:
            raise ValueError('Count must be an integer > 0')
        root_client.run('dd if=/dev/{0} of={1} bs={2} count={3}'.format(input_type, location, bs, count))

    @staticmethod
    def create_snapshot(vdisk, snapshot_name, timestamp=None, consistent=False, automatic=True, sticky=False):
        """
        Create a snapshot
        :param vdisk: Disk DAL object
        :param snapshot_name: Name for the snapshot
        :param timestamp: Timestamp snapshot was taken
        :param consistent: Consistent snapshot
        :param automatic: Snapshot is taken automatically by cron job
        :param sticky: Snapshot should not be deleted by delete_snapshots
        :return: None
        """
        if timestamp is None:
            timestamp = str(int(time.time()))
        return GeneralVDisk.api.execute_post_action(component='vdisks',
                                                    guid=vdisk.guid,
                                                    action='create_snapshot',
                                                    data={'name': snapshot_name,
                                                          'timestamp': timestamp,
                                                          'consistent': consistent,
                                                          'automatic': automatic,
                                                          'sticky': sticky,
                                                          'snapshot_id': snapshot_name})

    @staticmethod
    def delete_snapshot(disk, snapshot_name):
        """
        Delete a snapshot
        :param disk: Disk DAL object
        :param snapshot_name: Name of the snapshot
        :return: None
        """
        return GeneralVDisk.api.execute_post_action(component='vdisks',
                                                    guid=disk.guid,
                                                    action='remove_snapshot',
                                                    data={'snapshot_id': snapshot_name})

    @staticmethod
    def generate_hash_file(full_name, size, root_client=None):
        """
        Generate a hash file
        :param full_name: Absolute path of file to create
        :param size: Size of file to create
        :param root_client: SSHClient object
        :return:
        """
        if root_client is None:
            root_client = SSHClient('127.0.0.1', username='root')
        root_client.run('truncate -s {0} {1}'.format(size, full_name))
        random_hash = ''.join(random.choice(string.ascii_letters + string.digits) for _ in xrange(1024))
        with open(full_name, 'wb') as datafile:
            for x in xrange(size * 1024):
                datafile.write(random_hash)

    @staticmethod
    def get_filesystem_location(vpool, vdisk_name):
        """
        Retrieve the absolute path of the disk for the vPool
        :param vpool: vPool on which the disk is hosted
        :param vdisk_name: Disk to retrieve path for
        :return: Absolute path
        """
        hv_type = vpool.storagedrivers[0].storagerouter.pmachine.hvtype
        if hv_type == 'VMWARE':
            location = os.path.join('/mnt/{0}'.format(vpool.name), "{0}-flat.vmdk".format(vdisk_name))
        elif hv_type == 'KVM':
            location = os.path.join('/mnt/{0}'.format(vpool.name), "{0}.raw".format(vdisk_name))
        else:
            raise RuntimeError('Invalid hypervisor type specified: {0}'.format(hv_type))
        return location

    @staticmethod
    def get_config_params(vdisk):
        """
        :param vdisk: vdisk to retrieve config params from
        :return: {} containing config params
        """
        status, params = GeneralVDisk.api.execute_get_action('vdisks', vdisk.guid, 'get_config_params', wait=True)
        assert status is True,\
            'Retrieving config params failed: {0} for vdisk: {1} - {2}'.format(status, vdisk.name, params)

        assert 'metadata_cache_size' in params,\
            'Missing metadata_cache_size in vdisk config_params: {0}'.format(params)

        return params

    @staticmethod
    def set_config_params(vdisk, params):
        """
        Set specific vdisk params
        :param vdisk: vdisk to set config params on
        :param params: params to set
        :return:
        """
        status, _ = GeneralVDisk.api.execute_post_action(component='vdisks', guid=vdisk.guid,
                                                         action='set_config_params', data=params, wait=True)
        assert status is True,\
            'Retrieving config params failed: {0} for vdisk: {1} - {2}'.format(status, vdisk.name, params)
