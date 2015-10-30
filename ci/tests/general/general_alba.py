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

import json
import os

from uuid import uuid4
from ovs.dal.lists.albabackendlist import AlbaBackendList

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
