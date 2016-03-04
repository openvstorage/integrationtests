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

"""
Init for Backend testsuite
"""

from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_backend import GeneralBackend
from ci.tests.general.general_disk import GeneralDisk
from ci.tests.general.general_storagerouter import GeneralStorageRouter


def setup():
    """
    Setup for Backend package, will be executed when any test in this package is being executed
    Make necessary changes before being able to run the tests
    :return: None
    """
    autotest_config = General.get_config()
    backend_name = autotest_config.get('backend', 'name')
    assert backend_name, "Please fill out a valid backend name in autotest.cfg file"

    my_sr = GeneralStorageRouter.get_local_storagerouter()
    GeneralDisk.add_db_role(my_sr)
    backend = GeneralBackend.get_by_name(backend_name)
    if backend is None:
        alba_backend = GeneralAlba.add_alba_backend(backend_name)
    else:
        alba_backend = backend.alba_backend
    nr_disks_to_claim = autotest_config.getint('backend', 'nr_of_disks_to_claim')
    type_of_disk_to_claim = autotest_config.get('backend', 'type_of_disks_to_claim')
    GeneralAlba.claim_disks(alba_backend, nr_disks_to_claim, type_of_disk_to_claim)


def teardown():
    """
    Teardown for Backend package, will be executed when all started tests in this package have ended
    Removal actions of possible things left over after the test-run
    :return: None
    """
    autotest_config = General.get_config()
    backend_name = autotest_config.get('backend', 'name')
    backend = GeneralBackend.get_by_name(backend_name)
    if backend:
        GeneralAlba.unclaim_disks(backend.alba_backend)
        GeneralAlba.remove_alba_backend(backend.alba_backend)
