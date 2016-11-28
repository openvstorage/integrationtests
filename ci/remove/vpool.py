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

from ci.helpers.vpool import VPoolHelper
from ovs.log.log_handler import LogHandler
from ci.helpers.storagerouter import StoragerouterHelper


class VPoolRemover(object):

    LOGGER = LogHandler.get(source="remove", name="ci_vpool_remover")
    REMOVE_VPOOL_TIMEOUT = 500

    def __init__(self):
        pass

    @staticmethod
    def remove_vpool(vpool_name, storagerouter_ip, api, timeout=REMOVE_VPOOL_TIMEOUT):
        """
        Removes a existing vpool from a storagerouter

        :param vpool_name: the name of a existing vpool
        :type vpool_name: str
        :param storagerouter_ip: the ip address of a existing storagerouter
        :type storagerouter_ip: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: max. time to wait for a task to complete
        :type timeout: int
        :return: task was succesfull or not
        :rtype: bool
        """

        vpool_guid = VPoolHelper.get_vpool_by_name(vpool_name).guid
        storagerouter_guid = StoragerouterHelper.get_storagerouter_by_ip(storagerouter_ip).guid
        data = {"storagerouter_guid": storagerouter_guid}
        task_guid = api.post(api='/vpools/{0}/shrink_vpool/'.format(vpool_guid), data=data)

        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Deleting vPool `{0}` on storagerouter `{1}` has failed with error {2}".format(vpool_name, storagerouter_ip, task_result[1])
            VPoolRemover.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VPoolRemover.LOGGER.info("Deleting vPool `{0}` on storagerouter `{1}` should have succeeded"
                                     .format(vpool_name, storagerouter_ip))
            return True
