import os
import pwd
import random

from ci                     import autotests
from nose.plugins.skip      import SkipTest
from ci.tests.general       import general
from ci.tests.general       import general_hypervisor
from ci.tests.general       import general_openstack

from ovs.dal.lists.vpoollist        import VPoolList


machinename    = "AT_" + __name__.split(".")[-1]
cinder_type    = autotests.getConfigIni().get("openstack", "cinder_type")
vpool_name     = autotests.getConfigIni().get("vpool", "vpool_name")


def setup():
    if not general_openstack.is_openstack_present():
        raise SkipTest()

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    if not vpool:
        general.api_add_vpool(apply_to_all_nodes = True)
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
    general_openstack.cleanup()


def start_instance_test():
    instance_name = machinename + "start_inst"

    glance_image_id = general_openstack.create_glance_image()

    volume_id = general_openstack.create_volume_from_image(image_id    = glance_image_id,
                                                           cinder_type = cinder_type,
                                                           volume_name = machinename + "_disk",
                                                           volume_size = 3)

    main_host = general.get_this_hostname()

    instance_id     = general_openstack.create_instance_from_volume(volume_id     = volume_id,
                                                                    instance_name = instance_name,
                                                                    host          = main_host)

    vm_name = general_openstack.get_vm_name_hpv(instance_id)
    vm_ip   = general_openstack.get_instance_ip(instance_id)

    hpv = general_hypervisor.Hypervisor.get(vpool_name)
    hpv.wait_for_vm_pingable(vm_name, vm_ip = vm_ip)

    general_openstack.delete_instance(instance_id)


def live_migration_test():

    hosts = set([s['Host'] for s in general_openstack.get_formated_cmd_output("nova service-list")])
    if len(hosts) < 2:
        raise SkipTest("Need at least 2 nodes to run live migration")

    instance_name = machinename + "lv_migr"

    glance_image_id = general_openstack.create_glance_image()

    volume_id = general_openstack.create_volume_from_image(image_id    = glance_image_id,
                                                           cinder_type = cinder_type,
                                                           volume_name = machinename + "_disk",
                                                           volume_size = 3)

    main_host = general.get_this_hostname()

    instance_id     = general_openstack.create_instance_from_volume(volume_id     = volume_id,
                                                                    instance_name = instance_name,
                                                                    host          = main_host)

    vm_name = general_openstack.get_vm_name_hpv(instance_id)
    vm_ip   = general_openstack.get_instance_ip(instance_id)

    hpv = general_hypervisor.Hypervisor.get(vpool_name)
    hpv.wait_for_vm_pingable(vm_name, vm_ip = vm_ip)

    new_host = [h for h in hosts if h != main_host][random.randint(0, len(hosts) - 2)]
    general_openstack.live_migration(instance_id, new_host)

    general_openstack.delete_instance(instance_id)
