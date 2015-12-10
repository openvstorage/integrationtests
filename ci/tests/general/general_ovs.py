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

from ci.tests.general.connection import Connection
from ovs.extensions.generic.sshclient import SSHClient

import json


def get_pmachines_by_ip():
    """
    Group pmachines by ip + add node_type
    :return:
    """
    api = Connection.get_connection()
    pmachine_guids = api.list('pmachines')
    pmachines = dict()
    for guid in pmachine_guids:
        pmachine = api.fetch('pmachines', guid)
        sr = api.fetch('storagerouters', pmachine['storagerouters_guids'][0])
        pmachine['node_type'] = sr['node_type']
        pmachines[pmachine['ip']] = pmachine

    return pmachines


def get_storagerouter_by_ip(ip):
    api = Connection.get_connection()
    return api.get_components_with_attribute('storagerouters', 'ip', ip, single=True)


def get_ovs_config(ip):
    client = SSHClient(ip)
    return json.loads(client.file_read('/opt/OpenvStorage/config/ovs.json'))
