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

from fluo_deploy.util import get_arch, parse_args, get_ami

def test_util():
  assert get_arch('m1.large') == 'pvm'
  assert get_arch('m3.large') == 'hvm'
  
  assert get_ami('m3.large', 'us-east-1') == 'ami-61bbf104'
  assert get_ami('m1.large', 'us-east-1') == None

  hosts_dir = '../../conf/hosts'
  assert parse_args(hosts_dir, ['launch']) == None
  assert parse_args(hosts_dir, ['launch', 'mycluster']) == None
  assert parse_args(hosts_dir, ['-c', 'mycluster', 'launch']) != None

  hosts_dir = '../../conf/hosts/example'
  assert parse_args(hosts_dir, ['setup']) != None
  assert parse_args(hosts_dir, ['config']) == None
  assert parse_args(hosts_dir, ['-p', 'all', 'config']) != None
