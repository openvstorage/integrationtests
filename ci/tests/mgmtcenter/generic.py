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

from ovs.lib.mgmtcenter import MgmtCenterController
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.services.service import ServiceManager
from ovs.extensions.os.os import OSManager
from ci.tests.general.connection import Connection
from ci.tests.general import general

MGMT_NAME = general.test_config.get("mgmtcenter", "name")
MGMT_USERNAME = general.test_config.get("mgmtcenter", "username")
MGMT_PASS = general.test_config.get("mgmtcenter", "password")
MGMT_IP = general.test_config.get('mgmtcenter', 'ip')
MGMT_TYPE = general.test_config.get('mgmtcenter', 'type')
MGMT_PORT = general.test_config.get('mgmtcenter', 'port')


def is_devstack_installed():
    client = SSHClient('127.0.0.1', username='root')
    is_openstack = ServiceManager.has_service(OSManager.get_openstack_cinder_service_name(), client)
    is_devstack = 'stack' in str(client.run('ps aux | grep SCREEN | grep stack | grep -v grep || true'))
    return is_openstack or is_devstack


def create_mgmt_center(name, username, password, ip, center_type, port):
    api = Connection.get_connection()
    center = api.add('mgmtcenters', {'name': name, 'username': username, 'password': password, 'ip': ip, 'type': center_type, 'port': port})
    return center


def create_generic_mgmt_center():
    api = Connection.get_connection()
    management_centers = api.get_components('mgmtcenters')
    if len(management_centers) == 0 and is_devstack_installed():
        mgmtcenter = create_mgmt_center(MGMT_NAME, MGMT_USERNAME, MGMT_PASS, MGMT_IP, MGMT_TYPE, MGMT_PORT)
        for physical_machine in api.get_components('pmachines'):
            configure_pmachine_with_mgmtcenter(physical_machine['guid'], mgmtcenter['guid'])


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


def is_host_configured(pmachine_guid):
    return MgmtCenterController.is_host_configured(pmachine_guid)


def test_connection(mgmtcenter_guid):
    return MgmtCenterController.test_connection(mgmtcenter_guid)
