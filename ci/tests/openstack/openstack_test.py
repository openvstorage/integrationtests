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

from ovs.dal.lists.vpoollist import VPoolList
from ovs.lib.albacontroller  import AlbaController
from ovs.dal.lists.albanodelist import AlbaNodeList

from selenium.webdriver.remote.remote_connection import LOGGER

LOGGER.setLevel(logging.WARNING)

tests_to_run = general.get_tests_to_run(autotests.getTestLevel())
machinename = "AT_" + __name__.split(".")[-1]
CINDER_TYPE = autotests.getConfigIni().get("openstack", "cinder_type")
vpool_name = autotests.getConfigIni().get("vpool", "vpool_name")


def setup():
    global prev_os

    if not general_openstack.is_openstack_present():
        return
    prev_os = autotests.getOs()
    autotests.setOs('ubuntu_server14_kvm')

    # make sure we start with clean env
    general.cleanup()

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    if not vpool:
        general.api_add_vpool(apply_to_all_nodes=True, config_cinder=True)
        _ = VPoolList.get_vpool_by_name(vpool_name)


def teardown():
    if not general_openstack.is_openstack_present():
        return

    autotests.setOs(prev_os)
    if autotests.getConfigIni().get("main", "cleanup") == "True":
        general_openstack.cleanup()

    # Check the amount of open log files at the end at the test suite
    general.validate_logstash_open_files_amount()


def create_empty_volume_test():
    """
    Create an empty volume using cinder
     - validate if the volume is created successfully
     - cleanup the volume
    """
    general.check_prereqs(testcase_number=1, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    name = "{0}_{1}_empty_vol".format(machinename, int(time.time()))

    vol_id = general_openstack.create_volume(image_id="", cinder_type=CINDER_TYPE, volume_name=name, volume_size=1)

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

    volume_name = machinename + str(time.time()) + "_vol_from_img"

    glance_image_id = general_openstack.create_glance_image()
    glance_image = general_openstack.get_image(glance_image_id)

    # Adjust volume size according to the size of the image
    volume_size = 3
    if glance_image:
        glance_image_size = int(glance_image[0]['Size']) / 1024 ** 3
        if glance_image_size > volume_size:
            volume_size = glance_image_size

    vol_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=CINDER_TYPE, volume_name=volume_name,
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

    volume_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=CINDER_TYPE,
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

    volume_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=CINDER_TYPE,
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

    general_openstack.delete_instance(instance_id)
    general_openstack.delete_snapshot(snapshot_id)
    general_openstack.delete_volume(volume_id)


def permissions_check_test():
    """
    Check group and owner of the vpool
    Create an empty volume and check file/directory permissions
    """
    general.check_prereqs(testcase_number=5, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    expected_owner = "ovs"
    expected_group = "ovs"
    expected_dir_perms = "775"
    expected_file_perms = "775"

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    mount_point = vpool.storagedrivers[0].mountpoint

    st = os.stat(mount_point)
    owner = pwd.getpwuid(st.st_uid).pw_name
    group = pwd.getpwuid(st.st_gid).pw_name

    assert owner == expected_owner, "Wrong owner for {0}, expected {1} got {2}".\
        format(mount_point, expected_owner, owner)
    assert group == expected_group, "Wrong group for {0}, expected {1} got {2}".\
        format(mount_point, expected_group, group)

    volume_name = "{0}_empty_vol".format(machinename, int(time.time()))
    volume_id = general_openstack.create_volume(image_id="", cinder_type=CINDER_TYPE, volume_name=volume_name,
                                                volume_size=1)

    raw_file_name = os.path.join(mount_point, volume_name + ".raw")
    assert os.path.exists(raw_file_name), "Raw file {0} was not found after creating volume".format(raw_file_name)

    file_perms = general.get_file_perms(raw_file_name)
    assert file_perms[-3:] == expected_file_perms, "File permissions wrong, expected {0} got {1}".\
        format(expected_file_perms, file_perms)

    dir_perms = general.get_file_perms("/mnt/{0}/instances".format(vpool_name))
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

    hosts = set([s['Host'] for s in general_openstack.get_formated_cmd_output("nova service-list")])
    if len(hosts) < 2:
        raise SkipTest("Need at least 2 nodes to run live migration")

    t = str(time.time())
    instance_name = machinename + t + "lv_migr"
    volume_name = instance_name + "_disk"

    glance_image_id = general_openstack.create_glance_image()

    volume_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=CINDER_TYPE,
                                                volume_name=volume_name, volume_size=5)

    main_host = general.get_this_hostname()

    instance_id = general_openstack.create_instance(volume_id=volume_id, instance_name=instance_name, host=main_host)

    new_host = [h for h in hosts if h != main_host][random.randint(0, len(hosts) - 2)]
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

    disks_to_create = 10
    vol_ids = {}
    for idx in range(disks_to_create):
        time.sleep(5)
        vol_name = "{0}_{1}".format(volume_name, idx)
        vol_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=CINDER_TYPE,
                                                 volume_name=vol_name, volume_size=volume_size)
        vol_ids[vol_id] = vol_name

    for vol_id in vol_ids:
        general_openstack.delete_volume(vol_id, wait=False)

    for vol_id, vol_name in vol_ids.iteritems():
        general_openstack.wait_for_volume_to_disappear(vol_id, vol_name, retries=900)


def alba_license_volumes_limitation_test():
    """
    Get the active license of the OpenvStorage-Backend and
    test its boundaries
     - Create maximum allowed namespaces
    """
    general.check_prereqs(testcase_number=8, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    # Get alba license
    alba_license = general.get_alba_license()
    if not alba_license:
        raise SkipTest()

    # If an unlimited license is in use, check the quota vpool limit
    if alba_license.data['namespaces'] is None:
        quotas = general_openstack.get_formated_cmd_output("cinder quota-show $(keystone tenant-get admin | awk '/id/ {print $4}')")
        volumes_limit = int(general.get_elem_with_val(quotas, "Property", "volumes_{0}".
                                                      format(CINDER_TYPE))[0]['Value'])
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
                                                 cinder_type=CINDER_TYPE,
                                                 volume_name=vol_name,
                                                 volume_size=volume_size)
        vol_ids[vol_id] = vol_name

    # Try to create one more volume (should fail)
    try:
        vol_name = "{0}_{1}".format(volume_name, idx + 1)
        vol_id = general_openstack.create_volume(image_id=glance_image_id, cinder_type=CINDER_TYPE,
                                                 volume_name=vol_name, volume_size=volume_size)
        if vol_id:
            vol_limit_exceeded = True
    except Exception as ex:
        print 'Cannot exceed license namespaces limitation : {0}'.format(str(ex))

    # Cleanup vols
    for vol_id in vol_ids:
        general_openstack.delete_volume(vol_id, wait=True)

    assert not vol_limit_exceeded, 'Exceeding license namespaces limitation was allowed'


def alba_license_osds_limitation_test():
    """
    Get the active license of the OpenvStorage-Backend and
    test its boundaries
     - Create maximum allowed OSDs
    """
    general.check_prereqs(testcase_number=9, tests_to_run=tests_to_run)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    # Get alba license
    alba_license = general.get_alba_license()
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
        box_id = alba_node.box_id

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
                    general_alba.asd_start(asd_id, port, path, box_id, False)

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
                    general_alba.asd_start(asd_id, port, path, box_id, False)

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
