Safely handle local backups and docker compose deployments.
Also ensure correct ownership of docker volume folders.

This is basically a wrapper around docker-compose

This is more for rapid developments and testing rather than production which should use more advanced backup solutions.

# Install

``` bash
pip3 install ./
```

# Usage
``` bash
deploy: [path to project folder to deploy] [path to backup and replace before deploying]
docker_deploy deploy
docker_deploy deploy ./my_project
docker_deploy deploy ./my_project /production/my_project

up: [path to project folder to run 'docker-compose up -d']
docker_deploy up
docker_deploy up ./my_project

down: [path to project folder to run 'docker-compose down']
docker_deploy down
docker_deploy down ./my_project

backup: [path to project folder to backup]
docker_deploy backup
docker_deploy backup ./my_project

info: Runs 'docker ps'
docker_deploy info
```
