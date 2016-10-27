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
from ovs.log.log_handler import LogHandler
from ci.helpers.init_manager import InitManager
from ci.helpers.storagerouter import StoragerouterHelper
from ovs.extensions.storage.persistent.pyrakoonstore import PyrakoonStore, KeyNotFoundException


class ArakoonValidation(object):

    CASE_TYPE = 'FUNCTIONAL'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_arakoon_validation")

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
                ArakoonValidation.validate_cluster()
                return {'status': 'PASSED', 'case_type': ArakoonValidation.CASE_TYPE, 'errors': None}
            except Exception as ex:
                ArakoonValidation.LOGGER.error("Arakoon collapse failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': ArakoonValidation.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': ArakoonValidation.CASE_TYPE, 'errors': None}

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
        master_storagerouters = StoragerouterHelper.get_master_storagerouter_ips()
        assert len(master_storagerouters) >= 2, 'Environment has only `{0}` node(s)'.format(len(master_storagerouters))

        master_storagerouters.sort()
        arakoon_service_name = "ovs-arakoon-{0}".format(cluster_name)
        for storagerouter_ip in master_storagerouters:
            # check if service file is available
            ArakoonValidation.LOGGER.info("Validating if cluster service `{0}` is available on node `{1}`"
                                          .format(cluster_name, storagerouter_ip))
            assert InitManager.service_exists(arakoon_service_name, storagerouter_ip), \
                "Service file of `{0}` does not exists on storagerouter `{1}`".format(cluster_name, storagerouter_ip)

            # check if service is running on system
            ArakoonValidation.LOGGER.info("Validating if cluster service `{0}` is running on node `{1}`"
                                          .format(cluster_name, storagerouter_ip))
            assert InitManager.service_running(arakoon_service_name, storagerouter_ip), \
                "Service of `{0}` is not running on storagerouter `{1}`".format(cluster_name, storagerouter_ip)

        # perform nop, get and set on cluster
        key = 'integration-tests-{0}'.format(str(uuid.uuid4()))
        value = str(time.time())

        ArakoonValidation.LOGGER.info("Validating if cluster `{0}` works".format(cluster_name))

        # determine if there is a healthy cluster
        client = PyrakoonStore(cluster_name)
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
