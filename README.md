# cloud-emulator
Android emulator instances, running on remote cloud server

# Manual step-by-step deployment on production server
- Transfer docker-compose.yaml and .env to the production server
- Modify .env and set proper values for all env variables in this file
- Check if the system is running already by 'docker-compose -p titan-cloud-emulator ps' and stop it by 'docker-compose -p titan-cloud-emulator stop'
- Issue in the terminal "docker-compose pull && docker-compose -p titan-cloud-emulator up -d"
- For slave node deployment, transfer docker-compose-slave.yaml to the server and issue "docker-compose pull && docker-compose -f docker-compose-slave.yaml -p titan-cloud-emulator up -d"
- For pre-int deployment, set ENV_BUILD_TYPE=pre-int in .env prior doing previous step

# Automated deployment on production server
- to do once per deployment machine:
    - copy your ssh key to target machine: "ssh-copy-id $USER@hostname"
    - go to target machine via ssh and login yourself on remote docker registry: "docker login -u $USER artifactory-mb.harman.com:5036" and type your password in the prompt
- set the env variable SVC_TITANEMU_PASS to proper value (this is a password and should be kept in secret) for current terminal by issuing "export SVC_TITANEMU_PASS=value"
- issue in the terminal "./autodeploy.sh hostname", where hostname is domain name of deployment machine, for ex. "./autodeploy.sh inmdlx427as001"
- to autodeploy the cluster (master and several slaves): ./autodeploy.sh master-hostname slave-hostname-1 slave-hostname-2 ...
- to autodeploy pre-int build: ENV_BUILD_TYPE=pre-int ./autodeploy.sh hostname

# Building mainline and/or pre-int version and pushing to the registry
- note that pushing will override existing latest images in the registry
- mainline build: docker-compose -f docker-compose-build.yaml build && docker-compose push
- pre-int build: ENV_BUILD_TYPE=pre-int docker-compose -f docker-compose-build.yaml build && ENV_BUILD_TYPE=pre-int docker-compose push

# Development on local workstation
The system consists of four docker images and is launched with docker-compose.yaml file.
There is development variant of docker-compose file: docker-compose-dev.yaml
The command "docker-compose -f docker-compose-dev.yaml up --build" will rebuild modified images from source code and then will launch the containers locally.
List of image and which of them are rebuild:
	- Envoy proxy, build from Dockerfile.envoy, name: artifactory-mb.harman.com:5036/test/titan-emulator-envoy:latest
	- Nginx, downloaded from the Artifactory and is build separately from the repo https://androidhub.harman.com/admin/repos/android-emulator-container-scripts, name: artifactory-mb.harman.com:5036/test/titan-emulator-nginx:latest
	- Backend, build from Dockerfile.backend, name: artifactory-mb.harman.com:5036/test/titan-emulator-backend:latest
	- Usbip, build from Dockerfile.usbip, name: artifactory-mb.harman.com:5036/test/titan-emulator-backend-usbip-5.4.0-77-generic (TODO: to make it buildable from docker-compose)

# Development testing on external machine
Once the development is completed, modified images can be pushed to the docker registry and then used for development testing on some external machine.
- tag the image with unique tag and push the image into docker registry with the command "docker push your_image_name"
- transfer docker-compose.yaml and .env to the testing machine and use "docker-compose pull && docker-compose up" to bring the services up

# Environment variables
System wide environment variables:
- ENV_BUILD_TYPE - build type used for deployment: mainline, pre-int, release
- ENV_HOSTNAME - hostname of the machine where the system is to be running
- ENV_EXT_IP - ip address of the machine where the system is to be running
- ENV_REMOTE_REGISTRY_USER - username of an account with access to docker registry with android images
- ENV_REMOTE_REGISTRY_PASS - password of the account above
- ENV_POOL_NODES - list of slave nodes in the pool separated by comma, ex: ENV_POOL_NODES=http://backend-slave:8080,http://10.10.10.10:8080

Backend container environment variables:
- FLASK_APP - the role of the node, possible values: backend, node.slave
- TURN_EXTERNAL_IP - ip address of the machine where the TURN server is being launched (should be equal to ENV_EXT_IP for now). The TURN server is required in cloud setup, it makes it possible establish WebRTC connections from a web client towards the emulator.
- HOSTNAME - hostname of the machine where the backend is to be running (should be equal to ENV_EXT_IP for now)
- DOCKER_REGISTRY - url of remote docker registry
- DEBUG=1 - to see more traces from the backend
- LDAP_SERVER - url of custom ldap server, default is ldaps://ldapmd.ad.harman.com:3269
- AUTH_TEST_CREDS=test@test.com,admin@test.com' - to define user accounts for testing purposes (separated by comma if several), it is accepted with any password skipping ldap authentication, usernames with 'admin' word within are treated as test users in admin group
- ADMIN_GROUP_NAME - the name of the backend admins group on ldap server
- USBIP_RPC_URL - url of usbip RPC server
- USER_GROUP_NAME='examplegroup1,examplegroup2' - comma seprated list of groups allowed to login enclosed in single quotes.

# Other helpful info
## How build upbip part of backend:
Identify kernel version on target machine with 'uname -r', for ex. 5.4.0-77-generic
Refer to https://packages.ubuntu.com/focal/linux-tools-generic and indentify ubuntu version which provides the package linux-tools-generic for your kernel version, in our ex. it is 'focal'.
Build the image with:
> docker build -f Dockerfile.usbip --build-arg KERNEL_VERSION=<kernel_version> --build-arg REPO_NAME=<repo_name> -t titan-backend-usbip-<kernel_version> .
For our example:
> docker build -f Dockerfile.usbip --build-arg KERNEL_VERSION=5.4.0-77-generic --build-arg REPO_NAME=focal -t titan-backend-usbip-5.4.0-77-generic .

## How to launch backend without building the container
### usbip service
> pep8 . && sudo LOGLEVEL=DEBUG python3 -m usbip_client
### backend service
> pep8 . && AUTH_TEST_CREDS=test@test.com,user@test.com,admin@test.com ADMIN_GROUP_NAME=TITAN_EMULATOR_Admins USBIP_RPC_URL=http://192.168.0.4:8888 DEBUG=1 DOCKER_REGISTRY=localhost:5000 EXTERNAL_IP=192.168.0.4 FLASK_ENV=development FLASK_APP=backend python3 -m flask run --host 0.0.0.0 --port 8080

## How to launch coturn from command line:
> docker run -d --rm --name coturn --network=host instrumentisto/coturn --lt-cred-mech --user=emulator:titan --external-ip=10.92.6.107 --realm=titan.emulator.harman.realm.org

## Help on binding/attaching remote devices (Linux only)
###Server side
sudo apt install linux-tools-`uname -r` linux-cloud-tools-`uname -r`
sudo insmod /lib/modules/`uname -r`/kernel/drivers/usb/usbip/usbip-core.ko
sudo insmod /lib/modules/`uname -r`/kernel/drivers/usb/usbip/usbip-host.ko
sudo usbip list -l
sudo usbip bind -b <busid>
sudo usbipd -D

###Client side
sudo apt install linux-tools-`uname -r` linux-cloud-tools-`uname -r`
sudo insmod /lib/modules/`uname -r`/kernel/drivers/usb/usbip/usbip-core.ko
sudo insmod /lib/modules/`uname -r`/kernel/drivers/usb/usbip/vhci-hcd.ko
sudo usbip list -r <server_ip>
sudo usbip attach -r <server_ip> -b <busid>
sudo usbip port

