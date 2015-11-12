sudo sed -i 's|/opt/stack/cinder/cinder/|/opt/stack/new/cinder/cinder/|g' /opt/OpenvStorage/ovs/extensions/hypervisor/mgmtcenters/management/openstack_mgmt.py
sudo sed -i 's|/opt/stack/new/nova/nova/virt/libvirt/volume.py|/opt/stack/new/nova/nova/virt/libvirt/volume/volume.py|g' /opt/OpenvStorage/ovs/extensions/hypervisor/mgmtcenters/management/openstack_mgmt.py

echo "diff --git a/ovs/lib/disk.py b/ovs/lib/disk.py
index 916be39..0a4f6e0 100644
--- a/ovs/lib/disk.py
+++ b/ovs/lib/disk.py
@@ -68,7 +68,8 @@ class DiskController(object):
             with Remote(storagerouter.ip, [Context, os]) as remote:
                 context = remote.Context()
                 devices = [device for device in context.list_devices(subsystem='block')
-                           if 'ID_TYPE' in device and device['ID_TYPE'] == 'disk']
+                           if 'ID_TYPE' in device and device['ID_TYPE'] == 'disk'
+                           or (device['DEVTYPE'] in ('disk', 'partition') and device['DEVNAME'].startswith('/dev/vda'))]
                 for device in devices:
                     is_partition = device['DEVTYPE'] == 'partition'
                     device_path = device['DEVNAME']
@@ -98,9 +99,10 @@ class DiskController(object):
                     for path_type in ['by-id', 'by-uuid']:
                         if path is not None:
                             break
-                        for item in device['DEVLINKS'].split(' '):
-                            if path_type in item:
-                                path = item
+                        if 'DEVLINKS' in device:
+                            for item in device['DEVLINKS'].split(' '):
+                                if path_type in item:
+                                    path = item
                     if path is None:
                         path = device_path
                     sectors = int(client.run('cat /sys/block/{0}/size'.format(device_name)))

" | sudo tee /opt/OpenvStorage/patch_disk.diff
sudo patch /opt/OpenvStorage/ovs/lib/disk.py /opt/OpenvStorage/patch_disk.diff