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
from ci.api_lib.helpers.backend import BackendHelper
from ci.api_lib.remove.backend import BackendRemover
from ci.api_lib.setup.backend import BackendSetup
from ci.api_lib.validate.backend import BackendValidation
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.logger import Logger


class AddUpdateRemovePreset(CIConstants):

    CASE_TYPE = 'FUNCTIONALITY'
    TEST_NAME = "ci_scenario_add_remove_backend"
    LOGGER = Logger("scenario-{0}".format(TEST_NAME))

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components={'framework': ['ovs-workers'], 'arakoon': ['ovs-arakoon-*-abm']})
    def main(blocked):
        """
        Run all required methods for the test
        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        _ = blocked
        return AddUpdateRemovePreset.validate_add_update_remove_preset()

    @classmethod
    def validate_add_update_remove_preset(cls, preset_name='integrationtests'):
        """
        Validate if a preset can be added/updated/removed on a existing backend

        :param preset_name: name of a new preset (DEFAULT=integrationtests)
        :type preset_name: str
        :return:
        """
        # test different preset scenario's
        presets = {
           "preset_no_compression_no_encryption": {
              "name": preset_name,
              "compression": "none",
              "encryption": "none",
              "policies": [
                 [2, 2, 3, 4],
                 [1, 2, 2, 3]
              ],
              "fragment_size": 1048576
           },
           "preset_compression_no_encryption": {
              "name": preset_name,
              "compression": "snappy",
              "encryption": "none",
              "policies": [
                 [2, 2, 3, 4],
                 [1, 2, 2, 3]
              ],
              "fragment_size": 2097152
           },
           "preset_no_compression_encryption": {
              "name": preset_name,
              "compression": "none",
              "encryption": "aes-cbc-256",
              "policies": [
                 [2, 2, 3, 4],
                 [1, 2, 2, 3]
              ],
              "fragment_size": 4194304
           },
           "preset_compression_encryption": {
              "name": preset_name,
              "compression": "bz2",
              "encryption": "aes-cbc-256",
              "policies": [
                 [2, 2, 3, 4],
                 [1, 2, 2, 3]
              ],
              "fragment_size": 8388608
           }
        }

        # add_update_remove
        preset_basic = {
            "name": preset_name,
            "compression": "bz2",
            "encryption": "aes-cbc-256",
            "policies": [
              [2, 2, 3, 4],
              [1, 2, 2, 3]
            ],
            "fragment_size": 8388608
          }
        preset_altered = {
            "name": preset_name,
            "compression": "bz2",
            "encryption": "aes-cbc-256",
            "policies": [
              [2, 2, 3, 4]
            ],
            "fragment_size": 8388608
          }

        # fetch existing backends
        alba_backends = BackendHelper.get_alba_backends()
        assert len(alba_backends) >= 1, "Not enough alba backends to test"

        # choose first alba backend & perform required tests
        alba_backend = alba_backends[0]

        # add and remove different presets
        cls.LOGGER.info("Started adding and removing different presets")
        for preset_def, preset_details in presets.iteritems():
            cls._add_remove_preset(alba_backend.name, preset_details, preset_def)
        cls.LOGGER.info("Finished adding and removing different presets")

        # add, update & remove a preset
        cls.LOGGER.info("Starting adding, updating & removing a preset")
        assert BackendSetup.add_preset(albabackend_name=alba_backend.name, preset_details=preset_basic), \
            "Adding the preset `{0}` has failed".format(preset_name)
        time.sleep(1)
        assert BackendValidation.check_preset_on_backend(preset_name, alba_backend.name), \
            "Preset `{0}` does not exists but it should on backend `{1}`"\
            .format(preset_name, alba_backend.name)
        assert BackendSetup.update_preset(albabackend_name=alba_backend.name, preset_name=preset_altered['name'],
                                          policies=preset_altered['policies']), \
            "Updating the preset `{0}` has failed".format(preset_name)
        time.sleep(1)
        assert BackendValidation.check_policies_on_preset(preset_name=preset_altered['name'],
                                                          albabackend_name=alba_backend.name,
                                                          policies=preset_altered['policies']), \
            "Updating the preset `{0}` has failed".format(preset_name)
        assert BackendRemover.remove_preset(preset_name=preset_name, albabackend_name=alba_backend.name,
                                           ), "Removing the preset `{0}` has failed".format(preset_name)
        time.sleep(1)
        assert not BackendValidation.check_preset_on_backend(preset_name, alba_backend.name), \
            "Preset `{0}` does exists but it should not be on backend `{1}`"\
            .format(preset_name, alba_backend.name)
        cls.LOGGER.info("Finished adding, updating & removing a preset")

    @classmethod
    def _add_remove_preset(cls, albabackend_name, preset_details, preset_definition):
        """
        Add & remove a preset

        :param albabackend_name: name of a existing alba backend
        :type albabackend_name: str
        :param preset_details: details of a preset
        :type preset_details: dict
        :param preset_definition: definition of the preset (e.g. preset_compression_no_encryption)
        :type preset_definition: str
        """

        cls.LOGGER.info("Starting adding `{0}`".format(preset_definition))
        assert BackendSetup.add_preset(albabackend_name=albabackend_name, preset_details=preset_details), \
            "Adding the preset `{0}` has failed".format(preset_definition)
        time.sleep(1)
        assert BackendValidation.check_preset_on_backend(preset_details['name'], albabackend_name), \
            "Preset `{0}` does not exists but it should on backend `{1}`"\
            .format(preset_details['name'], albabackend_name)
        cls.LOGGER.info("Finished adding `{0}`".format(preset_definition))
        cls.LOGGER.info("Starting removing `{0}`".format(preset_definition))
        assert BackendRemover.remove_preset(preset_name=preset_details['name'], albabackend_name=albabackend_name),\
            "Removing the preset `{0}` has failed".format(preset_definition)
        time.sleep(1)
        assert not BackendValidation.check_preset_on_backend(preset_details['name'], albabackend_name), \
            "Preset `{0}` does exists but it should not be on backend `{1}`"\
            .format(preset_details['name'], albabackend_name)
        cls.LOGGER.info("Finished removing `{0}`".format(preset_definition))


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return AddUpdateRemovePreset().main(blocked)


if __name__ == "__main__":
    run()
