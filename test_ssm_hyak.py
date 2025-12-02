#!/usr/bin/env python3

import unittest
import os
import tempfile
from pathlib import Path

import ssm_hyak

class RemotePathTest(unittest.TestCase):
    def test_remotes(self):
        # Create absolute path from single string
        p = ssm_hyak.RemotePath.from_string('hostname:/path/to/file')
        self.assertEqual(str(p), 'hostname:/path/to/file')
        self.assertEqual(str(p.parent), 'hostname:/path/to')
        self.assertEqual(p.host, 'hostname')
        self.assertEqual(str(p / 'subdir'), 'hostname:/path/to/file/subdir')

    def test_leaks(self):
        p1 = ssm_hyak.RemotePath.from_string('host1:/path1')
        p2 = ssm_hyak.RemotePath.from_string('host2:/path2')
        self.assertEqual(p1.host, 'host1')
        self.assertEqual(p2.host, 'host2')

class SsmHyakTest(unittest.TestCase):
    def setUp(self):
        self.wd = os.getcwd()
        self.path = os.environ['PATH']

    def tearDown(self):
        os.chdir(self.wd)
        os.environ['PATH'] = self.path

    def test_get_run_param(self):
        # Single string parameter
        self.assertEqual('habitability', ssm_hyak.get_run_param('testdata/types.dat','STR1'))
        # Reading from file with comments
        self.assertEqual('T', ssm_hyak.get_run_param('testdata/comments.dat','VAL'))
        # Read multi-line parameter
        v = ssm_hyak.get_run_param('testdata/types.dat', 'CVEC')
        self.assertEqual(88, len(v))
        self.assertEqual('ermines', v[:7])
        self.assertEqual('rephrased', v[-9:])
        # Multiple parameters at once
        self.assertEqual(['habitability','regurgitates'],
                         ssm_hyak.get_run_param('testdata/types.dat',['STR1','STR2']))

    def test_stage_remote(self):
        # Set up the test fixture
        with tempfile.TemporaryDirectory() as d:
            tp = Path(d)
            run_root = tp / 'run_root'
            os.mkdir(run_root)
            instance = run_root / 'instance'
            os.mkdir(instance)
            os.chdir(instance)
            outdir = instance / 'output'
            os.mkdir(outdir)

            scrub = tp / 'scrub'
            os.mkdir(scrub)

            # Run the method
            h = ssm_hyak.HyakSetupHelper('nomethod', 'nocase', 'nobin',
                               run_root=run_root,
                               save_root='remote:/foo/bar',
                               scrub_dir_out=scrub)
            p = h._stage('output', 'test')

            # Tests
            self.assertEqual(tp / 'scrub', p.parent.parent)
            self.assertTrue((p / 'output').is_symlink())
            # hash is for remote:/foo/bar/instance/output
            self.assertEqual(os.fspath(tp / 'scrub' / os.environ['USER'] /
                                        'test' / 'c686c1ff2a6e7ebb1268da0d293cecbe'),
                              os.readlink(p / 'output'))

    def _hydro_fixture(self, tempdir):
        run_root = tempdir / 'run_root'
        os.mkdir(run_root)
        instance = run_root / 'instance'
        os.mkdir(instance)
        os.chdir(instance)
        outdir = instance / 'output'
        os.mkdir(outdir)
        inpdir = instance / 'input'
        os.mkdir(inpdir)
        with open(inpdir / 'input_file.txt', 'w') as inpf:
            inpf.write('test input file\n')
        with open(instance / 'case_run.dat', 'w') as runf:
            runf.write('INPDIR = input\n')
            runf.write('OUTDIR = output\n')
        with open(instance / 'run_fvcom.stub', 'w') as stubf:
            stubf.write('# Comment\n')
            stubf.write('SBATCH --job-name=test\n')

        scrub = tempdir / 'scrub'
        os.mkdir(scrub)

        return {
                'run_root': run_root,
                'scrub': scrub
        }

    def test_setup_hydro(self):
        # Set up the test fixture
        with tempfile.TemporaryDirectory() as d:
            tp = Path(d)
            paths = self._hydro_fixture(tp)
            run_root = paths['run_root']
            scrub = paths['scrub']

            # To allow the sbatch invocation to work, we need to make a dummy
            # binary that's in the PATH
            pathent = tp / 'bin'
            os.mkdir(pathent)
            os.symlink('/bin/true', pathent / 'sbatch')
            oldpath = os.environ['PATH']
            os.environ['PATH'] = os.fspath(pathent) + ':' + oldpath
            save_root = 'remote:/foo/bar'

            # Run the method
            h = ssm_hyak.HyakSetupHelper('hydro', 'case', 'runme',
                                     run_root=os.fspath(run_root),
                                     save_root=save_root,
                                     scrub_dir=os.fspath(scrub),
                                     scrub_dir_out=os.fspath(scrub))
            p = h.run()

            # reset environment
            os.environ['PATH'] = oldpath

            # Tests
            # Staging
            self.assertEqual(tp / 'scrub', p.parent.parent)
            self.assertTrue((p / 'output').is_symlink())
            # hash is for remote:/foo/bar/instance/output
            output_path_exp = Path(scrub / os.environ['USER'] / 'hyd_results' /
                'c686c1ff2a6e7ebb1268da0d293cecbe')

            self.assertEqual(os.fspath(output_path_exp), os.readlink(p / 'output'))

            # Model setup
            self.assertTrue((p / 'input' / 'input_file.txt').is_file())
            self.assertTrue((p / 'case_run.dat').is_file())
            self.assertTrue((p / 'run_fvcom.sh').is_file())

            # Now, run get_hyd_result_dest on the remote path and see if it
            # generates the same local path
            hyd_result_src = ssm_hyak.RemotePath.from_string(save_root) / 'instance' / 'output' / 'netcdf'
            hyd_result_dest = h._get_hyd_result_dest(hyd_result_src)
            self.assertEqual(output_path_exp / 'netcdf', hyd_result_dest)

    def test_setup_hydro_test(self):
        """Test for test-mode hydro setup"""
        with tempfile.TemporaryDirectory() as d:
            tp = Path(d)
            paths = self._hydro_fixture(tp)
            run_root = paths['run_root']
            scrub = paths['scrub']
            save_root = 'remote:/some/path'

            # Run the method
            h = ssm_hyak.HyakSetupHelper('hydro', 'case', 'runme',
                                     run_root=os.fspath(run_root),
                                     save_root=save_root,
                                     scrub_dir_out=os.fspath(scrub))
            h.test = True
            p = h.run()

            # Just a few basic tests, the real check is if the last command
            # did not raise a CalledProcessError
            self.assertEqual(tp / 'scrub', p.parent.parent)
            self.assertTrue((p / 'output').is_symlink())

    # TODO test case for setup_wqm

if __name__ == '__main__':
    unittest.main()
