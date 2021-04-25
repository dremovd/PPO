import os
import sys
import json
import time
import random
import platform
import math

import socket
HOST_NAME = socket.gethostname()

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

DEVICE="auto"
OUTPUT_FOLDER="./Run"
WORKERS=8

if len(sys.argv) == 3:
    DEVICE = sys.argv[2]


tuned_args = {
        'checkpoint_every': int(5e6),
        'workers': WORKERS,
        'env_name': 'DemonAttack',
        'epochs': 50,
        'max_grad_norm': 0.5,
        'agents': 128,
        'n_steps': 128,
        'policy_mini_batch_size': 512,      # does this imply microbatching is broken?
        'value_mini_batch_size': 512,
        'value_epochs': 2,                  # this seems really low?
        'policy_epochs': 4,
        'target_kl': 0.01,
        'ppo_epsilon': 0.05,
        'value_lr': 5e-4,                   # a bug caused this to be policy_lr...
        'policy_lr': 2.5e-4,
        'gamma': 0.999,
    }

v8_args = {
    'use_tvf': True,
    'tvf_hidden_units': 128,

    'tvf_horizon_samples': 128,
    'tvf_value_samples': 128,

    'tvf_lambda': -16,
    'tvf_coef': 0.01,
    'tvf_max_horizon': 3000,
    'gamma': 0.999,
    'tvf_gamma': 0.999,

    # required due to bug fix
    'value_lr': 2.5e-4,

    'tvf_loss_weighting': "advanced",
    'tvf_h_scale': "squared",

    **tuned_args,
}

# initial long horizon test... :)
better_args = {
    'checkpoint_every': int(5e6),
    'workers': WORKERS,
    'env_name': 'DemonAttack',
    'epochs': 50,
    'max_grad_norm': 5,             # more than before  [mode=5]
    'agents': 128,                  #                   [mode=128]
    'n_steps': 32,                  # less than before  [mode=128] (higher better)
    'policy_mini_batch_size': 1024, # more than before  [mode=1024]
    'value_mini_batch_size': 512,   #                   [mode=512] (lower better)
    'value_epochs': 4,              # more than before  [mode=2]
    'policy_epochs': 4,             #                   [mode=4] (higher better)
    'target_kl': 0.10,              # much more than before (see if this is an issue...) [no mode]
    'ppo_epsilon': 0.05,            # why so low?       [mode=0.05] (lower is better, but 0.3 works too?)
    'value_lr': 1e-4,               # much lower        [no mode]
    'policy_lr': 5e-4,              # higher? weird...  [mode=2.5e-4]
    'gamma': 0.999,
}

tvf_tuned_adv_args = {
    'use_tvf': True,
    'tvf_hidden_units': 128,
    'tvf_n_horizons': 128,
    'tvf_lambda': 1.0,
    'tvf_coef': 0.01,
    'tvf_max_horizon': 3000,
    'gamma': 0.999,
    'tvf_gamma': 0.999,
    'tvf_loss_weighting': "advanced",
    'tvf_h_scale': "squared",
    **tuned_args
}


# inspired mostly from new PPO search, but only to 10m...
# these did not work...
new_args = {
        'checkpoint_every': int(5e6),
        'workers': WORKERS,
        'env_name': 'DemonAttack',
        'epochs': 50,
        'max_grad_norm': 5,
        'agents': 256,                      # more is probably better
        'n_steps': 128,                     # hard to know, but atleast we are now free the MC algorithm
        'policy_mini_batch_size': 1024,
        'value_mini_batch_size': 256,       # smaller is probably better
        'value_epochs': 2,                  # I probably want 4 with early stopping
        'policy_epochs': 4,
        'target_kl': 0.01,                  # need to search more around this
        'ppo_epsilon': 0.1,                 # hard to say if this is right...
        'value_lr': 2.5e-4,                 # slow and steady wins the race
        'policy_lr': 2.5e-4,

        'use_tvf': True,
        'tvf_hidden_units': 128,            # big guess here
        'tvf_value_samples': 128,           # big guess here
        'tvf_horizon_samples': 32,          # 32 has been shown to be enough
        'tvf_lambda': -16,                  # n-steps is great
        'tvf_coef': 0.01,                   # big guess
        'tvf_max_horizon': 3000,            # could be much higher if we wanted
        'gamma': 0.999,
        'tvf_gamma': 0.999,                 # rediscounting is probably a good idea...
        'tvf_loss_weighting': "advanced",   # these seem to help
        'tvf_h_scale': "squared",
    }


# this are the 'fast but good' settings.
optimized_args = {
        'checkpoint_every': int(5e6),
        'workers': WORKERS,
        'env_name': 'DemonAttack',
        'epochs': 50,
        'max_grad_norm': 5.0,
        'agents': 256,                      # more is probably better
        'n_steps': 128,                     # hard to know, but atleast we are now free the MC algorithm
        'policy_mini_batch_size': 1024,
        'value_mini_batch_size': 256,       # smaller is probably better
        'value_epochs': 2,                  # I probably want 4 with early stopping
        'policy_epochs': 4,
        'target_kl': 0.01,                  # need to search more around this
        'ppo_epsilon': 0.1,                 # hard to say if this is right...
        'value_lr': 2.5e-4,                 # slow and steady wins the race
        'policy_lr': 2.5e-4,

        'use_tvf': True,
        'tvf_hidden_units': 128,            # big guess here
        'tvf_value_samples': 128,           # reducing from 128 samples to 64 is fine, even 16 would work.
        'tvf_horizon_samples': 32,          # 32 has been shown to be better than 128
        'tvf_return_mixing': 1,             # just makes things slowe to use more than 1
        'tvf_lambda': -16,
        'tvf_lambda_samples': 32,           # being cautious here...
        'tvf_coef': 0.01,                   # big guess
        'tvf_max_horizon': 3000,            # could be much higher if we wanted
        'gamma': 0.999,
        'tvf_gamma': 0.999,                 # rediscounting is probably a good idea...
        'tvf_loss_weighting': "advanced",   # these seem to help
        'tvf_h_scale': "squared",
    }

# tweaked optimized settings with constant h_scale
v13_args = {
        'checkpoint_every': int(5e6),
        'workers': WORKERS,
        'epochs': 50,
        'max_grad_norm': 20.0,
        'agents': 256,                      # more is probably better
        'n_steps': 128,                     # hard to know, but at least we are now free the MC algorithm
        'policy_mini_batch_size': 1024,
        'value_mini_batch_size': 256,       # smaller is probably better
        'value_epochs': 4,                  # I probably want 4 with early stopping
        'policy_epochs': 4,
        'target_kl': 0.01,                  # need to search more around this
        'ppo_epsilon': 0.1,                 # hard to say if this is right...
        'value_lr': 2.5e-4,                 # slow and steady wins the race
        'policy_lr': 2.5e-4,
        'export_video': False,               # in general not needed

        'use_tvf': True,
        'tvf_hidden_units': 128,            # big guess here
        'tvf_value_samples': 128,           # reducing from 128 samples to 64 is fine, even 16 would work.
        'tvf_horizon_samples': 64,          # 32 has been shown to be better than 128
        'tvf_lambda': -16,
        'tvf_lambda_samples': 32,
        'tvf_coef': 0.1,
        'tvf_max_horizon': 3000,
        'gamma': 0.999,
        'tvf_gamma': 0.999,
    }


# tweaked optimized settings from regression run
v14_args = v13_args.copy()
v14_args.update({
    'tvf_horizon_distribution': 'advanced',
    'tvf_horizon_scale': 'centered',
    'tvf_update_return_freq': 4,
}
)

v14_fast = v13_args.copy()
v14_fast.update({
    'tvf_horizon_distribution': 'advanced',
    'tvf_horizon_scale': 'centered',
    'tvf_update_return_freq': 4,
    'value_epochs': 2,
}
)

# this are based on the best model from PPO HPS at 10M
best10_args = {
        'checkpoint_every': int(5e6),
        'workers': WORKERS,
        'epochs': 50,
        'max_grad_norm': 20.0,
        'agents': 64,
        'n_steps': 256,
        'policy_mini_batch_size': 512,
        'value_mini_batch_size': 512,
        'value_epochs': 6,
        'policy_epochs': 4,
        'target_kl': 0.1,
        'ppo_epsilon': 0.1,                 # hard to say if this is right...
        'value_lr': 2.5e-4,                 # value should be 5e-4... but I don't want to do it for TVF
        'policy_lr': 2.5e-4,

        'use_tvf': True,
        'tvf_hidden_units': 128,
        'tvf_value_samples': 128,
        'tvf_horizon_samples': 32,
        'tvf_return_mixing': 1,
        'tvf_lambda': -16,
        'tvf_lambda_samples': 64,
        'tvf_coef': 0.01,
        'tvf_max_horizon': 3000,
        'gamma': 0.999,
        'tvf_gamma': 0.999,
        'tvf_loss_weighting': "advanced",
        'tvf_h_scale': "squared",
    }


def add_job(experiment_name, run_name, priority=0, chunk_size:int=10, default_params=None, score_threshold=None, **kwargs):

    if default_params is not None:
        for k,v in default_params.items():
            if k not in kwargs:
                kwargs[k]=v

    if "device" not in kwargs:
        kwargs["device"] = DEVICE

    job = Job(experiment_name, run_name, priority, chunk_size, kwargs)

    if score_threshold is not None and chunk_size > 0:
        job_details = job.get_details()
        if job_details is not None and 'score' in job_details:
            modified_kwargs = kwargs.copy()
            chunks_completed = job_details['completed_epochs'] / chunk_size
            if job_details['score'] < score_threshold * chunks_completed and chunks_completed > 0.75:
                modified_kwargs["epochs"] = chunk_size
            job = Job(experiment_name, run_name, priority, chunk_size, modified_kwargs)

    job_list.append(job)
    return job

def get_run_folders(experiment_name, run_name):
    """ Returns the paths for given experiment and run, or empty list if not found. """

    path = os.path.join(OUTPUT_FOLDER, experiment_name)
    if not os.path.exists(path):
        return []

    result = []

    for file in os.listdir(path):
        name = os.path.split(file)[-1]
        this_run_name = name[:-(8+3)]  # crop off the id code.
        if this_run_name == run_name:
            result.append(os.path.join(path, name))
    return result

def copy_source_files(source, destination, force=False):
    """ Copies all source files from source path to destination. Returns path to destination training script. """
    try:

        destination_train_script = os.path.join(destination, "train.py")

        if not force and os.path.exists(destination_train_script):
            return destination_train_script
        # we need to copy across train.py and then all the files under rl...
        os.makedirs(os.path.join(destination, "rl"), exist_ok=True)
        if platform.system() == "Windows":
            copy_command = "copy"
        else:
            copy_command = "cp"

        os.system("{} {} '{}'".format(copy_command, os.path.join(source, "train.py"), os.path.join(destination, "train.py")))
        os.system("{} {} '{}'".format(copy_command, os.path.join(source, "rl", "*.py"), os.path.join(destination, "rl")))

        return destination_train_script
    except Exception as e:
        print("Failed to copy training file to log folder.", e)
        return None


class Job:

    """
    Note: we don't cache any of the properties here as other worker may modify the filesystem, so we need to always
    use the up-to-date version.
    """

    # class variable to keep track of insertion order.
    id = 0

    def __init__(self, experiment_name, run_name, priority, chunk_size:int, params):
        self.experiment_name = experiment_name
        self.run_name = run_name
        self.priority = priority
        self.params = params
        self.id = Job.id
        self.chunk_size = chunk_size
        Job.id += 1

    def __lt__(self, other):
         return self._sort_key < other._sort_key

    @property
    def _sort_key(self):

        status = self.get_status()

        priority = self.priority

        # make running tasks appear at top...
        if status == "running":
            priority += 1000

        # if "search" in self.experiment_name.lower():
        #     # with search we want to make sure we complete partial runs first
        #     priority = priority + self.get_completed_epochs()
        # else:
        #     priority = priority - self.get_completed_epochs()

        priority = priority - self.get_completed_epochs()

        return (-priority, self.get_completed_epochs(), self.experiment_name, self.id)

    def get_path(self):
        # returns path to this job. or none if not found
        paths = self.get_paths()
        return paths[0] if len(paths) > 0 else None

    def get_paths(self):
        # returns list of paths for this jo
        return get_run_folders(self.experiment_name, self.run_name)

    def get_status(self):
        """
        Returns job status

        "": Job has not been started
        "clash": Job has multiple folders matching job name
        "running" Job is currently running
        "pending" Job has been started not not currently active
        "stale: Job has a lock that has not been updated in 30min

        """

        paths = self.get_paths()
        if len(paths) >= 2:
            return "clash"

        if len(paths) == 0:
            return ""

        status = ""

        path = paths[0]

        if os.path.exists(os.path.join(path, "params.txt")):
            status = "pending"

        if os.path.exists(os.path.join(path, "lock.txt")):
            status = "running"

        details = self.get_details()
        if details is not None and details["fraction_complete"] >= 1.0:
            status = "done"

        if status in ["running"] and self.minutes_since_modified() > 30:
            status = "stale"

        return status

    def minutes_since_modified(self):
        path = self.get_path()
        if path is None:
            return -1
        if os.path.exists(os.path.join(path, "lock.txt")):
            last_modifed = os.path.getmtime(os.path.join(path, "lock.txt"))
            return (time.time()-last_modifed)/60
        return -1

    def get_params(self):
        try:
            path = os.path.join(self.get_path(), "params.txt")
            return json.load(open(path, "r"))
        except:
            return None

    def get_details(self):
        try:
            path = os.path.join(self.get_path(), "progress.txt")

            details = json.load(open(path, "r"))

            # if max_epochs has changed fix up the fraction_complete.
            if details["max_epochs"] != self.params["epochs"]:
                details["fraction_complete"] = details["completed_epochs"] / self.params["epochs"]
                details["max_epochs"] = self.params["epochs"]
                details["eta"] = (details["max_epochs"] - details["completed_epochs"]) * 1e6 / details["fps"]

            return details
        except:
            return None

    def get_completed_epochs(self):
        details = self.get_details()
        if details is not None:
            return details["completed_epochs"]
        else:
            return 0

    def run(self, chunk_size:int):

        self.params["output_folder"] = OUTPUT_FOLDER

        experiment_folder = os.path.join(OUTPUT_FOLDER, self.experiment_name)

        # make the destination folder...
        if not os.path.exists(experiment_folder):
            print("Making new experiment folder {experiment_folder}")
            os.makedirs(experiment_folder, exist_ok=True)

        # copy script across if needed.
        train_script_path = copy_source_files("./", experiment_folder)

        self.params["experiment_name"] = self.experiment_name
        self.params["run_name"] = self.run_name

        details = self.get_details()

        if details is not None and details["completed_epochs"] > 0:
            # restore if some work has already been done.
            self.params["restore"] = True
            print(f"Found restore point {self.get_path()} at epoch {details['completed_epochs']}")
        else:
            print(f"No restore point found for path {self.get_path()}")

        if chunk_size > 0:
            # work out the next block to do
            if details is None:
                next_chunk = chunk_size
            else:
                next_chunk = (round(details["completed_epochs"] / chunk_size) * chunk_size) + chunk_size
            self.params["limit_epochs"] = int(next_chunk)


        python_part = "python {} {}".format(train_script_path, self.params["env_name"])

        params_part = " ".join([f"--{k}={nice_format(v)}" for k, v in self.params.items() if k not in ["env_name"] and v is not None])
        params_part_lined = "\n".join([f"--{k}={nice_format(v)}" for k, v in self.params.items() if k not in ["env_name"] and v is not None])

        print()
        print("=" * 120)
        print(bcolors.OKGREEN+self.experiment_name+" "+self.run_name+bcolors.ENDC)
        print("Running " + python_part + "\n" + params_part_lined)
        print("=" * 120)
        print()
        return_code = os.system(python_part + " " + params_part)
        if return_code != 0:
            raise Exception("Error {}.".format(return_code))

def run_next_experiment(filter_jobs=None):

    job_list.sort()

    for job in job_list:
        if filter_jobs is not None and not filter_jobs(job):
            continue
        status = job.get_status()

        if status in ["", "pending"]:

            job.get_params()

            job.run(chunk_size=job.chunk_size)
            return

def comma(x):
    if type(x) is int or (type(x) is float and x >= 100):
        postfix = ''
        # if x > 100*1e6:
        #     postfix = 'M'
        #     x /= 1e6
        # elif x > 100*1e3:
        #     postfix = 'K'
        #     x /= 1e3
        return f"{int(x):,}{postfix}"
    elif type(x) is float:
        return f"{x:.1f}"
    else:
        return str(x)

def show_experiments(filter_jobs=None, all=False):
    job_list.sort()
    print("-" * 161)
    print("{:^10}{:<20}{:<60}{:>10}{:>10}{:>10}{:>10}{:>10}{:>10}{:>10}".format("priority", "experiment_name", "run_name", "complete", "status", "eta", "fps", "score", "host", "ping"))
    print("-" * 161)
    for job in job_list:

        if filter_jobs is not None and not filter_jobs(job):
                continue

        status = job.get_status()

        if status == "done" and not all:
            continue

        details = job.get_details()

        if details is not None:
            percent_complete = "{:.1f}%".format(details["fraction_complete"]*100)
            eta_hours = "{:.1f}h".format(details["eta"] / 60 / 60)
            score = details["score"]
            if score is None: score = 0
            score = comma(score)
            host = details["host"][:8] if status == "running" else ""
            fps = int(details["fps"])
            minutes = job.minutes_since_modified()
            ping = f"{minutes:.0f}" if minutes >= 0 else ""
        else:
            percent_complete = ""
            eta_hours = ""
            score = ""
            host = ""
            fps = ""
            ping = ""

        print("{:^10}{:<20}{:<60}{:>10}{:>10}{:>10}{:>10}{:>10}{:>10}{:>10}".format(
            job.priority, job.experiment_name[:19], job.run_name, percent_complete, status, eta_hours, comma(fps), comma(score), host, ping))


def show_fps(filter_jobs=None):
    job_list.sort()

    fps = {}

    for job in job_list:

        if filter_jobs is not None and not filter_jobs(job):
            continue

        status = job.get_status()

        if status == "running":
            details = job.get_details()
            if details is None:
                continue
            host = details["host"]
            if host not in fps:
                fps[host] = 0
            fps[host] += int(details["fps"])

    for k,v in fps.items():
        print(f"{k:<20} {v:,.0f} FPS")


def random_search_old(run:str, main_params: dict, search_params:dict, envs: list, score_thresholds: list, count: int = 128,
                  max_batch_size=None
                  ):

    assert len(envs) == len(score_thresholds)

    for i in range(count):
        params = {}
        random.seed(i)
        for k, v in search_params.items():
            params[k] = random.choice(v)

        # make sure params aren't too high (due to memory)
        # todo: remove this constraint...
        if max_batch_size is not None:
            while params["agents"] * params["n_steps"] > max_batch_size:
                params["agents"] //= 2

        while params["agents"] * params["n_steps"] < params["policy_mini_batch_size"]:
            params["policy_mini_batch_size"] //= 2

        while params["agents"] * params["n_steps"] < params["value_mini_batch_size"]:
            params["value_mini_batch_size"] //= 2

        for env_name, score_threshold in zip(envs, score_thresholds):
            main_params['env_name'] = env_name
            add_job(run, run_name=f"{i:04d}_{env_name}", chunk_size=10, score_threshold=score_threshold, **main_params, **params)


def random_search(run:str, main_params: dict, search_params:dict, envs: list, score_thresholds: list, count: int = 128,
                  max_batch_size=64*1024
                  ):

    assert len(envs) == len(score_thresholds)

    for i in range(count):
        params = {}
        random.seed(i)
        for k, v in search_params.items():
            params[k] = v.sample()

        # enabled compression if batch_size is large than some limit
        if max_batch_size is not None and params["agents"] * params["n_steps"] >= max_batch_size:
                params["use_compression"] = True

        while params["agents"] * params["n_steps"] < params["policy_mini_batch_size"]:
            params["policy_mini_batch_size"] //= 2

        while params["agents"] * params["n_steps"] < params["value_mini_batch_size"]:
            params["value_mini_batch_size"] //= 2

        for env_name, score_threshold in zip(envs, score_thresholds):
            main_params['env_name'] = env_name
            add_job(run, run_name=f"{i:04d}_{env_name}", chunk_size=10, score_threshold=score_threshold, **main_params, **params)



def nice_format(x):
    if type(x) is str:
        return f'"{x}"'
    if x is None:
        return "None"
    if type(x) in [int, float, bool]:
        return str(x)

    return f'"{x}"'

# ---------------------------------------------------------------------------------------------------------

def setup_experiments_13_eval():

    for env_name in ["Alien", "BankHeist", "CrazyClimber"]:
        add_job(
            f"TVF_13_Test_64",
            run_name=f"{env_name}",
            env_name=env_name,
            epochs=50,
            tvf_horizon_samples=64,
            default_params=v14_args, # v14 are just the tuned v13
            priority=0,
        )
        add_job(
            f"TVF_13_Test_256",
            run_name=f"{env_name}",
            env_name=env_name,
            tvf_horizon_samples=256,
            epochs=50,
            default_params=v14_args,  # v14 are just the tuned v13
            priority=0,
        )
        add_job(
            # why not give it a try...
            f"TVF_13_Test_512_LH",
            run_name=f"{env_name}",
            env_name=env_name,
            tvf_horizon_samples=512,
            gamma=1.0,
            tvf_gamma=1.0,
            epochs=50,
            default_params=v14_args,  # v14 are just the tuned v13
            priority=0,
        )

class Categorical():

    def __init__(self, *args):
        self._values = args

    def sample(self):
        return random.choice(self._values)


class Uniform():
    def __init__(self, min, max):
        self._min = min
        self._max = max

    def sample(self):
        r = (self._max-self._min)
        a = self._min
        return a + random.random() * r

class LogUniform():
    def __init__(self, min, max, force_int=False):
        self._min = math.log(min)
        self._max = math.log(max)
        self._force_int = force_int

    def sample(self):
        r = (self._max - self._min)
        a = self._min
        result = math.exp(a + random.random() * r)
        return int(result) if self._force_int else result

def random_search_14_tvf():

    main_params = {
        'checkpoint_every': int(5e6),
        'workers': WORKERS,
        'export_video': False, # save some space...
        'use_tvf': True,
        'gamma': 0.999,
        'epochs': 50,
        'priority': -100,
    }

    search_params = {

        # ppo params
        'max_grad_norm':    LogUniform(10, 50),
        'agents':           LogUniform(128, 1024, force_int=True),
        'n_steps':          LogUniform(128, 1024, force_int=True),

        'policy_mini_batch_size': LogUniform(256, 1024, force_int=True),
        'value_mini_batch_size': LogUniform(256, 1024, force_int=True),

        'value_epochs':     Categorical(2, 3, 4, 6),
        'policy_epochs':    Categorical(2, 3, 4, 6),
        'target_kl':        LogUniform(0.01, 1.0),
        'ppo_epsilon':      Uniform(0.03, 0.3),
        'value_lr':         LogUniform(1e-4, 5e-4),
        'policy_lr':        LogUniform(1e-4, 5e-4),
        'entropy_bonus':    LogUniform(0.003, 0.03),

        # tvf params
        'tvf_coef':         LogUniform(0.01, 0.3),
        'tvf_gamma':        Categorical(0.999, 0.9999, 1.0),
        'tvf_lambda':       Categorical(-8, -16, -32, "exp", "adaptive"),
        'tvf_adaptive_ratio': LogUniform(0.01, 1.0), # only used with adaptive

        'time_aware':       Categorical(True, False),
        'tvf_max_horizon':  LogUniform(1000, 9000, force_int=True),
        'tvf_value_samples': LogUniform(32, 256, force_int=True),
        'tvf_horizon_samples': LogUniform(32, 256, force_int=True),
        'tvf_value_distribution': Categorical("uniform", "advanced"),
        'tvf_horizon_distribution': Categorical("uniform", "advanced"),
        'tvf_hidden_units': LogUniform(32, 1024, force_int=True),
        'tvf_soft_anchor': LogUniform(0.03, 3.0),
        'tvf_update_return_freq': Categorical(1, 2, 4),
        'tvf_horizon_scale': Categorical("default", "centered", "wide"),
        'tvf_time_scale': Categorical("default", "centered", "wide", "zero"),
    }

    # score threshold should be 200, but I want some early good results...
    random_search(
        "TVF_14_Search_999",
        main_params,
        search_params,
        count=32,
        envs=['BattleZone', 'DemonAttack', 'Amidar'],
        # set roughly to 2x random
        score_thresholds=[4000, 300, 10],
    )


def random_search_11_ppo():
    main_params = {
        'checkpoint_every': int(5e6),
        'workers': WORKERS,
        'export_video': False, # save some space...
        'use_tvf': False,
        'gamma': 0.999,
        'epochs': 50,
        'priority': -20,
    }

    search_params = {
        'max_grad_norm': [0.5, 5, 20.0],    # should have little to no effect
        'agents': [64, 128, 256, 512],      # I expect more is better
        'n_steps': [16, 32, 64, 128, 256],  # I expect more is better
        'policy_mini_batch_size': [512, 1024, 2048],
        'value_mini_batch_size': [256, 512, 1024, 2048], #I expect lower is better
        'value_epochs': [1, 2, 4, 6],
        'policy_epochs': [1, 2, 4, 6],
        'target_kl': [0.01, 0.03, 0.1, 1.0],  # 1.0 is effectively off
        'ppo_epsilon': [0.05, 0.1, 0.2, 0.3], # I have only gotten <= 0.1 to work so far
        'value_lr': [1e-4, 2.5e-4, 5e-4],
        'policy_lr': [1e-4, 2.5e-4, 5e-4],
        'vf_coef': [0.25, 0.5, 1.0],          # I don't think this matters?
        'entropy_bonus': [0.003, 0.01, 0.03]  # probably will not make much difference
    }

    # score threshold should be 200, but I want some early good results...
    random_search_old(
        "TVF_11_Search_PPO",
        main_params,
        search_params,
        count=32,
        envs=['BattleZone', 'DemonAttack', 'Amidar'],
        # set roughty to 2x random
        score_thresholds=[4000, 300, 10],
        max_batch_size=64*1024,
    )

def setup_experiments_13():

    for scale in ["centered"]:
        for tvf_ceof in [0.1, 0.01]:
            for distribution in ["uniform", "advanced"]:
                add_job(
                    f"TVF_13_Regression",
                    env_name="DemonAttack",
                    run_name=f"tvf_ceof={tvf_ceof} distribution={distribution} scale={scale}",
                    tvf_horizon_scale=scale,
                    tvf_horizon_distribution=distribution,
                    tvf_coef=tvf_ceof,
                    default_params=v13_args,
                    epochs=50,
                    priority=1000,
                )

    for gamma in [0.9, 0.99, 0.999, 0.9999, 1.0]:
        for timeout in [100*4, 1000*4]:
            add_job(
                f"TVF_13_TimeLimited",
                env_name="DemonAttack",
                timeout=timeout,
                run_name=f"timeout={timeout} gamma={gamma}",
                tvf_gamma=gamma,
                gamma=gamma,
                default_params=v13_args,
                epochs=20 if timeout == 400 else 30,
                priority=50,
            )

    for soft_anchor in [0, 1, 10]:
        add_job(
            f"TVF_13_SoftAnchor",
            env_name="DemonAttack",
            timeout=100*4,
            run_name=f"soft_anchor={soft_anchor}",
            tvf_soft_anchor=soft_anchor,
            default_params=v13_args,
            epochs=10,
            priority=250,
        )

    for weighting in ["default", "advanced"]:
        add_job(
            f"TVF_13_SoftAnchor",
            env_name="DemonAttack",
            timeout=100 * 4,
            run_name=f"samples=512 weighting={weighting}",
            tvf_loss_weighting=weighting,
            tvf_horizon_samples=512,
            tvf_value_samples=512,
            default_params=v13_args,
            epochs=10,
            priority=250,
        )

    for weighting in ["default", "advanced"]:
        add_job(
            f"TVF_13_SoftAnchor",
            env_name="DemonAttack",
            timeout=100 * 4,
            run_name=f"samples=128-64 weighting={weighting}",
            tvf_loss_weighting=weighting,
            default_params=v13_args,
            epochs=10,
            priority=250,
        )

    for horizon_scale in ["default", "unscaled", "centered"]:
        add_job(
            f"TVF_13_ImprovedTimeAware",
            env_name="DemonAttack",
            timeout=300*4,
            run_name=f"scale={horizon_scale} (300 step)",
            tvf_horizon_scale=horizon_scale,
            default_params=v13_args,
            epochs=10,
            priority=450,
        )

        add_job(
            f"TVF_13_ImprovedTimeAware",
            env_name="DemonAttack",
            timeout=1000 * 4,
            run_name=f"scale={horizon_scale} (10k step)",
            tvf_horizon_scale=horizon_scale,
            default_params=v13_args,
            epochs=10,
            priority=50,
        )

    # interested in ev and horizon quality among other things..
    for samples in [16, 32, 64, 128, 256, 512]:
        for distribution in ["uniform", "advanced"]:
            add_job(
                f"TVF_13_HorizonSampling",
                env_name="DemonAttack",
                timeout=300*4,
                run_name=f"distribution={distribution} samples={samples} (300 step)",
                tvf_horizon_distribution=distribution,
                tvf_horizon_samples=samples,
                default_params=v13_args,
                epochs=20,
                priority=50,
            )

    # these are my horizon quality experiments, want to get to the bottom of this
    # is there a bug with timeout terminals?
    for samples in [16, 256]:
        add_job(
            f"TVF_13_HQ_1000_Breakout",
            env_name="Breakout",
            timeout=1000 * 4,
            run_name=f"samples={samples}",
            tvf_horizon_distribution="advanced",
            tvf_horizon_samples=samples,
            tvf_horizon_scale="centered",
            default_params=v13_args,
            epochs=20,
            priority=0,
        )

        add_job(
            f"TVF_13_HQ_1000_Deferred",
            env_name="DemonAttack",
            timeout=1000 * 4,
            run_name=f"samples={samples}",
            tvf_horizon_distribution="advanced",
            tvf_horizon_samples=samples,
            deferred_rewards=True,
            tvf_horizon_scale="centered",
            default_params=v13_args,
            epochs=20,
            priority=0,
        )

        add_job(
            f"TVF_13_HQ_1000_NoNoop",
            env_name="DemonAttack",
            timeout=1000 * 4,
            run_name=f"samples={samples}",
            tvf_horizon_distribution="advanced",
            tvf_horizon_samples=samples,
            noop_start=False,
            tvf_horizon_scale="centered",
            default_params=v13_args,
            epochs=20,
            priority=0,
        )

    for noop_duration in [0, 15, 30, 60, 120]:
        add_job(
            f"TVF_13_HQ_1000_Noop",
            env_name="DemonAttack",
            timeout=1000 * 4,
            run_name=f"noop_duration={noop_duration}",
            tvf_horizon_distribution="advanced",
            noop_duration=noop_duration,
            tvf_horizon_scale="centered",
            default_params=v13_args,
            epochs=10,
            priority=50,
        )


    # # finally fixed the horizon bugs, want to see if it helps?
    # for samples in [256]:
    #     add_job(
    #         f"TVF_13_BugFix_Breakout",
    #         env_name="Breakout",
    #         timeout=1000 * 4,
    #         run_name=f"samples={samples}",
    #         tvf_horizon_distribution="advanced",
    #         tvf_horizon_samples=samples,
    #         tvf_horizon_scale="centered",
    #         default_params=v13_args,
    #         epochs=20,
    #         priority=50,
    #     )

        # add_job(
        #     f"TVF_13_BugFix_Breakout",
        #     env_name="Breakout",
        #     timeout=1000 * 4,
        #     run_name=f"samples={samples} horizon=1000",
        #     tvf_max_horizon=1000,
        #     tvf_horizon_distribution="advanced",
        #     tvf_horizon_samples=samples,
        #     tvf_horizon_scale="centered",
        #     default_params=v13_args,
        #     epochs=20,
        #     priority=50,
        # )

    # add_job(
    #     f"TVF_13_BugFix_Deferred",
    #     env_name="DemonAttack",
    #     timeout=1000 * 4,
    #     run_name=f"samples={samples}",
    #     tvf_horizon_distribution="advanced",
    #     tvf_horizon_samples=samples,
    #     deferred_rewards=True,
    #     tvf_horizon_scale="centered",
    #     default_params=v13_args,
    #     epochs=20,
    #     priority=50,
    # )
    #
    # add_job(
    #     f"TVF_13_BugFix_Deferred",
    #     env_name="DemonAttack",
    #     timeout=1000 * 4,
    #     run_name=f"samples={samples} horizon=1000",
    #     tvf_max_horizon=1000,
    #     tvf_horizon_distribution="advanced",
    #     tvf_horizon_samples=samples,
    #     deferred_rewards=True,
    #     tvf_horizon_scale="centered",
    #     default_params=v13_args,
    #     epochs=20,
    #     priority=50,
    # )
    #
    # add_job(
    #     f"TVF_13_BugFix_Deferred",
    #     env_name="DemonAttack",
    #     timeout=1000 * 4,
    #     run_name=f"h_samples=512 v_samples=512 horizon=1000",
    #     tvf_max_horizon=1000,
    #     tvf_horizon_distribution="advanced",
    #     tvf_horizon_samples=512,
    #     tvf_value_samples=512,
    #     deferred_rewards=True,
    #     tvf_horizon_scale="centered",
    #     default_params=v13_args,
    #     epochs=20,
    #     priority=50,
    # )

    for ta in [True, False]:
        for h_in in [True, False]:
            add_job(
                # with better weight initialization
                f"TVF_13_BugFix_Deferred3",
                env_name="DemonAttack",
                timeout=500 * 4,
                run_name=f"ta={ta} hin={h_in}",
                tvf_horizon_distribution="advanced",
                tvf_horizon_samples=128,
                tvf_value_samples=128,
                tvf_max_horizon=1000,
                deferred_rewards=True,
                tvf_horizon_scale="centered",

                default_params=v14_args,

                time_aware=ta,
                tvf_time_scale="centered" if h_in else "zero",

                epochs=10,
                priority=100,
            )

    add_job(
        f"TVF_13_BugFix_Deferred4",
        env_name="DemonAttack",
        timeout=500 * 4,
        run_name=f"halfway",
        tvf_horizon_distribution="advanced",
        tvf_horizon_samples=128,
        tvf_value_samples=128,
        tvf_max_horizon=1000,
        deferred_rewards=250,
        tvf_horizon_scale="centered",

        default_params=v14_args,

        time_aware=True,
        tvf_time_scale="centered",

        epochs=10,
        priority=100,
    )

    add_job(
        f"TVF_13_BugFix_Deferred4",
        env_name="DemonAttack",
        timeout=500 * 4,
        run_name=f"halfway no_anchor",
        tvf_horizon_distribution="advanced",
        tvf_horizon_samples=128,
        tvf_value_samples=128,
        tvf_max_horizon=1000,
        tvf_soft_anchor=0,
        deferred_rewards=250,
        tvf_horizon_scale="centered",

        default_params=v14_args,

        time_aware=True,
        tvf_time_scale="centered",

        epochs=10,
        priority=100,
    )

    add_job(
        f"TVF_13_BugFix_Deferred4",
        env_name="DemonAttack",
        timeout=500 * 4,
        run_name=f"halfway nodesync",
        tvf_horizon_distribution="advanced",
        tvf_horizon_samples=128,
        tvf_value_samples=128,
        tvf_max_horizon=1000,
        tvf_soft_anchor=0,
        deferred_rewards=250,
        tvf_horizon_scale="centered",

        default_params=v14_args,
        env_desync=False,

        time_aware=True,
        tvf_time_scale="centered",

        epochs=10,
        priority=100,
    )

    add_job(
        f"TVF_13_BugFix_Deferred4",
        env_name="DemonAttack",
        timeout=500 * 4,
        run_name=f"halfway no_v_update",
        tvf_horizon_distribution="advanced",
        tvf_horizon_samples=128,
        tvf_value_samples=128,
        tvf_max_horizon=1000,
        tvf_soft_anchor=0,
        deferred_rewards=250,
        tvf_horizon_scale="centered",

        default_params=v14_args,
        tvf_update_return_freq=4,

        time_aware=True,
        tvf_time_scale="centered",

        epochs=10,
        priority=100,
    )

    add_job(
        # now copy aux_features (just in case...)
        f"TVF_13_BugFix_Deferred5",
        env_name="DemonAttack",
        timeout=500 * 4,
        run_name=f"sampled",
        tvf_horizon_distribution="advanced",
        tvf_horizon_samples=128,
        tvf_value_samples=128,
        tvf_max_horizon=1000,
        tvf_soft_anchor=1,
        deferred_rewards=250,
        tvf_horizon_scale="centered",
        tvf_time_scale="centered",

        default_params=v14_args,

        epochs=10,
        priority=100,
    )

    add_job(
        f"TVF_13_BugFix_Deferred6",
        env_name="DemonAttack",
        timeout=500 * 4,
        run_name=f"hint",
        tvf_horizon_distribution="advanced",
        tvf_horizon_samples=128,
        tvf_value_samples=128,
        tvf_max_horizon=1000,
        tvf_soft_anchor=1,
        deferred_rewards=250,
        tvf_horizon_scale="wide",
        tvf_time_scale="wide",

        default_params=v14_args,

        epochs=10,
        priority=100,
    )

    add_job(
        # now copy aux_features (just in case...)
        f"TVF_13_BugFix_Deferred5",
        env_name="DemonAttack",
        timeout=500 * 4,
        run_name=f"not sampled",
        tvf_horizon_distribution="advanced",
        tvf_horizon_samples=128,
        tvf_value_samples=-1,
        tvf_max_horizon=1000,
        tvf_soft_anchor=1,
        deferred_rewards=250,
        tvf_horizon_scale="centered",
        tvf_time_scale="centered",

        default_params=v14_args,

        epochs=10,
        priority=100,
    )


    add_job(
        # now copy aux_features (just in case...)
        f"TVF_13_BugFix_Deferred5",
        env_name="DemonAttack",
        timeout=500 * 4,
        run_name=f"wide",
        tvf_horizon_distribution="advanced",
        tvf_horizon_samples=128,
        tvf_value_samples=128,
        tvf_max_horizon=1000,
        tvf_soft_anchor=1,
        deferred_rewards=250,
        tvf_horizon_scale="centered",
        tvf_time_scale="wide",

        default_params=v14_args,

        epochs=10,
        priority=100,
    )

    add_job(
        # now copy aux_features (just in case...)
        f"TVF_13_BugFix_Deferred7",
        env_name="DemonAttack",
        timeout=500 * 4,
        run_name=f"512",
        tvf_horizon_distribution="advanced",
        tvf_max_horizon=1000,
        deferred_rewards=250,
        tvf_lambda="exp",
        n_step=512,

        default_params=v14_fast,

        epochs=10,
        priority=400,
    )

    for n_step in [2, 16, 64, 128]:
        add_job(
            # with better weight initialization
            f"TVF_13_BugFix_Deferred_NStep",
            env_name="DemonAttack",
            timeout=500 * 4,
            run_name=f"n_step={n_step}",
            tvf_horizon_distribution="advanced",
            tvf_horizon_samples=128,
            tvf_value_samples=128,
            tvf_max_horizon=1000,
            deferred_rewards=250,
            tvf_horizon_scale="centered",

            default_params=v14_args,
            tvf_lambda=-n_step,

            time_aware=True,
            tvf_time_scale="centered",

            epochs=20,
            priority=100,
        )


    for hu in [2, 4, 5, 8]:
        add_job(
            # with better weight initialization
            f"TVF_13_BugFix_Deferred_HU",
            env_name="DemonAttack",
            timeout=500 * 4,
            run_name=f"hu={hu}",
            tvf_horizon_distribution="advanced",
            tvf_horizon_samples=128,
            tvf_value_samples=128,
            tvf_max_horizon=1000,
            deferred_rewards=250,
            tvf_hidden_units=hu,
            tvf_horizon_scale="centered",

            default_params=v14_args,
            tvf_lambda=-n_step,

            time_aware=True,
            tvf_time_scale="centered",

            epochs=20,
            priority=100,
        )

    add_job(
        # with better weight initialization
        f"TVF_13_BugFix_Deferred_NStep",
        env_name="DemonAttack",
        timeout=500 * 4,
        run_name=f"lambda={0.97}",
        tvf_horizon_distribution="advanced",
        tvf_horizon_samples=128,
        tvf_value_samples=128,
        tvf_max_horizon=1000,
        deferred_rewards=250,
        tvf_horizon_scale="centered",

        default_params=v14_args,
        tvf_lambda=0.97,

        time_aware=True,
        tvf_time_scale="centered",

        epochs=20,
        priority=100,
    )


def setup_experiments_14():
    for tvf_update_return_freq in [1, 2, 4]:
        add_job(
            f"TVF_14_Regression",
            env_name="DemonAttack",
            run_name=f"update_return_freq={tvf_update_return_freq}",
            tvf_update_return_freq=tvf_update_return_freq,
            default_params=v14_args,
            epochs=50,
            priority=250,
        )

    # this was also done with compression system in (but turned off)
    for tvf_lambda_samples in [2, 4, 8, 16, 32, 64]:
        add_job(
            f"TVF_14_Lambda",
            env_name="DemonAttack",
            run_name=f"tvf_lambda_samples={tvf_lambda_samples} lambda=0.98",
            tvf_lambda=0.98,
            tvf_lambda_samples=tvf_lambda_samples,
            default_params=v14_args,
            epochs=30,
            priority=100,
        )

    # this was also done with compression system in (but turned off)
    for compression in [True, False]:
        add_job(
            f"TVF_14_Compression",
            env_name="DemonAttack",
            run_name=f"compression={compression}",
            use_compression=compression,
            default_params=v14_args,
            epochs=30,
            priority=100,
        )

    # this was also done with compression system in (but turned off)
    for n_step in [64, 128, 256, 512, 1024]:
        add_job(
            f"TVF_14_Exp",
            env_name="DemonAttack",
            run_name=f"n_step={n_step}",
            n_step=n_step,
            tvf_lambda="exp",
            default_params=v14_args,
            epochs=50,
            priority=100,
        )

    # this was also done with compression system in (but turned off)
    # note: another wwy to do this is to run MC over the entire window, then select horizons
    # based on the actual n_step, i.e. transitions at end of window get short horizons, but ones at beginning get
    # long ones. This would give a uniform distribution of horizons though.
    for ratio in [0.01, 0.1, 1.0]: # 1.0 is effectively off (i.e. MC returns)
        add_job(
            f"TVF_14_Adaptive",
            env_name="DemonAttack",
            run_name=f"ratio={ratio}",
            tvf_adaptive_ratio=ratio,
            tvf_lambda="adaptive",
            default_params=v14_fast,
            epochs=50,
            priority=200,
        )

    # another go at this...
    # kind of wish we were using 2 value updates again...
    for env in ['DemonAttack', 'Skiing', 'Seaquest']:

        epochs = 20

        add_job(
            f"TVF_14_LongHorizon_{env}",
            env_name=env,
            run_name=f"ppo_999",

            use_tvf=False,
            gamma=0.999,
            tvf_gamma=0.999,

            default_params=v14_fast,
            epochs=epochs,
            priority=100,
        )

        add_job(
            f"TVF_14_LongHorizon_{env}",
            env_name=env,
            run_name=f"ppo_1",

            use_tvf=False,
            gamma=1.0,
            tvf_gamma=1.0,

            default_params=v14_fast,
            epochs=epochs,
            priority=100,
        )

        add_job(
            f"TVF_14_LongHorizon_{env}",
            env_name=env,
            run_name=f"tvf_default (999_3k_128)",

            use_tvf=True,
            gamma=0.999,
            tvf_gamma=0.999,
            tvf_max_horizon=3000,

            default_params=v14_fast,
            epochs=epochs,
            priority=100,
        )

        add_job(
            f"TVF_14_LongHorizon_{env}",
            env_name=env,
            run_name=f"tvf_default (1_30k_128)",

            use_tvf=True,
            gamma=1.0,
            tvf_gamma=1.0,
            tvf_max_horizon=30000,

            default_params=v14_fast,
            epochs=epochs,
            priority=100,
        )

        add_job(
            f"TVF_14_LongHorizon_{env}",
            env_name=env,
            run_name=f"tvf_exp (1_30k_128)",

            use_tvf=True,
            gamma=1.0,
            tvf_gamma=1.0,
            tvf_max_horizon=30000,
            tvf_lambda="exp",

            default_params=v14_fast,
            epochs=epochs,
            priority=100,
        )

        add_job(
            f"TVF_14_LongHorizon_{env}",
            env_name=env,
            run_name=f"tvf_exp (1_30k_512)",

            use_tvf=True,
            n_step=512,
            use_compression=True,
            gamma=1.0,
            tvf_gamma=1.0,
            tvf_lambda="exp",
            tvf_max_horizon=30000,

            default_params=v14_fast,
            epochs=epochs,
            priority=100,
        )

        add_job(
            f"TVF_14_LongHorizon_{env}",
            env_name=env,
            run_name=f"tvf_super (1_30k_1024)",

            use_tvf=True,
            n_step=1024,
            agents=1024,
            use_compression=True,
            gamma=1.0,
            tvf_gamma=1.0,
            tvf_lambda="exp",
            tvf_max_horizon=30000,

            default_params=v14_fast,
            epochs=epochs,
            priority=100,
        )


    # just run exp 512 on some interesting environments
    for env in ["Breakout", "MontezumaRevenge", "Pitfall", "PrivateEye"]:
        add_job(
            f"TVF_14_LongHorizon_{env}",
            env_name=env,
            run_name=f"ppo_999",

            use_tvf=False,
            gamma=0.999,
            tvf_gamma=0.999,

            default_params=v14_fast,
            epochs=epochs,
            priority=100,
        )

        add_job(
            f"TVF_14_LongHorizon_{env}",
            env_name=env,
            run_name=f"tvf_1_exp (512)",

            use_tvf=True,
            n_step=512,
            use_compression=True,
            gamma=1.0,
            tvf_gamma=1.0,
            tvf_lambda="exp",
            tvf_max_horizon=30000,

            default_params=v14_fast,
            epochs=epochs,
            priority=100,
        )


if __name__ == "__main__":

    # see https://github.com/pytorch/pytorch/issues/37377 :(
    os.environ["MKL_THREADING_LAYER"] = "GNU"

    id = 0
    job_list = []
    # random_search_11_ppo()
    # setup_experiments_13()
    # setup_experiments_13_eval()
    setup_experiments_14()
    random_search_14_tvf()

    if len(sys.argv) == 1:
        experiment_name = "show"
    else:
        experiment_name = sys.argv[1]

    if experiment_name == "show_all":
        show_experiments(all=True)
    elif experiment_name == "show":
        show_experiments()
    elif experiment_name == "fps":
        show_fps()
    elif experiment_name == "auto":
        run_next_experiment()
    else:
        run_next_experiment(filter_jobs=lambda x: x.experiment_name == experiment_name)