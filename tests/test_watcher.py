import os
import sys
import yaml
import shutil
from pathlib import Path
from launchpad.watcher import Watcher, YamlModule, PyModule, Group

def setup_file_system_1():
    if os.path.exists("./testfolder"):
        shutil.rmtree("./testfolder")
    
    os.mkdir("./testfolder")
    os.mkdir("./testfolder/deployments")
    os.mkdir("./testfolder/temporal")

    deployment1 = {
        'name': 'test1', 
        'runner': 'WorkflowRunner', 
        'workflow': {
            'workflow': 'Task', 
            'workflow_id': 'cute_id', 
            'task_queue': 'default', 
            'workflow_kwargs': {
                'activity': 'appfile', 
                'args': ['qwerty'], 
                'client_address': 'localhost:7233'
            }
        }
    }
    deployment2 = {
        'name': 'test2', 
        'runner': 'ScheduledWorkflowRunner', 
        'workflow': {
            'workflow': 'Task', 
            'workflow_id': 'cute_id', 
            'task_queue': 'default', 
            'workflow_kwargs': {
                'activity': 'appfile', 
                'args': ['Scheduled'], 
                'client_address': 'localhost:7233'
            }
        }, 
        'schedule': {
            'scheduler_id': 'cute_schedule_id', 
            'intervals': [{'every': {'seconds': 10}}]
        }
    }
    with open("./testfolder/deployments/test1.yaml", 'w+') as f:
        yaml.safe_dump(deployment1, f)
    with open("./testfolder/deployments/test2.yaml", 'w+') as f:
        yaml.safe_dump(deployment2, f)
    
    shutil.copy("./activities/activity1.py", "./testfolder/temporal/activities.py")
    shutil.copy("./launchpad/workflows.py", "./testfolder/temporal/workflows.py")
    

def rm_test_setup():
    if os.path.exists("./testfolder"):
        shutil.rmtree("./testfolder")
    
def test_pymodule_init():
    setup_file_system_1()
    module = PyModule(Path("./testfolder/temporal/workflows.py"))
    assert module.latest == "a39e9a5b085b6720a15168690bd51abe5c44226178b142aa001380eb42cb7d7f"
    assert module.changes == False
    rm_test_setup()

def test_pymodule_changes():
    setup_file_system_1()
    module = PyModule(Path("./testfolder/temporal/workflows.py"))
    with open(module.module.absolute(), "a") as f:
        f.write("add file modification\n")
   
    module.watch()
    assert module.latest == "79d59f49e0d913d9d94398fe7f7755cdb47cf0b0a58938409de3c05c10ea414a"
    assert module.changes == True
    rm_test_setup()

def test_pymodule_reload():
    setup_file_system_1()
    
    sys.modules.pop("testfolder.temporal.workflows", None)
    sys.modules.pop("testfolder.temporal.activities", None)
    module = PyModule(Path("./testfolder/temporal/workflows.py"))
    import testfolder.temporal.workflows
    
    with open("./testfolder/temporal/activities.py", "r") as f:
        content = f.read()
    
    with open("./testfolder/temporal/workflows.py", "a") as f:
        f.write(f"\n\n{content}")
    
    m = sys.modules[module.module_name].__dict__
    assert m.get("appfile", None) is None and m.get("blabla", None) is None and m.get("hello", None) is None
    
    module.reload()
    m = sys.modules[module.module_name].__dict__
    assert m.get("appfile", None) and m.get("blabla", None) and m.get("hello", None)

    rm_test_setup() 



def test_pymodule_temporal_objects():
    setup_file_system_1()
    sys.modules.pop("testfolder.temporal.workflows", None)
    sys.modules.pop("testfolder.temporal.activities", None)
    import testfolder.temporal.workflows
    import testfolder.temporal.activities
    
    module = PyModule(Path("./testfolder/temporal/workflows.py"))
    objects = module.temporal_objects()
    assert objects.get("Task", None)

    module = PyModule(Path("./testfolder/temporal/activities.py"))
    objects = module.temporal_objects()
    assert objects.get("appfile", None) and objects.get("blabla", None) and objects.get("hello", None)
    
    rm_test_setup() 

def test_pymodule_injection():
    setup_file_system_1()
    
    sys.modules.pop("testfolder.temporal.workflows", None)
    sys.modules.pop("testfolder.temporal.activities", None)
    import testfolder.temporal.workflows
    import testfolder.temporal.activities
    
    workflows = PyModule(Path("./testfolder/temporal/workflows.py"))
    activities = PyModule(Path("./testfolder/temporal/activities.py"))
    
    temporal_objects = activities.temporal_objects()
    
    m = sys.modules[workflows.module_name].__dict__
    assert m.get("appfile", None) is None and m.get("blabla", None) is None and m.get("hello", None) is None
    
    workflows.inject(temporal_objects)
    m = sys.modules[workflows.module_name].__dict__
    assert m.get("appfile", None) and m.get("blabla", None) and m.get("hello", None)
    
    rm_test_setup() 
    
def test_yamlmodule_payloads():    
    setup_file_system_1()
    
    deployment1 = {
        'name': 'test1', 
        'runner': 'WorkflowRunner', 
        'workflow': {
            'workflow': 'Task', 
            'workflow_id': 'cute_id', 
            'task_queue': 'default', 
            'workflow_kwargs': {
                'activity': 'appfile', 
                'args': ['qwerty'], 
                'client_address': 'localhost:7233'
            }
        }
    }    

    module = YamlModule(Path("./testfolder/deployments/test1.yaml"))
    assert module.payload() == deployment1
    
    rm_test_setup() 


def test_group_modules_sync():
    setup_file_system_1()
    
    deployments = Group("deployments", [Path("./testfolder/deployments")])
    app = Group("app", [Path("./testfolder")])
    activities = Group("activities", [Path("./testfolder/temporal/activities.py")])
    
    deployments_modules = [Path("./testfolder/deployments/test1.yaml"), Path("./testfolder/deployments/test2.yaml")]
    all_mods = [
        Path("./testfolder/deployments/test1.yaml"), 
        Path("./testfolder/deployments/test2.yaml"),
        Path("./testfolder/temporal/activities.py"), 
        Path("./testfolder/temporal/workflows.py"),
    ]

    assert all([p in deployments.paths for p in deployments_modules]) == True
    assert all([p in app.paths for p in all_mods]) == True
    assert activities.paths == [Path("./testfolder/temporal/activities.py")]
    
    
    deployment3 = {
        'name': 'test3', 
        'runner': 'WorkflowRunner', 
        'workflow': {
            'workflow': 'Task', 
            'workflow_id': 'cute_id', 
            'task_queue': 'default', 
            'workflow_kwargs': {
                'activity': 'appfile', 
                'args': ['qwerty'], 
                'client_address': 'localhost:7233'
            }
        }
    }  
    
    with open("./testfolder/deployments/test3.yaml", 'w+') as f:
        yaml.safe_dump(deployment3, f)
        
    deployments.visit()
    deployments_modules2 = [Path("./testfolder/deployments/test1.yaml"), Path("./testfolder/deployments/test2.yaml"), Path("./testfolder/deployments/test3.yaml")]
    
    assert all([p in deployments.paths for p in deployments_modules2]) == True
    assert deployments.modules.get(Path("./testfolder/deployments/test3.yaml")).changes == True
    
    os.remove("./testfolder/deployments/test3.yaml")
    deployments.visit()
    assert all([p in deployments.paths for p in deployments_modules]) == True
    assert deployments.modules.get(Path("./testfolder/deployments/test3.yaml"), None) is None
    rm_test_setup() 

def test_watcher_sync():
    setup_file_system_1()
    
    watcher = Watcher(
        deployments=["./testfolder/deployments"], 
        workflows= ["./testfolder/temporal/workflows.py"], 
        activities= ["./testfolder/temporal/activities.py"]
    )
    
    assert (
        watcher.groups.get("deployments", None) is not None and 
        watcher.groups.get("workflows", None) is not None and 
        watcher.groups.get("activities", None) is not None
    )
    
    assert watcher.get_module("./testfolder/deployments/test1.yaml")
    assert watcher.get_module("./testfolder/temporal/activities.py")    
    rm_test_setup() 
