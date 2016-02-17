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

import time
from ci.tests.backend import alba, general_backend
from ci.tests.disklayout import disklayout
from ci.tests.general.logHandler import LogHandler
from ovs.extensions.generic.system import System
from ovs.lib.albascheduledtask import AlbaScheduledTaskController
from ci.tests.general import general

logger = LogHandler.get('backend', name='alba')
logger.logger.propagate = False

testsToRun = general.get_tests_to_run(general.get_test_level())

BACKEND_NAME = general.get_config().get('backend', 'name')
BACKEND_TYPE = general.get_config().get('backend', 'type')
NR_OF_DISKS_TO_CLAIM = general.get_config().getint('backend', 'nr_of_disks_to_claim')
TYPE_OF_DISKS_TO_CLAIM = general.get_config().get('backend', 'type_of_disks_to_claim')

assert BACKEND_NAME, "Please fill out a valid backend name in autotest.cfg file"
assert BACKEND_TYPE in general_backend.VALID_BACKEND_TYPES, "Please fill out a valid backend type in autotest.cfg file"


def setup():
    """
    Make necessary changes before being able to run the tests
    :return: None
    """
    my_sr = System.get_my_storagerouter()
    disklayout.add_db_role(my_sr.guid)
    backend = general_backend.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    if not backend:
        backend_guid = alba.add_alba_backend(BACKEND_NAME)
        backend = general_backend.get_backend(backend_guid)
    alba.claim_disks(backend['alba_backend_guid'], NR_OF_DISKS_TO_CLAIM, TYPE_OF_DISKS_TO_CLAIM)


def teardown():
    """
    Removal actions of possible things left over after the test-run
    :return: None
    """
    backend = general_backend.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    if backend:
        alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
        alba.unclaim_disks(alba_backend)
        alba.remove_alba_backend(backend['alba_backend_guid'])


def verify_policies_for_preset(preset_name, policies, compression, encryption):
    backend = general_backend.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
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
    backend = general_backend.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    presets = alba_backend['presets']
    for preset in presets:
        if name == preset['name']:
            return True
    return False


def add_preset(name, compression, encryption, policies, remove_when_finished=True):
    backend = general_backend.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
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
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)
    if not general_backend.is_backend_present(BACKEND_NAME, BACKEND_TYPE):
        backend_guid = alba.add_alba_backend(BACKEND_NAME)
    else:
        backend_guid = general_backend.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)['guid']

    is_running = alba.is_alba_backend_running(backend_guid, trigger=True)
    assert is_running, "Backend {0} is not present/running!".format(BACKEND_NAME)


def be_0002_add_remove_preset_no_compression_no_encryption_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=2,
                          tests_to_run=testsToRun)
    compression = 'none'
    encryption = 'none'
    name = 'be_preset_02'
    policies = [[1, 1, 1, 2]]
    add_preset(name, compression, encryption, policies)


def be_0003_add_remove_preset_compression_no_encryption_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=3,
                          tests_to_run=testsToRun)
    name = 'be_preset_03'
    compression = 'bz2'
    encryption = 'none'
    policies = [[1, 1, 1, 2]]
    add_preset(name, compression, encryption, policies)


def be_0004_validate_preset_with_replication_copies_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=4,
                          tests_to_run=testsToRun)
    compression = 'none'
    encryption = 'none'
    name_prefix = 'be_preset_04'
    for nr in xrange(6):
        name = name_prefix + str(nr)
        policies = [[1, nr, 1, 1 + nr]]
        add_preset(name, compression, encryption, policies)


def be_0005_add_remove_preset_no_compression_encryption_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=5,
                          tests_to_run=testsToRun)
    name = 'be_preset_05'
    compression = 'none'
    encryption = 'aes-cbc-256'
    policies = [[1, 1, 1, 2]]
    add_preset(name, compression, encryption, policies)


def be_0006_add_remove_preset_compression_encryption_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=6,
                          tests_to_run=testsToRun)
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
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=7,
                          tests_to_run=testsToRun)
    backend = general_backend.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
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
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=8,
                          tests_to_run=testsToRun)

    name = 'ovs-3490'
    backend = general_backend.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
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


def ovs_3769_validation_test():
    """
    Create an albanode with an asd statistics part set to empty dictionary
    Assert code does not raise
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=9,
                          tests_to_run=testsToRun)

    from ovs.dal.hybrids.albanode import AlbaNode
    from ovs.dal.hybrids.albaasd import AlbaASD
    from ovs.dal.hybrids.albabackend import AlbaBackend
    from ovs.dal.hybrids.backend import Backend
    from ovs.dal.lists.backendtypelist import BackendTypeList

    an = AlbaNode()
    an.password = 'rooter'
    an.node_id = 'ovs3769an'
    an.port = 1234
    an.ip = '127.0.0.1'
    an.username = 'root'
    an.save()

    bet = BackendTypeList.get_backend_type_by_code('alba')

    be = Backend()
    be.backend_type = bet
    be.name = 'ovs3769be'
    be.save()

    abe = AlbaBackend()
    abe.backend = be
    abe.save()

    asd = AlbaASD()
    asd.alba_backend = abe
    asd.asd_id = 'ovs3769asd'
    asd.alba_node = an
    asd.save()

    try:
        abe._statistics()
    except KeyError, ex:
        logger.error('Regression OVS-3769 - asd statistics raises a KeyError: {0}'.format(str(ex)))

    assert asd.statistics == dict(), "asd statistics should return an empty dict, go {0}".format(asd.statistics)
    asd.delete()
    an.delete()
    abe.delete()
    be.delete()


def ovs_3188_verify_namespace_test():
    nr_of_disks_to_create = 5
    namespace_prefix = 'ovs_3188-'
    compression = 'none'
    encryption = 'none'
    preset_name = 'be_preset_02'
    policies = [[1, 1, 1, 2]]

    backend = general_backend.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    alba_backend_name = alba_backend['name']
    alba.add_preset(alba_backend, preset_name, policies, compression, encryption)

    for x in range(nr_of_disks_to_create):
        namespace_name = namespace_prefix + str(x)
        alba.create_namespace(alba_backend_name, namespace_name, preset_name)

        alba.upload_file(alba_backend_name, namespace_name, 1024*1024*1)

    AlbaScheduledTaskController.verify_namespaces()

    alba.remove_alba_namespaces(alba_backend_name)
    alba.remove_preset(alba_backend, preset_name)
