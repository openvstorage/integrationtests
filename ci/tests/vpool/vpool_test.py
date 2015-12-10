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

from ci.tests.general import general
from ci.tests.general.connection import Connection
from ci.tests.general.general import test_config
from ovs.dal.lists.vpoollist import VPoolList
from ci.tests.vpool import generic

VPOOL_NAME = test_config.get('vpool', 'vpool_name')
assert VPOOL_NAME, "Please fill out a valid vpool name in autotest.cfg file"


def setup():
    generic.add_alba_backend()


def teardown():
    generic.remove_alba_backend()


def add_vpool_test():
    api = Connection.get_connection()
    vpool_list = api.get_component_by_name('vpools', VPOOL_NAME)
    if not vpool_list:
        generic.add_generic_vpool()
    vpool = VPoolList.get_vpool_by_name(VPOOL_NAME)
    assert vpool, 'Vpool {0} was not created'.format(VPOOL_NAME)
    general.api_remove_vpool(VPOOL_NAME)
    vpool = VPoolList.get_vpool_by_name(VPOOL_NAME)
    assert not vpool, 'Vpool {0} was not deleted'.format(VPOOL_NAME)
