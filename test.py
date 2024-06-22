import sys
from launchpad.activities import Watcher



a = Watcher.initialize("./", "./configs/configs.yaml")

objs = a.load_temporal_objects()
sys.modules[__name__].__dict__.update(objs)

# print("____")
# for k,v in objs.items():
#     print(k,v)
