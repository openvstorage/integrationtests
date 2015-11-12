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


def setup():
    disklayout.add_db_role()
    if not generic.is_backend_present(BACKEND_NAME, BACKEND_TYPE):
        alba.add_alba_backend(BACKEND_NAME)


def teardown():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    if backend:
        alba.remove_alba_backend(backend['alba_backend_guid'])


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
    name = 'be_preset_02'
    status, message = alba.add_preset(alba_backend, name, policies=[[1, 1, 1, 2]])
    assert status, "Add preset failed with: {0}".format(message)
    status, message = alba.remove_preset(alba_backend, name)
    assert status, "Remove preset failed with: {0}".format(message)


def be_0003_add_remove_preset_compression_no_encryption_test():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    name = 'be_preset_03'
    status, message = alba.add_preset(alba_backend, name, policies=[[1, 1, 1, 2]])
    assert status, "Add preset failed with: {0}".format(message)
    status, message = alba.remove_preset(alba_backend, name)
    assert status, "Remove preset failed with: {0}".format(message)


def be_0004_validate_preset_with_replication_copies_test():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    name = 'be_preset_04'
    for nr in xrange(6):
        status, message = alba.add_preset(alba_backend, name + str(nr), policies=[[1, nr, 1, 1 + nr]])
        assert status, "Add preset failed with: {0}".format(message)
        status, message = alba.remove_preset(alba_backend, name + str(nr))
        assert status, "Remove preset failed with: {0}".format(message)


def be_0005_add_remove_preset_no_compression_encryption_test():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    name = 'be_preset_05'
    status, message = alba.add_preset(alba_backend, name, policies=[[1, 1, 1, 2]], encryption='aes-cbc-256')
    assert status, "Add preset failed with: {0}".format(message)
    status, message = alba.remove_preset(alba_backend, name)
    assert status, "Remove preset failed with: {0}".format(message)


def be_0006_add_remove_preset_compression_encryption_test():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    name = 'be_preset_06a'
    status, message = alba.add_preset(alba_backend, name, policies=[[1, 1, 1, 2]], compression='bz2', encryption='aes-cbc-256')
    assert status, "Add preset failed with: {0}".format(message)
    status, message = alba.remove_preset(alba_backend, name)
    assert status, "Remove preset failed with: {0}".format(message)
    name = 'be_preset_06b'
    status, message = alba.add_preset(alba_backend, name, policies=[[1, 1, 1, 2]], compression='snappy', encryption='aes-cbc-256')
    assert status, "Add preset failed with: {0}".format(message)
    status, message = alba.remove_preset(alba_backend, name)
    assert status, "Remove preset failed with: {0}".format(message)


def ovs_3490_add_remove_preset_test():
    """
    adds and removes a preset with encryption to an existing alba backend
    """
    name = 'ovs-3490'
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
    status, message = alba.add_preset(alba_backend, name, policies=[[1, 1, 1, 2]], encryption='aes-cbc-256')
    assert status, "Add preset failed with: {0}".format(message)
    status, message = alba.remove_preset(alba_backend, name)
    assert status, "Remove preset failed with: {0}".format(message)
