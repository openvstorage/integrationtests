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
from ci.helpers.api import OVSClient
from ci.setup.backend import BackendSetup
from ovs.log.log_handler import LogHandler
from ci.helpers.backend import BackendHelper
from ci.remove.backend import BackendRemover
from ci.validate.backend import BackendValidation


class AddUpdateRemovePreset(object):

    CASE_TYPE = 'FUNCTIONAL'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_add_remove_backend")

    def __init__(self):
        pass

    @staticmethod
    def main(blocked):
        """
        Run all required methods for the test

        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        if not blocked:
            try:
                # execute tests twice, because of possible leftover constraints
                AddUpdateRemovePreset.validate_add_update_remove_preset()
                return {'status': 'PASSED', 'case_type': AddUpdateRemovePreset.CASE_TYPE, 'errors': None}
            except Exception as ex:
                AddUpdateRemovePreset.LOGGER.error("Backend add-remove failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': AddUpdateRemovePreset.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': AddUpdateRemovePreset.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_add_update_remove_preset(preset_name='integrationtests'):
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

        with open(CONFIG_LOC, "r") as JSON_CONFIG:
            config = json.load(JSON_CONFIG)

        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )

        # fetch existing backends
        alba_backends = BackendHelper.get_alba_backends()
        assert len(alba_backends) >= 1, "Not enough alba backends to test"

        # choose first alba backend & perform required tests
        alba_backend = alba_backends[0]

        # add and remove different presets
        AddUpdateRemovePreset.LOGGER.info("Started adding and removing different presets")
        for preset_def, preset_details in presets.iteritems():
            AddUpdateRemovePreset._add_remove_preset(alba_backend.name, preset_details, preset_def, api)
        AddUpdateRemovePreset.LOGGER.info("Finished adding and removing different presets")

        # add, update & remove a preset
        AddUpdateRemovePreset.LOGGER.info("Starting adding, updating & removing a preset")
        assert BackendSetup.add_preset(albabackend_name=alba_backend.name, preset_details=preset_basic, api=api), \
            "Adding the preset `{0}` has failed".format(preset_name)
        assert BackendValidation.check_preset_on_backend(preset_name, alba_backend.name), \
            "Preset `{0}` does not exists but it should on backend `{1}`"\
            .format(preset_name, alba_backend.name)
        assert BackendSetup.update_preset(albabackend_name=alba_backend.name, preset_name=preset_altered['name'],
                                          policies=preset_altered['policies'], api=api), \
            "Updating the preset `{0}` has failed".format(preset_name)
        assert BackendValidation.check_policies_on_preset(preset_name=preset_altered['name'],
                                                          albabackend_name=alba_backend.name,
                                                          policies=preset_altered['policies']), \
            "Updating the preset `{0}` has failed".format(preset_name)
        assert BackendRemover.remove_preset(preset_name=preset_name, albabackend_name=alba_backend.name,
                                            api=api), "Removing the preset `{0}` has failed".format(preset_name)
        assert not BackendValidation.check_preset_on_backend(preset_name, alba_backend.name), \
            "Preset `{0}` does exists but it should not be on backend `{1}`"\
            .format(preset_name, alba_backend.name)
        AddUpdateRemovePreset.LOGGER.info("Finished adding, updating & removing a preset")

    @staticmethod
    def _add_remove_preset(albabackend_name, preset_details, preset_definition, api):
        """
        Add & remove a preset

        :param albabackend_name: name of a existing alba backend
        :type albabackend_name: str
        :param preset_details: details of a preset
        :type preset_details: dict
        :param preset_definition: definition of the preset (e.g. preset_compression_no_encryption)
        :type preset_definition: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :return:
        """

        AddUpdateRemovePreset.LOGGER.info("Starting adding `{0}`".format(preset_definition))
        assert BackendSetup.add_preset(albabackend_name=albabackend_name, preset_details=preset_details, api=api), \
            "Adding the preset `{0}` has failed".format(preset_definition)
        assert BackendValidation.check_preset_on_backend(preset_details['name'], albabackend_name), \
            "Preset `{0}` does not exists but it should on backend `{1}`"\
            .format(preset_details['name'], albabackend_name)
        AddUpdateRemovePreset.LOGGER.info("Finished adding `{0}`".format(preset_definition))
        AddUpdateRemovePreset.LOGGER.info("Starting removing `{0}`".format(preset_definition))
        assert BackendRemover.remove_preset(preset_name=preset_details['name'], albabackend_name=albabackend_name,
                                            api=api), "Removing the preset `{0}` has failed".format(preset_definition)
        assert not BackendValidation.check_preset_on_backend(preset_details['name'], albabackend_name), \
            "Preset `{0}` does exists but it should not be on backend `{1}`"\
            .format(preset_details['name'], albabackend_name)
        AddUpdateRemovePreset.LOGGER.info("Finished removing `{0}`".format(preset_definition))


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
