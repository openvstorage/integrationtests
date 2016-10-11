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

from ovs.extensions.generic.remote import remote
from ovs.dal.lists.servicelist import ServiceList
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.extensions.generic.sshclient import SSHClient
from ci.helpers.storagerouter import StoragerouterHelper
from ovs.lib.scheduledtask import ScheduledTaskController
from ovs.extensions.generic.configuration import Configuration


class ArakoonCollapse(object):

    CASE_TYPE = 'FUNCTIONAL'

    def __init__(self):
        pass

    @staticmethod
    def main():
        try:
            ArakoonCollapse.test_collapse()
            return {'status': 'PASSED', 'case_type': ArakoonCollapse.CASE_TYPE, 'errors': None}
        except AssertionError as ex:
            return {'status': 'FAILED', 'case_type': ArakoonCollapse.CASE_TYPE, 'errors': ex}

    @staticmethod
    def test_collapse():
        """
        Required method that has to follow our json output guideline
        This data will be sent to testrails to process it thereafter
        :return:
        """
        node_ips = StoragerouterHelper.get_storagerouter_ips()
        node_ips.sort()
        for node_ip in node_ips:
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
            for arakoon_cluster in arakoon_clusters:
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

                    ScheduledTaskController.collapse_arakoon()

                    nr_of_tlogs = ArakoonCollapse.get_nr_of_tlogs_in_folder(root_client, tlog_location)
                    new_headdb_timestamp = root_client.run('stat --format=%Y {0}/{1}'.format(tlog_location, 'head.db'))

                    # perform assertion
                    assert nr_of_tlogs <= 2,\
                        'Arakoon collapse left {0} tlogs on the environment, expecting less than 2'.format(nr_of_tlogs)
                    assert old_headdb_timestamp != new_headdb_timestamp,\
                        'Timestamp of the head_db file was not changed in the process of collapsing tlogs'

    @staticmethod
    def get_nr_of_tlogs_in_folder(root_client, tlog_location):
        nr_of_tlogs = 0
        for file_name in root_client.file_list(tlog_location):
            if file_name.endswith('tlx') or file_name.endswith('tlog'):
                nr_of_tlogs += 1
        return nr_of_tlogs


def run():
    return ArakoonCollapse().main()

if __name__ == "__main__":
    run()
