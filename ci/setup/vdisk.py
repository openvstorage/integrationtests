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

from ci.helpers.vdisk import VDiskHelper
from ci.helpers.vpool import VPoolHelper
from ovs.log.log_handler import LogHandler
from ci.helpers.storagerouter import StoragerouterHelper
from ci.validate.decorators import required_vdisk, required_snapshot, required_vtemplate


class VDiskSetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_vdisk_setup")
    CREATE_SNAPSHOT_TIMEOUT = 60
    CREATE_VDISK_TIMEOUT = 60
    CREATE_CLONE_TIMEOUT = 60
    SET_VDISK_AS_TEMPLATE_TIMEOUT = 60
    ROLLBACK_VDISK_TIMEOUT = 60

    def __init__(self):
        pass

    @staticmethod
    def create_snapshot(snapshot_name, vdisk_name, vpool_name, api, consistent=True, sticky=True,
                        timeout=CREATE_SNAPSHOT_TIMEOUT):
        """
        Create a new snapshot for a vdisk

        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param snapshot_name: name of a new snapshot
        :type snapshot_name: str
        :param consistent: was everything properly flushed to the backend?
        :type consistent: bool
        :param sticky: let this snapshot stick forever?
        :type sticky: bool
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: time to wait for the task to complete
        :type timeout: int
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :return: snapshot guid
        :rtype: str
        """
        vdisk_guid = VDiskHelper.get_vdisk_by_name(vdisk_name, vpool_name).guid

        data = {
            'name': snapshot_name,
            'consistent': consistent,
            'sticky': sticky
        }

        task_guid = api.post(
            api='/vdisks/{0}/create_snapshot/'.format(vdisk_guid),
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Creating snapshot `{0}` for vdisk `{1}` on vPool `{2}` has failed"\
                .format(snapshot_name, vdisk_name, vpool_name)
            VDiskSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskSetup.LOGGER.info("Creating snapshot `{0}` for vdisk `{1}` on vPool `{2}` should have succeeded"
                                   .format(snapshot_name, vdisk_name, vpool_name))
            return task_result[1]

    @staticmethod
    def create_vdisk(vdisk_name, vpool_name, size, storagerouter_ip, api, timeout=CREATE_VDISK_TIMEOUT):
        """
        Create a new vDisk on a certain vPool/storagerouter

        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :param size: size of the new vdisk in BYTES (e.g 10737418240 = 10G)
        :type size: int
        :param storagerouter_ip: ip address of a existing storagerouter
        :type storagerouter_ip: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: time to wait for the task to complete
        :type timeout: int
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :return: vdisk guid
        :rtype: str
        """
        vpool_guid = VPoolHelper.get_vpool_by_name(vpool_name).guid
        storagerouter_guid = StoragerouterHelper.get_storagerouter_by_ip(storagerouter_ip).guid

        # remove .raw or .vmdk if is present
        if '.raw' in vdisk_name or '.vmdk' in vdisk_name:
            official_vdisk_name = vdisk_name.split('.')[0]
        else:
            official_vdisk_name = vdisk_name

        data = {"name": official_vdisk_name,
                "size": int(size),
                "vpool_guid": vpool_guid,
                "storagerouter_guid": storagerouter_guid}

        task_guid = api.post(
            api='/vdisks/',
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Creating vdisk `{0}` on vPool `{1}` on storagerouter `{2}` has failed with error {3}"\
                .format(vdisk_name, vpool_name, storagerouter_ip, task_result[1])
            VDiskSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskSetup.LOGGER.info("Creating vdisk `{0}` on vPool `{1}` on storagerouter `{2}` should have succeeded"
                                   .format(vdisk_name, vpool_name, storagerouter_ip))
            return task_result[1]

    @staticmethod
    @required_vdisk
    def move_vdisk(vdisk_guid, target_storagerouter_guid, api, force=False, timeout=60):
        """
        Moves a vdisk
        :param vdisk_guid: guid of the vdisk
        :param target_storagerouter_guid: guid of the storuagerouter to move to
        :param api: instance of ovs client
        :param force: Indicates whether to force the migration or not (forcing can lead to dataloss)
        :param timeout: timeout in seconds
        :return:
        """
        data = {'target_storagerouter_guid': target_storagerouter_guid,
                'force': force}

        task_guid = api.post(
            api='/vdisks/{0}/move/'.format(vdisk_guid),
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Moving vdisk {0} to {1} has failed with {2}.".format(
                vdisk_guid, target_storagerouter_guid, task_result[1])
            VDiskSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskSetup.LOGGER.info(
                "Vdisk {0} should have been moved to {1}.".format(vdisk_guid, target_storagerouter_guid))
            return task_result[1]

    @staticmethod
    @required_vdisk
    @required_snapshot
    def create_clone(vdisk_name, vpool_name, new_vdisk_name, storagerouter_ip, api, snapshot_id=None,
                     timeout=CREATE_CLONE_TIMEOUT):
        """
        Create a new vDisk on a certain vPool/storagerouter

        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :param new_vdisk_name: location of the NEW vdisk on the vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type new_vdisk_name: str
        :param storagerouter_ip: ip address of a existing storagerouter where the clone will be deployed
        :type storagerouter_ip: str
        :param snapshot_id: GUID of a existing snapshot (DEFAULT=None -> will create new snapshot)
        :type snapshot_id: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: time to wait for the task to complete
        :type timeout: int
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :return: details about cloned vdisk e.g
        {u'backingdevice': u'/test2.raw',
         u'name': u'test2',
         u'vdisk_guid': u'c4414c07-3796-4dcd-96a1-2cb00f4dc82b'}
        :rtype: dict
        """

        # fetch the requirements
        vdisk = VDiskHelper.get_vdisk_by_name(vdisk_name, vpool_name)
        storagerouter_guid = StoragerouterHelper.get_storagerouter_by_ip(storagerouter_ip).guid

        # remove .raw or .vmdk if present
        if '.raw' in new_vdisk_name or '.vmdk' in new_vdisk_name:
            official_new_vdisk_name = new_vdisk_name.split('.')[0]
        else:
            official_new_vdisk_name = new_vdisk_name

        if not snapshot_id:
            data = {"name": official_new_vdisk_name,
                    "storagerouter_guid": storagerouter_guid}
        else:
            data = {"name": official_new_vdisk_name,
                    "storagerouter_guid": storagerouter_guid,
                    "snapshot_id": snapshot_id}

        task_guid = api.post(
            api='/vdisks/{0}/clone'.format(vdisk.guid),
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Creating clone `{0}` with snapshot_id `{4}` on vPool `{1}` on storagerouter `{2}` " \
                        "has failed with error {3}".format(vdisk_name, vpool_name, storagerouter_ip,
                                                           task_result[1], snapshot_id)
            VDiskSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskSetup.LOGGER.info("Creating clone `{0}` with snapshot_id `{3}` on vPool `{1}` on storagerouter `{2}` "
                                   "should have succeeded".format(vdisk_name, vpool_name, storagerouter_ip,
                                                                  snapshot_id))
            return task_result[1]

    @staticmethod
    @required_vdisk
    def set_vdisk_as_template(vdisk_name, vpool_name, api, timeout=SET_VDISK_AS_TEMPLATE_TIMEOUT):
        """
        Create a new vDisk on a certain vPool/storagerouter
        Set a existing vDisk as vTemplate

        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: time to wait for the task to complete
        """

        # fetch the requirements
        vdisk = VDiskHelper.get_vdisk_by_name(vdisk_name, vpool_name)

        task_guid = api.post(
            api='/vdisks/{0}/set_as_template'.format(vdisk.guid)
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Creating vTemplate `{0}` has failed with error {1}".format(vdisk_name, task_result[1])
            VDiskSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskSetup.LOGGER.info("Creating vTemplate `{0}` should have succeeded".format(vdisk_name))
            return task_result[1]

    @staticmethod
    @required_vtemplate
    def create_from_template(vdisk_name, vpool_name, new_vdisk_name, storagerouter_ip, api,
                             timeout=SET_VDISK_AS_TEMPLATE_TIMEOUT):
        """
        Create a new vDisk on a certain vPool/storagerouter
        Set a existing vDisk as vTemplate

        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :param new_vdisk_name: location of the NEW vdisk on the vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type new_vdisk_name: str
        :param storagerouter_ip: ip address of a existing storagerouter where the clone will be deployed
        :type storagerouter_ip: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: time to wait for the task to complete
        """

        # fetch the requirements
        vdisk = VDiskHelper.get_vdisk_by_name(vdisk_name, vpool_name)
        storagerouter_guid = StoragerouterHelper.get_storagerouter_by_ip(storagerouter_ip).guid

        # remove .raw or .vmdk if present
        if '.raw' in new_vdisk_name or '.vmdk' in new_vdisk_name:
            official_new_vdisk_name = new_vdisk_name.split('.')[0]
        else:
            official_new_vdisk_name = new_vdisk_name

        data = {"name": official_new_vdisk_name,
                "storagerouter_guid": storagerouter_guid}

        task_guid = api.post(
            api='/vdisks/{0}/create_from_template'.format(vdisk.guid),
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Creating vTemplate `{0}` has failed with error {1}".format(vdisk_name, task_result[1])
            VDiskSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskSetup.LOGGER.info("Creating vTemplate `{0}` should have succeeded".format(vdisk_name))
            return task_result[1]

    @staticmethod
    @required_vdisk
    def rollback_to_snapshot(vdisk_name, vpool_name, snapshot_id, api, timeout=ROLLBACK_VDISK_TIMEOUT):
        """
        Rollback a vdisk to a certain snapshot

        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :param snapshot_id: guid of a snapshot for the chosen vdisk
        :type snapshot_id: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: time to wait for the task to complete
        """

        # fetch the requirements
        vdisk_guid = VDiskHelper.get_vdisk_by_name(vdisk_name=vdisk_name, vpool_name=vpool_name).guid
        snapshot = VDiskHelper.get_snapshot_by_guid(snapshot_guid=snapshot_id, vdisk_name=vdisk_name,
                                                    vpool_name=vpool_name)

        task_guid = api.post(
            api='/vdisks/{0}/rollback'.format(vdisk_guid),
            data={"timestamp": snapshot['timestamp']}
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Rollback vDisk `{0}` has failed with error {1}".format(vdisk_name, task_result[1])
            VDiskSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskSetup.LOGGER.info("Rollback vDisk `{0}` should have succeeded".format(vdisk_name))
            return task_result[1]
