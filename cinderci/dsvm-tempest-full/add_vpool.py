import sys
sys.path.append('/opt/OpenvStorage')


from subprocess import check_output
from ovs.extensions.generic.system import System
from ovs.dal.hybrids.mgmtcenter import MgmtCenter
from ovs.dal.hybrids.diskpartition import DiskPartition
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.lib.storagerouter import StorageRouterController
from ovs.extensions.hypervisor.mgmtcenters.management.openstack_mgmt import OpenStackManagement


pmachine = System.get_my_storagerouter().pmachine
mgmt_center = MgmtCenter(data={'name':'Openstack',
                               'description':'test',
                               'username':'admin',
                               'password':'rooter',
                               'ip':'127.0.0.1',
                               'port':80,
                               'type':'OPENSTACK',
                               'metadata':{'integratemgmt':True,
                                           }
                               })

IP = check_output("""ip a l dev eth0 | grep "inet " | awk '{split($0,a," "); split(a[2],b,"/"); print(b[1])}'""", shell=True).strip()
mgmt_center.save()
pmachine.mgmtcenter = mgmt_center
pmachine.save()
osm = OpenStackManagement(None)
osm.configure_host(IP)
for sr in StorageRouterList.get_storagerouters():
     for disk in sr.disks:
         for partition in disk.partitions:
            for role in [DiskPartition.ROLES.DB, DiskPartition.ROLES.SCRUB, DiskPartition.ROLES.READ, DiskPartition.ROLES.WRITE]:
                partition.roles.append(role)
            partition.save()

add_vpool_params = {'storagerouter_ip':IP,
                    'vpool_name': 'local',
                    'type':'local',
                    'readcache_size': 10,
                    'writecache_size': 10,
                    'mountpoint_bfs':'/mnt/bfs',
                    'mountpoint_temp':'/mnt/tmp',
                    'mountpoint_md':'/mnt/md',
                    'mountpoint_readcaches':['/mnt/cache1'],
                    'mountpoint_writecaches':['/mnt/cache2'],
                    'mountpoint_foc':'/mnt/cache1',
                    'storage_ip':'127.0.0.1',
                    'vrouter_port':12326,
                    'integratemgmt':True,
                    'connection_backend': {},
                    'connection_password':'',
                    'connection_username':'',
                    'connection_host':'',
                    'connection_port':12326,
                    'config_params': {'dtl_mode': 'sync',
                                      'sco_size': 4,
                                      'dedupe_mode': 'dedupe',
                                      'dtl_enabled': False,
                                      'dtl_location': '/mnt/cache1',
                                      'write_buffer': 128,
                                      'cache_strategy': 'on_read',
                                      'dtl_transport': 'tcp',
                                      }
                    }
StorageRouterController.add_vpool.apply_async(kwargs={'parameters':add_vpool_params}).get(timeout=300)