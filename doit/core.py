import subprocess, sys, traceback
import StringIO

from odict import OrderedDict
from doit import logger

from doit.dependency import Dependency

class InvalidTask(Exception):pass
class TaskFailed(Exception):pass
class TaskError(Exception):pass

# interface 
class BaseTask(object):
    _dependencyManager = None 
    CAPTURE_OUT = False
    CAPTURE_ERR = False

    def __init__(self,name,action,dependencies=[]):
        """
        @param name string 
        @param action see derived classes
        @param dependencies list of absolute? file paths.
        """
        # check parameters make sense.
        if not(isinstance(dependencies,list) or isinstance(dependencies,tuple)):
            raise InvalidTask("'dependencies' paramater must be a list or tuple got:'%s' => %s"%(str(dependencies),dependencies.__class__))

        self.name = name
        self.action = action
        self.dependencies = dependencies

        if not BaseTask._dependencyManager:
            BaseTask._dependencyManager = Dependency(".doit.dbm")

    def check_execute(self):
        """execute if any dependency was modified
        @return True if executed, False if skipped execution"""
        # always execute task if there is no specified dependency.
        if not self.dependencies:
            self.execute()
            return True
        # check for dependencies before executing
        for d in self.dependencies:
            if self._dependencyManager.modified(self.name,d):
                self.execute()
                self.save_dependencies()
                return True
        return False

    def save_dependencies(self):
        """save dependencies value."""
        for d in self.dependencies:
            self._dependencyManager.save(self.name,d)


    def execute(self):
        """raise a TaskFailed or TaskError in case task was not completed"""
        pass

    def title(self):
        """return a string representing the task title"""
        return "%s => %s"%(self.name,str(self))


class CmdTask(BaseTask):

    def execute(self):
        if not self.CAPTURE_OUT:
            stdout = sys.__stdout__
        else:
            stdout = subprocess.PIPE

        if not self.CAPTURE_ERR:
            stderr = sys.__stderr__
        else:
            stderr = subprocess.PIPE
        
        try:
            p = subprocess.Popen(self.action,stdout=stdout,
                                 stderr=stderr)

        except OSError, e:
            raise TaskError("Error trying to execute the command: %s\n" % 
                             " ".join(self.action) + "    error: %s" % e)

        out,err = p.communicate()
        if out:
            logger.log('stdout',out)
        if err:
            logger.log('stderr',err)
        if p.returncode != 0:
            raise TaskFailed("Task failed")
            
    def __str__(self):
        return "Cmd: %s"%" ".join(self.action)

    def __repr__(self):
        return "<%s cmd:'%s'>"%(self.name," ".join(self.action))

class PythonTask(BaseTask):

    def __init__(self,name,action,dependencies=[],args=[],kwargs={}):
        BaseTask.__init__(self,name,action,dependencies)
        self.args = args
        self.kwargs = kwargs

    def execute(self):
        if self.CAPTURE_OUT:
            old_stdout = sys.stdout
            sys.stdout = StringIO.StringIO()

        if self.CAPTURE_ERR:
            old_stderr = sys.stderr
            sys.stderr = StringIO.StringIO()

        # TODO i guess a common mistake will be to pass a function
        # that returns a generator instead of passing the generator
        # itself. i could have a special test for this case.
        try:
            if not self.action(*self.args,**self.kwargs):
                raise TaskFailed("Task failed")
        finally:
            if self.CAPTURE_OUT:
                logger.log('stdout',sys.stdout.getvalue())
                sys.stdout.close()
                sys.stdout = old_stdout

            if self.CAPTURE_ERR:
                logger.log('stderr',sys.stderr.getvalue())
                sys.stderr.close()
                sys.stderr = old_stderr

            
        
    def __str__(self):
        # get object description excluding runtime memory address
        return "Python: %s"%str(self.action).split('at')[0][1:]

    def __repr__(self):
        return "<%s Python:'%s'>"%(self.name,repr(self.action))

class Runner(object):
    SUCCESS = 0
    FAILURE = 1
    ERROR = 2

    def __init__(self, verbosity=1):
        """
        verbosity
        # 0 => print (stderr and stdout) from failed tasks
        # 1 => print stderr and (stdout from failed tasks)
        # 2 => print stderr and stdout from all tasks
        """
        self.verbosity = verbosity
        self.success = None
        self._tasks = OrderedDict()
        
        BaseTask.CAPTURE_OUT = verbosity < 2
        BaseTask.CAPTURE_ERR = verbosity == 0

    def _addTask(self,task):
        # task must be a BaseTask
        if not isinstance(task,BaseTask):
            raise InvalidTask("Task must an instance of BaseTask class. %s"% 
                              (task.__class__))

        #task name must be unique
        if task.name in self._tasks:
            raise InvalidTask("Task names must be unique. %s"%task.name)
        # add
        self._tasks[task.name] = task

    def run(self, printTitle=True):
        """@param print_title bool print task title """
        for task in self._tasks.itervalues():
            # clear previous output
            logger.clear('stdout')
            logger.clear('stderr')

            try:                
                # print title
                if printTitle:
                    print task.title()
            
                task.check_execute()

            # task failed
            except TaskFailed, e:
                self.success = False
                logger.log("stdout",str(e)+'\n')
                return self.done(self.FAILURE)
            # task error
            except Exception:
                self.success = False
                return self.done(self.ERROR)
        
        self.success = True
        #done
        return self.done(self.SUCCESS)

    def done(self,result):
        # update dependencies 
        BaseTask._dependencyManager.close()
        BaseTask._dependencyManager = None

        # if test fails print output from failed task
        if result != self.SUCCESS:
            logger.flush('stdout',sys.stdout)
            logger.flush('stderr',sys.stderr)
        
        # always show traceback for whatever exception
        if result == self.ERROR:
            sys.stderr.write(traceback.format_exc())
        
        return result