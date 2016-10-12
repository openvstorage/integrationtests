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

from ovs.log.log_handler import LogHandler
from ci.validate.decorators import required_arakoon_cluster
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonInstaller


class ArakoonRemover(object):

    LOGGER = LogHandler.get(source="remove", name="ci_arakoon_remover")

    def __init__(self):
        pass

    @staticmethod
    @required_arakoon_cluster
    def remove_arakoon_cluster(cluster_name, master_storagerouter_ip):
        """
        Delete a whole arakoon cluster

        :param cluster_name: name of a existing arakoon cluster
        :type cluster_name: str
        :param master_storagerouter_ip: master ip address of a existing arakoon cluster
        :type master_storagerouter_ip: str
        """

        ArakoonRemover.LOGGER.info("Starting removing arakoon cluster with name `{0}`, master_ip `{1}`"
                                   .format(cluster_name, master_storagerouter_ip))
        ArakoonInstaller.delete_cluster(cluster_name, master_storagerouter_ip)
        ArakoonRemover.LOGGER.info("Finished removing arakoon cluster with name `{0}`, master_ip `{1}`"
                                   .format(cluster_name, master_storagerouter_ip))
