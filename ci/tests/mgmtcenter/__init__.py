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

from ci.tests.general.general_mgmtcenter import GeneralManagementCenter


def setup():
    """
    Setup for ManagementCenter package, will be executed when any test in this package is being executed
    Make necessary changes before being able to run the tests
    :return: None
    """
    GeneralManagementCenter.create_generic_mgmt_center()


def teardown():
    """
    Teardown for ManagementCenter package, will be executed when all started tests in this package have ended
    Removal actions of possible things left over after the test-run
    :return: None
    """
    for mgmt_center in GeneralManagementCenter.get_mgmt_centers():
        GeneralManagementCenter.remove_mgmt_center(mgmt_center)
