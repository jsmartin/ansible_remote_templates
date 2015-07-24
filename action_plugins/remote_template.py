# (c) 2015, Ansible Inc,
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


from ansible.plugins.action import ActionBase
import tempfile
import base64
import datetime
import os
import time

from ansible import constants as C
from ansible.utils.hashing import checksum_s
from ansible.utils.unicode import to_bytes, to_unicode
import q

class ActionModule(ActionBase):

    TRANSFERS_FILES = True

    def get_checksum(self, tmp, dest, try_directory=False, source=None):
        remote_checksum = self._remote_checksum(tmp, dest)

        if remote_checksum in ('0', '2', '3', '4'):
            # Note: 1 means the file is not present which is fine; template
            # will create it.  3 means directory was specified instead of file
            if try_directory and remote_checksum == '3' and source:
                base = os.path.basename(source)
                dest = os.path.join(dest, base)
                remote_checksum = self.get_checksum(tmp, dest, try_directory=False)
                if remote_checksum not in ('0', '2', '3', '4'):
                    return remote_checksum

            result = dict(failed=True, msg="failed to checksum remote file."
                        " Checksum error code: %s" % remote_checksum)
            return result

        return remote_checksum

    def run(self, tmp=None, task_vars=dict()):
        ''' handler for package operations '''
        dest  = self._task.args.get('dest', None)
        url   = self._task.args.get('src', None)
        method = self._task.args.get('method', 'GET')
        headers = self._task.args.get('headers', dict())

        uri_params = ['method', 'headers']


        if tmp is None:
            tmp = self._make_tmp_path()

        source = tmp + '/temp.j2'

        new_module_args = self._task.args.copy()
        new_module_args.update(
                dict(
                    url=url,
                    dest=source,
                    headers=headers,
                    method=method
                ),
            )
        result = self._execute_module(module_name='uri', module_args=new_module_args, task_vars=task_vars)



        directory_prepended = False
        if dest.endswith(os.sep):
            directory_prepended = True
            base = os.path.basename(source)
            dest = os.path.join(dest, base)

        # template the source data locally & get ready to transfer
        try:
            with open(source, 'r') as f:
                template_data = to_unicode(f.read())

            try:
                template_uid = pwd.getpwuid(os.stat(source).st_uid).pw_name
            except:
                template_uid = os.stat(source).st_uid

            temp_vars = task_vars.copy()
            temp_vars['template_host']     = os.uname()[1]
            temp_vars['template_path']     = source
            temp_vars['template_mtime']    = datetime.datetime.fromtimestamp(os.path.getmtime(source))
            temp_vars['template_uid']      = template_uid
            temp_vars['template_fullpath'] = os.path.abspath(source)
            temp_vars['template_run_date'] = datetime.datetime.now()

            managed_default = C.DEFAULT_MANAGED_STR
            managed_str = managed_default.format(
                host = temp_vars['template_host'],
                uid  = temp_vars['template_uid'],
                file = to_bytes(temp_vars['template_path'])
            )
            temp_vars['ansible_managed'] = time.strftime(
                managed_str,
                time.localtime(os.path.getmtime(source))
            )

            old_vars = self._templar._available_variables
            self._templar.set_available_variables(temp_vars)
            resultant = self._templar.template(template_data, preserve_trailing_newlines=True, convert_data=False)
            self._templar.set_available_variables(old_vars)
        except Exception as e:
            return dict(failed=True, msg=type(e).__name__ + ": " + str(e))

        local_checksum = checksum_s(resultant)
        remote_checksum = self.get_checksum(tmp, dest, not directory_prepended, source=source)
        if isinstance(remote_checksum, dict):
            # Error from remote_checksum is a dict.  Valid return is a str
            return remote_checksum

        if local_checksum != remote_checksum:
            # if showing diffs, we need to get the remote value
            dest_contents = ''

            xfered = self._transfer_data(self._connection._shell.join_path(tmp, 'source'), resultant)

            # fix file permissions when the copy is done as a different user
            if self._play_context.become and self._play_context.become_user != 'root':
                self._remote_chmod('a+r', xfered, tmp)

            # run the copy module
            new_module_args = self._task.args.copy()
            for param in uri_params:
                if param in new_module_args:
                    del new_module_args[param]
            new_module_args.update(
               dict(
                   src=xfered,
                   dest=dest,
                   original_basename=os.path.basename(source),
                   follow=True,
                ),
            )

            result = self._execute_module(module_name='copy', module_args=new_module_args, task_vars=task_vars)
            if result.get('changed', False):
                result['diff'] = dict(before=dest_contents, after=resultant)
            return result

        else:
            # when running the file module based on the template data, we do
            # not want the source filename (the name of the template) to be used,
            # since this would mess up links, so we clear the src param and tell
            # the module to follow links.  When doing that, we have to set
            # original_basename to the template just in case the dest is
            # a directory.
            new_module_args = self._task.args.copy()
            for param in uri_params:
                if param in new_module_args:
                    del new_module_args[param]
            new_module_args.update(
                dict(
                    src=None,
                    original_basename=os.path.basename(source),
                    follow=True,
                ),
            )

            return self._execute_module(module_name='file', module_args=new_module_args, task_vars=task_vars)





#        return result
