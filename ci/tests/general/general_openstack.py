import os
import time
import urlparse

from ovs.dal.lists.vdisklist        import VDiskList
from ovs.dal.lists.vmachinelist     import VMachineList

import general
from ci import autotests


IMAGE_NAME = "AUTOTEST_IMAGE"

#Setup environ
os.environ["OS_USERNAME"]    = "admin"
os.environ["OS_PASSWORD"]    = "rooter"
os.environ["OS_TENANT_NAME"] = "admin"
os.environ["OS_AUTH_URL"]    = "http://{node_ip}:35357/v2.0".format(node_ip = general.get_local_vsa().ip)


def is_openstack_present():
    return bool(general.execute_command("ps aux | awk '/cinder/ && !/awk/'")[0])


def restart_service_in_screen(name):
    #just send the up key + enter in window name of screen
    print "restarting ", name
    general.execute_command("""su -c 'screen -x stack -p {0} -X stuff "^C"' stack""".format(name))
    general.execute_command("""su -c 'screen -x stack -p {0} -X stuff "^[[A^[[A^[[A\n"' stack""".format(name))


def create_glance_image():

    existing_images = general.get_elem_with_val(get_formated_cmd_output("glance image-list"), "Name", "AUTOTEST_IMAGE")
    if existing_images:
        return existing_images[0]['ID']

    os_name = autotests.getOs()
    bootdisk_path_remote = autotests.getOsInfo(os_name)['bootdisk_location']
    template_server      = autotests.getTemplateServer()

    bootdisk_url = urlparse.urljoin(template_server, bootdisk_path_remote)
    md5_url      = urlparse.urljoin(template_server, "md5")
    disk_file    = os.path.join("/tmp", bootdisk_url.split("/")[-1])
    disk_format  = disk_file.split(".")[-1]

    download = True
    if os.path.exists(disk_file):
        remote_md5 = general.execute_command("curl -s {0} | awk '{{print $1}}'".format(md5_url))[0].strip()
        local_md5  = general.execute_command("md5sum {0} | awk '{{print $1}}'".format(disk_file))[0].strip()
        download   = remote_md5 != local_md5
        if download:
            os.remove(disk_file)

    if download:
        cmd = "cd /tmp; wget {0}".format(bootdisk_url)
        general.execute_command(cmd)

    cmd = "glance image-create --name {image_name} \
                               --container-format bare \
                               --is-public True \
                               --disk-format {disk_format} \
                               --file {disk_file}".format(image_name  = IMAGE_NAME,
                                                          disk_file   = disk_file,
                                                          disk_format = disk_format)

    image_info = get_formated_cmd_output(cmd)
    image_id = general.get_elem_with_val(image_info, "Property", "id")[0]['Value']
    return image_id


def get_formated_cmd_output(cmd, retries = 1):
    cmd = cmd + """ | awk '!/-------/ {gsub(" +",""); print}'"""
    while retries:
        retries -= 1
        try:
            out, err = general.execute_command(cmd)
            assert not err, err
        except Exception as ex:
            print str(ex)
            if not retries:
                raise
    lines = out.splitlines()
    table_head = lines[0].split("|")[1:-1]
    rows = lines[1:]
    return [dict(zip(table_head, r[1:-1].split("|"))) for r in rows]


def wait_for_status_on_item(cmd, item_id_field, item_id_value, status_field, required_status, retries = 300):
    while retries:
        items = get_formated_cmd_output(cmd)
        items = general.get_elem_with_val(items, item_id_field, item_id_value)

        if not items:
            raise Exception("Item with {0} {1} not found".format(item_id_field, item_id_value))
        if items[0].get(status_field).lower() == "error":
            raise Exception("{0} is error for {1}".format(status_field, item_id_value))

        items = general.get_elem_with_val(items, status_field, required_status)
        if items:
            return
        time.sleep(1)
        retries -= 1

    raise Exception("Item {0} did not changed its {1} to {2}".format(item_id_value, status_field, required_status))


def create_volume(image_id, cinder_type, volume_name, volume_size):

    cinder_types = get_formated_cmd_output("cinder type-list", retries = 10)
    assert general.get_elem_with_val(cinder_types, "Name", cinder_type), "Cinder type {0} not found".format(cinder_type)

    if image_id:
        glance_images = get_formated_cmd_output("glance image-list")
        assert general.get_elem_with_val(glance_images, "ID", image_id), "Glance image {0} not found".format(image_id)

    image = "--image-id {image_id}".format(image_id = image_id) if image_id else ""

    cmd = "cinder create --volume-type {cinder_type} \
                         --display-name {volume_name} \
                         {image} \
                         --availability-zone nova \
                         {volume_size} ".format(cinder_type = cinder_type,
                                                volume_name = volume_name,
                                                image       = image,
                                                volume_size = volume_size)

    volume_info = get_formated_cmd_output(cmd)
    volume_id = general.get_elem_with_val(volume_info, "Property", "id")[0]['Value']

    wait_for_status_on_item("cinder list", "ID", volume_id, "Status", "available")

    vdisk = [vd for vd in VDiskList.get_vdisks() if vd.name == volume_name]
    assert vdisk, "Cinder volume did not appear on ovs side"

    return volume_id


def create_snapshot(volume_id):

    cmd = "cinder snapshot-create {volume_id} \
                                  --display-name {display_name}".format(volume_id    = volume_id,
                                                                        display_name = "AT_snapshot" + str(time.time()))
    r = get_formated_cmd_output(cmd)
    snapshot_id = general.get_elem_with_val(r, "Property", "id")
    assert snapshot_id, "Unexpected output from cinder snapshot-create {0}".format(snapshot_id)
    snapshot_id = snapshot_id[0]["Value"]

    wait_for_status_on_item("cinder snapshot-list", "ID", snapshot_id, "Status", "available")

    return snapshot_id


def create_instance(instance_name, volume_id = "", image_id = "", snapshot_id = "", host = ""):

    assert [bool(volume_id), bool(image_id), bool(snapshot_id)].count(True) == 1, "Need to specify only one of volume_id or image_id or snapshot_id"

    if volume_id:
        volumes = get_formated_cmd_output("cinder list")
        assert general.get_elem_with_val(volumes, "ID", volume_id), "Volume with id {0} not found".format(volume_id)

    flavor_name = "m1.small"
    flavors     = get_formated_cmd_output("nova flavor-list")
    flavor      = general.get_elem_with_val(flavors, "Name", flavor_name)
    assert flavor, "Flavor with name {0} not found".format(flavor_name)
    flavor     = flavor[0]['ID']

    host_opt = host and ":" + host

    boot_volume = "--boot-volume {volume_id}".format(volume_id = volume_id)    if volume_id     else ""
    image       = "--image {image_id}".format(image_id = image_id)             if image_id      else ""
    snapshot    = "--snapshot {snapshot_id}".format(snapshot_id = snapshot_id) if snapshot_id   else ""

    cmd = "nova boot --flavor {flavor} \
                     {boot_volume} \
                     {image} \
                     {snapshot} \
                     --availability-zone nova{host} \
                     --config-drive=false \
                     {instance_name}".format(flavor        = flavor,
                                             boot_volume   = boot_volume,
                                             image         = image,
                                             snapshot      = snapshot,
                                             instance_name = instance_name,
                                             host          = host_opt).replace(" " * 4, " ")

    instance_info = get_formated_cmd_output(cmd)
    instance_id   = general.get_elem_with_val(instance_info, "Property", "id")[0]['Value']

    wait_for_status_on_item("nova list", "ID", instance_id, "Status", "ACTIVE")
    wait_for_status_on_item("nova list", "ID", instance_id, "PowerState", "Running")

    vm_host = get_instance_host(instance_id)
    assert vm_host == host, "Instance has wrong host, expected {0} got {1}".format(host, vm_host)

    vm_name = get_vm_name_hpv(instance_id)

    #check vm is registered in ovs too
    retries = 30
    while retries:
        vm = VMachineList.get_vmachine_by_name(vm_name)
        if vm:
            break
        time.sleep(1)
        retries -= 1
    assert vm, "Instance created with nova is not registered in ovs"
    vm = vm[0]
    assert len(vm.vdisks) == 1, "Vm {0} doesnt have expected disks but {1}".format(vm_name, len(vm.vdisks))

    return instance_id


def get_instance_host(instance_id):
    vm_host = general.get_elem_with_val(get_formated_cmd_output("nova show " + instance_id), "Property", "OS-EXT-SRV-ATTR:host")[0]['Value']
    return vm_host


def get_vm_name_hpv(instance_id):
    vm_name = general.get_elem_with_val(get_formated_cmd_output("nova show " + instance_id), "Property", "OS-EXT-SRV-ATTR:instance_name")[0]['Value']
    return vm_name


def get_instance_ip(instance_id):
    private_network = general.get_elem_with_val(get_formated_cmd_output("nova show " + instance_id), "Property", "privatenetwork")[0]['Value']
    return private_network


def get_vm_uptime(vm_ip):
    return int(general.execute_command_on_node(vm_ip, "uptime | awk '{print $3}'", "rooter"))


def live_migration(instance_id, new_host):
    prev_host = get_instance_host(instance_id)
    vm_ip = get_instance_ip(instance_id)

    uptime_before = get_vm_uptime(vm_ip)

    cmd = "nova live-migration {0} {1}".format(instance_id, new_host)
    general.execute_command(cmd)

    retries = 20
    while retries:
        vm_host = get_instance_host(instance_id)
        if vm_host == new_host:
            break
        time.sleep(1)
        retries -= 1
    assert retries, "Wrong host after live migration, expected {0} got {1}".format(new_host, vm_host)

    vm_name = get_vm_name_hpv(instance_id)

    out = general.execute_command_on_node(prev_host, "virsh list --all | grep {0} || true".format(vm_name))
    assert not out, "Vm should have been moved from current node after live migration\n{0}".format(out)

    out = general.execute_command_on_node(new_host, "virsh list --all | grep {0} || true".format(vm_name))
    assert out, "Vm should have been moved to new node after live migration\n{0}".format(out)

    uptime_after = get_vm_uptime(vm_ip)
    assert uptime_after >= uptime_before, "Vm did not remain up after live migration"


def delete_instance(instance_id):
    vm_name = get_vm_name_hpv(instance_id)
    general.execute_command("nova delete {0}".format(instance_id))

    #wait for vm to be gone
    retries = 50
    while retries:
        vms    = get_formated_cmd_output("nova list")
        vm     = general.get_elem_with_val(vms, "ID", instance_id)
        vm_ovs = VMachineList.get_vmachine_by_name(vm_name)

        if not (vm or vm_ovs):
            break
        time.sleep(1)
        retries -= 1

    assert not vm, "Vm is still present after deleting it from nova"
    assert not vm_ovs, "Vm still exists on OVS after deleting it from nova"


def get_vol(volume_id):
    vols    = get_formated_cmd_output("cinder list")
    vol     = general.get_elem_with_val(vols, "ID", volume_id)
    return vol


def wait_for_volume_to_disappear(volume_id, vol_name):
    vol = get_vol(volume_id)

    retries = 50
    while retries:
        vol = get_vol(volume_id)
        vd_ovs = [vd for vd in VDiskList.get_vdisks() if vd.name == vol_name]

        if not vol and not vd_ovs:
            break
        time.sleep(1)
        retries -= 1

    assert not vd_ovs, "Volume still exists on OVS after deleting it from cinder"
    assert not vol, "Volume is still present after deleting it from cinder"


def delete_volume(volume_id, wait = True):

    vol = get_vol(volume_id)
    if not vol:
        return

    vol_name = vol[0]['DisplayName']
    general.execute_command("cinder delete {0}".format(volume_id))

    if wait:
        #wait for volume to be gone
        wait_for_volume_to_disappear(volume_id, vol_name)


def cleanup():
    autotest_prefix = "AT_"
    for vm in get_formated_cmd_output("nova list"):
        if vm['Name'].startswith(autotest_prefix):
            delete_instance(vm["ID"])

    for snap in get_formated_cmd_output("cinder snapshot-list"):
        if snap['DisplayName'].startswith(autotest_prefix):
            general.execute_command("cinder snapshot-delete {0}".format(snap['ID']))

    for vol in get_formated_cmd_output("cinder list"):
        if vol['DisplayName'].startswith(autotest_prefix):
            general.execute_command("cinder delete {0}".format(vol["ID"]))

    general.execute_command("glance image-delete {0}".format(IMAGE_NAME))

