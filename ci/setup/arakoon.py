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
from ci.helpers.backend import BackendHelper
from ovs.lib.alba import AlbaController
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonInstaller
from ci.validate.decorators import required_backend, required_arakoon_cluster


class ArakoonSetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_arakoon_setup")

    def __init__(self):
        pass

    @staticmethod
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
        client = SSHClient(storagerouter_ip, username='root')

        # create required directories
        if not client.dir_exists(cluster_basedir):
            client.dir_create(cluster_basedir)

        # determine plugin
        if service_type == ServiceType.ARAKOON_CLUSTER_TYPES.FWK:
            plugins = None
        elif service_type == ServiceType.ARAKOON_CLUSTER_TYPES.ABM:
            plugins = {
                AlbaController.ABM_PLUGIN: AlbaController.ALBA_VERSION_GET
            }
        elif service_type == ServiceType.ARAKOON_CLUSTER_TYPES.NSM:
            plugins = {
                AlbaController.NSM_PLUGIN: AlbaController.ALBA_VERSION_GET
            }
        else:
            raise RuntimeError("Incompatible Arakoon cluster type selected: {0}".format(service_type))

        ArakoonSetup.LOGGER.info("Starting creation of new arakoon cluster with name `{0}`, servicetype `{1}`,"
                                 " ip `{2}`, base_dir `{3}`".format(cluster_name, service_type, storagerouter_ip,
                                                                    cluster_basedir))
        info = ArakoonInstaller.create_cluster(cluster_name=cluster_name, cluster_type=service_type,
                                               ip=storagerouter_ip, base_dir=cluster_basedir, plugins=plugins,
                                               locked=False, internal=False)
        if service_type == ServiceType.ARAKOON_CLUSTER_TYPES.ABM:
            client.run(['ln', '-s', '/usr/lib/alba/albamgr_plugin.cmxs', '{0}/arakoon/{1}/db'.format(cluster_basedir, cluster_name)])
        elif service_type == ServiceType.ARAKOON_CLUSTER_TYPES.NSM:
            client.run(['ln', '-s', '/usr/lib/alba/nsm_host_plugin.cmxs', '{0}/arakoon/{1}/db'.format(cluster_basedir, cluster_name)])
        ArakoonInstaller.start_cluster(metadata=info['metadata'])
        ArakoonInstaller.unclaim_cluster(cluster_name=cluster_name)
        ArakoonSetup.LOGGER.info("Finished creation of new arakoon cluster with name `{0}`, servicetype `{1}`,"
                                 " ip `{2}`, base_dir `{3}`".format(cluster_name, service_type, storagerouter_ip,
                                                                    cluster_basedir))

    @staticmethod
    @required_arakoon_cluster
    def extend_arakoon(cluster_name, master_storagerouter_ip, storagerouter_ip, cluster_basedir,
                       service_type=ServiceType.ARAKOON_CLUSTER_TYPES.FWK, clustered_nodes=[]):
        """
        Adds a external arakoon to a storagerouter

        :param cluster_name: name of the already existing arakoon cluster
        :type cluster_name: str
        :param master_storagerouter_ip: master ip address of the existing arakoon cluster
                                        e.g. 10.100.199.11
        :type master_storagerouter_ip: str
        :param storagerouter_ip: ip of a new storagerouter to extend to
                                 e.g. 10.100.199.12
        :type storagerouter_ip: str
        :param cluster_basedir: absolute path for the new arakoon cluster
        :type cluster_basedir: str
        :param service_type: type of plugin for arakoon (DEFAULT=ServiceType.ARAKOON_CLUSTER_TYPES.FWK)
            * FWK
            * ABM
            * NSM
        :type service_type: ovs.dal.hybrids.ServiceType.ARAKOON_CLUSTER_TYPES
        :param clustered_nodes: nodes who are available for the arakoon (including the to be extended_arakoon)
                                e.g. ['10.100.199.11', '10.100.199.12'] (DEFAULT=[])
        :type clustered_nodes: list
        :return: is created or not
        :rtype: bool
        """
        client = SSHClient(storagerouter_ip, username='root')

        # create required directories
        if not client.dir_exists(cluster_basedir):
            client.dir_create(cluster_basedir)

        ArakoonSetup.LOGGER.info("Starting extending arakoon cluster with name `{0}`, master_ip `{1}`,"
                                 " slave_ip `{2}`, base_dir `{3}`".format(cluster_name, master_storagerouter_ip,
                                                                          storagerouter_ip, cluster_basedir))
        ArakoonInstaller.extend_cluster(new_ip=storagerouter_ip, cluster_name=cluster_name, base_dir=cluster_basedir,
                                        locked=False)
        if service_type == ServiceType.ARAKOON_CLUSTER_TYPES.ABM:
            client.run(['ln', '-s', '/usr/lib/alba/albamgr_plugin.cmxs', '{0}/arakoon/{1}/db'
                       .format(cluster_basedir, cluster_name)])
        elif service_type == ServiceType.ARAKOON_CLUSTER_TYPES.NSM:
            client.run(['ln', '-s', '/usr/lib/alba/nsm_host_plugin.cmxs', '{0}/arakoon/{1}/db'
                       .format(cluster_basedir, cluster_name)])

        # checking if we need to restart the given nodes
        if len(clustered_nodes) != 0:
            ArakoonSetup.LOGGER.info("Trying to restart all given nodes of arakoon: {0}"
                                     .format(clustered_nodes, cluster_name))
            ArakoonInstaller.restart_cluster_add(cluster_name=cluster_name, current_ips=clustered_nodes,
                                                 new_ip=storagerouter_ip)
            ArakoonSetup.LOGGER.info("Finished restarting all given nodes of arakoon: {0}"
                                     .format(clustered_nodes, cluster_name))

        ArakoonSetup.LOGGER.info("Finished extending arakoon cluster with name `{0}`, master_ip `{1}`,"
                                 " slave_ip `{2}`, base_dir `{3}`".format(cluster_name, master_storagerouter_ip,
                                                                          storagerouter_ip, cluster_basedir))

    @staticmethod
    @required_backend
    def checkup_nsm_hosts(albabackend_name, amount):
        """
        Checkup the NSM hosts for a certain alba backend

        :param albabackend_name: name of a existing alba backend
        :type albabackend_name: str
        :param amount: amount of min. NSM hosts for a certain backend
        :type amount: int
        :return:
        """

        alba_backend_guid = BackendHelper.get_alba_backend_guid_by_name(albabackend_name)
        return AlbaController.nsm_checkup(backend_guid=alba_backend_guid, min_nsms=int(amount))
