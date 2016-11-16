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
A general class dedicated to vDisk logic
"""

import os
import time
import uuid
import random
import string
from ci.tests.general.connection import Connection
from ci.tests.general.general import General
from ci.tests.general.general_hypervisor import GeneralHypervisor
from ci.tests.general.logHandler import LogHandler
from ovs.dal.lists.vdisklist import VDiskList
from ovs.extensions.generic.sshclient import SSHClient
from subprocess import CalledProcessError


class GeneralVDisk(object):
    """
    A general class dedicated to vDisk logic
    """
    api = Connection()
    logger = LogHandler.get('vdisks', name='vdisk')

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
                root_client.run(['umount', '/mnt/', loop_device, '; echo 0'])
                root_client.run(['truncate', '-s', size, 'G ', location, ''])
                root_client.dir_create(['/mnt/', loop_device])
                root_client.run(['mkfs.ext4', '-F', location])
                root_client.run(['mount', '-o', 'loop', location, '/mnt/', loop_device])
            else:
                root_client.run(['truncate', '-s', str(size) + 'G', location])
        except CalledProcessError as cpe:
            GeneralVDisk.logger.error(str(cpe))
            if loop_device is not None:
                root_client.run('umount /mnt/{0}; rm {1}; rmdir /mnt/{0}; echo 0'.format(loop_device, location), allow_insecure=True)
            raise

        vdisk = None
        if wait is True:
            counter = 0
            timeout = 60
            volume_name = '/' + os.path.basename(location)
            while True and counter < timeout:
                time.sleep(1)
                vdisk = VDiskList.get_by_devicename_and_vpool(volume_name, vpool)
                if vdisk is not None:
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
            GeneralVDisk.disconnect_volume(loop_device, root_client)
        root_client.file_delete(location)

        if wait is True:
            counter = 0
            timeout = 60
            volume_name = '/' + os.path.basename(location)
            while True and counter < timeout:
                time.sleep(1)
                vdisks = VDiskList.get_by_devicename_and_vpool(volume_name, vpool)
                if vdisks is None:
                    break
                counter += 1
            if counter == timeout:
                raise RuntimeError('Disk {0} was not deleted from model after {1} seconds'.format(volume_name, timeout))

    @staticmethod
    def connect_volume(vpool, name, loop_device, root_client=None):
        """
        Connect/mount a volume to loop device
        :param vpool: vPool to create a volume for
        :param name: Name of the volume
        :param loop_device: Loop device to use to mount volume on
        :param root_client: SSHClient object
        :return: None
        """
        location = GeneralVDisk.get_filesystem_location(vpool=vpool,
                                                        vdisk_name=name)
        if root_client is None:
            root_client = SSHClient('127.0.0.1', username='root')

            try:
                if loop_device is not None:
                    root_client.dir_create('/mnt/{0}'.format(loop_device))
                    root_client.run(['mount', '-o', 'loop', location, '/mnt/' + loop_device])
            except CalledProcessError as cpe:
                GeneralVDisk.logger.error(str(cpe))
                root_client.run(['umount', '/mnt/' + loop_device, ';rmdir', '/mnt/' + loop_device])

    @staticmethod
    def disconnect_volume(loop_device, root_client=None):
        """
        Disconnect a vdisk and cleanup it's loop device
        :param loop_device: Loop device where volume is mounted on
        :param root_client: SSHClient object
        :return: None
        """
        if root_client is None:
            root_client = SSHClient('127.0.0.1', username='root')

        try:
            if loop_device is not None:
                root_client.run(['umount', '/mnt/' + loop_device, ';rmdir /mnt/' + loop_device])
            else:
                root_client.run(['rmdir', '/mnt/' + loop_device])
        except CalledProcessError as cpe:
            GeneralVDisk.logger.error(str(cpe))

    @staticmethod
    def write_to_volume(vdisk=None, vpool=None, location=None, count=1024, bs='1M', input_type='random',
                        root_client=None):
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
        if General.check_file_is_link(location, root_client.ip, root_client.username, root_client.password):
            print "Writing to {0}".format(root_client.file_read_link(location))
        else:
            if not root_client.file_exists(location):
                raise ValueError('File {0} does not exist on Storage Router {1}'.format(location, root_client.ip))
        if not isinstance(count, int) or count < 1:
            raise ValueError('Count must be an integer > 0')
        root_client.run(['dd', 'conv=notrunc', 'if=/dev/' + input_type, 'of=' + location, 'bs=' + bs, 'count=' + str(count)])

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
                                                          'snapshot_id': snapshot_name},
                                                    wait=True)

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
        :param size: Size of file to create in MB
        :param root_client: SSHClient object
        :return:
        """
        if root_client is None:
            root_client = SSHClient('127.0.0.1', username='root')
        root_client.run(['truncate', '-s', size, full_name])
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
        hv_type = GeneralHypervisor.get_hypervisor_type()
        if hv_type == 'VMWARE':
            location = '/'.join(['/mnt/{0}'.format(vpool.name), "{0}-flat.vmdk".format(vdisk_name)])
        elif hv_type == 'KVM':
            location = '/'.join(['/mnt/{0}'.format(vpool.name), "{0}.raw".format(vdisk_name)])
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

    @staticmethod
    def schedule_backend_sync(vdisk):
        """
        Schedule backend sync for vdisk
        :param vdisk: vdisk to schedule backend sync to
        :return: TLogName associated with the data sent off to the backend
        """
        status, tlog_name = GeneralVDisk.api.execute_post_action(component='vdisks', guid=vdisk.guid,
                                                                 action='schedule_backend_sync', data={}, wait=True)
        assert status is True,\
            'Schedule backend sync failed for vdisk: {0}'.format(vdisk.name)
        return tlog_name

    @staticmethod
    def is_volume_synced_up_to_tlog(vdisk, tlog_name):
        """
        Verify if volume is synced to backend up to a specific tlog
        :param vdisk: vdisk to verify
        :param tlog_name: tlog_name to verify
        """
        status, result = GeneralVDisk.api.execute_post_action(component='vdisks', guid=vdisk.guid,
                                                              action='is_volume_synced_up_to_tlog',
                                                              data={'tlog_name': tlog_name}, wait=True)
        assert status is True,\
            'is_volume_synced_up_to_tlog failed for vdisk: {0}'.format(vdisk.name)

        return result

    @staticmethod
    def is_volume_synced_up_to_snapshot(vdisk, snapshot_id):
        """
        Verify if volume is synced to backend up to a specific snapshot
        :param vdisk: vdisk to verify
        :param snapshot_id: snapshot_id to verify
        """
        status, result = GeneralVDisk.api.execute_post_action(component='vdisks', guid=vdisk.guid,
                                                              action='is_volume_synced_up_to_snapshot',
                                                              data={'snapshot_id': str(snapshot_id)}, wait=True)
        assert status is True,\
            'is_volume_synced_up_to_snapshot failed for vdisk: {0} with error: {1}'.format(vdisk.name, result)

        return result

    @staticmethod
    def clone_volume(vdisk, clone_name):
        """
        Clone a volume
        :param vdisk: vdisk to clone
        :param clone_name: name of clone
        :return:
        """
        status, result = GeneralVDisk.api.execute_post_action(component='vdisks', guid=vdisk.guid,
                                                              action='clone', data={'name': clone_name,
                                                                                    'storagerouter_guid': vdisk.storagerouter_guid},
                                                              wait=True)
        GeneralVDisk.logger.info('Status of cloning disk task: {0}'.format(status))
        assert status is True,\
            'clone failed for vdisk: {0}'.format(vdisk.name)
        GeneralVDisk.logger.info('Result of cloning disk task: {0}'.format(result))

        return result