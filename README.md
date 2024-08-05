# launchpad
Currently Under development. README and doc in construction.<br>
Launchpad aim to be a simple Open source declarative orchestration tool. It works as an HTTP wrapper around [Temporalio](https://temporal.io/) engine.
Provided out of the box:
* Built-in Runners and workflows, covering most needs:
  * standard, Scheduled runners for temporalIo
  * Senquential and batch workflows.
  * signals accross workflows.
  * ...
* Handlers for multiple temporalio servers and namespaces.
* a watcher handling file versionning, Hot realoading and Custom components injections
* A dynamic declarative framework handling environment variables injection, jinja2 templating and arguments overwrite.
* a JWT based authentication system.


# Prerequisites
* Docker
* Docker Compose
* python >= 3.10

## How to use

1. Setup and start Temporalio using [TemporalIO-docker-compose](https://github.com/temporalio/docker-compose)
```bash
git clone https://github.com/temporalio/docker-compose.git
cd docker-compose
docker-compose -f docker-compose-postgres.yml up
```
By default the port 7233 and 8080 are exposed for the server and the GUI. Temporal dockers also expose ports for Grafana, Prometheus and the server metrics.

2. Setup Launchpad on your repo
```bash
launchpad setup --name {your project folder name}
```
  Setup a few folders:
  * `deployments/workers`will contain all your workers configurations.
  * `deployments/tasks` will contain all your tasks configurations.
  * `{project-name}/temporal` folder in your repo. From there you can store your activities and/or build your own custom launchpad components.
  Setup configuration file and launcher:
  * `launchpad_configs.yaml`
    * Temporalio: Soon.
    * Watcher: soon.
    * Authentication: soon.
    ! to be changed!
    if you rename or change the location of your config file. make sure to either register the location of the file as argument in the `asgi.py` file
    or to set the your Env Variable CONFIGS_FILEPATH={config file path}
  * `asgi.py`. to be replaced by `launchpad start --configs` command

3. add your activities in `{src}/temporal/activities.py`. An activity must be decorated with `activity.defn`.
```python
...
@activity.defn()
def your_activity(args, kwargs) -> None:
    ...
...
```
4. define your deployments configurations.
  * Your workers in `deployments/workers`. Make sure that the workers you define do handle the Workflows and activities you want.
  * your tasks in `deployments/tasks`.
5. start the launchpad
```bash
sanic asgi:app --single-process --no-motd
```
