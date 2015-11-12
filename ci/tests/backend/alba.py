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

import logging
import time

from ci.tests.backend import generic
from ci.tests.general.connection import Connection
from ci.tests.general.general import execute_command

ALBA_BACKENDS = 'alba/backends'


def add_preset(alba_backend, name, policies=[[1, 1, 1, 2]], compression='none', encryption='none'):
    api = Connection.get_connection()
    data = {'name': name,
            'policies': policies,
            'compression': compression,
            'encryption': encryption}
    task_id = api.execute_action(ALBA_BACKENDS, alba_backend['guid'], 'add_preset', data)
    result = api.wait_for_task(task_id)

    return result


def remove_preset(alba_backend, name):
    api = Connection.get_connection()
    data = {'alba_backend_guid': alba_backend['guid'],
            'name': name}
    task_id = api.execute_action(ALBA_BACKENDS, alba_backend['guid'], 'delete_preset', data)
    result = api.wait_for_task(task_id)

    return result


def is_alba_backend_running(backend_guid, trigger=False):
    api = Connection.get_connection()
    timeout = 60
    wait = 5
    is_running = False
    while timeout > 0 and not is_running:
        backend = generic.get_backend(backend_guid)
        if backend:
            if backend['status'] in ['RUNNING']:
                is_running = True
                break
            elif trigger:
                trigger = False
                api.add('alba/backends', {'backend_guid': backend_guid})
        time.sleep(wait)
        timeout -= wait

    return is_running


def add_alba_backend(name):
    if not generic.is_backend_present(name, 'alba'):
        backend_guid = generic.add_backend(name, 'alba')
    else:
        backend = generic.get_backend_by_name_and_type(name, 'alba')
        backend_guid = backend['guid']
    is_alba_backend_running(backend_guid, trigger=True)

    return backend_guid


def remove_alba_backend(guid):
    api = Connection.get_connection()
    api.remove('alba/backends', guid)


def get_alba_backend(guid):
    api = Connection.get_connection()
    print 'get albabackend with guid: {0}'.format(guid)
    return api.fetch('alba/backends', guid)


def get_alba_namespaces(name):
    if not generic.is_backend_present(name):
        return

    cmd_list = "alba list-namespaces --config /opt/OpenvStorage/config/arakoon/{0}-abm/{0}-abm.cfg --to-json".format(name)
    out = execute_command(cmd_list)[0].replace('true', 'True')
    out = out.replace('false', 'False')
    logging.log(1, "output: {0}".format(out))
    if not out:
        logging.log(1, "No backend present with name: {0}:\n".format(name))
        return

    out = eval(out)
    if out['success']:
        nss = out['result']
        logging.log(1, "Namespaces present on backend: {0}:\n{1}".format(name, str(nss)))
        return nss
    else:
        logging.log(1, "Error while retrieving namespaces: {0}".format(out['error']))


def remove_alba_namespaces(name=""):
    if not generic.is_backend_present(name):
        return

    cmd_delete = "alba delete-namespace --config /opt/OpenvStorage/config/arakoon/{0}-abm/{0}-abm.cfg ".format(name)
    nss = get_alba_namespaces(name)
    logging.log(1, "Namespaces present: {0}".format(str(nss)))
    fd_namespaces = list()
    for ns in nss:
        if 'fd-' in ns:
            fd_namespaces.append(ns)
            logging.log(1, "Skipping vpool namespace: {0}".format(ns))
            continue
        logging.log(1, "WARNING: Deleting leftover namespace: {0}".format(str(ns)))
        print execute_command(cmd_delete + str(ns['name']))[0].replace('true', 'True')

    for ns in fd_namespaces:
        logging.log(1, "WARNING: Deleting leftover vpool namespace: {0}".format(str(ns)))
        print execute_command(cmd_delete + str(ns['name']))[0].replace('true', 'True')
    assert len(fd_namespaces) == 0, "Removing Alba namespaces should not be necessary!"