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
from ovs.dal.lists.vdisklist import VDiskList


class GeneralVDisk(object):
    """
    A general class dedicated to vDisk logic
    """
    @staticmethod
    def create_volume(size, vpool, root_client, wait=True):
        """
        Create a volume
        :param size: Size of the volume (in GB)
        :param vpool: vPool to create a volume for
        :param root_client: SSHClient object
        :param wait: Wait for the volume to be created on volumedriver and in model
        :return: Location of the created file
        """
        hv_type = vpool.storagedrivers[0].storagerouter.pmachine.hvtype
        if hv_type == 'VMWARE':
            location = os.path.join('/mnt/{0}'.format(vpool.name), "{0}-flat.vmdk".format(uuid.uuid4()))
        elif hv_type == 'KVM':
            location = os.path.join('/mnt/{0}'.format(vpool.name), "{0}.raw".format(uuid.uuid4()))
        else:
            raise RuntimeError('Invalid hypervisor type specified: {0}'.format(hv_type))

        root_client.run('truncate -s {0}G {1}'.format(size, location))
        if wait is True:
            counter = 0
            timeout = 60
            volume_name = os.path.basename(location).replace('-flat.vmdk', '').replace('.raw', '')
            while True and counter < timeout:
                time.sleep(1)
                vdisks = GeneralVDisk.get_vdisk_by_name(name=volume_name)
                if vdisks is not None:
                    break
                counter += 1
            if counter == timeout:
                raise RuntimeError('Disk {0} did not show up in model after {1} seconds'.format(volume_name, timeout))
        return location

    @staticmethod
    def delete_volume(location, root_client, wait=True):
        """
        Delete a volume
        :param location: Location of the volume
        :param root_client: SSHClient object
        :param wait: Wait for the volume to be deleted from model
        :return: None
        """
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
    def write_to_volume(location, root_client, count=1024, bs='1M', input_type='random'):
        """
        Write some data to a file
        :param location: Location of the file
        :param root_client: SSHClient object
        :param count: amount of blocks to write
        :param bs: Size of the blocks to write
        :param input_type: Type of input (null, zero, random)
        :return: None
        """
        if input_type not in ('null', 'zero', 'random'):
            raise ValueError('Invalid input type provided')
        if not root_client.file_exists(location):
            raise ValueError('File {0} does not exist on Storage Router {1}'.format(location, root_client.ip))
        if not isinstance(count, int) or count < 1:
            raise ValueError('Count must be an integer > 0')
        root_client.run('dd if=/dev/{0} of={1} bs={2} count={3}'.format(input_type, location, bs, count))

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
