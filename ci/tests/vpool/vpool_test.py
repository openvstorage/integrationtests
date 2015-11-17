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
from ovs.dal.lists.backendlist import BackendList
from ovs.dal.lists.albanodelist import AlbaNodeList
from ovs.lib.albacontroller import AlbaController
from ovs.lib.albanodecontroller import AlbaNodeController
from ci.tests.disklayout import disklayout

VPOOL_NAME = test_config.get('vpool', 'vpool_name')
VPOOL_NAME = 'vpool-' + VPOOL_NAME
BACKEND_NAME = test_config.get('backend', 'name')
BACKEND_TYPE = test_config.get('backend', 'type')


def setup():
    disklayout.add_db_role()
    disklayout.add_read_write_scrub_roles()
    if not generic.is_backend_present(BACKEND_NAME, BACKEND_TYPE):
        backend_guid = alba.add_alba_backend(BACKEND_NAME)
    backend = BackendList.get_by_name(BACKEND_NAME)
    alba_node = AlbaNodeList.get_albanode_by_ip('172.20.54.252')
    node_guid = alba_node.guid
    # claim disks up to max
    nr_of_claimed_disks = 0
    for disk in backend.alba_backend.all_disks:
        if 'asd_id' in disk and disk['status'] in 'claimed' and disk['node_id'] == alba_node.node_id:
            nr_of_claimed_disks += 1

    if nr_of_claimed_disks < 3:
        disks_to_init = [d['name'] for d in alba_node.all_disks if d['available'] is True]
        failures = AlbaNodeController.initialize_disks(node_guid, disks_to_init)
        if failures:
            raise 'Alba disk initialization failed for (some) disks: {0}'.format(failures)

    claimable_ids = list()
    for disk in backend.alba_backend.all_disks:
        if 'asd_id' in disk and disk['status'] in 'available':
            claimable_ids.append(disk['asd_id'])
    osds = dict()
    disks_to_claim = [d['name'] for d in alba_node.all_disks if d['available'] is False]
    for name in disks_to_claim:
        for disk in alba_node.all_disks:
            if name == disk['name'] and disk['asd_id'] in claimable_ids:
                osds[disk['asd_id']] = node_guid
    AlbaController.add_units(backend.alba_backend_guid, osds)


def teardown():
    pass
    # backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    # if backend:
    #    alba.remove_alba_backend(backend['alba_backend_guid'])


def add_vpool_test():
    vpool_params = general.api_add_vpool(vpool_name = VPOOL_NAME,
                                         apply_to_all_nodes=True,
                                         config_cinder=True,
                                         integratemgmt=True)
    assert vpool_params['vpool_name'] == VPOOL_NAME, "Adding the vpool was unsuccsesfull\n{0}".format(vpool_params)
    # sanity_checks_test.check_vpool_sanity_test()
    # if vpool_params:
    #    general.api_remove_vpool(vpool_params['vpool_name'])
    #    # sanity_checks_test.check_vpool_remove_sanity_test()
    #    general.validate_vpool_cleanup(vpool_params['vpool_name'])
