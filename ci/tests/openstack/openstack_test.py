import os
import pwd
import time
import random

from ci                     import autotests
from nose.plugins.skip      import SkipTest
from ci.tests.general       import general
from ci.tests.general       import general_hypervisor
from ci.tests.general       import general_openstack

from ovs.dal.lists.vpoollist        import VPoolList

testsToRun     = general.getTestsToRun(autotests.getTestLevel())
machinename    = "AT_" + __name__.split(".")[-1]
cinder_type    = autotests.getConfigIni().get("openstack", "cinder_type")
vpool_name     = autotests.getConfigIni().get("vpool", "vpool_name")


def setup():
    global prev_os
    prev_os = autotests.getOs()
    autotests.setOs('ubuntu_server14_kvm')

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    if not vpool:
        general.api_add_vpool(apply_to_all_nodes = True, config_cinder = True)
        vpool = VPoolList.get_vpool_by_name(vpool_name)

    instances_dir = "/mnt/{0}/instances".format(vpool_name)
    stack_user = "stack"
    if not os.path.exists(instances_dir):
        os.makedirs(instances_dir)
        passwd = pwd.getpwnam(stack_user)
        os.chown(instances_dir, passwd.pw_uid, passwd.pw_gid)
        for srv in ["c-api", "c-sch", "c-vol"]:
            general_openstack.restart_service_in_screen(srv)


def teardown():
    autotests.setOs(prev_os)
    if autotests.getConfigIni().get("main", "cleanup") == "True":
        general_openstack.cleanup()


def create_empty_volume_test():

    general.checkPrereqs(testCaseNumber = 1,
                         testsToRun     = testsToRun)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    name = machinename + str(time.time()) + "empty_vol"

    vol_id = general_openstack.create_volume(image_id    = "",
                                             cinder_type = cinder_type,
                                             volume_name = name,
                                             volume_size = 1)

    general_openstack.delete_volume(vol_id)


def create_volume_from_image_test():

    general.checkPrereqs(testCaseNumber = 2,
                         testsToRun     = testsToRun)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    volume_name = machinename + str(time.time()) + "_vol_from_img"

    glance_image_id = general_openstack.create_glance_image()

    vol_id = general_openstack.create_volume(image_id    = glance_image_id,
                                             cinder_type = cinder_type,
                                             volume_name = volume_name,
                                             volume_size = 3)

    general_openstack.delete_volume(vol_id)


def boot_nova_instance_from_volume_test():

    general.checkPrereqs(testCaseNumber = 3,
                         testsToRun     = testsToRun)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    t = str(time.time())
    instance_name = machinename + t + "_boot_from_vol"
    volume_name = instance_name + "_disk"

    glance_image_id = general_openstack.create_glance_image()


    volume_id = general_openstack.create_volume(image_id    = glance_image_id,
                                                cinder_type = cinder_type,
                                                volume_name = volume_name,
                                                volume_size = 3)

    main_host = general.get_this_hostname()

    instance_id     = general_openstack.create_instance(volume_id     = volume_id,
                                                        instance_name = instance_name,
                                                        host          = main_host)

    vm_name = general_openstack.get_vm_name_hpv(instance_id)
    vm_ip   = general_openstack.get_instance_ip(instance_id)

    hpv = general_hypervisor.Hypervisor.get(vpool_name)
    hpv.wait_for_vm_pingable(vm_name, vm_ip = vm_ip)

    general_openstack.delete_instance(instance_id)
    general_openstack.delete_volume(volume_id)


def boot_nova_instance_from_snapshot_test():

    general.checkPrereqs(testCaseNumber = 4,
                         testsToRun     = testsToRun)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    t = str(time.time())
    instance_name = machinename + t + "_boot_from_snap"
    volume_name = instance_name + "_disk"

    glance_image_id = general_openstack.create_glance_image()


    volume_id = general_openstack.create_volume(image_id    = glance_image_id,
                                                cinder_type = cinder_type,
                                                volume_name = volume_name,
                                                volume_size = 3)

    snapshot_id = general_openstack.create_snapshot(volume_id = volume_id)

    main_host = general.get_this_hostname()

    instance_id     = general_openstack.create_instance(snapshot_id   = snapshot_id,
                                                        instance_name = instance_name,
                                                        host          = main_host)

    vm_name = general_openstack.get_vm_name_hpv(instance_id)
    vm_ip   = general_openstack.get_instance_ip(instance_id)

    hpv = general_hypervisor.Hypervisor.get(vpool_name)
    hpv.wait_for_vm_pingable(vm_name, vm_ip = vm_ip)

    general_openstack.delete_instance(instance_id)
    general.execute_command("cinder snapshot-delete {0}".format(snapshot_id))
    general_openstack.delete_volume(volume_id)


def boot_nova_instance_from_image_test():

    general.checkPrereqs(testCaseNumber = 5,
                         testsToRun     = testsToRun)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    instance_name = machinename + str(time.time()) + "_boot_from_image"

    glance_image_id = general_openstack.create_glance_image()

    main_host = general.get_this_hostname()

    instance_id     = general_openstack.create_instance(image_id      = glance_image_id,
                                                        instance_name = instance_name,
                                                        host          = main_host)

    vm_name = general_openstack.get_vm_name_hpv(instance_id)
    vm_ip   = general_openstack.get_instance_ip(instance_id)

    hpv = general_hypervisor.Hypervisor.get(vpool_name)
    hpv.wait_for_vm_pingable(vm_name, vm_ip = vm_ip)

    general_openstack.delete_instance(instance_id)


def permissions_check_test():

    general.checkPrereqs(testCaseNumber = 6,
                         testsToRun     = testsToRun)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    expected_owner      = "stack"
    expected_group      = "libvirtd"
    expected_dir_perms  = "644"
    expected_file_perms = "755"

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    mountpoint = vpool.storagedrivers[0].mountpoint

    st = os.stat(mountpoint)
    owner = pwd.getpwuid(st.st_uid).pw_name
    group = pwd.getpwuid(st.st_gid).pw_name

    assert owner == expected_owner, "Wrong owner for {0}, expected {1} got {2}".format(mountpoint, expected_owner, owner)
    assert group == expected_group, "Wrong group for {0}, expected {1} got {2}".format(mountpoint, expected_group, group)

    volume_name = machinename + str(time.time()) + "empty_vol"
    volume_id = general_openstack.create_volume(image_id    = "",
                                                cinder_type = cinder_type,
                                                volume_name = volume_name,
                                                volume_size = 1)

    raw_file_name = os.path.join(mountpoint, volume_name + ".raw")
    assert os.path.exists(raw_file_name), "Raw file {0} was not found after creating volume".format(raw_file_name)

    file_perms = general.get_file_perms(raw_file_name)
    assert file_perms[-3:] == expected_file_perms, "File permissions wrong, expected {0} got {1}".format(expected_file_perms, file_perms)

    dir_perms = general.get_file_perms("/mnt/saio/instances")
    assert dir_perms[-3:] == expected_dir_perms, "Dir permissions wrong, expected {0} got {1}".format(expected_dir_perms, dir_perms)


def live_migration_test():

    general.checkPrereqs(testCaseNumber = 7,
                         testsToRun     = testsToRun)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    hosts = set([s['Host'] for s in general_openstack.get_formated_cmd_output("nova service-list")])
    if len(hosts) < 2:
        raise SkipTest("Need at least 2 nodes to run live migration")

    t = str(time.time())
    instance_name = machinename + t + "lv_migr"
    volume_name = instance_name + "_disk"

    glance_image_id = general_openstack.create_glance_image()

    volume_id = general_openstack.create_volume(image_id    = glance_image_id,
                                                cinder_type = cinder_type,
                                                volume_name = volume_name,
                                                volume_size = 3)

    main_host = general.get_this_hostname()

    instance_id     = general_openstack.create_instance(volume_id     = volume_id,
                                                        instance_name = instance_name,
                                                        host          = main_host)

    vm_name = general_openstack.get_vm_name_hpv(instance_id)
    vm_ip   = general_openstack.get_instance_ip(instance_id)

    hpv = general_hypervisor.Hypervisor.get(vpool_name)
    hpv.wait_for_vm_pingable(vm_name, vm_ip = vm_ip)

    new_host = [h for h in hosts if h != main_host][random.randint(0, len(hosts) - 2)]
    general_openstack.live_migration(instance_id, new_host)

    general_openstack.delete_instance(instance_id)


def fillup_multinode_system_test():

    general.checkPrereqs(testCaseNumber = 8,
                         testsToRun     = testsToRun)

    if not general_openstack.is_openstack_present():
        raise SkipTest()

    hosts = set([s['Host'] for s in general_openstack.get_formated_cmd_output("nova service-list")])
    if len(hosts) < 2:
        raise SkipTest("Need at least 2 nodes required")

    quotas = general_openstack.get_formated_cmd_output("cinder quota-show $(keystone tenant-get admin | awk '/id/ {print $4}')")

    volumes_limit       = int(general.get_elem_with_val(quotas, "Property", "volumes")[0]['Value'])
    volumes_limit_vpool = int(general.get_elem_with_val(quotas, "Property", "volumes_{0}".format(cinder_type))[0]['Value'])

    max_vols_per_node = min(volumes_limit, volumes_limit_vpool)

    t = str(time.time())
    name = machinename + t + "max_vols"

    images = [img for img in general_openstack.get_formated_cmd_output("glance image-list") if img['ContainerFormat'] not in ["aki", "ari"]]
    images = sorted(images, key = lambda x: int(x['Size']))
    glance_image_id = images[0]['ID']

    existing_volumes = general_openstack.get_formated_cmd_output("cinder list")
    vols_to_create = max_vols_per_node * len(hosts) - len(existing_volumes)

    for idx in range(vols_to_create):
        general_openstack.create_volume(image_id    = glance_image_id,
                                        cinder_type = cinder_type,
                                        volume_name = name + str(idx),
                                        volume_size = 1)

    hosts_usage = dict(zip(hosts, [0] * len(hosts)))
    cinder_vols = general_openstack.get_formated_cmd_output("cinder list")

    for cvol in cinder_vols:
        cvol_info = general_openstack.get_formated_cmd_output("cinder show {0}".format(cvol['ID']))
        host = general.get_elem_with_val(cvol_info, "Property", "os-vol-host-attr:host")[0]["Value"]
        hosts_usage[host] += 1

    assert all([(max_vols_per_node - 2 < hu < max_vols_per_node + 2) for hu in hosts_usage.values()]), "Cinder volumes are not evenly distributed: {0}".format(hosts_usage)


