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

from ovs.lib.mgmtcenter import MgmtCenterController
from ci.tests.general.connection import Connection


def create_mgmt_center(name, username, password, ip, center_type, port):
    api = Connection.get_connection()
    center = api.add('mgmtcenters', {'name' : name, 'username' : username, 'password' : password, 'ip' : ip, 'type' : center_type, 'port' : port})
    return center


def remove_mgmt_center(mgmtcenter_guid):
    api = Connection.get_connection()
    management_center = api.fetch('mgmtcenters', mgmtcenter_guid)
    for pmachine_guid in management_center['pmachines_guids']:
        unconfigure_pmachine_with_mgmtcenter(pmachine_guid, mgmtcenter_guid)
    _ = api.remove('mgmtcenters', mgmtcenter_guid)


def configure_pmachine_with_mgmtcenter(pmachine_guid, mgmtcenter_guid):
    MgmtCenterController.configure_host(pmachine_guid, mgmtcenter_guid, True)


def unconfigure_pmachine_with_mgmtcenter(pmachine_guid, mgmtcenter_guid):
    MgmtCenterController.unconfigure_host(pmachine_guid, mgmtcenter_guid, True)
