#!/mmfs1/gscratch/brett/bedaro/venvs/ssmhyak/bin/python

import os
import sys
import re
import stat
import hashlib
import logging
import glob
from pathlib import Path, PurePosixPath
from argparse import ArgumentParser, FileType
from configparser import ConfigParser
import tempfile
import shutil
import subprocess
from dataclasses import dataclass

import psutil
import f90nml

logger = logging.getLogger(__name__)

def hashit(string):
    """Simple string -> string hash function"""
    res = hashlib.md5(bytes(str.encode(string))).hexdigest()
    logger.debug(f'hash({string}) -> {res}')
    return res

def get_run_param(runfile, names, dtype=str):
    """Get a parameter value from the run control file"""
    ret_scalar = not isinstance(names, list)
    if ret_scalar:
        names = [names]
    values = [None] * len(names)
    found = 0
    nvre = re.compile(r'\s*=\s*')
    with open(runfile) as f:
        for line in f:
            # Ignore everything after an exclamation point (comment)
            # and strip whitespace
            line = line[:line.find('!')].strip()
            # Skip empty lines
            if len(line) == 0:
                continue
            # combine multiline entries continued with two backslashes
            while line[-2:] == r'\\':
                l2 = next(f)
                l2 = l2[:l2.find('!')].strip()
                l1 = line[:-2].strip()
                line = l1 + ' ' + l2
            pname, pval = nvre.split(line, 2)
            if pname in names:
                i = names.index(pname)
                values[i] = dtype(pval)
                found += 1
            if found == len(names):
                break
    return values[0] if ret_scalar else values

DEFAULT_SCRUBDIR = '/gscratch/scrubbed'
DEFAULT_SCRATCHDIR = '/gscratch/scrubbed'

REGISTER_STATEDIR = Path(os.environ['HOME']) / '.local' / 'state' / 'ssm'

@dataclass(frozen=True)
class RemotePath():
    """Special version of Path that understands paths on remote systems (SCP syntax)

    The attribute `host` stores the remote host if there is one.
    The attribute `path` stores the actual path.
    """
    host: str
    path: PurePosixPath

    @staticmethod
    def from_string(s):
        if ':' in s:
            conn_dest, path = s.split(':', 2)
        else:
            path = s
            conn_dest = None
        return RemotePath(conn_dest, PurePosixPath(path))

    @property
    def parts(self):
        if self._conn_dest is None:
            return self.path.parts
        return tuple([self.conn_dest + ':'] + list(self.path.parts))

    @property
    def is_remote(self):
        """Whether or not this is actually a remote Path"""
        return self.host is not None

    def __repr__(self):
        return f'{self.__class__.__name__}({self.__str__()})'

    def with_segments(self, *segments):
        return RemotePath(self.host, PurePosixPath(*segments))

    def __str__(self):
        if self.host is None:
            return self.path.__fspath__()
        else:
            return f'{self.host}:{self.path.__str__()}'

    def __truediv__(self, p2):
        return RemotePath(self.host, self.path / p2)

    @property
    def parent(self):
        return RemotePath(self.host, self.path.parent)

class HyakSetupHelper:
    def __init__(self, method, casename, mpi_bin, save_root=None,
                 **config):
        self.method = method
        self.config = config
        self.casename = casename
        self.mpi_bin = mpi_bin
        self.save_root = RemotePath.from_string(save_root) if save_root is not None else None
        self.home = Path(os.getcwd()).resolve()
        self.test = False

    def _get_scrub_path(self, name='scrub_dir'):
        scrubdir = Path(self.config[name] if name in self.config else DEFAULT_SCRUBDIR)
        return scrubdir if os.environ['USER'] in scrubdir.parts else scrubdir / os.environ['USER']

    def _stage(self, outdir, stagename):
        """Set up staging directories so the model can run from a different location"""
        instance_root = Path.cwd()
        run_root = Path(self.config['run_root']) if 'run_root' in self.config else instance_root
        save_root = RemotePath(None, run_root) if self.save_root is None else self.save_root
        scrub_path = self._get_scrub_path('scrub_dir_out')
        # run_tail is the path to the current instance relative to run_root
        run_tail = (instance_root / outdir).relative_to(run_root)

        if save_root.is_remote:
            out_path = scrub_path / stagename / hashit(str(save_root / run_tail))
        else:
            out_path = save_root / run_tail
        os.makedirs(out_path, exist_ok=True)
        outdir_path = Path(outdir).absolute()
        if out_path != outdir_path:
            if outdir_path.is_symlink():
                os.unlink(outdir_path)
            elif outdir_path.is_dir():
                shutil.rmtree(outdir_path)
            os.symlink(out_path, outdir)
        # Don't delete the temporary directory ourselves!
        inst_dir = tempfile.mkdtemp(dir=scrub_path)
        inst_path = Path(inst_dir)
        os.symlink(out_path, inst_path / outdir)

        return inst_path

    def _write_job_file(self, fp, stubfile):
        fp.write('#!/bin/bash\n')
        fp.write('# Auto-generated sbatch file from a stub\n')
        fp.write('#\n')
        with open(stubfile) as s:
            for l in s:
                fp.write(f'#{l}')
        fp.write('module purge\n')
        if 'modules' in self.config:
            for m in self.config['modules'].split():
                fp.write(f"module load {m}\n")
        if self.save_root is not None and self.save_root.is_remote:
            # Have the sbatch file register the job
            fp.write(f'echo "{self.home}" > "{REGISTER_STATEDIR}/$SLURM_JOB_ID.job"\n')
        fp.write(f"time mpirun -np $SLURM_NTASKS {self.mpi_bin} {self.casename}\n")

    def run(self):
        if self.method == 'hydro':
            return self.setup_hydro()
        elif self.method == 'wqm':
            return self.setup_wqm()
        else:
            raise ValueError(f'Unknown method {self.method}')

    def _invoke_sbatch(self, pth, scr):
        if self.test:
            logger.info('==== Test mode ====')
            logger.info(f'Temporary instance is at {str(pth)}')
            return
        logger.info('==== Submitting the job ====')
        subprocess.run(["sbatch","-D",str(pth),"-o",str(self.home / "slurm-%j.out"),scr],
                       stdout=sys.stdout, stderr=sys.stderr, check=True)

    def setup_hydro(self):
        runfile = f"{self.casename}_run.dat"
        inpdir, outdir = get_run_param(runfile, ['INPDIR','OUTDIR'], dtype=Path)

        logger.info('==== Staging inputs ====')
        scratch_path = self._stage(outdir, 'hyd_results')

        shutil.copytree(inpdir, scratch_path / inpdir)
        shutil.copy2(runfile, scratch_path)
        instance_root = Path(os.getcwd())
        with open(scratch_path / 'run_fvcom.sh','w') as b:
            self._write_job_file(b, 'run_fvcom.stub')
            # Preserve restart files after job concludes
            b.write(f"mv re_* {instance_root}\n")
        os.chmod(scratch_path / 'run_fvcom.sh', stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        logger.debug(f'Run instance is at {str(scratch_path)}')
        self._invoke_sbatch(scratch_path, 'run_fvcom.sh')
        return scratch_path

    def _get_hyd_result_dest(self, hyd_result_src):
        scrub_path = self._get_scrub_path()
        if hyd_result_src.path.name == 'netcdf':
            # Remove the "netcdf" ending so the hash matches what setup_hydro made
            hyd_result_dest = scrub_path / 'hyd_results' / hashit(str(hyd_result_src.parent))
            return hyd_result_dest / 'netcdf'
        else:
            return scrub_path / 'hyd_results' / hashit(str(hyd_result_src))

    def setup_wqm(self):
        wqmlink = f90nml.read('wqm_linkage.in')
        hyd_result_src = RemotePath.from_string(wqmlink['hydro_netcdf']['hydro_dir'])
        if hyd_result_src.is_remote:
            if self.save_root.is_remote and hyd_result_src.host != self.save_root.host:
                logger.warning(f'Remote host for save_root ({self.save_root.host}) does not match hydro_dir ({hyd_result_src.host})')
            hyd_result_nc = self._get_hyd_result_dest(hyd_result_src)
            logger.info(f'==== Syncing {str(hyd_result_src)} to {os.fspath(hyd_result_nc)} ====')
            os.makedirs(hyd_result_nc, exist_ok=True)
            args = ['rsync','-vrtlz','--filter=+ *.nc','--filter=- *',str(hyd_result_src) + '/',hyd_result_nc]
            rsync_pipe = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=sys.stderr)
            while True:
                line = rsync_pipe.stdout.readline()
                if not line:
                    rsync_pipe.poll()
                    break
                logger.info(line.strip())
            if rsync_pipe.returncode:
                raise subprocess.CalledProcessError(rsync_pipe.returncode, args)

        logger.info('==== Staging inputs ====')
        scratch_path = self._stage('outputs', 'wqm_results')

        shutil.copytree('inputs', scratch_path / 'inputs')
        runfile = f"{self.casename}_run.dat"
        if Path(runfile).is_file():
            shutil.copy2(runfile, scratch_path)
        shutil.copy2('wqm_con.npt', scratch_path)
        # Search through wqm_con.npt for files that are not in inputs/ or outputs/
        with open('wqm_con.npt') as wc:
            try:
                subhead_pattern = re.compile('^[A-Z ]+ FILE[^A-Z]')
                for line in wc:
                    if subhead_pattern.match(line):
                        filecand = next(wc).strip()
                        while filecand != '':
                            if filecand[:7] != 'inputs/' and filecand[:8] != 'outputs/':
                                logger.info(f'Found extra file {filecand} to copy')
                                shutil.copy2(filecand, scratch_path)
                            filecand = next(wc).strip()
            except StopIteration:
                pass

        if hyd_result_src.is_remote:
            wqmlink_patch = {'hydro_netcdf': {'hydro_dir': os.fspath(hyd_result_nc) + '/'}}
            f90nml.patch('wqm_linkage.in', wqmlink_patch, os.fspath(scratch_path / 'wqm_linkage.in'))
        else:
            shutil.copy2('wqm_linkage.in', scratch_path)
        instance_root = Path(os.getcwd())
        with open(scratch_path / 'run_icm.sh','w') as b:
            self._write_job_file(b, instance_root / 'run_icm.stub')
        logger.debug(f'Run instance is at {str(scratch_path)}')
        self._invoke_sbatch(scratch_path, 'run_icm.sh')
        return scratch_path

class SyncHelper:
    """Class to handle syncing model files from registered jobs"""
    def __init__(self, _, **config):
        self.config = config
        self.sync_count = 0

    def _job_running(self, jobid):
        """Is this job running?"""
        result = subprocess.run(['squeue','--job',jobid], capture_output=True)
        return result.returncode == 0

    def _call_process_with_logging(self, args):
        rsync_pipe = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=sys.stderr)
        while True:
            line = rsync_pipe.stdout.readline()
            if not line:
                rsync_pipe.poll()
                break
            logger.info(line.strip())
        if rsync_pipe.returncode:
            raise subprocess.CalledProcessError(rsync_pipe.returncode, args)

    def _do_sync(self, job_dir: Path, copy_dest: RemotePath, final: bool=False):
        # FIXME this does not reference OUTDIR in ssm_run.dat like setup_hydro
        # does
        os.chdir(job_dir)
        # Copy everything except outputs first
        self._call_process_with_logging(['rsync','-az','--exclude=OUTPUT','--exclude=outputs','./', str(copy_dest)])
        if os.path.isdir('OUTPUT'):
            args = ['rsync','-az']
            if not final:
                args.append('--append-verify')
            args += ['OUTPUT/',str(copy_dest / 'OUTPUT')]
            self._call_process_with_logging(args)
        elif os.path.isdir('outputs'):
            args = ['rsync','-az','--exclude=ssm_history_*']
            if not final:
                args.append('--append-verify')
            args += ['outputs/',str(copy_dest / 'outputs')]
            self._call_process_with_logging(args)
            histfiles = glob.glob('outputs/ssm_history_*')
            if len(histfiles):
                self._call_process_with_logging(['rsync','-az','--append-verify'] + histfiles + [str(copy_dest / 'outputs')])
        self.sync_count += 1

    def _lock(self, unlock=False):
        me = os.getpid()
        pidfile = REGISTER_STATEDIR / 'sync.pid'
        if pidfile.is_file():
            with open(pidfile) as fp:
                pid = int(next(fp))
            if pid == me:
                # We own the lock, ignore unless we're unlocking
                if unlock:
                    pidfile.unlink()
                return
            elif psutil.pid_exists(pid):
                # The lockfile PID matches a running process, let's see what it is
                p = psutil.Process(pid)
                mep = putil.Process(me)
                if p.name() == mep.name():
                    raise RuntimeError(f'A sync process is already running (pid {pid})')
                else:
                    logger.warning('Found stale pid file, ignoring')
        with open(pidfile, 'w') as fp:
            fp.write(f'{me}\n')

    def run(self):
        self.sync_count = 0
        self._lock()
        try:
            logger.info('Syncing jobs...')
            for jf in REGISTER_STATEDIR.glob('*.job'):
                jobid = jf.stem
                with open(jf) as fp:
                    jobdir = Path(next(fp).rstrip('\n'))
                if not jobdir.is_dir():
                    logger.warning(f'Found nonexistent job directory {str(jobdir)} from {jobid}')
                    jf.unlink()
                    continue
                config = ConfigParser()
                config.read_dict({'DEFAULT': self.config})
                config.read(str(jobdir / 'ssm_hyak.ini'))
                config = config['wqm' if (jobdir / 'wqm_con.npt').is_file() else 'hydro']
                run_root = Path(config['run_root']) if 'run_root' in config else jobdir
                save_root = RemotePath.from_string(config['save_root']) if 'save_root' in config else None
                if save_root is None or not save_root.is_remote:
                    logger.info(f'Job directory {str(jobdir)} from {jobid} is not remote, ignoring')
                    jf.unlink()
                    continue
                run_tail = jobdir.relative_to(run_root)
                copy_dest = save_root / run_tail
                logger.info(f'Copying {jobid} in {str(jobdir)} to {str(copy_dest)}')
                self._call_process_with_logging(['ssh', copy_dest.host, 'mkdir', '-p', copy_dest.path])
                if self._job_running(jobid):
                    self._do_sync(jobdir, copy_dest)
                else:
                    logger.debug('(Job is completed, final sync)')
                    self._do_sync(jobdir, copy_dest, final=True)
                    jf.unlink()
            logger.info(f'Check complete, {self.sync_count} jobs synced')
        except Exception as e:
            raise e
        finally:
            self._lock(unlock=True)

def main():
    parser = ArgumentParser('SSM job management for Hyak')
    parser.add_argument("-v", "--verbose", action="store_true",
            help="Increase output")
    subparsers = parser.add_subparsers()
    parser_hydro = subparsers.add_parser('hydro', description='Start hydro job')
    parser_hydro.set_defaults(cls=HyakSetupHelper, group='hydro')
    parser_hydro.add_argument('-t', '--testing', action='store_true',
                              help='Test mode, stage but do not submit the job')
    parser_wqm = subparsers.add_parser('wqm', description='Start WQM job')
    parser_wqm.add_argument('-t', '--testing', action='store_true',
                            help='Test mode, stage but do not submit the job')
    parser_wqm.set_defaults(cls=HyakSetupHelper, group='wqm')
    parser_sync = subparsers.add_parser('sync', description='Perform remote sync')
    parser_sync.set_defaults(cls=SyncHelper, group='DEFAULT')

    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    config = ConfigParser()
    files = [f"{os.environ['HOME']}/.config/ssm_hyak/ssm_hyak.ini",'ssm_hyak.ini']
    config.read(files)
    helper = args.cls(args.group, **config[args.group])
    if 'testing' in args and args.testing:
        helper.test = True
    helper.run()

if __name__ == '__main__':
    main()
