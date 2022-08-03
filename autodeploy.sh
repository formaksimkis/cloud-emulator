# This script is to provide ability to deploy latest images of Cloud Emulator
# available on Artifactory in automated way on an arbirary machine from another
# machine. The primary user of the script is Jenkins job but also can be used
# for deploying from any developer machine.
#!/bin/bash

[[ $# -gt 0 && $1 != -* ]] || {
    echo "Usage: $0 [master-node-hostname] <slave-node-hostname | slave-node-hostname | ...>";
    echo "Make sure the env var SVC_TITANEMU_PASS is set prior running.";
    exit 1; }

NODES=($@)
SLAVES=(${NODES[@]:1})
POOL_NODES=""

for SLAVE in "${!SLAVES[@]}"
do
    [[ $SLAVE -eq 0 ]] && { POOL_NODES="http://${SLAVES[$SLAVE]}:8080"; }
    [[ $SLAVE -eq 0 ]] || { POOL_NODES="$POOL_NODES,http://${SLAVES[$SLAVE]}:8080"; }
done

for NODE in "${!NODES[@]}"
do
    [[ $NODE -eq 0 ]] && { ROLE="[MASTER]"; COMPOSEFILE="./docker-compose.yaml"; }
    [[ $NODE -eq 0 ]] || { ROLE="[SLAVE #$NODE]"; COMPOSEFILE="./docker-compose-slave.yaml"; }

    HOSTNAME=${NODES[$NODE]}
    echo $ROLE HOST NAME: $HOSTNAME

    HOST_ADDRESS=$(nslookup "$HOSTNAME" | awk -F':' '/^Address: / { matched = 1 } matched { print $2}' | xargs)
    [[ $HOST_ADDRESS ]] || { echo "$HOSTNAME lookup failure. Exiting."; exit 1; }
    echo $ROLE HOST ADDRESS: $HOST_ADDRESS

    REMOTE_HOME=$(ssh -q -oBatchMode=yes $USER@$HOSTNAME 'echo $HOME') || {
        echo "Please make sure ssh via publickey is possible with \"ssh -q -oBatchMode=yes $USER@$HOSTNAME\". Exiting."; exit 1; }
    echo $ROLE HOST HOME DIR: $REMOTE_HOME

    [[ -z $ENV_BUILD_TYPE ]] && ENV_BUILD_TYPE="mainline"
    echo $ROLE BUILD TYPE: $ENV_BUILD_TYPE

    PROJECT_NAME="titan-cloud-emulator"
    echo $ROLE PROJECT NAME: $PROJECT_NAME

    echo $ROLE SLAVE NODES: $POOL_NODES
    ENV_POOL_NODES=$(echo $POOL_NODES | sed "s/\//\\\\\\//g")  # escape '/' with '\/'

    scp -q -oBatchMode=yes ./.env $USER@$HOSTNAME:$REMOTE_HOME/. && echo $ROLE "COPY .env: DONE"
    scp -q -oBatchMode=yes $COMPOSEFILE $USER@$HOSTNAME:$REMOTE_HOME/. && echo $ROLE "COPY $COMPOSEFILE: DONE"

    ssh -q -oBatchMode=yes $USER@$HOSTNAME "sed -i -E 's/(ENV_BUILD_TYPE=.*)/ENV_BUILD_TYPE='$ENV_BUILD_TYPE'/g' .env" && echo $ROLE "UPDATE ENV_BUILD_TYPE: DONE"
    ssh -q -oBatchMode=yes $USER@$HOSTNAME "sed -i -E 's/(ENV_HOSTNAME=.*)/ENV_HOSTNAME='$HOSTNAME'/g' .env" && echo $ROLE "UPDATE ENV_HOSTNAME: DONE"
    ssh -q -oBatchMode=yes $USER@$HOSTNAME "sed -i -E 's/(ENV_EXT_IP=.*)/ENV_EXT_IP='$HOST_ADDRESS'/g' .env" && echo $ROLE "UPDATE ENV_EXT_IP: DONE"
    ssh -q -oBatchMode=yes $USER@$HOSTNAME "sed -i -E 's/(ENV_REMOTE_REGISTRY_PASS=.*)/ENV_REMOTE_REGISTRY_PASS='$SVC_TITANEMU_PASS'/g' .env" && echo $ROLE "UPDATE ENV_REMOTE_REGISTRY_PASS: DONE"
    ssh -q -oBatchMode=yes $USER@$HOSTNAME "sed -i -E 's/(ENV_POOL_NODES=.*)/ENV_POOL_NODES='${ENV_POOL_NODES@Q}'/g' .env" && echo $ROLE "UPDATE ENV_POOL_NODES: DONE"

    ssh -q -oBatchMode=yes $USER@$HOSTNAME docker-compose -f $COMPOSEFILE -p $PROJECT_NAME stop > /dev/null 2>&1 && echo $ROLE "STOP: DONE"
    ssh -q -oBatchMode=yes $USER@$HOSTNAME docker-compose -f $COMPOSEFILE pull -q > /dev/null 2>&1 && echo $ROLE "PULL: DONE"
    ssh -q -oBatchMode=yes $USER@$HOSTNAME docker-compose -f $COMPOSEFILE -p $PROJECT_NAME up -d > /dev/null 2>&1 && echo $ROLE "UP: DONE" && echo -e ""
    ssh -q -oBatchMode=yes $USER@$HOSTNAME docker-compose -f $COMPOSEFILE -p $PROJECT_NAME ps && echo -e ""
done
