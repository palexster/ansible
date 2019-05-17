#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
module: helm
short_description: Manage a Helm deployment (and template)
description:
  - Manage the atomic host platform.
  - Rebooting of Atomic host platform should be done outside this module.
version_added: "2.8"
author:
  - Lucas Boisserie (@krsacme)
notes:
  - To just run a `helm template`, use check mode
requirements: ["helm"]
options:
  state:
    choices: ['present', 'absent']
    description: ''
    required: false
    default: present 
  binary_path:
    description:
      - The path of a terraform binary to use, relative to the 'service_path'
        unless you supply an absolute path.
    required: false
  namespace:
    description:
      - Kubernetes namespace where the chart should be installed.
    default: "default"
  name:
    description:
      - Release name to manage.
'''

EXAMPLES = '''
'''

RETURN = '''
'''

import yaml
import tempfile

from ansible.module_utils.basic import AnsibleModule

module = None


# get helm Version
def get_client_version(command):
    version_command = command + " version --client --template '{{ .Client.SemVer }}'"

    rc, out, err = module.run_command(version_command)

    if rc != 0:
        module.fail_json(
            msg="Failure when executing Helm command. Exited {0}.\nstdout: {1}\nstderr: {2}".format(rc, out, err),
            command=' '.join(version_command)
        )

    return out


# Get Values from deployed release
def get_values(command, release_name):
    get_command = command + " get values --output=yaml " + release_name
    rc, out, err = module.run_command(get_command)

    if rc != 0:
        module.fail_json(
            msg="Failure when executing Helm command. Exited {0}.\nstdout: {1}\nstderr: {2}".format(rc, out, err),
            command=' '.join(get_command)
        )

    return yaml.safe_load(out)


# Get Release from all deployed releases
def get_release(status, release_name):
    for release in status['Releases']:
        if release['Name'] == release_name:
            return release
    return None


# Get Release status from deployed release
def status(command, release_name):
    list_command = command + " list --output=yaml"
    rc, out, err = module.run_command(list_command)

    if rc != 0:
        module.fail_json(
            msg="Failure when executing Helm command. Exited {0}.\nstdout: {1}\nstderr: {2}".format(rc, out, err),
            command=' '.join(list_command)
        )

    release = get_release(yaml.safe_load(out), release_name)

    if release is None: # not install
        return None

    release['Values'] = get_values(command, release_name)

    return release


# Install/upgrade release chart
def deploy(command,
           release_namespace, release_name, release_value,
           chart_name, chart_version,
           repo_url, repo_username, repo_password):
    deploy_command = command + " upgrade -i "     # install/upgrade

    if chart_version is not None:
        deploy_command.append(" --version=" + chart_version)

    if repo_url is not None:
        deploy_command.append(" --repo=" + repo_url)
        if repo_username is not None and repo_password is not None:
            deploy_command.append(" --username=" + repo_username)
            deploy_command.append(" --password=" + repo_password)

    if release_value is not None:
        f, path = tempfile.mkstemp(suffix='.yml')
        yaml.dump(release_value, f)
        deploy_command.append(" -f=" + path)

    deploy_command.append(" --namespace=" + release_namespace + " " + release_name)
    deploy_command.append(" " + release_name)
    deploy_command.append(" " + chart_name)

    rc, out, err = module.run_command(deploy_command)

    if rc != 0:
        module.fail_json(
            msg="Failure when executing Helm command. Exited {0}.\nstdout: {1}\nstderr: {2}".format(rc, out, err),
            command=' '.join(deploy_command)
        )

    return out


# Delete release chart
def delete(command, release_name, purge=True):
    delete_command = command + " delete"

    if purge:
        delete_command.append(" --purge")

    delete_command.append(" " + release_name)

    rc, out, err = module.run_command(delete_command)

    if rc == 1 and "Error: release: {0} not found".format(release_name) in err:
        changed = False
    elif rc != 0:
        module.fail_json(
            msg="Failure when executing Helm command. Exited {0}.\nstdout: {1}\nstderr: {2}".format(rc, out, err),
            command=' '.join(delete_command)
        )
    else:
        changed = True

    return changed, out


def main():
    global module
    module = AnsibleModule(
        argument_spec=dict(
            binary_path=dict(type='path'),
            chart_name=dict(type='str', required=True),
            chart_version=dict(type='str'),
            release_name=dict(type='str', required=True, aliases=['name']),
            release_namespace=dict(type='str', default='default', aliases=['namespace']),
            release_state=dict(default='present', choices=['present', 'absent'], aliases=['state']),
            release_values=dict(type='dict', default={}, aliases=['values']),
            repo_url=dict(type='str', required=True),
            repo_username=dict(type='str'),
            repo_password=dict(type='str'),
            tiller_host=dict(type='str'),
            tiller_namespace=dict(type='str', default='default'),
        ),
    )

    bin_path          = module.params.get('binary_path')
    chart_name        = module.params.get('chart_name')
    chart_version     = module.params.get('chart_version')
    release_name      = module.params.get('release_name')
    release_namespace = module.params.get('release_namespace')
    release_state     = module.params.get('release_state')
    release_values    = module.params.get('release_values')
    repo_url          =  module.params.get('repo_url')
    repo_username     =  module.params.get('repo_username')
    repo_password     =  module.params.get('repo_password')
    tiller_namespace  = module.params.get('tiller_namespace')
    tiller_host       = module.params.get('tiller_host')

    if bin_path is not None:
        command = [bin_path]
    else:
        command = [module.get_bin_path('helm', required=True)]

    helm_version = get_client_version(command)
    if helm_version.startswith("v2."):
        if tiller_host is not None:
            command.append(" --tiller-namespace=" + tiller_namespace)
        else:
            command.append(" --host=" + tiller_namespace)

    release_status = status(command, release_name)

    if release_state == "present":
        if release_status is None:  # Not installed
            out, err = deploy(command, release_namespace, release_name, release_values, chart_name, chart_version,
                              repo_url, repo_username, repo_password)
            changed = True
        elif release_namespace != release_status['Namespace']:
            module.fail_json(
                msg="Target Namespace can't be changed on deployed chart ! Need to destroy and recreate it"
            )
        elif release_values != release_status['Values'] \
                and (chart_name + '-' + chart_version) != release_status["Chart"]:
            out, err = deploy(command, release_namespace, release_name, release_values, chart_name, chart_version,
                              repo_url, repo_username, repo_password)
            changed = True
        else:
            changed = False
    else:  # release_state == "absent":
        changed = delete(command, release_name)

    module.exit_json(changed=changed, stdout=out, stderr=err,)


if __name__ == '__main__':
    main()