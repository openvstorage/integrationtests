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
import time
import uuid
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.logger import Logger
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.services.servicefactory import ServiceFactory
from ovs_extensions.storage.persistent.pyrakoonstore import PyrakoonStore, KeyNotFoundException


class ArakoonValidation(CIConstants):

    CASE_TYPE = 'FUNCTIONALITY'
    TEST_NAME = "ci_scenario_arakoon_validation"
    LOGGER = Logger("scenario-{0}".format(TEST_NAME))

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=['arakoon'])
    def main(blocked):
        """
        Run all required methods for the test
        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        _ = blocked
        return ArakoonValidation.validate_cluster()

    @staticmethod
    def validate_cluster(cluster_name='ovsdb'):
        """
        Validate if the chosen cluster is
         * deployed on all required nodes
         * running on all required nodes
         * working correctly on all required nodes

        :param cluster_name: name of a existing arakoon cluster (DEFAULT=ovsdb)
        :type cluster_name: str
        :return:
        """
        ArakoonValidation.LOGGER.info("Starting validating arakoon cluster")
        master_storagerouters = [storagerouter.ip for storagerouter in StorageRouterList.get_masters()]
        assert len(master_storagerouters) >= 2, 'Environment has only `{0}` node(s)'.format(len(master_storagerouters))

        master_storagerouters.sort()
        arakoon_service_name = "ovs-arakoon-{0}".format(cluster_name)
        service_manager = ServiceFactory.get_manager()
        for storagerouter_ip in master_storagerouters:
            client = SSHClient(storagerouter_ip, username='root')
            # check if service file is available
            ArakoonValidation.LOGGER.info("Validating if cluster service `{0}` is available on node `{1}`".format(cluster_name, storagerouter_ip))
            assert service_manager.has_service(arakoon_service_name, client), "Service file of `{0}` does not exists on storagerouter `{1}`"\
                .format(cluster_name, storagerouter_ip)
            # check if service is running on system
            ArakoonValidation.LOGGER.info("Validating if cluster service `{0}` is running on node `{1}`"
                                          .format(cluster_name, storagerouter_ip))
            assert service_manager.get_service_status(arakoon_service_name, client) == 'active', \
                "Service of `{0}` is not running on storagerouter `{1}`".format(cluster_name, storagerouter_ip)

        # perform nop, get and set on cluster
        key = 'integration-tests-{0}'.format(str(uuid.uuid4()))
        value = str(time.time())
        ArakoonValidation.LOGGER.info("Validating if cluster `{0}` works".format(cluster_name))
        # determine if there is a healthy cluster
        configuration = Configuration.get('/ovs/arakoon/{0}/config'.format(cluster_name), raw=True)
        client = PyrakoonStore(cluster_name, configuration)
        client.nop()
        # perform set, get & compare
        client.set(key, value)
        get_value = client.get(key)
        assert get_value == value, "Value mismatch on cluster `{0}`, get value `{1}`, " \
                                   "expected value `{2}` on key `{3}`".format(cluster_name, get_value, value, key)

        # perform delete
        client.delete(key)
        try:
            assert not client.get(key), "Key `{0}` still exists on cluster `{1}` after deleting it"\
                .format(key, cluster_name)
        except KeyNotFoundException:
            # key not found so test has passed
            assert True

        ArakoonValidation.LOGGER.info("Finished validating arakoon cluster")


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return ArakoonValidation().main(blocked)


if __name__ == "__main__":
    run()
