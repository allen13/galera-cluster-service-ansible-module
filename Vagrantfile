Vagrant.configure("2") do |config|
  config.vm.synced_folder '.', '/vagrant', disabled: true
  config.ssh.password = 'vagrant'

  create_vm(config, name:"galera", id: 1)
  create_vm(config, name: "galera", id: 2)
end

def create_vm(config, options = {})
  name = options.fetch(:name, "node")
  id = options.fetch(:id, 1)
  vm_name = "%s-%02d" % [name, id]

  memory = options.fetch(:memory, 1024)
  cpus = options.fetch(:cpus, 1)

  config.vm.define vm_name do |config|
    config.vm.box = "chef/centos-7.0"
    config.vm.hostname = vm_name

    management_ip = "192.168.1.10#{id}"

    config.vm.network :private_network, ip: management_ip, netmask: "255.255.255.0"

    config.vm.provider :virtualbox do |vb|
      vb.memory = memory
      vb.cpus = cpus
    end
  end
end
