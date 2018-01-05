from ci.scenario_helpers.ci_constants import CIConstants
from ci.api_lib.helpers.system import SystemHelper


class SetupHelper(CIConstants):

    def setup_cloud_info(self, client, src_std):
        cloud_init_loc = self.CLOUD_INIT_DATA.get('script_dest')
        client.run(['wget', self.CLOUD_INIT_DATA.get('script_loc'), '-O', cloud_init_loc])
        client.file_chmod(cloud_init_loc, 755)
        assert client.file_exists(cloud_init_loc), 'Could not fetch the cloud init script'
        is_ee = SystemHelper.get_ovs_version(src_std.storagerouter) == 'ee'
        return cloud_init_loc, is_ee
