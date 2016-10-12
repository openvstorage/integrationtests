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
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonInstaller
from ci.validate.decorators import required_cluster_basedir, required_arakoon_cluster


class ArakoonSetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_arakoon_setup")

    def __init__(self):
        pass

    @staticmethod
    @required_cluster_basedir
    def add_arakoon(cluster_name, storagerouter_ip, cluster_basedir,
                    service_type=ServiceType.ARAKOON_CLUSTER_TYPES.FWK):
        """
        Adds a external arakoon to a storagerouter

        :param cluster_name: name of the new arakoon cluster
        :type cluster_name: str
        :param service_type: type of plugin for arakoon (DEFAULT=ServiceType.ARAKOON_CLUSTER_TYPES.FWK)
            * FWK
            * ABM
            * NSM
        :type service_type: ovs.dal.hybrids.ServiceType.ARAKOON_CLUSTER_TYPES
        :param storagerouter_ip: ip of a storagerouter
        :type storagerouter_ip: str
        :param cluster_basedir: absolute path for the new arakoon cluster
        :type cluster_basedir: str
        :return:
        """

        ArakoonSetup.LOGGER.info("Starting creation of new arakoon cluster with name `{0}`, servicetype `{1}`,"
                                 " ip `{2}`, base_dir `{3}`".format(cluster_name, service_type, storagerouter_ip,
                                                                    cluster_basedir))
        ArakoonInstaller.create_cluster(cluster_name, service_type, storagerouter_ip, cluster_basedir)
        ArakoonSetup.LOGGER.info("Finished creation of new arakoon cluster with name `{0}`, servicetype `{1}`,"
                                 " ip `{2}`, base_dir `{3}`".format(cluster_name, service_type, storagerouter_ip,
                                                                    cluster_basedir))

    @staticmethod
    @required_cluster_basedir
    @required_arakoon_cluster
    def extend_arakoon(cluster_name, master_storagerouter_ip, storagerouter_ip, cluster_basedir):
        """
        Adds a external arakoon to a storagerouter

        :param cluster_name: name of the already existing arakoon cluster
        :type cluster_name: str
        :param master_storagerouter_ip: master ip address of the existing arakoon cluster
        :type master_storagerouter_ip: str
        :param storagerouter_ip: ip of a new storagerouter to extend to
        :type storagerouter_ip: str
        :param cluster_basedir: absolute path for the new arakoon cluster
        :type cluster_basedir: str
        :return: is created or not
        :rtype: bool
        """

        ArakoonSetup.LOGGER.info("Starting extending arakoon cluster with name `{0}`, master_ip `{1}`,"
                                 " slave_ip `{2}`, base_dir `{3}`".format(cluster_name, master_storagerouter_ip,
                                                                          storagerouter_ip, cluster_basedir))
        ArakoonInstaller.extend_cluster(master_storagerouter_ip, storagerouter_ip, cluster_name, cluster_basedir)
        ArakoonSetup.LOGGER.info("Finished extending arakoon cluster with name `{0}`, master_ip `{1}`,"
                                 " slave_ip `{2}`, base_dir `{3}`".format(cluster_name, master_storagerouter_ip,
                                                                          storagerouter_ip, cluster_basedir))
