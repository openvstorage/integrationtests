# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# cd /opt/OpenvStorage/webapps/api/backend/views
# grep -Rn -A4 expose * | grep def
#
# branding.py-34-    def list(self, request, format=None, hints=None):
# branding.py-44-    def retrieve(self, request, obj):
#
# generic.py-36-    def list(self, request, format=None):
# generic.py-44-    def retrieve(self, request, pk=None, format=None):
#
# messaging.py-38-    def list(self, request, format=None):
# messaging.py-47-    def retrieve(self, request, pk=None, format=None):
# messaging.py-78-    def wait(self, request, pk=None, format=None):
# messaging.py-98-    def last(self, request, pk=None, format=None):
# messaging.py-113-    def subscribe(self, request, pk=None, format=None):
#
# mgmtcenters.py-45-    def list(self, request, format=None, hints=None):
# mgmtcenters.py-56-    def retrieve(self, request, obj):
# mgmtcenters.py-66-    def destroy(self, request, obj):
# mgmtcenters.py-76-    def create(self, request, format=None):
#
# pmachines.py-40-    def list(self, request, format=None, hints=None):
# pmachines.py-51-    def retrieve(self, request, obj):
# pmachines.py-61-    def partial_update(self, request, obj):
#
# statistics.py-93-    def list(self, request, format=None):
# statistics.py-115-    def retrieve(self, request, pk=None, format=None):
#
# storagedrivers.py-40-    def list(self, request, format=None, hints=None):
# storagedrivers.py-51-    def retrieve(self, request, obj):
# storagedrivers.py-61-    def can_be_deleted(self, request, obj):
#
# storagerouters.py-44-    def list(self, request, hints):
# storagerouters.py-55-    def retrieve(self, request, obj):
# storagerouters.py-65-    def filter(self, request, pk=None, format=None, hints=None):
# storagerouters.py-80-    def move_away(self, request, obj):
# storagerouters.py-91-    def get_available_actions(self, request, obj):
# storagerouters.py-107-    def get_metadata(self, request, obj):
# storagerouters.py-123-    def get_version_info(self, request, obj):
# storagerouters.py-137-    def check_s3(self, request, obj):
# storagerouters.py-157-    def check_mtpt(self, request, obj):
# storagerouters.py-178-    def add_vpool(self, request, obj):
#
# tasks.py-38-    def list(self, request, format=None):
# tasks.py-52-    def retrieve(self, request, pk=None, format=None):
# tasks.py-75-    def get(self, request, pk=None, format=None):
#
# users.py-56-    def list(self, request, format=None, hints=None):
# users.py-67-    def retrieve(self, request, obj):
# users.py-81-    def create(self, request, format=None):
# users.py-95-    def destroy(self, request, pk=None, format=None):
# users.py-111-    def set_password(self, request, obj):
#
# vdisks.py-42-    def list(self, request, format=None, hints=None):
# vdisks.py-61-    def retrieve(self, request, obj):
# vdisks.py-73-    def rollback(self, request, obj):
#
# vmachines.py-46-    def list(self, request, hints):
# vmachines.py-69-    def retrieve(self, request, obj):
# vmachines.py-81-    def destroy(self, request, obj):
# vmachines.py-95-    def rollback(self, request, obj):
# vmachines.py-109-    def snapshot(self, request, obj):
# vmachines.py-127-    def get_children(self, request, obj, hints):
# vmachines.py-148-    def filter(self, request, pk=None, format=None, hints=None):
# vmachines.py-163-    def set_as_template(self, request, obj):
# vmachines.py-175-    def create_from_template(self, request, obj):
# vmachines.py-195-    def create_multiple_from_template(self, request, obj):
# vmachines.py-227-    def get_target_pmachines(self, request, obj, hints):
#
# vpools.py-42-    def list(self, request, format=None, hints=None):
# vpools.py-53-    def retrieve(self, request, obj):
# vpools.py-65-    def sync_vmachines(self, request, obj):
# vpools.py-77-    def storagerouters(self, request, obj, hints):
# vpools.py-95-    def update_storagedrivers(self, request, obj):
