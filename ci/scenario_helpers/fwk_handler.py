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

from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class FwkHandler(object):
    """
    Class handling fwk actions
    """
    LOGGER = LogHandler.get(source='scenario_helpers', name='fwk_handler')

    @classmethod
    def restart(cls, storagerouters, logger=LOGGER):
        """
        Restarts a list of storagerouters
        :param storagerouters: list of storagerouters
        :param logger: logging instance
        :return: None
        """
        for storagerouter in storagerouters:
            logger.info("Restarting ovs-workers on {0}".format(storagerouter.ip))
            client = SSHClient(str(storagerouter.ip), username='root', cached=False)
            client.run(['systemctl', 'restart', 'ovs-workers.service'])

    @classmethod
    def restart_masters(cls):
        """
        Will restart ovs-workers on all master nodes
        :return: None
        """
        cls.restart([sr for sr in StorageRouterList.get_masters()])

    @classmethod
    def restart_slaves(cls):
        """
        Will restart ovs-workers on all slave nodes
        :return: None
        """
        cls.restart([sr for sr in StorageRouterList.get_slaves()])

    @classmethod
    def restart_all(cls):
        """
        Will restart ovs-workers on all nodes
        :return: None
        """
        cls.restart_masters()
        cls.restart_slaves()
