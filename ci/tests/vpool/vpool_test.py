# Copyright 2015 iNuron NV
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

from ci.tests.general import general
from ci.tests.general.general import test_config
from ci.tests.sanity import sanity_checks_test
from ci.tests.backend import alba, generic, test_alba

VPOOL_NAME = test_config.get('vpool', 'vpool_name')
VPOOL_NAME = 'vpool-' + VPOOL_NAME
BACKEND_NAME = test_config.get('backend', 'name')
BACKEND_TYPE = test_config.get('backend', 'type')


def setup():
    if not generic.is_backend_present(BACKEND_NAME, BACKEND_TYPE):
        alba.add_alba_backend(BACKEND_NAME)
    # claim the disks


def teardown():
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    if backend:
        alba.remove_alba_backend(backend['alba_backend_guid'])


def add_vpool_test():
    vpool_params = general.api_add_vpool(vpool_name = VPOOL_NAME,
                                         apply_to_all_nodes=True,
                                         config_cinder=True,
                                         integratemgmt=True)
    assert vpool_params.name == VPOOL_NAME, "Adding the vpool was unsuccsesfull\n{0}".format(vpool_params)
    # sanity_checks_test.check_vpool_sanity_test()
    if vpool_params:
        general.api_remove_vpool(vpool_params['vpool_name'])
        # sanity_checks_test.check_vpool_remove_sanity_test()
        general.validate_vpool_cleanup(vpool_params['vpool_name'])
