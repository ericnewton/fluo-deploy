# Copyright 2014 Fluo authors (see AUTHORS)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ConfigParser import ConfigParser
from util import get_num_ephemeral, exit, get_arch, get_ami
import os
from os.path import join

SERVICES = ['zookeeper', 'namenode', 'resourcemanager', 'accumulomaster', 'worker', 'fluo', 'metrics']

class DeployConfig(ConfigParser):

  def __init__(self, deploy_path, config_path, hosts_path, cluster_name):
    ConfigParser.__init__(self)
    self.deploy_path = deploy_path
    self.read(config_path)
    self.hosts_path = hosts_path
    self.cluster_name = cluster_name
    self.ephemeral_root = 'ephemeral'
    self.mount_root = '/media/' + self.ephemeral_root
    self.device_root = '/dev/xvd'
    self.metrics_drive_root = 'media-' + self.ephemeral_root
    self.node_d = None
    self.hosts = None
    self.init_nodes()

  def verify_config(self, action):
    proxy = self.get('general', 'proxy_hostname')
    if not proxy:
      exit("ERROR - proxy.hostname must be set in fluo-deploy.props")

    if proxy not in self.node_d:
      exit("ERROR - The proxy (set by property proxy.hostname={0}) cannot be found in 'nodes' section of fluo-deploy.props".format(proxy))

    if action != 'launch':
      self.proxy_public_ip()

    if action in ['launch', 'setup']:
      self.get_image_id(self.get('ec2', 'default_instance_type'))
      self.get_image_id(self.get('ec2', 'worker_instance_type'))

      for service in SERVICES:
        if service not in ['fluo', 'metrics']:
          if not self.has_service(service):
            exit("ERROR - Missing '{0}' service from [nodes] section of fluo-deploy.props".format(service))

  def init_nodes(self):
    self.node_d = {}
    for (hostname, value) in self.items('nodes'):
      if hostname in self.node_d:
        exit('Hostname {0} already exists twice in nodes'.format(hostname))
      service_list = []
      for service in value.split(','):
        if service in SERVICES:
          service_list.append(service)
        else:
          exit('Unknown service "%s" declared for node %s' % (service, hostname))
      self.node_d[hostname] = service_list

  def default_num_ephemeral(self):
    return get_num_ephemeral(self.get('ec2', 'default_instance_type'))

  def worker_num_ephemeral(self):
    return get_num_ephemeral(self.get('ec2', 'worker_instance_type'))

  def max_ephemeral(self):
    return max((self.worker_num_ephemeral(), self.default_num_ephemeral()))

  def node_type_map(self):
    node_types = {}
    node_list = [('default', self.default_num_ephemeral()), ('worker', self.worker_num_ephemeral())]
    for (ntype, num_ephemeral) in node_list:
      node_types[ntype] = {'mounts': self.mounts(num_ephemeral), 'devices': self.devices(num_ephemeral)}
    return node_types

  def node_type(self, hostname):
    if 'worker' in self.node_d[hostname]:
      return 'worker'
    return 'default'

  def num_ephemeral(self, hostname):
    if 'worker' in self.node_d[hostname]:
      return self.worker_num_ephemeral()
    else:
      return self.default_num_ephemeral()

  def mounts(self, num_ephemeral):
    mounts = []
    for i in range(0, num_ephemeral):
      mounts.append(self.mount_root + str(i))
    return tuple(mounts)

  def devices(self, num_ephemeral):
    devices = []
    for i in range(0, num_ephemeral):
      devices.append(self.device_root + chr(ord('b') + i))
    return tuple(devices)

  def metrics_drive_ids(self):
    drive_ids = []
    for i in range(0, self.max_ephemeral()):
      drive_ids.append(self.metrics_drive_root + str(i))
    return tuple(drive_ids)

  def version(self, software_id):
    return self.get('general', software_id + '_version')

  def sha256(self, software_id):
    return self.get('general', software_id + '_sha256')

  def get_image_id(self, instance_type):
    if get_arch(instance_type) == 'pvm':
      exit("ERROR - Configuration contains instance type '{0}' that uses pvm architecture.  Only hvm architecture is supported!".format(instance_type))
    return get_ami(instance_type, self.get('ec2', 'region'))

  def instance_tags(self):
    retd = {}
    if self.has_option('ec2', 'instance.tags'):
      value = self.get('ec2', 'instance.tags')
      if value:
        for kv in value.split(','):
          (key, val) = kv.split(':')
          retd[key] = val
    return retd

  def nodes(self):
    return self.node_d

  def get_node(self, hostname):
    return self.node_d[hostname]

  def has_service(self, service):
    for (hostname, service_list) in self.node_d.items():
      if service in service_list:
        return True
    return False

  def get_host_services(self):
    retval = []
    for (hostname, service_list) in self.node_d.items():
      retval.append((hostname, ' '.join(service_list)))
    retval.sort()
    return retval

  def get_service_private_ips(self, service):
    retval = []
    for (hostname, service_list) in self.node_d.items():
      if service in service_list:
        retval.append(self.get_private_ip(hostname))
    retval.sort()
    return retval

  def get_service_hostnames(self, service):
    retval = []
    for (hostname, service_list) in self.node_d.items():
      if service in service_list:
        retval.append(hostname)
    retval.sort()
    return retval

  def get_non_proxy(self):
    retval = []
    proxy_ip = self.get_private_ip(self.get('general', 'proxy_hostname'))
    for (hostname, (private_ip, public_ip)) in self.hosts.items():
      if private_ip != proxy_ip:
        retval.append((private_ip, hostname))
    retval.sort()
    return retval

  def get_private_ip_hostnames(self):
    retval = []
    for (hostname, (private_ip, public_ip)) in self.hosts.items():
      retval.append((private_ip, hostname))
    retval.sort()
    return retval

  def parse_hosts(self):
    if not os.path.isfile(self.hosts_path):
      exit('ERROR - A hosts file does not exist at %s' % self.hosts_path)  

    self.hosts = {} 
    with open(self.hosts_path) as f:
      for line in f:
        line = line.strip()
        if line.startswith("#") or not line:
          continue
        args = line.split(' ')
        if len(args) == 2:
          self.hosts[args[0]] = (args[1], None)
        elif len(args) == 3:
          self.hosts[args[0]] = (args[1], args[2])
        else:
          exit('ERROR - Bad line %s in hosts %s' % (line, self.hosts_path))
        
  def get_hosts(self):
    if self.hosts is None:
      self.parse_hosts()
    return self.hosts

  def get_private_ip(self, hostname):
    return self.get_hosts()[hostname][0]

  def get_public_ip(self, hostname):
    return self.get_hosts()[hostname][1]

  def proxy_public_ip(self):
    retval = self.get_public_ip(self.get('general', 'proxy_hostname'))
    if not retval:
      exit("ERROR - Leader {0} does not have a public IP".format(self.get('general', 'proxy_hostname')))
    return retval

  def proxy_private_ip(self):
    return self.get_private_ip(self.get('general', 'proxy_hostname'))

  def get_performance_prop(self, prop):
    profile = self.get('performance', 'profile')
    return self.get(profile, prop)

  def print_all(self):
    print 'proxy_public_ip = ', self.proxy_public_ip()
    for (name, val) in self.items('general'):
      print name, '=', val

    for (name, val) in self.items('ec2'):
      print name, '=', val

  def print_property(self, key):
    if key == 'proxy.public.ip':
      print self.proxy_public_ip()
      return
    else:
      for section in self.sections():
        if self.has_option(section, key):
          print self.get(section, key)
          return

    exit("Property '{0}' was not found".format(key))
