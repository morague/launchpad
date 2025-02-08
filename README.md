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





### Configuration

#### Temporalio

You can handle multiple servers and namespaces per servers.
It is necessary to set at least one server configuration for launchpad to work.
If only one server is set, with one namespace. The server and namespace will automatically be set as defaults.
In case, there is multiple servers or namespaces per server, and no default values are defined, then the first/namespace listed are set as defaults.
Otherwise, `default_server` value define the default server
and `default_namespace` value define the default namespace of a server.

A Temporalio Server is defined as follow:
* `name` is the name under which the server is registered in the launchpad.
* `ip` server domain name.
* `port` temporalio server port. Generally set as 7233 by temporalio
* `gui_port` temporalio gui-server port. Generally set as 8233 on the dev server and 8080 on the docker-compose
* `namespaces` list of all namespaces to be create or to register on a server. a namespace is define by a `name` and a `retention` time in seconds.
* `default_namespace` name of the namespace to be set as default.

```yaml
temporalio:
  default_server: Optional[str] # server name
  servers:
    - name: str
      ip: str
      port: int
      gui_port: int
      # proxy
      # ...
      namespaces:
        # default namespace exist by default
        - name: str
          retention: int # in seconds
      default_namespace: Optional[str]
```

#### Watcher
The watcher observe a set of designated yaml and python files.
It looks for modification and do some hot realoading when activated.
It is also responsible for loading tasks
and workers settings as well as collecting and injecting accress modules all temporal objects
that are built-in or customs.

`polling` define the polling system that will visit and potentialy hot reaload modified files.
the polling system can be started at server start if `on_server_start` is set to true.
you can modify the polling frequency with `polling_interval` and determine if the polling can
try to reload all modified files with `automatic_refresh`.

the watcher, regroup watched folders/files by categories depending what the file contains such as `settings` or `temporal_objects`
`modules` list all groups you want to create, with the files/folders you want to watch or to skip.
By default, `workers`, `workflows`, `tasks`, `runners` are defined. you can add as much folders/files into those groups as you want.
You must on your side setup 2 necessary groups: `activities` and `configs` with the files containing respectively your activities and your configs.
By default, the `launchpad setup --name {name}` will build the module configs with those 2 groups targeting the default `temporal/activities.py` and `launchpad_configs.yaml`.

a group is defined by both `basepaths` which is the list of all folders/files to watch and `skips` the list of all files to explicitly not watch over.

```yaml
watcher:
  modules:
    workers:
      basepaths:
        - ./path/to/folder
      skips:
        - ...
    workflows:
    tasks:
      basepaths:
        - ./path/to/folder
    activities:
      basepaths:
        - ./path/to/file
    runners:
  polling:
    on_server_start: bool # default: false
    automatic_refresh: bool # default: false
    polling_interval: int # default 600. in seconds.
```


#### Authentication

The authentication system is based on JWT. The Jwt system lies on the sanic secret key.
In order to use the Auth system, you must first define a secret key in `sanic.app.secret`.
The users are stored on a Sqlite database. By default the database is cached with `:memory:`, however you can define the location of the database using `db`.

`base_users` list all the configurated users. A user is defined by a `username`, a `password`, a `max_age` for the token and a list of `auth_level`.
`auth_level` determine the authorization level granted for a token. Currently there is 2 level of auth `user` and `super user`
All endpoint recquire an authorization token when the authenticator is activated.
However, most endpoints only recquire a `user` auth level. `super user` auth level exist for endpoint that lead into importing or modifying files in the server.

```yaml
sanic:
  app:
    secret: xxxxxxx

authenticator:
  db: ":memory:"
  base_users:
    - username: test
      password: test
      auth_level:
        - user
        - super user
      max_age: 600
```

### Tasks settings
Launchpad deployments templates: `templates/deployments_templates/`
Launchpad deployments examples: `templates/deployments_examples/`
[temporalio python-sdk](https://docs.temporal.io/develop/python)
[temporalio api docs](https://python.temporal.io/index.html)

a task setting file is composed of 3 levels of settings:
* the fileroot that contains settings relative to the Runner as well as few global settings.
* the `workflow` argument that contains every settings relative to the workflow execution.
* the `workflow_kwargs` argument that contain every settings relative the activity execution as well as potentials other actions by a workflow.

#### Minimal Settings
A tasks settings file can be fairly simple when not using the many Optional TemporalIo argument or the launchpad built-in behaviors.
At it's bare minimum, a task setting file can be as follow:
```yaml
name: str # name must be also the filename.
runner: str # WorkflowRunner | ScheduledWorkflowRunner | WorkflowRunnerWithTempWorker or your Customs Runners.
workflow:
  task_queue: str # worker task_queue name to be used.
  workflow_id: str
  workflow: str # Task | TaskDispatcher | AwaitedTask | BatchTask | AwaitedBatchTask or your Customs Workflows.
  scheduler_id: # str Required when using ScheduledWorkflowRunner.
  workflow_kwargs:
    activity: str # Activity function name
    args: list[Any] # activity function arguments
```

When `server` or `namespace` are omitted, the launchpad will use your default server and namespace.
To run, a task settings require at least a task `name` that will be your lone way to retrieve and deploy your task via `/tasks/deploy/{name}` endpoint.
Select a `runner` depending on how you want to run the task.
* `WorkflowRunner` will run a task instantly on an already running Temporalio worker without waiting for any return from your workflow.
* `ScheduledWorkflowRunner` will start a scheduled tasks that will run when specified on an already running Temporalio worker. Schedules needs to be specified.
* `WorkflowRunnerWithTempWorker` will create a worker and start the task instantly. Because the task only live in the context of this temporary worker,
the runner must wait the completion of the workflow to return. This can suit well workflows that are quick to finish.
* `Custom Runners`. When setting up launchpad, a file `temporal/runners.py` is created to store any customs runners you would create.
Obviously, you can use another file, but in this case you should specify the file / folder into the watcher configs.
A CustomRunner Must inherite fromt the `Runner` type.

Next you must define your workflow.
The workflow needs a worker `task_queue` (this define which worker must be used), unless you use `WorkflowRunnerWithTempWorker`.
`workflow_id` is important to clearly identify your tasks on the temporalIo-gui, but also for workflow signals communications between workflows.
`scheduler_id` is necessary only when you are using `ScheduledWorkflowRunner`.
Select a `workflow` among the built-in workflows our your Customs workflows.
All Workflow types handle temporalIo Optional arguments such as the `retry_policy`, `*_timeout`, `*_signals`
and the launchpad built-in arguments like `chain_with` or `renew`.
* `Task` is the Simplest workflow Type. It does run your defined activity.
* `TaskDispatcher` is particular workflow as it does do much on it's own. It is a workflow with a `queue`, awaiting signals to receive `tasks`
and to run them as child workflows.
As signals, only works between running workflows, `TaskDispatcher` allow start a new task without having to signal that task directly.
* `AwaitedTask` is a workflow awaiting a `start` signal before executing it's activity.
* `BatchTask` is a workflow that takes a list of activity as settings and run them as a batch of activity.
* `AwaitedBatchTask` Similarly to `BatchTask`, this workflow await a `start` signal before starting it's batched activities.
* `Custom Workflows` When setting up launchpad, a file `temporal/workflows.py` is created to store any customs runners you would create.
Obviously, you can use another file, but in this case you should specify the file / folder into the watcher configs.
A CustomWorkflow must be decorated with the temporalio `workflow.defn` and can inherite from `BaseWorkflow` type for handling temporalIo optional arguments.

Finally, define `workflow_kwargs` which must at least describe the `activity` you want to run and it's `args`.

#### Additional Settings
##### Global Settings
Additionaly, beside `name` and `runner`, you can pass few options:
```yaml
server: Optional[str] # by default, use the server set as default in the configs.
namespace: Optional[str] # by default, use the default namespace from the given server.
overwritable: Optional[bool] # default False. Define if a setting file can be overwritten when deploying a tasks.
template: Optional[bool # default False. Define if a setting file is template tasks or not. A template task cannot be deployed on server start.
deploy_on_server_start: Optional[bool] # default : False. Define if a task is automatically deployed on server start.
```
* `server` and `namespace`, as previously stated are useful in case you use multiple servers or mutiple namespaces.
Whevener you need to run a workflow on a specified server or namespace that are not your default settings, then you must define those arguments.
* `overwritable` and `template` are bool values that define if fields values can be respectively overwritten or act as a jinja2 variable.
  * if `overwritable` is set to true, when you deploy a task using `/tasks/deploy/{name}`,
  you can pass a payload such as: `{"overwrite": {"path.to.arg": "new_value", ...}}`. The specified fields will overwritten.
  * if `template` is set to true, you can use jinja2 variable formating inside your task settings file `argument_name: {{variable_name}}`
  when you deploy a task using `/tasks/deploy/{name}`, you can pass a payload such as: `{"template_args": {"variable_name": "variable_value", ...}}`.
* `deploy_on_server_start`, when set to true, launchpad deploy automatically the task when the server is starting.
This can be useful for all your awaiting tasks.

##### Workflows Temporalio options
You can complement your `workflow` settings with many Temporalio options:
You can find those [arguments documentation on the temporalio api documentation](https://python.temporal.io/index.html).
Alternatively, you can take a look on the deployments templates, for better description of timedelatas and datetimes arguments.

```yaml
id_reuse_policy: Optional[str] # TemporalIO: ALLOW_DUPLICATE | ALLOW_DUPLICATE_FAILED_ONLY | REJECT_DUPLICATE | TERMINATE_IF_RUNNING
cron_schedule: Optional[str] # TemporalIO
request_eager_start: Optional[bool] # TemporalIO. default = False
start_signal: Optional[str] # TemporalIO  . Workflow signal name as STR
start_signal_args: Optional[list[Any]] # TemporalIO.
retry_policy: Optional[dict[str, Any]] # TemporalIO.
execution_timeout: Optional[timedelta] # TemporalIO.
run_timeout: Optional[timedelta] # TemporalIO.
task_timeout: Optional[timedelta] # TemporalIO.
rpc_timeout: Optional[timedelta] # TemporalIO.
start_delay: Optional[timedelta] # TemporalIO.
memo: Optional[dict[str, Any]] # TemporalIO.
rpc_metadata: Optional[dict[str, Any]] # TemporalIO.
```

##### Workflows Temporalio Schedules Options
You can complement your `workflow` settings with the Temporalio Schedules Options:
You can find those [arguments documentation on the temporalio api documentation](https://python.temporal.io/index.html).
Alternatively, you can take a look on the deployments templates, for better description of timedelatas and datetimes arguments.

```yaml
  trigger_immediately: False # bool. default: False
  tz: "Europe/Paris" # Optional[str] . default: "Europe/Paris"
  intervals: # Optional[list]
    - every: # timedelta
      offset: # Optional[timedelta]
  calendars: # Optional[list[int]]
  skip: # Optional[list]
  crons: # Optional[list[str]] e.g: "* * * * *"
  jitter: # Optional[timedelta]
  start_at: # Optional[datetime]
  end_at: # Optional[datetime]
  catchup_window: # Optional[timedelta]
  overlap: # Optional[str]. default: SKIP. > ScheduleOverlapPolicy ALLOW_ALL | BUFFER_ALL | BUFFER_ONE | CANCEL_OTHER | SKIP | TERMINATE_OTHER
  pause_on_failure: #Optional[bool]. default False
  limited_actions: #Optional[bool]. default False
  note: # Optional[str]. default None
  paused: #Optional[bool]. default False
  remaining_actions: # Optional[int]. default 0.
```

##### Workflows_kwargs Options

`at_start` and `at_end` are built-in arguments that allow multiple behaviours at the start of a workflow (after await conditions, for the `awaitedTasks`)
or at its end.
* Both `at_start` and `at_end` can handle `chain_with` argument. `chain_with` is a built-in behaviour that allow for external signals accross workflow.
By providing an `handle` (a workflow type and workflow id) and a `signal` (signal name and it's arguments),
a workflow can communicate at its beginning or end with other workflows
* `at_end` can handle `renew` arguments, that, when set to true, allow the workflow to restart as new, thus recreating a new identical workflow.

```yaml
activity_id: Optional[str] # default None. ~ if not defined at workflow level
task_queue: Optional[str] # default None. ~ if not defined at workflow level

at_start: # Optional[dict[str, Any]]. potentials actions triggered at the begining of a workflow.
  chain_with: # Optional[list[dict]]. chain_with allow to send a signal to a designated running workflow.
    - handle:
        workflow: str # Workflow class name
        workflow_id: str # targeted Workflow id
      signal:
        signal: str # Signal function name of the receiver workflow
        signal_args: Optional[list[Any]] # arguments of the receiver singal function.

at_end: # Optional[dict[str, Any]]. potentials actions triggered at the end of a workflow.
  renew: Optional[bool] # default False. renew use the Temporalio method to restart a workflow as new when this one finish.
  chain_with: # Optional[list[dict]]. chain_with allow to send a signal to a designated running workflow.
    - handle:
        workflow: str # Workflow class name
        workflow_id: str # targeted Workflow id
      signal:
        signal: str # Signal function name of the receiver workflow
        signal_args: Optional[list[Any]] # arguments of the receiver singal function.

retry_policy: Optional[dict[str, Any]] # TemporalIO
versioning_intent: Optional[str] # TemporalIO. COMPATIBLE | DEFAULT . default None.
cancellation_type: Optional[str] # TemporalIO. ABANDON | TRY_CANCEL ABANDON | TRY_CANCEL | WAIT_CANCELLATION_COMPLETED. default TRY_CANCEL.
schedule_to_close_timeout: Optional[timedelta] # TemporalIO
schedule_to_start_timeout: Optional[timedelta] # TemporalIO
start_to_close_timeout: Optional[timedelta] # TemporalIO
heartbeat_timeout: Optional[timedelta] # TemporalIO
```
