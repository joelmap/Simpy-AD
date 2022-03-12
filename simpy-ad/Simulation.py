"""
Simulation scenario

    Vehicle - 1x
        PU - TX2 x1
    
    RSU - 1x
        Server - 1x
            PU - TeslaV100 1x
    
    TaskMapper - 1x
        Task - n
        PU - 2

    Trip
        Gare VA -> Gare Lille
        Frames -> 189639
    
    Goal is 60 FPS, repeat trip until FPS reaches 60 by optimizing model
    or until required latency is reached (or almost) 
"""
import simpy
from Vehicle import Vehicle
from Location import Location
from ProcessingUnit import AGX, TeslaV100
from TaskSchedulingPolicy import TaskSchedulingPolicy
from RoadSideUnit import RoadSideUnit
from Server import Server
from CNNModel import CNNModel
from Task import Task
from TaskMapper import TaskMapper
from Colors import END
from TaskCriticality import TaskCriticality

env = simpy.Environment()

"""
Vehicle init
"""
start = Location("Gare VA", 50.36328322047431, 3.5171747551323005)
final = Location("Gare Lille", 50.63725143907785, 3.0702985651377745)
## PU init
pu = AGX(task_list=[], scheduler=TaskSchedulingPolicy("FIFO"), env=env)

inception = CNNModel('Inception-v3', 1024)
resnet18 = CNNModel('ResNet-18', 480)
mobilenet = CNNModel('MobileNet0.25-v1', 240)

vehicle_tasks = [
    Task(inception.getModelFLOPS(), inception.getModelMemory(), criticality=TaskCriticality.HIGH),
    Task(resnet18.getModelFLOPS(), resnet18.getModelMemory(), criticality=TaskCriticality.MEDIUM),
    Task(mobilenet.getModelFLOPS(), mobilenet.getModelMemory(), criticality=TaskCriticality.LOW),
]
vehicle = Vehicle(c_location=start, f_location=final, speed=50, task_list=vehicle_tasks, PU_list=[pu], required_FPS=1, env=env)
print(vehicle.getFramesToBeProcessed())

"""
RSU init
"""
location = Location("", 50, 45)
# PU init
pu = TeslaV100(task_list=[], scheduler=TaskSchedulingPolicy("FIFO"), env=env)
## Server init
server = Server(pu_list=[pu], bw=1, env=env)

rsu = RoadSideUnit(location=location, server_list=[server], to_vehicle_bw=1, to_cloud_bw=1, env=env)

vehicle.showInfo()
rsu.showInfo()

TaskMapper.showPUs()

#input(f"{END}Enter to continue")

taskMapper = TaskMapper(env)

#print("t ", taskMapper.task_list)
#print("TaskMapper ", TaskMapper.task_list)

SIM_TIME = 10**10
print("Enter to start SImulation")
input()
env.run(until=SIM_TIME)

print("Env finished at ", env.now)