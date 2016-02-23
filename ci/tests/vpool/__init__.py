# Copyright 2014 iNuron NV
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

from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_backend import GeneralBackend


def setup():
    """
    Setup for vPool package, will be executed when any test in this package is being executed
    Make necessary changes before being able to run the tests
    :return: None
    """
    autotest_config = General.get_config()
    backend_name = autotest_config.get('backend', 'name')
    assert backend_name, "Please fill out a valid backend name in autotest.cfg file"

    GeneralAlba.prepare_alba_backend()


def teardown():
    """
    Teardown for vPool package, will be executed when all started tests in this package have ended
    Removal actions of possible things left over after the test-run
    :return: None
    """
    autotest_config = General.get_config()
    be = GeneralBackend.get_by_name(autotest_config.get('backend', 'name'))
    if be:
        GeneralAlba.unclaim_disks_and_remove_alba_backend(alba_backend=be.alba_backend)
