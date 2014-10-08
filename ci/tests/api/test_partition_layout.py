
import os
import itertools
import random

from ci.tests.general                   import general
from ci                                 import autotests

from ovs.lib.setup                      import SetupController
from ovs.extensions.generic.sshclient   import SSHClient
from ovs.lib.storagerouter              import StorageRouterController

from nose.plugins.skip                  import SkipTest
from ovs.dal.lists.vpoollist            import VPoolList


def setup():

    global client
    global sc
    global fstab_contents

    print "setup called " + __name__

    client = SSHClient.load('127.0.0.1', 'rooter')
    sc     = SetupController()

    with open("/etc/fstab") as f:
        fstab_contents = f.read()

    #make sure we start with clean env
    general.cleanup()


def teardown():
    global fstab_contents
    with open("/etc/fstab", "w") as f:
        f.write(fstab_contents)


def each_mountpoint_own_partition_test():

    unused_disks = general.get_unused_disks()

    if not unused_disks:
        raise SkipTest("Need at least one unused disk")

    vpool_readcache1_mp  = "/mnt/test_cache1"
    vpool_readcache2_mp  = "/mnt/test_cache2"
    vpool_writecache_mp  = "/mnt/test_wcache"
    vpool_foc_mp         = "/mnt/test_fcache"

    disk_layout = {vpool_readcache1_mp: {'device': unused_disks[0], 'percentage': 25, 'label': 'test_cache1'},
                   vpool_readcache2_mp: {'device': unused_disks[0], 'percentage': 25, 'label': 'test_cache2'},
                   vpool_writecache_mp: {'device': unused_disks[0], 'percentage': 25, 'label': 'test_wcache'},
                   vpool_foc_mp:        {'device': unused_disks[0], 'percentage': 25, 'label': 'test_foc'}}

    vpool_params = {}
    try:

        general.apply_disk_layout(disk_layout)

        vpool_params = general.api_add_vpool(vpool_readcache1_mp = vpool_readcache1_mp,
                                             vpool_readcache2_mp = vpool_readcache2_mp,
                                             vpool_writecache_mp = vpool_writecache_mp,
                                             vpool_foc_mp        = vpool_foc_mp)

        general.validate_vpool_size_calculation(vpool_params['vpool_name'], disk_layout)

    finally:
        if vpool_params:
            general.api_remove_vpool(vpool_params['vpool_name'])
        general.clean_disk_layout(disk_layout)


def all_mountpoints_root_partition_test():

    vpool_readcache1_mp  = "/mnt/test_cache1"
    vpool_readcache2_mp  = "/mnt/test_cache2"
    vpool_writecache_mp  = "/mnt/test_wcache"
    vpool_foc_mp         = "/mnt/test_fcache"

    disk_layout = {vpool_readcache1_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache1'},
                   vpool_readcache2_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache2'},
                   vpool_writecache_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_wcache'},
                   vpool_foc_mp:        {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_foc'}}
    initial_part_used_space = {"/": general.get_filesystem_size("/")[3]}
    vpool_params = {}
    try:
        general.apply_disk_layout(disk_layout)

        vpool_params = general.api_add_vpool(vpool_readcache1_mp = vpool_readcache1_mp,
                                             vpool_readcache2_mp = vpool_readcache2_mp,
                                             vpool_writecache_mp = vpool_writecache_mp,
                                             vpool_foc_mp        = vpool_foc_mp)


        general.validate_vpool_size_calculation(vpool_params['vpool_name'], disk_layout, initial_part_used_space)
    finally:
        if vpool_params:
            general.api_remove_vpool(vpool_params['vpool_name'])
        general.clean_disk_layout(disk_layout)


def all_mountpoints_root_partition_one_readcache_test():

    vpool_readcache1_mp  = "/mnt/test_cache1"
    vpool_writecache_mp  = "/mnt/test_wcache"
    vpool_foc_mp         = "/mnt/test_fcache"

    disk_layout = {vpool_readcache1_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache1'},
                   vpool_writecache_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_wcache'},
                   vpool_foc_mp:        {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_foc'}}
    initial_part_used_space = {"/": general.get_filesystem_size("/")[3]}
    vpool_params = {}
    try:
        general.apply_disk_layout(disk_layout)

        vpool_params = general.api_add_vpool(vpool_readcache1_mp = vpool_readcache1_mp,
                                             vpool_readcache2_mp = vpool_readcache1_mp,
                                             vpool_writecache_mp = vpool_writecache_mp,
                                             vpool_foc_mp        = vpool_foc_mp)


        general.validate_vpool_size_calculation(vpool_params['vpool_name'], disk_layout, initial_part_used_space)

    finally:
        if vpool_params:
            general.api_remove_vpool(vpool_params['vpool_name'])
        general.clean_disk_layout(disk_layout)


def dir_and_partition_layout_test():

    unused_disks = general.get_unused_disks()

    if not unused_disks:
        raise SkipTest("Need at least one unused disk")

    vpool_readcache1_mp  = "/mnt/test_cache1"
    vpool_readcache2_mp  = "/mnt/test_cache2"
    vpool_writecache_mp  = "/mnt/test_wcache"
    vpool_foc_mp         = "/mnt/test_fcache"

    for idx in range(4):
        l = [unused_disks[0]] * 4
        l[idx] = 'DIR_ONLY'
        disk_layout = {vpool_readcache1_mp: {'device': l[0], 'percentage': 25, 'label': 'test_cache1'},
                       vpool_readcache2_mp: {'device': l[1], 'percentage': 25, 'label': 'test_cache2'},
                       vpool_writecache_mp: {'device': l[2], 'percentage': 25, 'label': 'test_wcache'},
                       vpool_foc_mp:        {'device': l[3], 'percentage': 25, 'label': 'test_foc'}}

        initial_part_used_space = {"/": general.get_filesystem_size("/")[3]}

        vpool_params = {}
        try:
            general.apply_disk_layout(disk_layout)

            vpool_params = general.api_add_vpool(vpool_readcache1_mp = vpool_readcache1_mp,
                                                 vpool_readcache2_mp = vpool_readcache2_mp,
                                                 vpool_writecache_mp = vpool_writecache_mp,
                                                 vpool_foc_mp        = vpool_foc_mp)


            general.validate_vpool_size_calculation(vpool_params['vpool_name'], disk_layout, initial_part_used_space)
        finally:
            if vpool_params:
                general.api_remove_vpool(vpool_params['vpool_name'])
            general.clean_disk_layout(disk_layout)


def two_disks_layout_test():

    unused_disks = general.get_unused_disks()

    if len(unused_disks) < 2:
        raise SkipTest("Need at least 2 unused disks")

    vpool_readcache1_mp  = "/mnt/test_cache1"
    vpool_readcache2_mp  = "/mnt/test_cache2"
    vpool_writecache_mp  = "/mnt/test_wcache"
    vpool_foc_mp         = "/mnt/test_fcache"

    combinations = [comb for comb in list(itertools.product([0,1], repeat = 4)) if comb.count(0) >= 1 and comb.count(1) >= 1]
    random.shuffle(combinations)
    for comb in combinations[:6]:

        disk_layout = {vpool_readcache1_mp: {'device': unused_disks[comb[0]], 'percentage': 25, 'label': 'test_cache1'},
                       vpool_readcache2_mp: {'device': unused_disks[comb[1]], 'percentage': 25, 'label': 'test_cache2'},
                       vpool_writecache_mp: {'device': unused_disks[comb[2]], 'percentage': 25, 'label': 'test_wcache'},
                       vpool_foc_mp:        {'device': unused_disks[comb[3]], 'percentage': 25, 'label': 'test_foc'}}

        vpool_params = {}
        try:
            general.apply_disk_layout(disk_layout)

            vpool_params = general.api_add_vpool(vpool_readcache1_mp = vpool_readcache1_mp,
                                                 vpool_readcache2_mp = vpool_readcache2_mp,
                                                 vpool_writecache_mp = vpool_writecache_mp,
                                                 vpool_foc_mp        = vpool_foc_mp)


            general.validate_vpool_size_calculation(vpool_params['vpool_name'], disk_layout)
        finally:
            if vpool_params:
                general.api_remove_vpool(vpool_params['vpool_name'])
            general.clean_disk_layout(disk_layout)




def same_disk_different_percentages_layout_test():

    unused_disks = general.get_unused_disks()

    if not unused_disks:
        raise SkipTest("Need at least 1 unused disk")

    vpool_readcache1_mp  = "/mnt/test_cache1"
    vpool_readcache2_mp  = "/mnt/test_cache2"
    vpool_writecache_mp  = "/mnt/test_wcache"
    vpool_foc_mp         = "/mnt/test_fcache"

    #Layout1
    disk_layout = {vpool_readcache1_mp: {'device': unused_disks[0], 'percentage': 10, 'label': 'test_cache1'},
                   vpool_readcache2_mp: {'device': unused_disks[0], 'percentage': 40, 'label': 'test_cache2'},
                   vpool_writecache_mp: {'device': unused_disks[0], 'percentage': 25, 'label': 'test_wcache'},
                   vpool_foc_mp:        {'device': unused_disks[0], 'percentage': 25, 'label': 'test_foc'}}

    vpool_params = {}
    try:
        general.apply_disk_layout(disk_layout)

        vpool_params = general.api_add_vpool(vpool_readcache1_mp = vpool_readcache1_mp,
                                             vpool_readcache2_mp = vpool_readcache2_mp,
                                             vpool_writecache_mp = vpool_writecache_mp,
                                             vpool_foc_mp        = vpool_foc_mp)


        general.validate_vpool_size_calculation(vpool_params['vpool_name'], disk_layout)
    finally:
        if vpool_params:
            general.api_remove_vpool(vpool_params['vpool_name'])
        general.clean_disk_layout(disk_layout)


    #Layout2
    disk_layout = {vpool_readcache1_mp: {'device': unused_disks[0], 'percentage': 40, 'label': 'test_cache1'},
                   vpool_readcache2_mp: {'device': unused_disks[0], 'percentage': 10, 'label': 'test_cache2'},
                   vpool_writecache_mp: {'device': unused_disks[0], 'percentage': 25, 'label': 'test_wcache'},
                   vpool_foc_mp:        {'device': unused_disks[0], 'percentage': 25, 'label': 'test_foc'}}
    vpool_params = {}
    try:
        general.apply_disk_layout(disk_layout)

        vpool_params = general.api_add_vpool(vpool_readcache1_mp = vpool_readcache1_mp,
                                             vpool_readcache2_mp = vpool_readcache2_mp,
                                             vpool_writecache_mp = vpool_writecache_mp,
                                             vpool_foc_mp        = vpool_foc_mp)


        general.validate_vpool_size_calculation(vpool_params['vpool_name'], disk_layout)
    finally:
        if vpool_params:
            general.api_remove_vpool(vpool_params['vpool_name'])
        general.clean_disk_layout(disk_layout)


def root_partition_already_at_60_percent_test():

    fss = general.get_filesystem_size("/")
    fs_size = fss[1]
    avail_size = fss[2]

    big_file = "/root/bigfile"
    to_alocate = int((fs_size * 0.6 - (fs_size - avail_size))) / 100 * 100
    if to_alocate > 0:
        cmd = "fallocate -l {0} {1}".format(to_alocate, big_file)
        general.execute_command(cmd)

    vpool_readcache1_mp  = "/mnt/test_cache1"
    vpool_readcache2_mp  = "/mnt/test_cache2"
    vpool_writecache_mp  = "/mnt/test_wcache"
    vpool_foc_mp         = "/mnt/test_fcache"

    disk_layout = {vpool_readcache1_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache1'},
                   vpool_readcache2_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache2'},
                   vpool_writecache_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_wcache'},
                   vpool_foc_mp:        {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_foc'}}

    initial_part_used_space = {"/": general.get_filesystem_size("/")[3]}

    vpool_params = {}
    try:
        general.apply_disk_layout(disk_layout)

        vpool_params = general.api_add_vpool(vpool_readcache1_mp = vpool_readcache1_mp,
                                             vpool_readcache2_mp = vpool_readcache2_mp,
                                             vpool_writecache_mp = vpool_writecache_mp,
                                             vpool_foc_mp        = vpool_foc_mp)


        general.validate_vpool_size_calculation(vpool_params['vpool_name'], disk_layout, initial_part_used_space)
    finally:
        os.remove(big_file)
        if vpool_params:
            general.api_remove_vpool(vpool_params['vpool_name'])
        general.clean_disk_layout(disk_layout)


def readcache_and_writecache_same_dir_test():

    vpool_cache_mp = "/mnt/test_cache"
    vpool_foc_mp   = "/mnt/test_fcache"

    disk_layout = {vpool_cache_mp: {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_cache1'},
                   vpool_foc_mp:   {'device': 'DIR_ONLY', 'percentage': 25, 'label': 'test_foc'}}
    initial_part_used_space = {"/": general.get_filesystem_size("/")[3]}
    vpool_params = {}
    try:
        general.apply_disk_layout(disk_layout)

        vpool_params = general.api_add_vpool(vpool_readcache1_mp = vpool_cache_mp,
                                             vpool_readcache2_mp = vpool_cache_mp,
                                             vpool_writecache_mp = vpool_cache_mp,
                                             vpool_foc_mp        = vpool_foc_mp)


        general.validate_vpool_size_calculation(vpool_params['vpool_name'], disk_layout, initial_part_used_space)

    finally:
        if vpool_params:
            general.api_remove_vpool(vpool_params['vpool_name'])
        general.clean_disk_layout(disk_layout)


def three_disks_layout_test():

    unused_disks = general.get_unused_disks()

    if len(unused_disks) < 3:
        raise SkipTest("Need at least 2 unused disks")

    vpool_readcache1_mp  = "/mnt/test_cache1"
    vpool_readcache2_mp  = "/mnt/test_cache2"
    vpool_writecache_mp  = "/mnt/test_wcache"
    vpool_foc_mp         = "/mnt/test_fcache"

    combinations = [comb for comb in list(itertools.product([0, 1, 2], repeat = 4)) if comb.count(0) >= 1 and comb.count(1) >= 1 and comb.count(2) >= 1]
    random.shuffle(combinations)

    for comb in combinations[:6]:
        disk_layout = {vpool_readcache1_mp: {'device': unused_disks[comb[0]], 'percentage': 25, 'label': 'test_cache1'},
                       vpool_readcache2_mp: {'device': unused_disks[comb[1]], 'percentage': 25, 'label': 'test_cache2'},
                       vpool_writecache_mp: {'device': unused_disks[comb[2]], 'percentage': 25, 'label': 'test_wcache'},
                       vpool_foc_mp:        {'device': unused_disks[comb[3]], 'percentage': 25, 'label': 'test_foc'}}

        vpool_params = {}
        try:
            general.apply_disk_layout(disk_layout)

            vpool_params = general.api_add_vpool(vpool_readcache1_mp = vpool_readcache1_mp,
                                                 vpool_readcache2_mp = vpool_readcache2_mp,
                                                 vpool_writecache_mp = vpool_writecache_mp,
                                                 vpool_foc_mp        = vpool_foc_mp)


            general.validate_vpool_size_calculation(vpool_params['vpool_name'], disk_layout)
        finally:
            if vpool_params:
                general.api_remove_vpool(vpool_params['vpool_name'])
            general.clean_disk_layout(disk_layout)
