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
from ovs.extensions.generic.remote import remote
from ovs.dal.lists.servicelist import ServiceList
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.extensions.generic.sshclient import SSHClient
from ci.helpers.storagerouter import StoragerouterHelper
from ovs.lib.scheduledtask import ScheduledTaskController
from ovs.extensions.generic.configuration import Configuration


class ArakoonCollapse(object):

    CASE_TYPE = 'FUNCTIONAL'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_arakoon_collapse")

    def __init__(self):
        pass

    @staticmethod
    def main(blocked):
        """
        Run all required methods for the test

        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        if not blocked:
            try:
                ArakoonCollapse.test_collapse()
                return {'status': 'PASSED', 'case_type': ArakoonCollapse.CASE_TYPE, 'errors': None}
            except Exception as ex:
                ArakoonCollapse.LOGGER.error("Arakoon collapse failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': ArakoonCollapse.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': ArakoonCollapse.CASE_TYPE, 'errors': None}

    @staticmethod
    def test_collapse():
        """
        Test the arakoon collapsing

        :return:
        """
        ArakoonCollapse.LOGGER.info("Starting validating arakoon collapse")
        node_ips = StoragerouterHelper.get_storagerouter_ips()
        node_ips.sort()
        for node_ip in node_ips:
            ArakoonCollapse.LOGGER.info("Fetching arakoons on node `{1}`".format(node_ip))
            arakoon_clusters = []
            root_client = SSHClient(node_ip, username='root')

            # fetch arakoon clusters
            for service in ServiceList.get_services():
                if service.is_internal is True and service.storagerouter.ip == node_ip and \
                    service.type.name in (ServiceType.SERVICE_TYPES.ARAKOON,
                                          ServiceType.SERVICE_TYPES.NS_MGR,
                                          ServiceType.SERVICE_TYPES.ALBA_MGR):
                    arakoon_clusters.append(service.name.replace('arakoon-', ''))

            # perform collapse
            ArakoonCollapse.LOGGER.info("Starting arakoon collapse on node `{1}`".format(node_ip))
            for arakoon_cluster in arakoon_clusters:
                ArakoonCollapse.LOGGER.info("Fetching `{0}` arakoon on node `{1}`".format(arakoon_cluster, node_ip))
                arakoon_config_path = Configuration.get_configuration_path('/ovs/arakoon/{0}/config'
                                                                           .format(arakoon_cluster))
                tlog_location = '/opt/OpenvStorage/db/arakoon/{0}/tlogs'.format(arakoon_cluster)

                # read_tlog_dir
                with remote(node_ip, [Configuration]) as rem:
                    config_contents = rem.Configuration.get('/ovs/arakoon/{0}/config'.format(arakoon_cluster),
                                                            raw=True)
                for line in config_contents.splitlines():
                    if 'tlog_dir' in line:
                        tlog_location = line.split()[-1]

                nr_of_tlogs = ArakoonCollapse.get_nr_of_tlogs_in_folder(root_client, tlog_location)
                old_headdb_timestamp = 0
                if root_client.file_exists('/'.join([tlog_location, 'head.db'])):
                    old_headdb_timestamp = root_client.run('stat --format=%Y {0}/{1}'.format(tlog_location,
                                                                                             'head.db'))
                if nr_of_tlogs <= 2:
                    benchmark_command = 'arakoon --benchmark -n_clients 1 -max_n 5_000 -config {0}'\
                        .format(arakoon_config_path)
                    root_client.run(benchmark_command)

                ArakoonCollapse.LOGGER.info("Collapsing arakoon `{0}` on node `{1}` ..."
                                            .format(arakoon_cluster, node_ip))
                ScheduledTaskController.collapse_arakoon()

                nr_of_tlogs = ArakoonCollapse.get_nr_of_tlogs_in_folder(root_client, tlog_location)
                new_headdb_timestamp = root_client.run('stat --format=%Y {0}/{1}'.format(tlog_location, 'head.db'))

                # perform assertion
                assert nr_of_tlogs <= 2,\
                    'Arakoon collapse left {0} tlogs on the environment, expecting less than 2 in `{1}` on node `{1}`'\
                    .format(nr_of_tlogs, arakoon_cluster, node_ip)
                assert old_headdb_timestamp != new_headdb_timestamp,\
                    'Timestamp of the head_db file was not changed ' \
                    'in the process of collapsing tlogs of arakoon `{0}` on node `{1}`'\
                    .format(arakoon_cluster, node_ip)

                ArakoonCollapse.LOGGER.info("Successfully collapsed arakoon `{0}` on node `{1}`"
                                            .format(arakoon_cluster, node_ip))

        ArakoonCollapse.LOGGER.info("Finished validating arakoon collapsing")

    @staticmethod
    def get_nr_of_tlogs_in_folder(root_client, tlog_location):
        nr_of_tlogs = 0
        for file_name in root_client.file_list(tlog_location):
            if file_name.endswith('tlx') or file_name.endswith('tlog'):
                nr_of_tlogs += 1
        return nr_of_tlogs


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """

    return ArakoonCollapse().main(blocked)

if __name__ == "__main__":
    run()
