##### Start and join galera service with a given server group

    galera_cluster_service: state=started cluster_group=openstack
    
##### Notes
This is a work in progress. Not usable at all right now!

Building this may require using the dual module/action_module [trick]( http://ndemengel.github.io/2015/01/20/ansible-modules-and-action-plugins/) because of the need to access the inventory_hostname and groups vars. I could pass these in directly but it doesn't seem elegant. It would look like this without the trick.

    galera_cluster_service: state=started cluster_group={{ groups["openstack"] }} inventory_hostname={{ inventory_hostname }}
