# Copyright 2015 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ci.tests.backend import alba, generic
from ci.tests.disklayout import disklayout
from ci.tests.general.general import test_config

from ovs.extensions.generic.system import System

import time

BACKEND_NAME = test_config.get('backend', 'name')
BACKEND_TYPE = test_config.get('backend', 'type')
NR_OF_DISKS_TO_CLAIM = int(test_config.get('backend', 'nr_of_disks_to_claim'))
TYPE_OF_DISKS_TO_CLAIM = test_config.get('backend', 'type_of_disks_to_claim')

assert BACKEND_NAME, "Please fill out a valid backend name in autotest.cfg file"
assert BACKEND_TYPE in generic.VALID_BACKEND_TYPES, "Please fill out a valid backend type in autotest.cfg file"


def setup():
    my_sr = System.get_my_storagerouter()
    disklayout.add_db_role(my_sr.guid)
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    if not backend:
        backend_guid = alba.add_alba_backend(BACKEND_NAME)
        backend = generic.get_backend(backend_guid)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    alba.claim_disks(alba_backend, NR_OF_DISKS_TO_CLAIM, TYPE_OF_DISKS_TO_CLAIM)


def teardown():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    alba.unclaim_disks(alba_backend)
    if backend:
        alba.remove_alba_backend(backend['alba_backend_guid'])


def verify_policies_for_preset(preset_name, policies, compression, encryption):
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    presets = alba_backend['presets']

    valid = False
    for preset in presets:
        if preset['name'] == preset_name:
            assert preset['compression'] == compression,\
                "Alba compression {0} does not match configured {1} type".format(preset['compression'],
                                                                                 compression)
            assert preset['fragment_encryption'][0] == encryption, \
                "Alba encryption {0} does not match configured {1} type".format(preset['fragment_encryption'],
                                                                                encryption)
            for policy in policies:
                valid = False
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


def add_preset(name, compression, encryption, policies, remove_when_finished=True):
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    status, message = alba.add_preset(alba_backend, name, policies, compression, encryption)
    assert status, "Add preset failed with: {0}".format(message)
    assert is_preset_present(name), "Preset with name {0} is not present".format(name)
    verify_policies_for_preset(name, policies, compression, encryption)
    if remove_when_finished:
        status, message = alba.remove_preset(alba_backend, name, )
        assert status, "Remove preset failed with: {0}".format(message)
        assert not is_preset_present(name), "Preset with name {0} is not present".format(name)


def be_0001_add_and_verify_backend_is_running_test():
    if not generic.is_backend_present(BACKEND_NAME, BACKEND_TYPE):
        backend_guid = alba.add_alba_backend(BACKEND_NAME)
    else:
        backend_guid = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)['guid']

    is_running = alba.is_alba_backend_running(backend_guid, trigger=True)
    assert is_running, "Backend {0} is not present/running!".format(BACKEND_NAME)


def be_0002_add_remove_preset_no_compression_no_encryption_test():
    compression = 'none'
    encryption = 'none'
    name = 'be_preset_02'
    policies = [[1, 1, 1, 2]]
    add_preset(name, compression, encryption, policies)


def be_0003_add_remove_preset_compression_no_encryption_test():
    name = 'be_preset_03'
    compression = 'bz2'
    encryption = 'none'
    policies = [[1, 1, 1, 2]]
    add_preset(name, compression, encryption, policies)


def be_0004_validate_preset_with_replication_copies_test():
    compression = 'none'
    encryption = 'none'
    name_prefix = 'be_preset_04'
    for nr in xrange(6):
        name = name_prefix + str(nr)
        policies = [[1, nr, 1, 1 + nr]]
        add_preset(name, compression, encryption, policies)


def be_0005_add_remove_preset_no_compression_encryption_test():
    name = 'be_preset_05'
    compression = 'none'
    encryption = 'aes-cbc-256'
    policies = [[1, 1, 1, 2]]
    add_preset(name, compression, encryption, policies)


def be_0006_add_remove_preset_compression_encryption_test():
    name = 'be_preset_06a'
    compression = 'bz2'
    encryption = 'aes-cbc-256'
    policies = [[1, 1, 1, 2]]
    add_preset(name, compression, encryption, policies)

    name = 'be_preset_06b'
    compression = 'snappy'
    add_preset(name, compression, encryption, policies)


def be_0007_add_update_remove_preset_test():
    """
    Validation for OVS-3187 - edit policy of preset
    """
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])

    timeout = 120
    preset_name = 'be_preset_0007'
    namespace_name = 'be_0007_ns'
    compression = 'none'
    encryption = 'aes-cbc-256'
    org_policy = [[1, 1, 1, 2]]
    new_policy = [[2, 2, 3, 3]]

    add_preset(preset_name, compression, encryption, org_policy, remove_when_finished=False)
    result = alba.list_namespaces(BACKEND_NAME)

    for namespace in result:
        if namespace['name'] == namespace_name:
            alba.delete_namespace(BACKEND_NAME, namespace_name)
    alba.create_namespace(BACKEND_NAME, namespace_name, preset_name)

    # @todo: remove next deliver messages command when http://jira.cloudfounders.com/browse/OVS-3580 is fixed
    # command is necessary after namespace create to allow object upload to be distributed to all disks according
    # to policy
    alba.run(BACKEND_NAME, 'deliver-messages', [], False)

    _, _ = alba.upload_file(BACKEND_NAME, namespace_name, 1024*1024)

    result = alba.show_namespace(BACKEND_NAME, namespace_name)['bucket_count']

    assert len(result) == 1, "Only one policy should be present, found: {0}".format(result)
    alba.is_bucket_count_valid_with_policy(result, org_policy)

    # update and verify policies for preset
    alba.update_preset(alba_backend, preset_name, new_policy)

    result = alba.show_namespace(BACKEND_NAME, namespace_name)['bucket_count']
    assert len(result) == 1, "Expected 1 policy, but got: {0}".format(result)

    object_has_new_policy = False
    for _ in xrange(timeout):
        if alba.is_bucket_count_valid_with_policy(result, new_policy):
            object_has_new_policy = True
            break
        time.sleep(1)
        result = alba.show_namespace(BACKEND_NAME, namespace_name)['bucket_count']

    assert object_has_new_policy, "Object was not rewritten within {0} seconds: {1}".format(timeout, result)

    # cleanup
    alba.delete_namespace(BACKEND_NAME, namespace_name)
    alba.remove_preset(alba_backend, preset_name)


def ovs_3490_add_remove_preset_test():
    """
    Adds and removes a preset with encryption to an existing alba backend
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
