# Tiny single line script which can be put into home directory on deployment
# machine for rapid execution of titan-cloud-emulator.py python script inside
# running backend container.
#!/bin/bash
docker exec -it `docker ps | grep titan-emulator-backend | grep -v usbip | grep -v resource | awk '{print($NF)}'` python3 titan-cloud-emulator.py $@ 2>/dev/null || echo "Wrong command or no backend containers are running"
