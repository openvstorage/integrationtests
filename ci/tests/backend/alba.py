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

import json
import os
import random
import tempfile
import time

from ci.tests.backend import generic
from ci.tests.general import general
from ci.tests.general.connection import Connection
from ci.tests.general.general import execute_command
from ci.tests.general.general import get_physical_disks
from ci.tests.general.general import test_config
from ovs.lib.albanodecontroller import AlbaNodeController
from ovs.lib.albacontroller import AlbaController
from ovs.dal.lists.albanodelist import AlbaNodeList
from ci.tests.general.logHandler import LogHandler

logger = LogHandler.get('backend', name='alba')
logger.logger.propagate = False

ALBA_BACKENDS = 'alba/backends'
ALBA_NODES = 'alba/nodes'
GRID_IP = test_config.get('main', 'grid_ip')
ALBA_TIMER = 1800
ALBA_TIMER_STEP = 5


def get_config(backend_name):
    return '--config etcd://127.0.0.1:2379/ovs/arakoon/{0}-abm/config'.format(backend_name)


def wait_for_disk_count_with_status(alba_backend_guid, nr_of_disks, status):
    counter = ALBA_TIMER / ALBA_TIMER_STEP
    while counter > 0:
        logger.info('counter: {0}'.format(counter))
        all_disks = get_all_disks(alba_backend_guid)
        disks_with_status = [disk['name'] for disk in all_disks if 'status' in disk and disk['status'] == status and 'asd_id' in disk]
        logger.info('looking for {0} disks with status {1}: {2}'.format(nr_of_disks, status, disks_with_status))
        if len(disks_with_status) >= nr_of_disks:
            break
        counter -= 1
        time.sleep(ALBA_TIMER_STEP)
    assert len(disks_with_status) >= nr_of_disks,\
        "Unable to find {0} disks, only found {1} disks with status: {2}.\n".format(nr_of_disks, len(disks_with_status),
                                                                                    status)
    return disks_with_status


def run(backend_name, action, params, json_output=True):
    config = get_config(backend_name)
    cmd = ['alba', action, config]
    if json_output:
        cmd.append('--to-json')
    cmd.extend(params)

    output = ''
    try:
        output = execute_command(' '.join(cmd))
        if json_output:
            output = json.loads(output[0])
    except (ValueError, RuntimeError):
        print "Command {0} failed:\nOutput: {1}".format(cmd, output)
        assert False, "Command {0} failed".format(' '.join(cmd))
    if json_output:
        return output['result']
    else:
        return output


def add_preset(alba_backend, name, policies=[[1, 1, 1, 2]], compression='none', encryption='none'):
    api = Connection.get_connection()
    data = {'name': name,
            'policies': policies,
            'compression': compression,
            'encryption': encryption}
    task_id = api.execute_action(ALBA_BACKENDS, alba_backend['guid'], 'add_preset', data)
    result = api.wait_for_task(task_id)

    return result


def update_preset(alba_backend, name, policies):
    api = Connection.get_connection()
    data = {'name': name, 'policies': policies}
    task_id = api.execute_action(ALBA_BACKENDS, alba_backend['guid'], 'update_preset', data)
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
    timeout = ALBA_TIMER
    wait = ALBA_TIMER_STEP
    is_running = False
    while timeout > 0 and not is_running:
        backend = generic.get_backend(backend_guid)
        if backend:
            if backend['status'] in ['RUNNING']:
                is_running = True
                logger.info('Backend in status running after {0} seconds'.format((ALBA_TIMER - timeout) * wait))
                break
            elif trigger:
                logger.info('Trigger backend installation')
                trigger = False
                api.add('alba/backends', {'backend_guid': backend_guid})
        time.sleep(wait)
        timeout -= wait

    return is_running


def add_alba_backend(name):
    if not generic.is_backend_present(name, 'alba'):
        backend_guid = generic.add_backend(name, 'alba')
        assert (is_alba_backend_running(backend_guid, trigger=True)), 'Backend {0} not in status RUNNING'.format(name)
    else:
        backend = generic.get_backend_by_name_and_type(name, 'alba')
        backend_guid = backend['guid']

    out, err = general.execute_command('etcdctl ls /ovs/alba/asdnodes')
    if err == '' and len(out):
        AlbaNodeController.model_local_albanode()

    return backend_guid


def remove_alba_backend(guid):
    api = Connection.get_connection()
    name = api.fetch('alba/backends', guid)['name']
    api.remove('alba/backends', guid)

    counter = ALBA_TIMER / ALBA_TIMER_STEP
    while counter >= 0:
        if not api.get_component_by_name('backends', name):
            break
        counter -= 1
        time.sleep(ALBA_TIMER_STEP)

    assert (api.get_component_by_name('backends', name) is None), "Unable to remove backend {0}".format(name)


def get_alba_backend(guid):
    api = Connection.get_connection()

    return api.fetch('alba/backends', guid)


def get_node_by_id(node_id):
    api = Connection.get_connection()
    nodes = api.list(ALBA_NODES)
    for node_guid in nodes:
        node = api.fetch(ALBA_NODES, node_guid)
        if node['node_id'] == node_id:
            return node_guid


def create_namespace(backend_name, namespace_name, preset_name):

    return run(backend_name, 'create-namespace', [namespace_name, preset_name], False)


def delete_namespace(backend_name, namespace_name):

    return run(backend_name, 'delete-namespace', [namespace_name], False)


def list_namespaces(backend_name):

    return run(backend_name, 'list-namespaces', [])


def show_namespace(backend_name, namespace_name):

    return run(backend_name, 'show-namespace', [namespace_name])


def upload_file(backend_name, namespace, filesize, cleanup=False):
    contents = ''.join(random.choice(chr(random.randint(32, 126))) for _ in xrange(filesize))
    temp_file_name = tempfile.mktemp()
    with open(temp_file_name, 'wb') as temp_file:
        temp_file.write(contents)
        temp_file.flush()

    result = run(backend_name, 'upload', [namespace, temp_file_name, temp_file_name], False)
    if cleanup and os.path.exists(temp_file_name):
        os.remove(temp_file_name)

    return temp_file_name, result


def get_alba_namespaces(name):
    if not generic.is_backend_present(name, 'alba'):
        return

    cmd = "alba list-namespaces {0} --to-json".format(get_config(name))
    out = execute_command(cmd)[0]
    out = json.loads(out)
    logger.info("output: {0}".format(out))
    if not out:
        logger.info("No backend present with name: {0}:\n".format(name))
        return

    if out['success']:
        nss = out['result']
        logger.info("Namespaces present on backend: {0}:\n{1}".format(name, str(nss)))
        return nss
    else:
        logger.info("Error while retrieving namespaces: {0}".format(out['error']))


def remove_alba_namespaces(name=""):
    if not generic.is_backend_present(name, 'alba'):
        return

    cmd_delete = "alba delete-namespace {0} ".format(get_config(name))
    nss = get_alba_namespaces(name)
    logger.info("Namespaces present: {0}".format(str(nss)))
    fd_namespaces = list()
    for ns in nss:
        if 'fd-' in ns['name']:
            fd_namespaces.append(ns)
            logger.info("Skipping vpool namespace: {0}".format(ns['name']))
            continue
        logger.info("WARNING: Deleting leftover namespace: {0}".format(str(ns)))
        print execute_command(cmd_delete + str(ns['name']))[0].replace('true', 'True')

    for ns in fd_namespaces:
        logger.info("WARNING: Deleting leftover vpool namespace: {0}".format(str(ns)))
        print execute_command(cmd_delete + str(ns['name']))[0].replace('true', 'True')
    assert len(fd_namespaces) == 0, "Removing Alba namespaces should not be necessary!"


def is_bucket_count_valid_with_policy(bucket_count, policies):
    # policy (k, m, c, x)
    # for both bucket_count and policy:
    # - k = nr of data fragments, should equal for both
    # - m = nr of parity fragments, should be equal for both

    # policy
    # - c = min nr of fragments to write
    # - x = max nr of fragments per storage node

    # bucket_count:
    # - c = nr of effectively written fragments, should be >= policy.c
    # - x = max nr of effectively written fragments on one specific node, should be<= policy.x

    # policies should all be present in bucket_count, removed policy via update could still be present during
    # maintenance rewrite cycle

    safe = False
    for policy in policies:
        policy = tuple(policy)
        for entry in bucket_count:
            bc_policy = entry[0]
            pol_k, pol_m, pol_c, pol_x = tuple(policy)
            bc_k, bc_m, bc_c, bc_x = tuple(bc_policy)
            safe = (pol_k == bc_k) and (pol_m == bc_m) and (bc_c >= pol_c) and (bc_x <= pol_c)

    return safe


def get_all_disks(alba_backend_guid):
    api = Connection.get_connection()
    alba_backend = api.fetch('alba/backends', alba_backend_guid)
    if 'all_disks' in alba_backend:
        all_disks = alba_backend['all_disks']
    else:
        all_disks = list()

    return all_disks


def filter_disks(available_disks, amount, disk_type=''):
    hdds, ssds = get_physical_disks(GRID_IP)
    count = 0
    filtered_disks = list()

    if disk_type == 'SATA':
        list_to_check = hdds.values()
    elif disk_type == 'SSD':
        list_to_check = ssds.values()
    else:
        hdds.update(ssds)
        list_to_check = hdds.values()

    for disk_name in available_disks:
        for disk in list_to_check:
            if disk_name == disk['name']:
                filtered_disks.append(disk['name'])
                count += 1
        if count == amount:
            break

    return filtered_disks


def initialise_disks(alba_backend_guid, nr_of_disks, disk_type=''):
    # assume no disks are claimed by a remote environment
    all_disks = get_all_disks(alba_backend_guid)

    initialised_disks = [disk['name'] for disk in all_disks if disk['status'] == 'available']
    nr_of_disks_to_init = nr_of_disks - len(initialised_disks)
    if nr_of_disks_to_init <= 0:
        return True

    uninitialized_disks = [disk['name'] for disk in all_disks if disk['status'] == 'uninitialized']
    assert len(uninitialized_disks) >= nr_of_disks_to_init, "Not enough disks to initialize!"

    disks_to_init = filter_disks(uninitialized_disks, nr_of_disks_to_init, disk_type)
    assert len(disks_to_init) >= nr_of_disks_to_init, "Not enough disks to initialize!"

    alba_node = AlbaNodeList.get_albanode_by_ip(GRID_IP)
    failures = AlbaNodeController.initialize_disks(alba_node.guid, disks_to_init)
    assert not failures, 'Alba disk initialization failed for (some) disks: {0}'.format(failures)


def claim_disks(alba_backend_guid, nr_of_disks, disk_type=''):
    all_disks = get_all_disks(alba_backend_guid)

    claimed_disks = [disk['name'] for disk in all_disks if 'status' in disk and disk['status'] == 'claimed' and 'name' in disk]
    nr_disks_to_claim = nr_of_disks - len(claimed_disks)
    if nr_disks_to_claim <= 0:
        return True

    initialise_disks(alba_backend_guid, nr_disks_to_claim, disk_type)

    claimable_disks = wait_for_disk_count_with_status(alba_backend_guid, nr_disks_to_claim, 'available')

    disks_to_claim = filter_disks(claimable_disks, nr_disks_to_claim, disk_type)
    assert len(disks_to_claim) >= nr_disks_to_claim,\
        "Unable to claim {0} disks, only found {1} disks.\n".format(nr_of_disks, len(disks_to_claim))

    all_disks = get_all_disks(alba_backend_guid)
    osds = dict()

    alba_node = AlbaNodeList.get_albanode_by_ip(GRID_IP)
    for name in disks_to_claim:
        for disk in all_disks:
            if name in disk['name'] and 'asd_id' in disk:
                osds[disk['asd_id']] = alba_node.guid

    logger.info('osds: {0}'.format(osds))
    AlbaController.add_units(alba_backend_guid, osds)

    wait_for_disk_count_with_status(alba_backend_guid, nr_of_disks, 'claimed')


def unclaim_disks(alba_backend):
    api = Connection.get_connection()
    all_disks = api.fetch('alba/backends', alba_backend['guid'])['all_disks']
    for disk in all_disks:
        if disk['status'] in ['available', 'claimed']:
            node_guid = get_node_by_id(disk['node_id'])
            data = {'alba_backend_guid': alba_backend['guid'],
                    'disk': disk['name'],
                    'safety': {'good': 0, 'critical': 0, 'lost': 0}}
            task_id = api.execute_action(ALBA_NODES, node_guid, 'remove_disk', data)
            api.wait_for_task(task_id)[0]
