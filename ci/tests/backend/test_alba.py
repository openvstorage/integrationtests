# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Non-Commercial License, Version 1.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/OVS_NON_COMMERCIAL
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ci.tests.backend import alba, generic
from ci.tests.disklayout import disklayout
from ci.tests.general.general import test_config

BACKEND_NAME = test_config.get('backend', 'name')
BACKEND_TYPE = test_config.get('backend', 'type')

assert BACKEND_NAME, "Please fill out a valid backend name in autotest.cfg file"
assert BACKEND_TYPE in generic.VALID_BACKEND_TYPES, "Please fill out a valid backend type in autotest.cfg file"


def setup():
    disklayout.add_db_role()
    if not generic.is_backend_present(BACKEND_NAME, BACKEND_TYPE):
        alba.add_alba_backend(BACKEND_NAME)


def teardown():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    if backend:
        alba.remove_alba_backend(backend['alba_backend_guid'])


def verify_policies_for_preset(preset_name, policies, compression, encryption):
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    presets = alba_backend['presets']

    valid = False
    for preset in presets:
        if preset['name'] == preset_name:
            print preset
            assert preset['compression'] == compression,\
                "Alba compression {0} does not match configured {1} type".format(preset['compression'],
                                                                                 compression)
            assert preset['fragment_encryption'][0] == encryption, \
                "Alba encryption {0} does not match configured {1} type".format(preset['fragment_encryption'],
                                                                                encryption)
            for policy in policies:
                valid = False
                print 'Validating policy: {0}'.format(policy)
                for alba_policy in preset['policies']:
                    print 'Matching: {0} with {1}'.format(tuple(policy), alba_policy)
                    if tuple(policy) == alba_policy:
                        valid = True
                        continue
    return valid


def is_preset_present(name):
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    presets = alba_backend['presets']
    for preset in presets:
        if name == preset['name']:
            return True
    return False


def be_0001_add_and_verify_backend_is_running_test():
    disklayout.add_db_role()
    if not generic.is_backend_present(BACKEND_NAME, BACKEND_TYPE):
        backend_guid = alba.add_alba_backend(BACKEND_NAME)
    else:
        backend_guid = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)['guid']

    is_running = alba.is_alba_backend_running(backend_guid, trigger=True)
    assert is_running, "Backend {0} is not present/running!".format(BACKEND_NAME)


def be_0002_add_remove_preset_no_compression_no_encryption_test():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    compression = 'none'
    encryption = 'none'
    name = 'be_preset_02'
    policies = [[1, 1, 1, 2]]
    status, message = alba.add_preset(alba_backend, name, policies, compression, encryption)
    assert status, "Add preset failed with: {0}".format(message)
    assert is_preset_present(name), "Preset with name {0} is not present".format(name)
    verify_policies_for_preset(name, policies, compression, encryption)
    status, message = alba.remove_preset(alba_backend, name, )
    assert status, "Remove preset failed with: {0}".format(message)
    assert not is_preset_present(name), "Preset with name {0} is not present".format(name)


def be_0003_add_remove_preset_compression_no_encryption_test():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    name = 'be_preset_03'
    compression = 'bz2'
    encryption = 'none'
    policies = [[1, 1, 1, 2]]
    status, message = alba.add_preset(alba_backend, name, policies, compression, encryption)
    assert status, "Add preset failed with: {0}".format(message)
    assert is_preset_present(name), "Preset with name {0} is not present".format(name)
    verify_policies_for_preset(name, policies, compression, encryption)
    status, message = alba.remove_preset(alba_backend, name)
    assert status, "Remove preset failed with: {0}".format(message)
    assert not is_preset_present(name), "Preset with name {0} is not present".format(name)


def be_0004_validate_preset_with_replication_copies_test():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    compression = 'none'
    encryption = 'none'
    name = 'be_preset_04'
    for nr in xrange(6):
        name += str(nr)
        policies = [[1, nr, 1, 1 + nr]]
        status, message = alba.add_preset(alba_backend, name, policies, compression, encryption)
        assert status, "Add preset failed with: {0}".format(message)
        assert is_preset_present(name), "Preset with name {0} is not present".format(name)
        verify_policies_for_preset(name, policies, compression, encryption)
        status, message = alba.remove_preset(alba_backend, name)
        assert status, "Remove preset failed with: {0}".format(message)
        assert not is_preset_present(name), "Preset with name {0} is not present".format(name)



def be_0005_add_remove_preset_no_compression_encryption_test():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    name = 'be_preset_05'
    compression = 'none'
    encryption = 'aes-cbc-256'
    policies = [[1, 1, 1, 2]]
    status, message = alba.add_preset(alba_backend, name, policies, compression, encryption)
    assert status, "Add preset failed with: {0}".format(message)
    verify_policies_for_preset(name, policies, compression, encryption)
    status, message = alba.remove_preset(alba_backend, name)
    assert status, "Remove preset failed with: {0}".format(message)
    assert not is_preset_present(name), "Preset with name {0} is not present".format(name)


def be_0006_add_remove_preset_compression_encryption_test():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    name = 'be_preset_06a'
    compression = 'bz2'
    encryption = 'aes-cbc-256'
    policies = [[1, 1, 1, 2]]
    status, message = alba.add_preset(alba_backend, name, policies, compression, encryption)
    assert status, "Add preset failed with: {0}".format(message)
    verify_policies_for_preset(name, policies, compression, encryption)
    status, message = alba.remove_preset(alba_backend, name)
    assert status, "Remove preset failed with: {0}".format(message)
    assert not is_preset_present(name), "Preset with name {0} is not present".format(name)

    name = 'be_preset_06b'
    compression = 'snappy'
    status, message = alba.add_preset(alba_backend, name, policies, compression, encryption)
    assert status, "Add preset failed with: {0}".format(message)
    verify_policies_for_preset(name, policies, compression, encryption)
    status, message = alba.remove_preset(alba_backend, name)
    assert status, "Remove preset failed with: {0}".format(message)
    assert not is_preset_present(name), "Preset with name {0} is not present".format(name)


def ovs_3490_add_remove_preset_test():
    """
    adds and removes a preset with encryption to an existing alba backend
    """
    name = 'ovs-3490'
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    policies = [[1, 1, 1, 2]]
    compression = 'none'
    encryption = 'aes-cbc-256'
    status, message = alba.add_preset(alba_backend, name, policies, compression, encryption)
    assert status, "Add preset failed with: {0}".format(message)
    verify_policies_for_preset(name, policies, compression, encryption)
    status, message = alba.remove_preset(alba_backend, name)
    assert status, "Remove preset failed with: {0}".format(message)
    assert not is_preset_present(name), "Preset with name {0} is not present".format(name)
