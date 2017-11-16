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
import json
from ci.main import CONFIG_LOC
from ci.api_lib.helpers.api import OVSClient
from ci.api_lib.remove.backend import BackendRemover
from ci.api_lib.setup.backend import BackendSetup
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.logger import Logger


class AddRemoveBackend(CIConstants):

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = "ci_scenario_add_remove_backend"
    LOGGER = Logger("scenario-{0}".format(TEST_NAME))

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=[{'framework': ['ovs-workers']}])
    def main(blocked):
        """
        Run all required methods for the test
        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        _ = blocked
        return AddRemoveBackend.validate_add_remove_backend()

    @classmethod
    def validate_add_remove_backend(cls, backend_name='integrationtests'):
        """
        Validate if a add & remove backend works

        :param backend_name: name of a new alba backend (DEFAULT=integrationtests)
        :type backend_name: str
        :return:
        """
        AddRemoveBackend.LOGGER.info("Starting creation of backend `{0}`".format(backend_name))
        assert BackendSetup.add_backend(backend_name=backend_name, api=cls.api, scaling='LOCAL'), \
            "Backend `{0}` has failed to create".format(backend_name)
        AddRemoveBackend.LOGGER.info("Finished creation of backend `{0}`".format(backend_name))
        AddRemoveBackend.LOGGER.info("Starting removal of backend `{0}`".format(backend_name))
        assert BackendRemover.remove_backend(albabackend_name=backend_name, api=cls.api), \
            "Backend `{0}` has failed to be removed".format(backend_name)
        AddRemoveBackend.LOGGER.info("Finished removal of backend `{0}`".format(backend_name))

        # @TODO: add global backend, add a local backend, remove it


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return AddRemoveBackend().main(blocked)

if __name__ == "__main__":
    run()
