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

import os
import itertools
import random
import logging

from ci.tests.general import general
from ovs.lib.setup import SetupController
from ovs.extensions.generic.sshclient import SSHClient
from nose.plugins.skip import SkipTest
from nose.tools import assert_raises

log = logging.getLogger('test_partition_layout')
vpool_name = general.test_config.get("vpool", "vpool_name")
vpool_name = 'api-' + vpool_name


def setup():
    global client
    global sc
    global fstab_contents

    print "setup called " + __name__

    grid_ip = general.test_config.get("main", "grid_ip")
    client = SSHClient(grid_ip, username='root', password='rooter')
    sc = SetupController()

    with open("/etc/fstab") as f:
        fstab_contents = f.read()

    # make sure we start with clean env
    general.cleanup()


def teardown():
    global fstab_contents
    with open("/etc/fstab", "w") as f:
        f.write(fstab_contents)


def run_and_validate_partitioning(disk_layout, vpool_readcaches_mp, vpool_writecaches_mp, vpool_dtl_mp,
                                  initial_part_used_space=None):
    vpool_params = {}
    general.remove_alba_namespaces()
    try:
        general.apply_disk_layout(disk_layout)
        vpool_params = general.api_add_vpool(vpool_name=vpool_name,
                                             vpool_readcaches_mp=vpool_readcaches_mp,
                                             vpool_writecaches_mp=vpool_writecaches_mp,
                                             vpool_dtl_mp=vpool_dtl_mp,
                                             apply_to_all_nodes=True,
                                             config_cinder=True,
                                             integratemgmt=True)
        return general.validate_vpool_size_calculation(vpool_params['vpool_name'], disk_layout, initial_part_used_space)
    finally:
        if vpool_params:
            general.api_remove_vpool(vpool_params['vpool_name'])
            general.validate_vpool_cleanup(vpool_params['vpool_name'])
        general.clean_disk_layout(disk_layout)
        verify_no_namespaces_remain_after_testsuite()


def each_mountpoint_own_partition_test():
    unused_disks = general.get_unused_disks()
    if not unused_disks:
        raise SkipTest("Need at least one unused disk: {0}".format(unused_disks))

    vpool_readcaches_mp = ["/mnt/test_cache1", "/mnt/test_cache2"]
    vpool_writecaches_mp = ["/mnt/test_write_cache"]
    vpool_dtl_mp = "/mnt/test_dtl"

    r1_perc = {1: 24, 2: 33, 3: 49}[len(unused_disks)]
    r2_perc = {1: 24, 2: 98, 3: 98}[len(unused_disks)]
    w1_perc = {1: 24, 2: 33, 3: 98}[len(unused_disks)]
    f_perc = {1: 24, 2: 33, 3: 49}[len(unused_disks)]

    disk_layout = {vpool_readcaches_mp[0]: {'device': unused_disks[0], 'percentage': r1_perc, 'label': 'test_cache1',
                                            'type': 'readcache', 'ssd': False},
                   vpool_readcaches_mp[1]: {'device': unused_disks[1] if len(unused_disks) > 1 else unused_disks[0],
                                            'percentage': r2_perc, 'label': 'test_cache2', 'type': 'readcache',
                                            'ssd': False},
                   vpool_writecaches_mp[0]: {'device': unused_disks[2] if len(unused_disks) > 2 else unused_disks[0],
                                             'percentage': w1_perc, 'label': 'test_write_cache', 'type': 'writecache',
                                             'ssd': False},
                   vpool_dtl_mp: {'device': unused_disks[0], 'percentage': f_perc, 'label': 'test_dtl'}}

    result = run_and_validate_partitioning(disk_layout, vpool_readcaches_mp, vpool_writecaches_mp, vpool_dtl_mp)
    for mp in [vpool_readcaches_mp[0], vpool_readcaches_mp[1], vpool_writecaches_mp[0], vpool_dtl_mp]:
        logging.log(1, disk_layout[mp])
        logging.log(1, result[mp])


def all_mountpoints_root_partition_test():

    vpool_readcaches_mp = ["/mnt/test_cache1", "/mnt/test_cache2"]
    vpool_writecaches_mp = ["/mnt/test_write_cache"]
    vpool_dtl_mp = "/mnt/test_dtl"

    disk_layout = {vpool_readcaches_mp[0]: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache1',
                                            'type': 'readcache', 'ssd': False},
                   vpool_readcaches_mp[1]: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache2',
                                            'type': 'readcache', 'ssd': False},
                   vpool_writecaches_mp[0]: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_write_cache',
                                             'type': 'writecache', 'ssd': False},
                   vpool_dtl_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_dtl', 'type': 'writecache',
                                  'ssd': False}}
    initial_part_used_space = {"/": general.get_filesystem_size("/")[3]}

    result = run_and_validate_partitioning(disk_layout, vpool_readcaches_mp, vpool_writecaches_mp, vpool_dtl_mp,
                                           initial_part_used_space)

    for mp in [vpool_readcaches_mp[0], vpool_readcaches_mp[1], vpool_writecaches_mp[0], vpool_dtl_mp]:
        logging.log(1, disk_layout[mp])
        logging.log(1, result[mp])


def all_mountpoints_root_partition_one_readcache_test():

    vpool_readcaches_mp = ["/mnt/test_cache1"]
    vpool_writecaches_mp = ["/mnt/test_write_cache"]
    vpool_dtl_mp = "/mnt/test_dtl"

    disk_layout = {vpool_readcaches_mp[0]: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache1',
                                            'type': 'readcache', 'ssd': False},
                   vpool_writecaches_mp[0]: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_write_cache',
                                             'type': 'writecache', 'ssd': False},
                   vpool_dtl_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_dtl', 'type': 'writecache',
                                  'ssd': False}}
    initial_part_used_space = {"/": general.get_filesystem_size("/")[3]}

    result = run_and_validate_partitioning(disk_layout, vpool_readcaches_mp, vpool_writecaches_mp, vpool_dtl_mp,
                                           initial_part_used_space)
    for mp in [vpool_readcaches_mp[0], vpool_writecaches_mp[0], vpool_dtl_mp]:
        logging.log(1, disk_layout[mp])
        logging.log(1, result[mp])


def dir_and_partition_layout_test():
    unused_disks = general.get_unused_disks()

    if not unused_disks:
        raise SkipTest("Need at least one unused disk")

    vpool_readcaches_mp = ["/mnt/test_cache1", "/mnt/test_cache2"]
    vpool_writecaches_mp = ["/mnt/test_write_cache"]
    vpool_dtl_mp = "/mnt/test_dtl"

    for idx in range(4):
        l = [unused_disks[0]] * 4
        l[idx] = 'DIR_ONLY'
        disk_layout = {vpool_readcaches_mp[0]: {'device': l[0], 'percentage': 25, 'label': 'test_cache1',
                                                'type': 'readcache', 'ssd': False},
                       vpool_readcaches_mp[1]: {'device': l[1], 'percentage': 25, 'label': 'test_cache2',
                                                'type': 'readcache', 'ssd': False},
                       vpool_writecaches_mp[0]: {'device': l[2], 'percentage': 25, 'label': 'test_write_cache',
                                                 'type': 'writecache', 'ssd': False},
                       vpool_dtl_mp: {'device': l[3], 'percentage': 25, 'label': 'test_dtl', 'type': 'writecache',
                                      'ssd': False}}

        initial_part_used_space = {"/": general.get_filesystem_size("/")[3]}

        result = run_and_validate_partitioning(disk_layout, vpool_readcaches_mp, vpool_writecaches_mp, vpool_dtl_mp,
                                               initial_part_used_space)
        logging.log(1, idx)
        for mp in [vpool_readcaches_mp[0], vpool_readcaches_mp[1], vpool_writecaches_mp[0], vpool_dtl_mp]:
            logging.log(1, disk_layout[mp])
            logging.log(1, result[mp])


def two_disks_layout_test():

    unused_disks = general.get_unused_disks()

    if len(unused_disks) < 2:
        raise SkipTest("Need at least 2 unused disks")

    vpool_readcaches_mp = ["/mnt/test_cache1", "/mnt/test_cache2"]
    vpool_writecaches_mp = ["/mnt/test_write_cache"]
    vpool_dtl_mp = "/mnt/test_dtl"

    combinations = [comb for comb in list(itertools.product([0, 1], repeat=4)) if comb.count(0) >= 1 and
                    comb.count(1) >= 1]
    random.shuffle(combinations)
    for comb in combinations[:6]:

        disk_layout = {vpool_readcaches_mp[0]: {'device': unused_disks[comb[0]], 'percentage': 25,
                                                'label': 'test_cache1', 'type': 'readcache', 'ssd': False},
                       vpool_readcaches_mp[1]: {'device': unused_disks[comb[0]], 'percentage': 25,
                                                'label': 'test_cache2', 'type': 'readcache', 'ssd': False},
                       vpool_writecaches_mp[0]: {'device': unused_disks[comb[0]], 'percentage': 25,
                                                 'label': 'test_write_cache', 'type': 'writecache', 'ssd': False},
                       vpool_dtl_mp: {'device': unused_disks[comb[0]], 'percentage': 25, 'label': 'test_dtl',
                                      'type': 'writecache', 'ssd': False}}
        result = run_and_validate_partitioning(disk_layout, vpool_readcaches_mp, vpool_writecaches_mp, vpool_dtl_mp)
        logging.log(1, 'comb')
        for mp in [vpool_readcaches_mp[0], vpool_readcaches_mp[1], vpool_writecaches_mp[0], vpool_dtl_mp]:
            logging.log(1, disk_layout[mp])
            logging.log(1, result[mp])


def same_disk_different_percentages_layout_test():

    unused_disks = general.get_unused_disks()

    if not unused_disks:
        raise SkipTest("Need at least 1 unused disk")

    vpool_readcaches_mp = ["/mnt/test_cache1", "/mnt/test_cache2"]
    vpool_writecaches_mp = ["/mnt/test_write_cache"]
    vpool_dtl_mp = "/mnt/test_dtl"

    # Layout 1
    disk_layout = {vpool_readcaches_mp[0]: {'device': unused_disks[0], 'percentage': 10, 'label': 'test_cache1',
                                            'type': 'readcache', 'ssd': False},
                   vpool_readcaches_mp[1]: {'device': unused_disks[0], 'percentage': 40, 'label': 'test_cache2',
                                            'type': 'readcache', 'ssd': False},
                   vpool_writecaches_mp[0]: {'device': unused_disks[0], 'percentage': 25, 'label': 'test_write_cache',
                                             'type': 'writecache', 'ssd': False},
                   vpool_dtl_mp: {'device': unused_disks[0], 'percentage': 25, 'label': 'test_dtl',
                                  'type': 'writecache', 'ssd': False}}

    result = run_and_validate_partitioning(disk_layout, vpool_readcaches_mp, vpool_writecaches_mp, vpool_dtl_mp)
    logging.log(1, 'Layout 1:...')
    for mp in [vpool_readcaches_mp[0], vpool_readcaches_mp[1], vpool_writecaches_mp[0], vpool_dtl_mp]:
        logging.log(1, disk_layout[mp])
        logging.log(1, result[mp])

    # Layout 1
    disk_layout = {vpool_readcaches_mp[0]: {'device': unused_disks[0], 'percentage': 40, 'label': 'test_cache1',
                                            'type': 'readcache', 'ssd': False},
                   vpool_readcaches_mp[1]: {'device': unused_disks[0], 'percentage': 10, 'label': 'test_cache2',
                                            'type': 'readcache', 'ssd': False},
                   vpool_writecaches_mp[0]: {'device': unused_disks[0], 'percentage': 25, 'label': 'test_write_cache',
                                             'type': 'writecache', 'ssd': False},
                   vpool_dtl_mp: {'device': unused_disks[0], 'percentage': 25, 'label': 'test_dtl',
                                  'type': 'writecache', 'ssd': False}}

    result = run_and_validate_partitioning(disk_layout, vpool_readcaches_mp, vpool_writecaches_mp, vpool_dtl_mp)
    logging.log(1, 'Layout 2:...')
    for mp in [vpool_readcaches_mp[0], vpool_readcaches_mp[1], vpool_writecaches_mp[0], vpool_dtl_mp]:
        logging.log(1, disk_layout[mp])
        logging.log(1, result[mp])


def root_partition_already_at_60_percent_test():

    fss = general.get_filesystem_size("/")
    fs_size = fss[1]
    avail_size = fss[2]

    big_file = "/root/bigfile"
    to_alocate = int((fs_size * 0.6 - (fs_size - avail_size))) / 100 * 100
    if to_alocate > 0:
        cmd = "fallocate -l {0} {1}".format(to_alocate, big_file)
        general.execute_command(cmd)

    vpool_readcaches_mp = ["/mnt/test_cache1", "/mnt/test_cache2"]
    vpool_writecaches_mp = ["/mnt/test_write_cache"]
    vpool_dtl_mp = "/mnt/test_dtl"

    disk_layout = {vpool_readcaches_mp[0]: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache1',
                                            'type': 'readcache', 'ssd': False},
                   vpool_readcaches_mp[1]: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache2',
                                            'type': 'readcache', 'ssd': False},
                   vpool_writecaches_mp[0]: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_write_cache',
                                             'type': 'writecache', 'ssd': False},
                   vpool_dtl_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_dtl', 'type': 'writecache',
                                  'ssd': False}}

    initial_part_used_space = {"/": general.get_filesystem_size("/")[3]}

    result = run_and_validate_partitioning(disk_layout, vpool_readcaches_mp, vpool_writecaches_mp, vpool_dtl_mp,
                                           initial_part_used_space)
    for mp in [vpool_readcaches_mp[0], vpool_readcaches_mp[1], vpool_writecaches_mp[0], vpool_dtl_mp]:
        logging.log(1, disk_layout[mp])
        logging.log(1, result[mp])
    os.remove(big_file)


def three_disks_layout_test():

    unused_disks = general.get_unused_disks()

    if len(unused_disks) < 3:
        raise SkipTest("Need at least 3 unused disks")

    vpool_readcaches_mp = ["/mnt/test_cache1", "/mnt/test_cache2"]
    vpool_writecaches_mp = ["/mnt/test_write_cache"]
    vpool_dtl_mp = "/mnt/test_dtl"

    combinations = [comb for comb in list(itertools.product([0, 1, 2], repeat=4)) if comb.count(0) >= 1 and
                    comb.count(1) >= 1 and comb.count(2) >= 1]
    random.shuffle(combinations)

    for comb in combinations[:6]:
        disk_layout = {vpool_readcaches_mp[0]: {'device': unused_disks[comb[0]], 'percentage': 25,
                                                'label': 'test_cache1', 'type': 'readcache', 'ssd': False},
                       vpool_readcaches_mp[1]: {'device': unused_disks[comb[0]], 'percentage': 25,
                                                'label': 'test_cache2', 'type': 'readcache', 'ssd': False},
                       vpool_writecaches_mp[0]: {'device': unused_disks[comb[0]], 'percentage': 25,
                                                 'label': 'test_write_cache', 'type': 'writecache', 'ssd': False},
                       vpool_dtl_mp: {'device': unused_disks[comb[0]], 'percentage': 25, 'label': 'test_dtl',
                                      'type': 'writecache', 'ssd': False}}

        result = run_and_validate_partitioning(disk_layout, vpool_readcaches_mp, vpool_writecaches_mp, vpool_dtl_mp)
        logging.log(1, comb)
        for mp in [vpool_readcaches_mp[0], vpool_readcaches_mp[1], vpool_writecaches_mp[0], vpool_dtl_mp]:
            logging.log(1, disk_layout[mp])
            logging.log(1, result[mp])


def readcache_and_writecache_same_dir_test():
    vpool_readcaches_mp = ["/mnt/test_cache1", "/mnt/test_cache2"]
    vpool_writecaches_mp = ["/mnt/test_cache1"]
    vpool_dtl_mp = "/mnt/test_dtl"

    disk_layout = {vpool_readcaches_mp[0]: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache1',
                                            'type': 'readcache', 'ssd': False},
                   vpool_readcaches_mp[1]: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache2',
                                            'type': 'readcache', 'ssd': False},
                   vpool_writecaches_mp[0]: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_write_cache',
                                             'type': 'writecache', 'ssd': False},
                   vpool_dtl_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_dtl', 'type': 'writecache',
                                  'ssd': False}}
    initial_part_used_space = {"/": general.get_filesystem_size("/")[3]}

    assert_raises(Exception, run_and_validate_partitioning, disk_layout, vpool_readcaches_mp, vpool_writecaches_mp,
                  vpool_dtl_mp, initial_part_used_space)


def verify_no_namespaces_remain_after_testsuite():
    alba_namespaces = general.get_alba_namespaces()
    assert len(alba_namespaces) == 0,\
        "No alba namespaces should be present at the end of api test suite: {0}".format(alba_namespaces)
