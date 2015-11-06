sudo mkdir -p /home/jenkins/.ssh
sudo chown -R jenkins:jenkins /home/jenkins
sudo chmod 400 /home/jenkins/.ssh/*
sudo chown -R jenkins:jenkins /var/log
ssh ovs-ci@172.19.7.191 "find /data/www/ci_logs -type d -ctime +14 -exec rm -rf {} \;"
ssh ovs-ci@172.19.7.191 "mkdir -p /data/www/ci_logs/$LOG_PATH"
sudo find /var/log -iname "*.log" -execdir gzip -9 {} \+
sudo find /var/log -type f -print0 | xargs -0 sudo chmod 644
sudo find /var/log -type d -print0 | xargs -0 sudo chmod 777
scp -r /opt/stack/logs/* ovs-ci@172.19.7.191:/data/www/ci_logs/$LOG_PATH
scp -r /var/log/* ovs-ci@172.19.7.191:/data/www/ci_logs/$LOG_PATH

echo "Triggered by: https://review.openstack.org/$ZUUL_CHANGE patchset $ZUUL_PATCHSET"
echo "Detailed logs: http://packages.cloudfounders.com/ci_logs/$LOG_PATH/"
