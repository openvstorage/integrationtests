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

import os
import json
from ci.tests.backend import alba
from ci.tests.backend import general_backend
from ci.tests.disklayout import disklayout
from ci.tests.general import general
from ovs.dal.lists.albabackendlist import AlbaBackendList
from ovs.extensions.generic.system import System
from uuid import uuid4

local_nodeid_prefix = str(uuid4())
alba_bin = '/usr/bin/alba'


def _detach(inner, out='/dev/null'):
    cmd = ['nohup', ' '.join(inner), '> %s' % out, '2>&1', '&']
    return ' '.join(cmd)


def dump_to_cfg_as_json(cfg_path, obj):
    cfg_content = json.dumps(obj)
    cfg_file = open(cfg_path, 'w')
    cfg_file.write(cfg_content)
    cfg_file.close()


def _config_asd(asd_id, port, path, node_id, slow):
    global local_nodeid_prefix
    cfg_path = path + "/asd.json"
    dump_to_cfg_as_json(cfg_path, {'asd_id': asd_id,
                                   'port' : port,
                                   'node_id' : node_id,
                                   'home' : "%s/data" % path,
                                   'log_level' : 'debug'})
    cmd = [alba_bin, 'asd-start', "--config", cfg_path]
    if slow:
        cmd.append('--slow')
    return cmd


def asd_start(asd_id, port, path, node_id, slow):
    # Configure ASD
    os.popen("mkdir -p %s" % path)
    os.popen("mkdir %s/data" % path)
    asd_start_cmd = _config_asd(asd_id, port, path, node_id, slow and port == 8000)
    cmd_line = _detach(asd_start_cmd, out="%s/output" % path)

    # Start the ASD
    os.popen(cmd_line)


def asd_stop(port):
    cmd = ["fuser -k -n tcp %s" % port]
    os.popen(' '.join(cmd))


def get_alba_backend():
    alba_bes = AlbaBackendList.get_albabackends()
    return alba_bes[0] if len(alba_bes) else None


def add_alba_backend():
    """
    Create an ALBA backend and claim disks
    :return: None
    """
    # @TODO: Fix this, because backend_type should not be configurable if you always create an ALBA backend
    # @TODO 2: Get rid of these asserts, any test (or testsuite) should verify the required params first before starting execution
    backend_name = general.get_config().get('backend', 'name')
    backend_type = general.get_config().get('backend', 'type')
    nr_of_disks_to_claim = general.get_config().getint('backend', 'nr_of_disks_to_claim')
    type_of_disks_to_claim = general.get_config().get('backend', 'type_of_disks_to_claim')
    assert backend_name, "Please fill out a valid backend name in autotest.cfg file"
    assert backend_type in general_backend.VALID_BACKEND_TYPES, "Please fill out a valid backend type in autotest.cfg file"

    my_sr = System.get_my_storagerouter()
    disklayout.add_db_role(my_sr.guid)
    disklayout.add_read_write_scrub_roles(my_sr.guid)
    backend = general_backend.get_backend_by_name_and_type(backend_name, backend_type)
    if not backend:
        backend_guid = alba.add_alba_backend(backend_name)
        backend = general_backend.get_backend(backend_guid)
    alba.claim_disks(backend['alba_backend_guid'], nr_of_disks_to_claim, type_of_disks_to_claim)


def remove_alba_backend():
    """
    Removes an ALBA backend
    :return: None
    """
    backend_name = general.get_config().get('backend', 'name')
    backend_type = general.get_config().get('backend', 'type')
    assert backend_name, "Please fill out a valid backend name in autotest.cfg file"
    assert backend_type in general_backend.VALID_BACKEND_TYPES, "Please fill out a valid backend type in autotest.cfg file"

    be = general_backend.get_backend_by_name_and_type(backend_name, backend_type)
    if be:
        alba_backend = alba.get_alba_backend(be['alba_backend_guid'])
        alba.unclaim_disks(alba_backend)
        alba.remove_alba_backend(be['alba_backend_guid'])
