Support framework for running SSM models on Hyak in a way that minimizes
required storage. Models are run in their own instance directories in a
"scratch" location. Hydrodynamic outputs are kept in temporary locations
and are re-synchronized from a remote save location when needed.

The main functionality is implemented in the script `ssm_hyak.py`. This
script requires a relatively recent version of Python (that supports
dataclasses) and the f90nml module. A suitable venv can be created with:

 * `python -m venv /path/to/venvs/ssmhyak`
 * `source /path/to/venvs/ssmhyak/bin/activate`
 * `python -m pip install --upgrade pip` (recommended)
 * `pip install -r requirements.txt`

Finally, update the "shebang" line in `ssm_hyak.py` to point to the python
inside the venv.

# Usage

1. Set up a model instance as usual, either hydrodynamic or water quality model.
2. Create a `run_fvcom.stub` or `run_icm.stub` file that acts as a sbatch
   preamble. Syntax is just like an sbatch file header but without the leading
   `#` characters. See the files in `stubs` for examples.
3. Create a `ssm_hyak.ini` file, which uses the Python [ConfigParser](https://docs.python.org/3/library/configparser.html)
   format. See the example file (which is all-encompassing, most jobs don't
   need much more than `run_root`, `save_root`, `mpi_bin`, and `modules`).
   Default values can also be placed in a single file in
   `$HOME/.config/ssm_hyak/ssm_hyak.ini` to avoid repetition.
3. For water quality runs: edit the `wqm_linkage.in` file's `hydro_dir`
   parameter to point to the remote path where hydrodynamic model output is
   permanently kept.
4. When you are ready to queue the job:
   * *For hydro runs*: run `ssm_hyak.py hydro` (optionally use the -v option
     for verbose output).
     This will copy everything to a temporary working location in
     /gscratch/scrubbed, set up symbolic links to temporary model output
     storage, generates a sbatch file (which registers the job for data sync
     once it begins, see below), and calls `sbatch` to queue the job.
   * *For water quality runs*: run `ssm_hyak.py wqm`.
     This does everything the `hydro` option does but specific to the water
     quality model. It also fetches the hydrodynamic results from the remote
     path set in `wqm_linkage.in` and updates the temporary copy of that file
     to point the model to the local copy of those results.

# Job synchronization

As jobs are running on Klone, `ssm_hyak.py` has a `sync` command that is
intended to run on a [systemd timer](https://opensource.com/article/20/7/systemd-timers)
to execute `rsync` on the running model instance. Jobs register themselves by
creating small `*.job` files in `$HOME/.local/state/ssm`; those files are used
to find running model instances and keep the remote server up-to-date during
and after the run.

To set up sync, run the script `ssm_syncsetup.sh install` from Klone. Later,
`uninstall` can be used to disable the timer if you don't want it to run
anymore.

Systemd jobs and timers by default are only active when you have a user
session going. The standard way around this is to run `loginctl enable-linger`.
However, it appears that Klone "forgets" this setting periodically, so I
recommend including that command in a login script.

Another complication is that there are multiple Klone login nodes and the sync
job should not be running more than once at a time. To prevent this, the systemd
unit files have a "HostCondition" check included that ensures the sync only runs
on klone-login01. The effect of this is that sync will not occur unless you are
logged in or have linger enabled on that specific login node.

If for any reason scheduled sync is not working, you can just run
`ssm_hyak.py sync` and it will sync all the running and recently run jobs.
