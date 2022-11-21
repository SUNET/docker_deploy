from typing import Optional, List, Tuple
import os
import subprocess
from datetime import datetime, timezone
import sys
import argparse
import yaml
import pwd
import grp

COMPOSE_FILES = [
    "./docker-compose.yml",
    "./docker-compose.yaml",
    "./compose.yml",
    "./compose.yaml",
]


def change_cwd(path: Optional[str]) -> str:
    """Change current working dir and return the old cwd.

    :param path: Dir to change into.
    :return: str
    """

    old_cwd = os.getcwd()

    if path is not None:
        os.chdir(path)

    return old_cwd


def check_docker_membership() -> None:
    """Ensure user is member of the 'docker' group."""

    # Check docker group membership
    for group in os.getgroups():
        if grp.getgrgid(group).gr_name == "docker":
            break
    else:
        print("ERROR: Your user is not a member of 'docker' group")
        print(f"sudo usermod -a -G sudo {os.environ['USER']}")
        print("Then open a new shell")
        sys.exit(1)


def volumes_from_compose_file() -> Optional[List[Tuple[str, str]]]:
    """Get volumes from the compose file.

    :return: Optional[List[Tuple[str, str]]]
    """

    volumes: List[Tuple[str, str]] = []

    for compose in COMPOSE_FILES:
        if os.path.isfile(compose):
            compose_file = compose
            break
    else:
        print(f"Could not find any of {COMPOSE_FILES} in {os.getcwd()}")
        sys.exit(1)

    with open(compose_file, encoding="utf-8") as f_data:
        yaml_data = yaml.safe_load(f_data)

    if "services" not in yaml_data:
        print(f"ERROR: Found compose file at {compose_file} but not 'services' in it")
        sys.exit(1)

    for service in yaml_data["services"]:
        if "volumes" in yaml_data["services"][service]:
            for volume in yaml_data["services"][service]["volumes"]:
                volume_path = volume.split(":")[0]
                if not os.path.isdir(volume_path):
                    volumes.append((volume_path, "root"))
                    continue

                if not volume.startswith("/opt/"):
                    print(
                        f"\nWARNING: Skipping volume, must start with /opt/ : {volume_path}\n"
                    )
                    continue

                owner_username = pwd.getpwuid(os.stat(volume_path).st_uid).pw_name
                volumes.append((volume_path, owner_username))

    return volumes


def fix_volumes_ownership() -> None:
    """Set correct ownership on docker volume dirs."""

    volumes = volumes_from_compose_file()

    for volume in volumes:

        if not os.path.isdir(volume[0]):
            print(
                f"\nWARNING: You should probably create and/or set non root owner of volume folder: {volume[0]}\n"
            )
            print(
                f"sudo mkdir -p {volume[0]} && sudo chown -R OWNER_HERE {volume[0]}\n"
            )
            continue

        # Do not run on first volumes never used
        owner_username = pwd.getpwuid(os.stat(volume[0]).st_uid).pw_name
        if owner_username == "root":
            print(
                f"\nWARNING: You should probably set non root owner of volume folder: {volume[0]}\n"
            )
            print(f"sudo chown -R OWNER_HERE {volume[0]}\n")
            continue

        subprocess.check_call(["sudo", "chown", "-R", volume[1], volume[0]])


def check_compose_file(project_path: Optional[str]) -> None:
    """Ensure we have a compose file in the project directory.

    :param project_path: Directory to the project where we look for a compose file.
    """

    old_cwd = change_cwd(project_path)

    for compose_file in COMPOSE_FILES:
        if os.path.isfile(compose_file):
            break
    else:
        print(f"ERROR: Could not find any of {COMPOSE_FILES}")
        sys.exit(1)

    os.chdir(old_cwd)


def backup(project_path: Optional[str]) -> None:
    """Backup the volume data.

    :param project_path: Path to project which uses the volume.
    :return:
    """

    old_cwd = change_cwd(project_path)

    app_name = os.getcwd().split("/")[-1]

    if not os.path.isdir(f"/opt/{app_name}/data"):
        print(f"Skipping backup: Nothing to backup at /opt/{app_name}/data")
        return

    # Ensure backup folder exist
    subprocess.check_call(["sudo", "mkdir", "-p", f"/opt/{app_name}/backup"])

    now = datetime.now(timezone.utc)

    from_path = f"/opt/{app_name}/data"
    to_path = f"/opt/{app_name}/backup/data_{now.strftime('%Y%m%d_%H%M%S_utc')}"

    # With sudo since another user/group might own the data
    subprocess.check_call(["sudo", "cp", "-r", from_path, to_path])
    subprocess.check_call(["sudo", "chown", "700", f"{to_path}"])

    # Set ownership on the data
    for entry in os.listdir(from_path):
        owner_username = pwd.getpwuid(os.stat(f"{from_path}/{entry}").st_uid).pw_name
        subprocess.check_call(
            ["sudo", "chown", "-R", owner_username, f"{to_path}/{entry}"]
        )

    print(f"\nBacked up data to {to_path}\n")
    os.chdir(old_cwd)


def down_action(project_path: Optional[str]) -> None:
    """Stop the containers for the project.

    :param project_path: Path to the project.
    """

    check_compose_file(project_path)
    old_cwd = change_cwd(project_path)

    subprocess.check_call(["docker-compose", "down"])

    os.chdir(old_cwd)


def up_action(project_path: Optional[str]) -> None:
    """Start the containers for the project.

    :param project_path: Path to the project.
    """

    check_compose_file(project_path)
    old_cwd = change_cwd(project_path)

    fix_volumes_ownership()

    subprocess.check_call(["docker-compose", "up", "-d"])

    os.chdir(old_cwd)


def info_action() -> None:
    """Alias for 'docker ps'."""

    subprocess.check_call(["docker", "ps"])


def build(project_path: Optional[str]) -> None:
    """Build the containers for the project.

    :param project_path: Path to the project.
    """

    check_compose_file(project_path)
    old_cwd = change_cwd(project_path)

    ret = subprocess.check_call(["docker-compose", "build"])

    os.chdir(old_cwd)


def backup_action(project_path: Optional[str]) -> None:
    """Safely backup the project by stopping the containers, backup then starting them.

    :param project_path: Path to the project.
    """

    check_compose_file(project_path)

    # Stop the service to ensure data integrity
    down_action(project_path)

    # Make the backup
    backup(project_path)

    # Start the service again
    up_action(project_path)


def deploy_action(project_path: Optional[str], replace_path: Optional[str]) -> None:
    """Deploy or update the project safely.

    :param project_path: Path to the project.
    :param replace_path: If not None then replace the project with this one safely.
    """

    if replace_path is not None:
        replace_abs = os.path.abspath(replace_path)
        project_abs = os.path.abspath(project_path)
        old_cwd = os.getcwd()
        os.chdir("/")

        check_compose_file(replace_abs)

        build(project_abs)

        down_action(replace_abs)

        now = datetime.now(timezone.utc)
        to_path = f"{replace_abs}_{now.strftime('%Y%m%d_%H%M%S_utc')}"
        subprocess.check_call(["mv", replace_abs, to_path])
        subprocess.check_call(["cp", "-r", project_abs, replace_abs])

        backup_action(replace_abs)

        os.chdir(old_cwd)

        print(
            f"Backed up project {replace_abs} to {to_path} replaced with {project_abs}"
        )
        print(f"You can now delete {project_abs}")
    else:
        build(project_path)
        backup_action(project_path)


def main() -> None:
    """Main function."""

    check_docker_membership()

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter, description="SOC Collector CLI"
    )
    parser.add_argument(
        "action",
        choices=["info", "backup", "up", "down", "deploy"],
        help="""Action to take

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
    

    Pro tip, in ~/.bashrc:

    _docker_deploy()
    {
        local cur prev words cword
        _init_completion || return

        local commands command

        commands='info backup deploy up down'

        if ((cword == 1)); then
            COMPREPLY=($(compgen -W "$commands" -- "$cur"))
        else

        command=${words[1]}
        _filedir
        return
        fi
    }
    complete -F _docker_deploy -o default docker_deploy

    """,
    )
    parser.add_argument("project_path", nargs="?", help="Path to project directory")
    parser.add_argument(
        "replace_path", nargs="?", help="Path to project directory to be replaced"
    )

    args = parser.parse_args()

    if args.project_path is not None and not os.path.isdir(args.project_path):
        print(f"No such project directory: {args.project_path}")
        sys.exit(1)

    if args.replace_path is not None and not os.path.isdir(args.replace_path):
        print(f"No such project directory: {args.replace_path}")
        sys.exit(1)

    if args.action == "deploy":
        deploy_action(args.project_path, args.replace_path)
    elif args.action == "backup":
        backup_action(args.project_path)
    elif args.action == "info":
        info_action()
    elif args.action == "up":
        up_action(args.project_path)
    elif args.action == "down":
        down_action(args.project_path)

    else:
        print("ERROR: Wrong action")
        sys.exit(1)


if __name__ == "__main__":
    main()
