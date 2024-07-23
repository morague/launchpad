
import os
import shutil
from jinja2 import Template
import argparse
from importlib.resources import files

import click

@click.group()
def cli():
    pass


@cli.command()
@click.option("-n", "--name", default=None)
def setup(name):
    # parser = argparse.ArgumentParser()
    # parser.add_argument("-n", "--name", default=None)

    # args = parser.parse_args()
    name = name or "src"
    
    if os.path.exists(f"./{name}") is False:
        raise KeyError(f"folder ./{name} does not exist")

    # -- setup temporal
    if os.path.exists(f"./{name}/temporal") is False:
        temporal = files('templates.temporal')
        shutil.copytree(temporal, f"./{name}/temporal", ignore=shutil.ignore_patterns("__*"))

    # -- templates
    if os.path.exists(f"./deployments_templates") is False:
        templates = files('templates.deployments_templates')
        shutil.copytree(templates, f"./deployments_templates", ignore=shutil.ignore_patterns("__*"))

    if os.path.exists(f"./deployments") is False:
        deployments = files('templates.deployments')
        shutil.copytree(deployments, f"./deployments", ignore=shutil.ignore_patterns("__*"))

    if os.path.exists(f"./launchpad_configs") is False: 
        with open(f"{str(files('templates'))}/configs.yaml", "r") as f:
            configs = Template(f.read())
        with open(f"./launchpad_configs.yaml", "w+") as f:
            f.write(configs.render(name=name))

    if os.path.exists(f"./asgi.py") is False: 
        templates = files('templates')
        shutil.copy(f"{templates}/asgi.py", "./asgi.py")

if __name__ == "__main__":
    cli()