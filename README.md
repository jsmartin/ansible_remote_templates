#Fetching remote templates

Sometimes application developers like to store their jinja2 templates for their application's configuration along with the application source code itself.  This makes a lot of sense because application configs often change regularly with the application.  This could prove difficult to manage by having to then move that application's jinja2-templated config file to an Ansible repository.  This proves even more difficult when multiple machines may be running different versions of the same application, and all need different versions of the configuration file.


#Solutions?

The Ansible template module doesn't know how to read remote sources, so I've built two options.

`render_a.yml` uses a number of tasks to:

1. create some temporary directories
2. uses the uri module to download the file to a temporary file.
3. renders the template from the temporary, and removes the temporary directory.

`render_b.yml` uses a modified template module (technically an action plugin), called remote_template.  Behind the scences, it calls the uri module to download the template and renders it.  This is a lot cleaner, less tasks, and is much faster.  It's using a slightly modified uri module to make it behave properly with sending custom headers.  The updated uri module is currently [submitted as a PR](https://github.com/ansible/ansible-modules-core/pull/1789).


Both solutions demonstrate the ability to fetch a single template from a public and non-public git hub repo.  


playbooks can be run as so (assuming you have access to the private repo in the playbook, if not substitute your own):

```
ansible-playbook -i hosts render_a.yml  -e 'github_access_token=mygithubaccesstoken'
ansible-playbook -i hosts render_b.yml  -e 'github_access_token=mygithubaccesstoken'
```