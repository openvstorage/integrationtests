# Copyright 2014 Open vStorage NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os
import pwd
import time
import random

from ci import autotests
from nose.plugins.skip import SkipTest
from ci.tests.general import general
from ci.tests.general import general_openstack
from ci.tests.general import general_alba

from nose.tools import timed

from ovs.dal.lists.vpoollist import VPoolList
from ovs.lib.albacontroller import AlbaController
from ovs.dal.lists.albanodelist import AlbaNodeList

from selenium.webdriver.remote.remote_connection import LOGGER

LOGGER.setLevel(logging.WARNING)

tests_to_run = general.get_tests_to_run(autotests.getTestLevel())
machinename = "AT_" + __name__.split(".")[-1]
vpool_name = general.test_config.get("vpool", "vpool_name")
vpool_name = 'openstack-' + vpool_name


def setup():
    global prev_os

    if not general_openstack.is_openstack_present():
        return
    prev_os = autotests.getOs()
    autotests.setOs('ubuntu_server14_kvm')

    # make sure we start with clean env
    if general_openstack.is_openstack_present():
        general_openstack.cleanup()
    general.cleanup()

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    if not vpool:
        general.api_add_vpool(vpool_name=vpool_name, apply_to_all_nodes=True, config_cinder=True)
        _ = VPoolList.get_vpool_by_name(vpool_name)


def teardown():
    if not general_openstack.is_openstack_present():
        return

    autotests.setOs(prev_os)
    if general.test_config.get("main", "cleanup") == "True":
        general_openstack.cleanup()

    # Check the amount of open log files at the end at the test suite
    # OVS-2638 - logstash is no longer installed by default
    # general.validate_logstash_open_files_amount()


def create_empty_volume_test():
    """
    Create an empty volume using cinder
     - validate if the volume is created successfully
     - cleanup the volume
    """
    general.check_prereqs(testcase_number=1, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()
    else:
        general_openstack.cleanup()

    name = "{0}_{1}_empty_vol".format(machinename, int(time.time()))

    vol_id = general_openstack.create_volume(image_id="", cinder_type=vpool_name, volume_name=name, volume_size=1)

    general_openstack.delete_volume(vol_id)


def create_volume_from_image_test():
    """
    Create a new volume from an image (created with glance)
     - validate if the volume is created successfully
     - cleanup the volume
    """
    general.check_prereqs(testcase_number=2, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()
    else:
        general_openstack.cleanup()

    _ = general.setup_vpool(vpool_name)

    volume_name = machinename + str(time.time()) + "_vol_from_img"

    glance_image_id = general_openstack.create_glance_image()
    glance_image = general_openstack.get_image(glance_image_id)

    # Adjust volume size according to the size of the image
    volume_size = 3
    if glance_image:
        glance_image_size = int(glance_image[0]['Size']) / 1024 ** 3
        if glance_image_size > volume_size:
            volume_size = glance_image_size

    vol_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=vpool_name, volume_name=volume_name,
                                             volume_size=volume_size)
    general_openstack.delete_volume(vol_id)


def boot_nova_instance_from_volume_test():
    """
    Create and boot an instance using a volume (created from image)
     - validate if volume and instance are created successfully
     - validate the existence of the instance on both OpenStack and OVS
     - retrieve the IP from hypervisor and try to ping the instance
     - cleanup volume and instance
    """
    general.check_prereqs(testcase_number=3, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()
    else:
        general_openstack.cleanup()

    _ = general.setup_vpool(vpool_name)

    instance_name = "{0}_{1}_boot_from_vol".format(machinename, int(time.time()))
    volume_name = "{0}_disk".format(instance_name)

    glance_image_id = general_openstack.create_glance_image()
    glance_image = general_openstack.get_image(glance_image_id)

    # Adjust volume size according to the size of the image
    volume_size = 3
    if glance_image:
        glance_image_size = int(glance_image[0]['Size']) / 1024 ** 3
        if glance_image_size > volume_size:
            volume_size = glance_image_size

    volume_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=vpool_name,
                                                volume_name=volume_name, volume_size=volume_size)

    main_host = general.get_this_hostname()
    instance_id = general_openstack.create_instance(volume_id=volume_id, instance_name=instance_name, host=main_host)

    # @todo: Fix assignment of IP addr on the instance and uncomment this part
    # vm_name = general_openstack.get_vm_name_hpv(instance_id)
    # vm_ip   = general_openstack.get_instance_ip(instance_id)
    # hpv = general_hypervisor.Hypervisor.get(vpool_name)
    # hpv.wait_for_vm_pingable(vm_name, vm_ip = vm_ip, retries = 150)

    general_openstack.delete_instance(instance_id)
    general_openstack.delete_volume(volume_id)


def boot_nova_instance_from_snapshot_test():
    """
    Create a volume from image and snapshot it;
    Create and boot an instance using the snapshot of volume
     - validate if volume snapshot and instance are created successfully
     - validate the existence of the instance on both OpenStack and OVS
     - retrieve the IP from hypervisor and try to ping the instance
     - cleanup volume, snapshot and instance
    """
    general.check_prereqs(testcase_number=4, tests_to_run=tests_to_run)

    # Skip this test due to an issue in voldrv
    # Bug reference : OVS-2022
    # raise SkipTest()

    if not general_openstack.is_openstack_present():
        raise SkipTest()
    else:
        general_openstack.cleanup()

    _ = general.setup_vpool(vpool_name)

    instance_name = "{0}_{1}_boot_from_snap".format(machinename, int(time.time()))
    volume_name = "{0}_disk".format(instance_name)

    glance_image_id = general_openstack.create_glance_image()
    glance_image = general_openstack.get_image(glance_image_id)

    # Adjust volume size according to the size of the image
    volume_size = 3
    if glance_image:
        glance_image_size = int(glance_image[0]['Size']) / 1024 ** 3
        if glance_image_size > volume_size:
            volume_size = glance_image_size

    volume_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=vpool_name,
                                                volume_name=volume_name, volume_size=volume_size)
    snapshot_id = general_openstack.create_snapshot(volume_id=volume_id)

    main_host = general.get_this_hostname()
    instance_id = general_openstack.create_instance(snapshot_id=snapshot_id, instance_name=instance_name,
                                                    host=main_host)

    # @todo: Fix assignment of IP addr on the instance and uncomment this part
    # vm_name = general_openstack.get_vm_name_hpv(instance_id)
    # vm_ip   = general_openstack.get_instance_ip(instance_id)
    # hpv = general_hypervisor.Hypervisor.get(vpool_name)
    # hpv.wait_for_vm_pingable(vm_name, vm_ip = vm_ip)

    logging.log(1, "Deleting instance with id: {0}".format(instance_id))
    general_openstack.delete_instance(instance_id, delete_volumes=True)
    logging.log(1, "Deleting snapshot with id: {0}".format(snapshot_id))
    general_openstack.delete_snapshot(snapshot_id)
    logging.log(1, "Deleting volume with id:: {0}".format(volume_id))
    general_openstack.delete_volume(volume_id)
    logging.log(1, "Cleanup complete".format())


def permissions_check_test():
    """
    Check group and owner of the vpool
    Create an empty volume and check file/directory permissions
    """
    general.check_prereqs(testcase_number=5, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()
    else:
        general_openstack.cleanup()

    expected_owner = "ovs"
    expected_group = "ovs"
    expected_dir_perms = "755"
    expected_file_perms = "775"

    vpool = general.setup_vpool(vpool_name)

    assert vpool.storagedrivers, "At least one storagedriver should be configured for vpool: {0}".format(vpool.name)
    mount_point = vpool.storagedrivers[0].mountpoint

    st = os.stat(mount_point)
    owner = pwd.getpwuid(st.st_uid).pw_name
    group = pwd.getpwuid(st.st_gid).pw_name

    assert owner == expected_owner, "Wrong owner for {0}, expected {1} got {2}".\
        format(mount_point, expected_owner, owner)
    assert group == expected_group, "Wrong group for {0}, expected {1} got {2}".\
        format(mount_point, expected_group, group)

    volume_name = "{0}_empty_vol".format(machinename, int(time.time()))
    volume_id = general_openstack.create_volume(image_id="", cinder_type=vpool_name, volume_name=volume_name,
                                                volume_size=1)

    raw_file_name = os.path.join(mount_point, volume_name + ".raw")
    assert os.path.exists(raw_file_name), "Raw file {0} was not found after creating volume".format(raw_file_name)

    file_perms = general.get_file_perms(raw_file_name)
    assert file_perms[-3:] == expected_file_perms, "File permissions wrong, expected {0} got {1}".\
        format(expected_file_perms, file_perms)

    dir_perms = general.get_file_perms("/opt/stack/data/nova/instances")
    assert dir_perms[-3:] == expected_dir_perms, "Dir permissions wrong, expected {0} got {1}".\
        format(expected_dir_perms, dir_perms)

    general_openstack.delete_volume(volume_id)


def live_migration_test():
    """
    Create a volume from image.
    Create and boot an instance using the volume
    Validate Live Migration of the instance to a different host
    """
    general.check_prereqs(testcase_number=6, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()
    else:
        general_openstack.cleanup()

    hosts = set([s['Host'] for s in general_openstack.get_formated_cmd_output("nova service-list")])
    if len(hosts) < 2:
        raise SkipTest("Need at least 2 nodes to run live migration")

    t = str(time.time())
    instance_name = machinename + t + "lv_migr"
    volume_name = instance_name + "_disk"

    glance_image_id = general_openstack.create_glance_image()
    logging.log(1, "image created: {0}".format(glance_image_id))

    volume_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=vpool_name,
                                                volume_name=volume_name, volume_size=5)
    logging.log(1, "volume created: {0}".format(volume_id))

    main_host = general.get_this_hostname()
    logging.log(1, "main host: {0}".format(main_host))

    instance_id = general_openstack.create_instance(volume_id=volume_id, instance_name=instance_name, host=main_host)
    logging.log(1, "instance id: {0}".format(instance_id))

    new_host = [h for h in hosts if h != main_host][random.randint(0, len(hosts) - 2)]
    logging.log(1, "target host: {0}".format(new_host))

    general_openstack.live_migration(instance_id, new_host)

    general_openstack.delete_instance(instance_id)


def delete_multiple_volumes_test():
    """
    Create multiple volumes from image and delete them
     - Validate if volumes are deleted after waiting
       for the initiated delete actions to finish
    """
    general.check_prereqs(testcase_number=7, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()
    else:
        general_openstack.cleanup()

    volume_name = "{0}_{1}_del_multi".format(machinename, int(time.time()))

    images = [img for img in general_openstack.get_formated_cmd_output("glance image-list")
              if img['ContainerFormat'] not in ["aki", "ari"]]
    images = sorted(images, key=lambda x: int(x['Size']))
    glance_image_id = images[0]['ID']
    glance_image = general_openstack.get_image(glance_image_id)

    # Adjust volume size according to the size of the image
    volume_size = 1
    if glance_image:
        glance_image_size = int(glance_image[0]['Size']) / 1024 ** 3
        if glance_image_size > volume_size:
            volume_size = glance_image_size

    disks_to_create = 5
    vol_ids = {}
    for idx in range(disks_to_create):
        time.sleep(5)
        vol_name = "{0}_{1}".format(volume_name, idx)
        logging.log(1, "Creating volume: {0}".format(vol_name))
        vol_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=vpool_name,
                                                 volume_name=vol_name, volume_size=volume_size)
        vol_ids[vol_id] = vol_name

    for vol_id in vol_ids:
        logging.log(1, "Deleting volume: {0}".format(vol_name))
        general_openstack.delete_volume(vol_id, wait=False)

    for vol_id, vol_name in vol_ids.iteritems():
        logging.log(1, "Waiting for volume: {0} to dissappear on openstack level".format(vol_name))
        general_openstack.wait_for_volume_to_disappear(vol_id, vol_name, retries=900)

# disabled as licensing will become obsolete
def alba_license_volumes_limitation():
    """
    Get the active license of the OpenvStorage-Backend and
    test its boundaries
     - Create maximum allowed namespaces
    """
    general.check_prereqs(testcase_number=8, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    # Get alba license
    alba_license = general.get_alba_license('alba')
    if not alba_license:
        raise SkipTest()

    # If an unlimited license is in use, check the quota vpool limit
    if alba_license.data['namespaces'] is None:
        quotas = general_openstack.get_formated_cmd_output("cinder quota-show $(keystone tenant-get admin | awk '/id/ {print $4}')")
        volumes_limit = int(general.get_elem_with_val(quotas, "Property", "volumes_{0}".
                                                      format(vpool_name))[0]['Value'])
    else:
        volumes_limit = alba_license.data['namespaces']

    volume_name = "{0}_{1}_max_vols".format(machinename, int(time.time()))

    images = [img for img in general_openstack.get_formated_cmd_output("glance image-list")
              if img['ContainerFormat'] not in ["aki", "ari"]]
    images = sorted(images, key=lambda x: int(x['Size']))
    glance_image_id = images[0]['ID']
    glance_image = general_openstack.get_image(glance_image_id)

    # Adjust volume size according to the size of the image
    volume_size = 1
    if glance_image:
        glance_image_size = int(glance_image[0]['Size']) / 1024 ** 3
        if glance_image_size > volume_size:
            volume_size = glance_image_size

    # Max allowed volumes to create, for a license with 100 namespaces:
    # - Every volume = 1 namespace
    # - Every vpool = 1 namespace
    # So we can create 99 volumes, because one namespace is reserved for the vpool
    # Trying to create more than 99 volumes should fail
    existing_volumes = general_openstack.get_formated_cmd_output("cinder list")
    vols_to_create = volumes_limit - len(existing_volumes) - 1

    logging.log(1, "Nr of volumes to create to reach license limitation: {0}".format(vols_to_create))

    vol_ids = {}
    vol_limit_exceeded = False
    idx = 0
    for idx in range(vols_to_create):
        time.sleep(2)
        vol_name = "{0}_{1}".format(volume_name, idx)
        vol_id = general_openstack.create_volume(image_id=glance_image_id,
                                                 cinder_type=vpool_name,
                                                 volume_name=vol_name,
                                                 volume_size=volume_size)
        vol_ids[vol_id] = vol_name

    # Try to create one more volume (should fail)
    try:
        vol_name = "{0}_{1}".format(volume_name, idx + 1)
        vol_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=vpool_name,
                                                 volume_name=vol_name, volume_size=volume_size)
        if vol_id:
            vol_limit_exceeded = True
    except Exception as ex:
        print 'Cannot exceed license namespaces limitation : {0}'.format(str(ex))

    # Cleanup vols
    for vol_id in vol_ids:
        general_openstack.delete_volume(vol_id, wait=True)

    assert not vol_limit_exceeded, 'Exceeding license namespaces limitation was allowed'


# disabled as licensing will become obsolete
@timed(3600)
def alba_license_osds_limitation():
    """
    Get the active license of the OpenvStorage-Backend and
    test its boundaries
     - Create maximum allowed OSDs
    """
    general.check_prereqs(testcase_number=9, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    # Get alba license
    alba_license = general.get_alba_license('alba')
    if not alba_license:
        raise SkipTest()

    # Validate maximum allowed OSDs
    asds = {}
    osd_limit_exceeded = False
    asd_create_error = False
    alba_be = None
    if alba_license.data['osds']:
        alba_be = general_alba.get_alba_backend()
        alba_node = AlbaNodeList.get_albanodes()[0]
        node_id = alba_node.node_id

        nr_asds_to_create = alba_license.data['osds'] - len(alba_be.asds_guids)
        if nr_asds_to_create > 0:
            asd_id = None
            idx = 0
            asd_id = None
            try:
                for idx in range(nr_asds_to_create):
                    # Create and start Dummy ASD
                    asd_id = 'AT_asd_{0}'.format(idx)
                    port = 8630 + idx
                    path = '/mnt/alba-asd/{0}'.format(asd_id)
                    general_alba.asd_start(asd_id, port, path, node_id, False)

                    # Add ASD in the OVS lib
                    AlbaController.add_units(alba_be.guid, {asd_id: alba_node.guid})

                    # Update asds list
                    asds[asd_id] = {'port': port, 'path': path}
            except Exception as ex:
                print 'ASD creation failed {0} with error: {1}'.format(asd_id, str(ex))
                asd_create_error = True

            if not asd_create_error:
                # Try to exceed the OSDs license limit
                idx = 0
                try:
                    idx += 1
                    asd_id = 'AT_asd_{0}'.format(idx)
                    port = 8630 + idx
                    path = '/mnt/alba-asd/{0}'.format(asd_id)
                    general_alba.asd_start(asd_id, port, path, node_id, False)

                    # Add ASD in the OVS lib
                    AlbaController.add_units(alba_be.guid, {asd_id: alba_node.guid})

                    # Update ASDs list
                    asds[asd_id] = {'port': port, 'path': path}
                    osd_limit_exceeded = True
                except Exception as ex:
                    print 'Cannot exceed license OSDs limitation : {0}'.format(str(ex))

    # Cleanup created ASDs
    if asds:
        for asd_id, asd_info in asds.iteritems():
            AlbaController.remove_units(alba_be.guid, [asd_id])

            # Stop the ASD
            general_alba.asd_stop(asd_info['port'])

            # Remove leftover files
            os.popen('rm -r {0}'.format(asd_info['path']))

        # Remove ASD from the model
        alba_be = general_alba.get_alba_backend()
        for asd in alba_be.asds:
            if asd.asd_id in asds.keys():
                asd.delete()

    assert not asd_create_error, 'Failed to create ODSs'
    assert not osd_limit_exceeded, 'Exceeding license OSDs limitation was allowed'
