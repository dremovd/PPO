import os
import sys
import json
import time
import random
import platform

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


CHUNK_SIZE=10
DEVICE="auto"
OUTPUT_FOLDER="./Run"
WORKERS=4

if len(sys.argv) == 3:
    DEVICE = sys.argv[2]

def add_job(experiment_name, run_name, priority=0, chunked=True, default_params=None, **kwargs):

    if default_params is not None:
        for k,v in default_params.items():
            if k not in kwargs:
                kwargs[k]=v

    if "device" not in kwargs:
        kwargs["device"] = DEVICE



    job_list.append(Job(experiment_name, run_name, priority, chunked, kwargs))

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

    def __init__(self, experiment_name, run_name, priority, chunked, params):
        self.experiment_name = experiment_name
        self.run_name = run_name
        self.priority = priority
        self.params = params
        self.id = Job.id
        self.chunked = chunked
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

        if "search" in self.experiment_name:
            # with search we want to make sure we complete partial runs first
            priority = priority + self.get_completed_epochs()
        else:
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

            return details
        except:
            return None

    def get_completed_epochs(self):
        details = self.get_details()
        if details is not None:
            return details["completed_epochs"]
        else:
            return 0

    def run(self, chunked=False):

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

        if chunked:
            # work out the next block to do
            if details is None:
                next_chunk = CHUNK_SIZE
            else:
                next_chunk = (round(details["completed_epochs"] / CHUNK_SIZE) * CHUNK_SIZE) + CHUNK_SIZE
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

            job.run(chunked=job.chunked)
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
    else:
        return x

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



def setup_experiments6():

    default_args = {
        'env_name': "Breakout",
        'checkpoint_every': int(5e6),
        'epochs': 50,
        'agents': 256,
        'n_steps': 128,
        'max_grad_norm': 5.0,
        'entropy_bonus': 0.01,
        'use_tvf': True,
        'tvf_coef': 0.1,
        'tvf_n_horizons': 128,
        'tvf_advantage': True,
        'vf_coef': 0.0,
        'workers': WORKERS, # we will be running lots of experiments so reduce this down a little... (8 is better though)
        'tvf_gamma': 0.997,
        'gamma': 0.997,
        'n_mini_batches': 32,
    }

    for entropy_bonus in [0.001, 0.003, 0.01, 0.03]:
        add_job(
            "TVF_6A",
            run_name=f"entropy_bonus={entropy_bonus}",
            tvf_max_horizon=1000,
            entropy_bonus=entropy_bonus,
            priority=100,
            **{k: v for k, v in default_args.items() if k != "entropy_bonus"}
        )

    for tvf_max_horizon in [300, 1000, 3000, 10000]:
        add_job(
            "TVF_6B",
            run_name=f"tvf_mh={tvf_max_horizon}",
            tvf_max_horizon=tvf_max_horizon,
            epochs=70,
            priority=300 if tvf_max_horizon==10000 else 200,
            **{k: v for k, v in default_args.items() if k != "epochs"}
        )

    # as per previous
    for tvf_max_horizon in [999, 1000, 1001, 2000, 4000]:
        add_job(
            "TVF_6B2",
            run_name=f"tvf_mh={tvf_max_horizon}",
            tvf_max_horizon=tvf_max_horizon,
            priority=100,
            **default_args
        )

    for agents in [64, 128, 256, 512]:
        add_job(
            "TVF_6C",
            run_name=f"agents={agents}",
            tvf_max_horizon=1000,
            agents=agents,
            **{k:v for k,v in default_args.items() if k != "agents"}
        )

    for n_steps in [16, 32, 64, 128, 256]:
        add_job(
            "TVF_6D",
            run_name=f"n_steps={n_steps}",
            tvf_max_horizon=1000,
            n_steps=n_steps,
            **{k:v for k,v in default_args.items() if k != "n_steps"}
        )

    for distribution in ["uniform", "linear", "first_and_last"]:
        add_job(
            "TVF_6E",
            run_name=f"tvf_sample_dist={distribution} samples=32",
            tvf_max_horizon=1000,
            tvf_sample_dist=distribution,
            tvf_n_horizons=32,
            **{k:v for k,v in default_args.items() if k != "tvf_n_horizons"}
        )

    for n_mini_batches in [8, 16, 32, 64]:
        add_job(
            "TVF_6F",
            run_name=f"n_mini_batches={n_mini_batches}",
            tvf_max_horizon=1000,
            n_mini_batches=n_mini_batches,
            **{k:v for k,v in default_args.items() if k != "n_mini_batches"}
        )

    for tvf_coef in [0.01, 0.03, 0.1, 0.3, 1]:
        add_job(
            "TVF_6G",
            run_name=f"tvf_coef={tvf_coef}",
            tvf_max_horizon=1000,
            tvf_coef=tvf_coef,
            **{k:v for k,v in default_args.items() if k != "tvf_coef"}
        )

    # make sure new advantage normalization code, and improved sampling works
    for tvf_max_horizon in [1000, 999, 1001]: # just a way to get 3 runs...
        add_job(
            "TVF_6H",
            run_name=f"tvf_mh={tvf_max_horizon}",
            tvf_max_horizon=tvf_max_horizon,
            priority=100,
            **default_args
        )


    # evaluation on MR
    for env in ['MontezumaRevenge']:
        add_job(
            "TVF_6_mr",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=1000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=True,
            tvf_advantage=True,
            vf_coef=0.0,

            tvf_coef=0.01,
            tvf_n_horizons=64,

            workers=WORKERS,  # we will be running lots of experiments so reduce this down a little... (8 is better though)
            tvf_gamma=0.997,
            gamma=0.997,
            n_mini_batches=32,

            priority=100,
        )

    # evaluation on MR
    for env in ['Alien', 'MontezumaRevenge']:
        add_job(
            "TVF_6_rnd",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=1000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=True,
            tvf_advantage=True,

            tvf_coef=0.01,
            tvf_n_horizons=64,

            use_rnd=True,
            observation_normalization=True,
            vf_coef=0.5,
            intrinsic_reward_scale=1.0,

            workers=WORKERS,
            # we will be running lots of experiments so reduce this down a little... (8 is better though)
            tvf_gamma=0.997,
            gamma=0.997,
            n_mini_batches=32,

            priority=100,
        )

    # evaluation run (only setting difference is tvf_coef is now 0.01)
    for env in ['Alien', 'BankHeist', 'CrazyClimber']:
        add_job(
            "TVF_6_eval",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=1000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=True,
            tvf_advantage=True,
            vf_coef=0.0,

            tvf_coef=0.01,
            tvf_n_horizons=64,

            workers=WORKERS,  # we will be running lots of experiments so reduce this down a little... (8 is better though)
            tvf_gamma=0.997,
            gamma=0.997,
            n_mini_batches=32,

            chunked=False,
            priority=0,
        )

    # longer horizon..
    for env in ['Alien', 'BankHeist', 'CrazyClimber']:
        add_job(
            "TVF_6_eval_999",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=3000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=True,
            tvf_advantage=True,
            vf_coef=0.0,

            tvf_coef=0.01,
            tvf_n_horizons=64,

            workers=WORKERS,
            # we will be running lots of experiments so reduce this down a little... (8 is better though)
            tvf_gamma=0.999,
            gamma=0.999,
            n_mini_batches=32,

            chunked=False,
            priority=0,
        )


    # trying the split model... (so we don't have to balance value and policy...
    for env in ['Alien', 'BankHeist', 'CrazyClimber']:
        add_job(
            "TVF_6_eval_split",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=1000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=True,
            tvf_advantage=True,
            vf_coef=0.0,

            tvf_coef=0.01,
            tvf_n_horizons=64,
            tvf_model='split',

            workers=WORKERS,  # we will be running lots of experiments so reduce this down a little... (8 is better though)
            tvf_gamma=0.997,
            gamma=0.997,
            n_mini_batches=32,

            chunked=False,
            priority=0,
        )

    # trying the split model... (so we don't have to balance value and policy...
    for env in ['Alien', 'BankHeist', 'CrazyClimber']:
        add_job(
            "TVF_6_eval_joint",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=1000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=True,
            tvf_advantage=True,
            vf_coef=0.0,

            tvf_coef=0.01,
            tvf_n_horizons=64,
            tvf_model='split',
            tvf_joint_weight=0.1, # just a little hint to make these weights the same

            workers=WORKERS,
            # we will be running lots of experiments so reduce this down a little... (8 is better though)
            tvf_gamma=0.997,
            gamma=0.997,
            n_mini_batches=32,

            priority=0,
        )

    # some RND exploration
    for env in ['Alien', 'BankHeist', 'CrazyClimber']:
        add_job(
            "TVF_6_eval_rnd",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=1000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=True,
            tvf_advantage=True,

            tvf_coef=0.01,
            tvf_n_horizons=64,

            workers=WORKERS,  # we will be running lots of experiments so reduce this down a little... (8 is better though)
            tvf_gamma=0.997,
            gamma=0.997,
            n_mini_batches=32,

            use_rnd=True,
            observation_normalization=True,
            vf_coef=0.5,
            intrinsic_reward_scale=0.25, # big guess here...

            priority=100,
        )

    # stronger RND
    for env in ['Alien', 'BankHeist', 'CrazyClimber']:
        add_job(
            "TVF_6_eval_rnd2",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=1000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=True,
            tvf_advantage=True,

            tvf_coef=0.01,
            tvf_n_horizons=64,

            workers=WORKERS,
            # we will be running lots of experiments so reduce this down a little... (8 is better though)
            tvf_gamma=0.997,
            gamma=0.997,
            n_mini_batches=32,

            use_rnd=True,
            observation_normalization=True,
            vf_coef=0.5,
            intrinsic_reward_scale=1.0,  # big guess here...

            priority=100,
        )

    # evaluation run (only setting difference is tvf_coef is now 0.01)
    for env in ['Alien', 'BankHeist', 'CrazyClimber']:
        add_job(
            "TVF_6_eval_high_samples",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=1000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=True,
            tvf_advantage=True,
            vf_coef=0.0,

            tvf_coef=0.01,
            tvf_n_horizons=256,

            workers=WORKERS,
            tvf_gamma=0.997,
            gamma=0.997,
            n_mini_batches=32,

            priority=100,
        )

    # evaluation run (only setting difference is tvf_coef is now 0.01)
    for env in ['Alien', 'BankHeist', 'CrazyClimber']:
        add_job(
            "TVF_6_eval_99",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=300,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=True,
            tvf_advantage=True,
            vf_coef=0.0,

            tvf_coef=0.01,
            tvf_n_horizons=64,

            workers=WORKERS,
            # we will be running lots of experiments so reduce this down a little... (8 is better though)
            tvf_gamma=0.99,
            gamma=0.99,
            n_mini_batches=32,

            priority=100,
        )

    for env in ['Alien', 'BankHeist', 'CrazyClimber']:
        add_job(
            "TVF_6_eval_ppo_997",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=1000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=False,
            tvf_advantage=False,
            vf_coef=0.5,

            workers=WORKERS,  # we will be running lots of experiments so reduce this down a little... (8 is better though)
            gamma=0.997,
            n_mini_batches=32,

            priority=85,
        )

    for env in ['Alien', 'BankHeist', 'CrazyClimber']:
        add_job(
            "TVF_6_eval_ppo_999",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=1000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=False,
            tvf_advantage=False,
            vf_coef=0.5,

            workers=WORKERS,  # we will be running lots of experiments so reduce this down a little... (8 is better though)
            gamma=0.999,
            n_mini_batches=32,

            priority=85,
        )

    for env in ['Alien', 'BankHeist', 'CrazyClimber']:
        add_job(
            "TVF_6_eval_ppo_99",
            env_name=env,
            run_name=f"env={env}",
            tvf_max_horizon=1000,

            checkpoint_every=int(5e6),
            epochs=50,
            agents=256,
            n_steps=128,
            max_grad_norm=5.0,
            entropy_bonus=0.01,

            use_tvf=False,
            tvf_advantage=False,
            vf_coef=0.5,

            workers=WORKERS,  # we will be running lots of experiments so reduce this down a little... (8 is better though)
            gamma=0.99,
            n_mini_batches=32,

            priority=70,
        )


def random_search(run, main_params, search_params, count=128):

    for i in range(count):
        params = {}
        random.seed(i)
        for k, v in search_params.items():
            params[k] = random.choice(v)

        # make sure params arn't too high (due to memory)
        while params["agents"] * params["n_steps"] > 64*1024:
            params["agents"] //= 2

        add_job(run, run_name=f"{i:04d}", chunked=True, **main_params, **params)


def nice_format(x):
    if type(x) is str:
        return f'"{x}"'
    if x is None:
        return "None"
    if type(x) in [int, float, bool]:
        return str(x)

    return f'"{x}"'

def setup_tvf_random_search():

    main_params = {
        'env_name': "Breakout",
        'checkpoint_every': int(5e6),
        'epochs': 50, # can be done now that n_horizons is low, and we are using fast MC algorithm.
        'use_tvf': True,
        'tvf_advantage': True,
        'vf_coef': 0.0,
        'workers': WORKERS,
        'tvf_gamma': 0.997,
        'gamma': 0.997,
        'priority': -100,
        'tvf_max_horizon': 1000,

    }

    # just want to figure out the interplay between mini_batch_size, n_steps, and n_agents...
    # I should plot 'mini_batch_size' as well... and look for correlations between variables...

    # goal would be to find some good settings, and get 500+ on atari in 50m.

    search_params = {
        'agents': [64, 128, 256, 512],
        'n_steps': [32, 64, 128, 256, 512],
        'tvf_coef': [0.1, 0.03, 0.01, 0.003],
        'n_mini_batches': [4, 8, 16, 32, 64],  # might be better to have this as mini_batch size?

        # I'm just interested to see what effect these have, but I don't expect any interplay.
        'entropy_bonus': [0.03, 0.01, 0.003],
        'ppo_epsilon': [0.1, 0.2], # allow for faster learning
        'tvf_n_horizons': [16, 32, 64], # smaller samples should work and will be faster
        'adam_epsilon': [1e-5, 1e-8],
        'max_grad_norm': [0.5, 5.0, 10.0],
        'tvf_sample_dist': ['uniform', 'linear'],
        'learning_rate': [2.5e-4, 1e-4, 2.5e-5],  # try slower learning rates... might help for 200m
    }

    random_search("tvf_v6_search", main_params, search_params)

def setup_experiments7():

    default_args = {
        'env_name': "Breakout",
        'checkpoint_every': int(5e6),
        'epochs': 50,
        'agents': 256,
        'n_steps': 128,
        'max_grad_norm': 5.0,
        'entropy_bonus': 0.003,
        'use_tvf': True,
        'tvf_coef': 0.01,
        'tvf_n_horizons': 64,
        'tvf_advantage': True,
        'vf_coef': 0.0,
        'workers': 8,
        'tvf_gamma': 0.997,
        'gamma': 0.997,
        'mini_batch_size': 1024,
    }

    for tvf_max_horizon in [300, 1000, 3000]:
        add_job(
            "TVF_7A",
            run_name=f"tvf_mh={tvf_max_horizon}",
            tvf_max_horizon=tvf_max_horizon,
            priority=0,
            default_params=default_args
        )

    # mostly so I can see what kl should be...
    for gamma in [0.99, 0.997, 0.999]:
        add_job(
            "TVF_PPO",
            run_name=f"gamma={gamma}",
            use_tvf=False,
            vf_coef=0.5,
            priority=0,
            gamma=gamma,
            default_params=default_args
        )


    for tvf_max_horizon in [300, 1000, 3000]:
        add_job(
            "TVF_7B",
            run_name=f"tvf_mh={tvf_max_horizon}",
            tvf_max_horizon=tvf_max_horizon,
            priority=0,
            default_params=default_args
        )

    # this didn't work
    # for n_steps in [128, 256, 512]:
    #     add_job(
    #         "TVF_7C",
    #         run_name=f"n_steps={n_steps} moving=True",
    #         tvf_max_horizon=1000,
    #         moving_updates=True,
    #         priority=200,
    #         default_params=default_args
    #     )

    # for n_steps in [128, 256, 512]:
    #     add_job(
    #         "TVF_7C",
    #         run_name=f"n_steps={n_steps} moving=False",
    #         tvf_max_horizon=1000,
    #         moving_updates=False,
    #         priority=200,
    #         default_params=default_args
    #     )

    # what network capacity is needed to learn ev_10?
    for tvf_hidden_units in [64, 128, 256, 512]:
        add_job(
            "TVF_7D2b",
            run_name=f"tvf_hu={tvf_hidden_units}",

            tvf_hidden_units=tvf_hidden_units,

            tvf_model="split",
            tvf_joint_weight=0.1,

            tvf_coef=0.5,
            entropy_bonus=0.01,

            epochs=25,
            priority=0,

            default_params=default_args

        )

    # average reward (might need to redo this...?
    # for tvf_h_scale in ['constant', 'linear', 'squared', 100, -100, 'mse']:
    #     add_job(
    #         "TVF_7E",
    #         run_name=f"tvf_hs={tvf_h_scale}",
    #         tvf_coef=0.5,
    #         entropy_bonus=0.01,
    #         tvf_max_horizon=1000,
    #         tvf_h_scale=tvf_h_scale,
    #         default_params=default_args,
    #         priority=320 if tvf_h_scale == "squared" else 310,
    #     )


    # first attempt at really long horizons (vinilla)
    for tvf_max_horizon in [1000, 3000, 10000]:
        add_job(
            "TVF_7F",
            run_name=f"tvf_mh={tvf_max_horizon}",
            tvf_max_horizon=tvf_max_horizon,
            tvf_gamma=0.999,
            gamma=0.999,
            priority=0,

            # improved settings...
            tvf_model="split",
            tvf_joint_weight=0.1,
            tvf_coef=0.5,
            entropy_bonus=0.01,

            default_params=default_args
        )

        add_job(
            "TVF_7F",
            run_name=f"tvf_mh={tvf_max_horizon} (high samples)",
            tvf_max_horizon=tvf_max_horizon,
            tvf_gamma=0.999,
            gamma=0.999,
            priority=0,

            tvf_n_horizons=256,

            # improved settings...
            tvf_model="split",
            tvf_joint_weight=0.1,
            tvf_coef=0.5,
            entropy_bonus=0.01,

            default_params=default_args
        )


    # pending experiments
    # activation function
    # horizon warmup (don't like this)
    # long horizon
    # mse weighted sampling
    #


def setup_experiments8():

    # these are just for the regression test
    initial_args = {
        'env_name': "Breakout",
        'checkpoint_every': int(5e6),
        'epochs': 50,
        'agents': 256,
        'n_steps': 128,
        'max_grad_norm': 5.0,
        'entropy_bonus': 0.01,
        'use_tvf': True,
        'tvf_advantage': True,
        'tvf_coef': 0.5,
        'vf_coef': 0.0,
        'tvf_n_horizons': 64,
        'workers': 8,
        'tvf_gamma': 0.997,
        'gamma': 0.997,
        'mini_batch_size': 1024,
    }

    # these are the settings we will move towards
    # (not worked out yet...)
    prefered_args = {
        'env_name': "Breakout",
        'checkpoint_every': int(5e6),
        'epochs': 50,
        'agents': 256,
        'n_steps': 64,
        'max_grad_norm': 5.0,
        'entropy_bonus': 0.01,
        'use_tvf': True,
        'tvf_advantage': True,
        'tvf_coef': 0.5,
        'vf_coef': 0.0,
        'tvf_n_horizons': 64,
        'workers': 8,
        'tvf_gamma': 0.997,
        'gamma': 0.997,
        'mini_batch_size': 1024,
    }

    # Standard regression test
    for tvf_max_horizon in [1000, 2000, 4000]:
        add_job(
            "TVF_8A",
            run_name=f"tvf_mh={tvf_max_horizon}",
            tvf_max_horizon=tvf_max_horizon,
            priority=0,
            default_params=initial_args,
        )

if __name__ == "__main__":

    # see https://github.com/pytorch/pytorch/issues/37377 :(
    os.environ["MKL_THREADING_LAYER"] = "GNU"

    id = 0
    job_list = []
    setup_experiments6()
    setup_experiments7()
    setup_experiments8()

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