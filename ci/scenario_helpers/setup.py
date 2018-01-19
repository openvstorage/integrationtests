import random
from ci.scenario_helpers.ci_constants import CIConstants
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.helpers.vpool import VPoolHelper

from helpers.domain import DomainHelper
from helpers.storagedriver import StoragedriverHelper
from helpers.storagerouter import StoragerouterHelper
from ovs.extensions.generic.logger import Logger


class SetupHelper(CIConstants):
    LOGGER = Logger('scenario_helpers-setup_helper')

    @classmethod
    def setup_cloud_info(cls, client, src_std):
        """
        Retrieve the cloud init file
        :param client: SSHclient to use for cloud initialization
        :type client: ovs.extensions.generic.SSHClient
        :param src_std: storagedriver to check which edition is running
        :type src_std: ovs.dal.hybrids.StorageDriver
        :return:
        """
        cloud_init_loc = cls.CLOUD_INIT_DATA.get('script_dest')
        client.run(['wget', cls.CLOUD_INIT_DATA.get('script_loc'), '-O', cloud_init_loc])
        client.file_chmod(cloud_init_loc, 755)
        assert client.file_exists(cloud_init_loc), 'Could not fetch the cloud init script'
        is_ee = SystemHelper.get_ovs_version(src_std.storagerouter) == 'ee'
        return cloud_init_loc, is_ee

    @classmethod
    def get_vpool_with_2_storagedrivers(cls):
        """
        Check for all vpools if there is at least one containing two storagedrivers
        :return: ovs.dal.hybrids.vpool
        """
        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 2 and vp.configuration['dtl_mode'] == 'sync':
                vpool = vp
                return vpool
        assert vpool is not None, 'We need at least one vpool with two storagedrivers'

    @classmethod
    def check_images(cls, client):
        """
        Check if enough images are available on the provided node
        :param client: SSHclient to check for images
        :type client: ovs.extensions.generic.SSHClient
        :return: str
        """
        images = cls.get_images()
        assert len(images) >= 1, 'We require an cloud init bootable image file.'
        image_path = images[0]
        assert client.file_exists(image_path), 'Image `{0}` does not exists on `{1}`!'.format(images[0], client.ip)
        return image_path

    @classmethod
    def get_fio_bin_path(cls, client, is_ee):
        """
        Returns the location of the fio binary
        :param client: sshclient to connect with
        :param is_ee: boolean whether the install is ee edition or not
        :return:
        """
        if is_ee is True:
            fio_bin_loc = cls.FIO_BIN_EE['location']
            fio_bin_url = cls.FIO_BIN_EE['url']
        else:
            fio_bin_loc = cls.FIO_BIN['location']
            fio_bin_url = cls.FIO_BIN['url']
        # Get the fio binary
        client.run(['wget', fio_bin_url, '-O', fio_bin_loc])
        client.file_chmod(fio_bin_loc, 755)
        assert client.file_exists(fio_bin_loc), 'Could not get the latest fio binary.'
        return fio_bin_loc

    @classmethod
    def setup_env(cls, domainbased=False):
        """
        Return a dict containing instances of storagedrivers and storagerouters
        :param domainbased:
        :return: dict
        """
        vpool = None
        if domainbased:
            destination_str, source_str, compute_str = StoragerouterHelper().get_storagerouters_by_role()
            destination_storagedriver = None
            source_storagedriver = None
            if len(source_str.regular_domains) == 0:
                storagedrivers = StoragedriverHelper.get_storagedrivers()
            else:
                storagedrivers = DomainHelper.get_storagedrivers_in_same_domain(domain_guid=source_str.regular_domains[0])
            for storagedriver in storagedrivers:
                if len(storagedriver.vpool.storagedrivers) < 2:
                    continue
                if storagedriver.guid in destination_str.storagedrivers_guids:
                    if destination_storagedriver is None and (source_storagedriver is None or source_storagedriver.vpool_guid == storagedriver.vpool_guid):
                        destination_storagedriver = storagedriver
                        cls.LOGGER.info('Chosen destination storagedriver is: {0}'.format(destination_storagedriver.storage_ip))
                elif storagedriver.guid in source_str.storagedrivers_guids:
                    # Select if the source driver isn't select and destination is also unknown or the storagedriver has matches with the same vpool
                    if source_storagedriver is None and (destination_storagedriver is None or destination_storagedriver.vpool_guid == storagedriver.vpool_guid):
                        source_storagedriver = storagedriver
                        cls.LOGGER.info('Chosen source storagedriver is: {0}'.format(source_storagedriver.storage_ip))
            assert source_storagedriver is not None and destination_storagedriver is not None, 'We require at least two storagedrivers within the same domain.'

        else:
            vpool = SetupHelper.get_vpool_with_2_storagedrivers()

            available_storagedrivers = [storagedriver for storagedriver in vpool.storagedrivers]
            destination_storagedriver = available_storagedrivers.pop(random.randrange(len(available_storagedrivers)))
            source_storagedriver = available_storagedrivers.pop(random.randrange(len(available_storagedrivers)))
            destination_str = destination_storagedriver.storagerouter  # Will act as volumedriver node
            source_str = source_storagedriver.storagerouter  # Will act as volumedriver node
            compute_str = [storagerouter for storagerouter in StoragerouterHelper.get_storagerouters() if
                           storagerouter.guid not in [destination_str.guid, source_str.guid]][0]  # Will act as compute node

            # Choose source & destination storage driver
            destination_storagedriver = [storagedriver for storagedriver in destination_str.storagedrivers if storagedriver.vpool_guid == vpool.guid][0]
            source_storagedriver = [storagedriver for storagedriver in source_str.storagedrivers if storagedriver.vpool_guid == vpool.guid][0]
            cls.LOGGER.info('Chosen destination storagedriver is: {0}'.format(destination_storagedriver.storage_ip))
            cls.LOGGER.info('Chosen source storagedriver is: {0}'.format(source_storagedriver.storage_ip))

        cluster_info = {'storagerouters': {'destination': destination_str,
                                           'source': source_str,
                                           'compute': compute_str},
                        'storagedrivers': {'destination': destination_storagedriver,
                                           'source': source_storagedriver},
                        'vpool': vpool}

        return cluster_info
