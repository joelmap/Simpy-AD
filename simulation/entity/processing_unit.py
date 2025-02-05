from simulation.utils.units import Units
import simpy
from simulation.entity.server import Server
from simulation.task_scheduling import TaskSchedulingPolicy
from simulation.utils.colors import YELLOW, END
from time import time
#import TaskMapper
from typing import List, TYPE_CHECKING
from simulation.exception import OutOfMemoryException, NoMoreTasksException

if TYPE_CHECKING:
    from entity.vehicle import Vehicle
    from entity.task import Task
'''
Benchmarks sources : https://developer.nvidia.com/embedded/jetson-modules 
and https://developer.nvidia.com/blog/nvidia-jetson-agx-xavier-32-teraops-ai-robotics/

'''

"""
PU's parent can be
    - Vehicle
    - RSU
    - DataCenter
"""
class ProcessingUnit(simpy.Resource):
    idx = 0
    name = ''
    CYCLE = 0.00001

    def __init__(self, flops, memory, power, memory_bw, scheduler: TaskSchedulingPolicy, env: simpy.Environment, capacity=1, MAX_QUEUE_SIZE=200):
        super().__init__(env, capacity)
        self.name = f'PU-{ProcessingUnit.idx}'
        ProcessingUnit.idx += 1

        self.parent = None
        self.flops = flops
        self.memory = memory
        self.actual_memory = 0
        self.power = power
        self.memory_bw = memory_bw
        self.task_list = []
        self.MAX_QUEUE_SIZE = MAX_QUEUE_SIZE
        self.scheduler = scheduler
        self.env = env
        self.proc = env.process(self.run())

        self.executed_tasks = 0

    def run(self):
        while True:
            #print(f"{GREEN}{self.name} run at {self.env.now}, tasks={len(self.tasks)}")
            # scheduler update tasks
            #print(f"sched tasks {len(self.scheduler.task_list)}")
            try:
                task: 'Task' = self.scheduler.getNextTask()

                #print(f"task {task.getInfos()}")
                
                self.log(f"run: processing task {task}")
                yield self.env.process(self.execute_task(task))
                self.log(f"run: processed task {task}")
                #self.log(f"after exec {task}-flop={task.remaining_flop} at {self.env.now}, tasks={len(self.tasks)}")
                self.log(f"after exec {task}-flop={task.flop}, remaining_flop={task.remaining_flop} at {self.env.now}")

                if task.getRemainingFlop() > 0:
                    #self.log(f"run: Back to scheduler {task}")
                    task.addSchedulerRound()
                    self.scheduler.addTaskInQueue(task)
                
                if task.getRemainingFlop() <= 0:
                    task.setExecutionEndTime(self.env.now)
                    self.actual_memory -= task.getSize()

                    self.log(f"run: Finished task execution {task}, deadline={task.getDeadline()} Success: {task.isSuccess()}")
                    # task.isSuccess()
                    #self.log(f'Took {total}, expected {task.getExpectedExecTime()}, diff {task.getExpectedExecTime() - total}')
            except NoMoreTasksException as e:
                #self.log(f'No more tasks to execute')
                yield self.env.timeout(self.CYCLE)
            except Exception as e:
                self.log(f'{e} CYCLE')
                yield self.env.timeout(self.CYCLE)
            #yield self.env.timeout(self.CYCLE)

    def submitTask(self, task: 'Task'):
        if task not in self.getTaskList():
            if self.actual_memory + task.getSize() > self.memory:
                raise OutOfMemoryException()
            else:
                self.actual_memory += task.getSize()
                #print(f"PU memory {self.actual_memory}/{self.memory}")
                #input()
            task.setCurrentPu(self)
            self.task_list.append(task)

            # add task to scheduler
            self.scheduler.addTaskInQueue(task)

            self.executed_tasks += 1
            self.log(f'submitTask: {task.getTaskName()} submitted to {self.getPUName()}')
        else:
            self.log(f'submitTask: {task.getTaskName()} already assigned to {self.getPUName()}')

    def getTaskLoadingTime(self, task: 'Task'):
        return task.getSize() / self.getMemoryBandwidth()

    def getTaskExecutionTime(self, task: 'Task'):
        flops = self.getFlops()
        # if self.getScheduler().getParallel():
        #     flops = int(self.getFlops()/len(self.getTaskList()))
        return task.getFlop() / flops

    def execute_task(self, task: 'Task'):
        # load task in memory 
        yield self.env.timeout(self.getTaskLoadingTime(task))

        if task.getExecutionStartTime() == -1:
            task.setExecutionStartTime(self.env.now)

        TIMEOUT = 0
        QUANTUM = self.getScheduler().getQuantum()
        if QUANTUM:
            qty = self.getQuantumFlop()
            self.log(f"{self.name} qty={qty}, remaining_flop={task.getRemainingFlop()}, diff={task.getRemainingFlop()-qty}")

            # if have less to burn in 1 quantum
            if qty >= task.getRemainingFlop():
                # get needed quantum for remaining flop to be yielded
                current_quantum = task.getRemainingFlop()/self.flops
                # task finished
                task.setRemainingFlop(0)
                self.log(f'execute_task: Task {task} finished at {self.env.now}')
                #self.log(f"execute_task: quantum {current_quantum}")
                TIMEOUT = current_quantum
            # normal quantum execution
            else:
                self.log(f'execute_task: before burst task {task} remaining_flop={task.getRemainingFlop()}')
                #self.log(f'Burst qty {qty}')
                task.decreaseRemainingFlop(qty)
                self.log(f'execute_task:  after burst task {task} remaining_flop={task.getRemainingFlop()} at {self.env.now}')
                TIMEOUT = QUANTUM
        else:
            self.log("execute_task: No quantum")
            exec_time = self.getTaskExecutionTime(task) * 1000
            # task finished
            task.setRemainingFlop(0)
            TIMEOUT = exec_time

        self.log(f"execute_task: TIMEOUT {TIMEOUT}")
        #print("timeout quantum", TIMEOUT)
        yield self.env.timeout(TIMEOUT)
        #yield TIMEOUT

    def getTaskEnergyConsumption(self, task: 'Task'):
        return self.getTaskExecutionTime(task) * self.getPower()

    def removeTask(self, task: 'Task'):
        if task in self.task_list:
            self.task_list.remove(task)

    def getQuantumFlop(self):
        q = self.scheduler.getQuantum()
        return q * self.getFlops()

    def getCycle(self) -> float:
        return ProcessingUnit.CYCLE

    def getPUName(self):
        return self.name

    def setPuName(self, name):
        self.name = name

    def getFlops(self):
        return self.flops

    def setFlops(self, flops):
        self.flops = flops

    def getMemory(self):
        return self.memory

    def setMemory(self, memory):
        self.memory = memory

    def getPower(self):
        return self.power

    def setPower(self, power):
        self.power = power

    def getMemoryBandwidth(self):
        return self.memory_bw

    def setMemoryBandwidth(self, memory_bw):
        self.memory_bw = memory_bw

    def getTaskList(self) -> List['Task']:
        return self.task_list

    def setTaskList(self, task_list: List['Task']):
        task: 'Task' = None
        for task in task_list:
            task.setCurrentPu(self)
            self.task_list.append(task)
            self.log(f'ProcessingUnit-setTaskList: {task.getTaskName()} submitted to {self.getPUName()}')

    def getScheduler(self) -> TaskSchedulingPolicy:
        return self.scheduler

    def setScheduler(self, scheduler: TaskSchedulingPolicy):
        self.scheduler = scheduler
    
    def log(self, message):
        pass
        #print(f"{END}{self.env.now}: {YELLOW}[{self.name}] {message}{END}")
    
    def show_stats(self):
        self.log(f"{self.name} Executed {self.executed_tasks} tasks")

    def setParent(self, parent):
        self.parent=parent
    
    def getParent(self):
        return self.parent
    
    def getQueueSize(self):
        return self.scheduler.getQueueSize()
    
    def getAvailability(self):
        n = self.getQueueSize() / self.getMaxQueueSize()
        # if n < .25:
        #     n = 0
        # elif n < .5:
        #     n  = 1
        # elif n < .75:
        #     n  = 2
        # elif n < 1:
        #     n  = 3
        return n

    def getMaxQueueSize(self):
        return self.MAX_QUEUE_SIZE

    def __repr__(self) -> str:
        return f"{self.name}"

class AGX(ProcessingUnit):
    currentVehicle = None
    idx = 0

    def __init__(self, scheduler: TaskSchedulingPolicy, env, capacity=1):
        name = f'AGX-{AGX.idx}'
        AGX.idx += 1
        flops = 11 * Units.tera
        memory = 32 * Units.giga
        power = 30  # 10W / 15W / 30W
        memory_bw = 137 * Units.giga
        CYCLE = 0.001
        super().__init__(flops, memory, power, memory_bw, scheduler, env, capacity, MAX_QUEUE_SIZE=200)
        super().setPuName(name)
    
    def getCurrentVehicle(self):
        return self.currentVehicle

    def setCurrentCurrentVehicle(self, vehicle: 'Vehicle'):
        self.currentVehicle = vehicle

class TX2(ProcessingUnit):
    currentVehicle = None
    idx = 0

    def __init__(self, scheduler: TaskSchedulingPolicy, env, capacity=1):
        name = f'TX2-{TX2.idx}'
        TX2.idx += 1
        flops = 1.33 * Units.tera
        memory = 8 * Units.giga
        power = 15  # 7.5W / 15W
        memory_bw = 59.7 * Units.giga
        super().__init__(flops, memory, power, memory_bw, scheduler, env, capacity, MAX_QUEUE_SIZE=300)
        super().setPuName(name)

    def getCurrentVehicle(self):
        return self.currentVehicle

    def setCurrentCurrentVehicle(self, vehicle: 'Vehicle'):
        self.currentVehicle = vehicle


# Values got from
# https://www.nvidia.com/fr-fr/data-center/tesla-v100/
class TeslaV100(ProcessingUnit):
    currentServer = None
    idx = 0

    def __init__(self, scheduler: TaskSchedulingPolicy, env, capacity=1):
        name = f'TeslaV100-{TeslaV100.idx}'
        TeslaV100.idx += 1
        flops = 112 * Units.tera
        memory = 32 * Units.giga
        power = 300
        memory_bw = 900 * Units.giga
        super().__init__(flops, memory, power, memory_bw, scheduler, env, capacity, MAX_QUEUE_SIZE=400)
        super().setPuName(name)

    def getCurrentServer(self):
        return self.currentServer

    def setCurrentServer(self, server: Server):
        self.currentServer = server


# Values got from
# https://images.nvidia.com/aem-dam/Solutions/Data-Center/nvidia-dgx-a100-datasheet.pdf
class DGXa100(ProcessingUnit):
    currentServer = None
    idx = 0

    def __init__(self, scheduler: TaskSchedulingPolicy, env, capacity=1):
        name = f'DGXa100-{DGXa100.idx}'
        DGXa100.idx += 1
        flops = 5 * Units.peta
        memory = 320 * Units.giga
        power = 6.5 * Units.kilo
        memory_bw = 2 * Units.tera
        super().__init__(flops, memory, power, memory_bw, scheduler, env, capacity, MAX_QUEUE_SIZE=500)
        super().setPuName(name)

    def getCurrentServer(self):
        return self.currentServer

    def setCurrentServer(self, server: Server):
        self.currentServer = server


UI_OPTIONS = [
    AGX, TX2, TeslaV100, DGXa100
]

def getProcessingUnit(name: str) -> ProcessingUnit:
    for option in UI_OPTIONS:
        if option.__name__ == name:
            return option
