from jube2.main import main
import os.path
import pickle
import time
import logging

logger = logging.getLogger("JUBERunner")


class JUBERunner(object):
    """
    JUBERunner is a class that takes care of handling the interaction with
    JUBE and generating the right files in order to specify the JUBE runs
    with the parameters defined by the optimzier. This class consists of
    helper tools to generate JUBE configuration files as well as routines
    to interact with JUBE and gather the results to pass them back to
    the environment.
    """

    def __init__(self, trajectory):
        """
        Initializes the JUBERunner using the parameters found inside the
        trajectory in the param dictionary called JUBE_params.

        :param trajectory: A trajectory object holding the parameters to
                           use in the initialization
        """
        self.trajectory = trajectory
        self.done = False
        if 'JUBE_params' not in self.trajectory.par.keys():
            raise Exception("JUBE parameters not found in trajectory")
        else:
            args = self.trajectory.par["JUBE_params"].params

        self.generation = 0

        self._prefix = args.get('fileprefix', "")
        self.jube_config = {
            'submit_cmd': args.get('submit_cmd', ""),
            'job_file': args.get('job_file', ""),
            'nodes': args.get('nodes', ""),
            'walltime': args.get('walltime', ""),
            'ppn': args.get('ppn', ""),
            'ready_file': args.get('ready_file', ""),
            'mail_mode': args.get('mail_mode', ""),
            'mail_address': args.get('mail_address', ""),
            'err_file': args.get('err_file', "error.out"),
            'out_file': args.get('out_file', "jout.out"),
            'tasks_per_job': args.get('tasks_per_job', "1"),
            'cpu_pp': args.get('cpu_pp', "1"),
        }
        self.scheduler = "None"
        if 'scheduler' in args.keys():
            self.scheduler = args.get('scheduler'),

        self.executor = args['exec']
        self.filename = ""
        self.path = args['work_path']
        self.paths = args['paths_obj']
        # Create directories for workspace
        subdirs = ['jube_xml', 'run_files', 'ready_files',
                   'trajectories', 'results', 'work']
        self.work_paths = {sdir: os.path.join(self.path, sdir)
                           for sdir in subdirs}

        os.makedirs(self.path, exist_ok=True)

        for d in self.work_paths:
            os.makedirs(self.work_paths[d], exist_ok=True)

        self.zeepath = os.path.join(self.path, "optimizee.bin")

    def write_pop_for_jube(self, trajectory, generation):
        """
        Writes an XML file which contains the parameters for JUBE
        :param trajectory: A trajectory object holding the parameters to
                           generate the JUBE XML file for each generation
        :param generation: Id of the current generation
        """
        self.trajectory = trajectory
        eval_pop = trajectory.individuals[generation]
        self.generation = generation
        fname = "_jube_%s.xml" % str(self.generation)
        self.filename = os.path.join(self.work_paths['jube_xml'], fname)

        f = open(self.filename, 'w')
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<jube>\n'
                '  <benchmark name="l2l_inner_loop" outpath="bench_run">\n'
                '    <parameterset name="l2l_parameters">\n'
                '      <parameter name="index" type="int">')

        inds = [i.ind_idx for i in eval_pop]
        indices = ",".join(str(i) for i in inds)
        f.write(indices)

        sch = (
            '</parameter>\n'
            '    </parameterset>\n\n'
            '    <!-- benchmark configuration -->\n'
            '    <!-- Job configuration -->\n'
            '    <parameterset name="execute_set">\n'
            '    <parameter name="exec">{}</parameter>\n'
            '    <parameter name="tasks_per_job">{}</parameter>\n'
        )
        f.write(sch.format(self.executor, self.jube_config['tasks_per_job']))

        if self.scheduler != 'None':
            jobfname = '{}$index {}'.format(
                self.jube_config['job_file'], str(generation))
            readysch = os.path.join(self.work_paths['ready_files'],
                                    'ready_ + ${index} + ')
            readyname = '{}{}'.format(
                self.jube_config['ready_file'], str(self.generation))
            sch = (
                '    <parameter name="submit_cmd">{}</parameter>\n'
                '    <parameter name="job_file">{}</parameter>\n'
                '    <parameter name="nodes" type="int">{}</parameter>\n'
                '    <parameter name="walltime">{}</parameter>\n'
                '    <parameter name="ppn" type="int">{}</parameter>\n'
                '    <parameter name="ready_file_scheduler" mode="python"'
                ' type="string">{}</parameter>\n'
                '    <parameter name="ready_file">{}</parameter>\n'
                '    <parameter name="mail_mode">{}</parameter>\n'
                '    <parameter name="mail_address">{}</parameter>\n'
                '    <parameter name="err_file">{}</parameter>\n'
                '    <parameter name="out_file">{}</parameter>\n')
            p = (
                self.jube_config['submit_cmd'], jobfname,
                self.jube_config['nodes'], self.jube_config['walltime'],
                self.jube_config['ppn'], readysch, readyname,
                self.jube_config['mail_mode'],
                self.jube_config['mail_address'],
                self.jube_config['err_file'],
                self.jube_config['out_file']
            )
            f.write(sch.format(*p))

        f.write('    </parameterset>\n')

        if self.scheduler != 'None':
            # Write the specific scheduler file
            self.write_scheduler_file(f)

        wpath = os.path.join(
            self.work_paths['work'],
            'jobsystem_bench_${jube_benchmark_id}_${jube_wp_id}')
        sch = (
            '    <!-- Operation -->\n'
            '    <step name="submit" work_dir="{}" >\n'
            '    <use>l2l_parameters</use>\n'
            '    <use>execute_set</use>\n')
        f.write(sch.format(wpath))

        rpath = os.path.join(self.work_paths['ready_files'],
                             'ready_w_%s' % self.generation)
        if self.scheduler != 'None':
            sch = (
                '    <use>files,sub_job</use>\n'
                '    <do done_file="{}">$submit_cmd $job_file </do> '
                '<!-- shell command -->\n')
            sch = sch.format(rpath)
        else:
            sch = (
                '    <do done_file="{}">$exec $index {}'
                
                ' -n $tasks_per_job </do> <!-- shell command -->\n')
            sch = sch.format(rpath, str(self.generation))

        f.write(sch)
        f.write('    </step>   \n')

        # Close
        f.write('  </benchmark>\n')
        f.write('</jube>\n')
        f.close()
        logger.info(
            'Generated JUBE XML file for generation: ' + str(self.generation))

    def write_scheduler_file(self, f):
        """
        Writes the scheduler specific part of the JUBE XML specification file
        :param f: the handle to the XML configuration file
        """
        sgen = str(self.generation)
        sch = ('    <!-- Load jobfile -->\n'
               '    <fileset name="files">\n'
               '    <copy>${job_file}.in</copy>\n'
               '    </fileset>\n'
               '    <!-- Substitute jobfile -->\n'
               '    <substituteset name="sub_job">\n'
               '    <iofile in="${job_file}.in" out="$job_file" />\n'
               '    <sub source="#NODES#" dest="$nodes" />\n'
               '    <sub source="#PROCS_PER_NODE#" dest="$ppn" />\n'
               '    <sub source="#WALLTIME#" dest="$walltime" />\n'
               '    <sub source="#ERROR_FILEPATH#" dest="$err_file" />\n'
               '    <sub source="#OUT_FILEPATH#" dest="$out_file" />\n'
               '    <sub source="#MAIL_ADDRESS#" dest="$mail_address" />\n'
               '    <sub source="#MAIL_MODE#" dest="$mail_mode" />\n'
               '    <sub source="#EXEC#" '
               'dest="$exec $index {} -n $tasks_per_job"/>\n'
               '    <sub source="#READY#" dest="$ready_file{}" />\n'
               '    </substituteset> \n')
        f.write(sch.format(sgen, sgen))

    def collect_results_from_run(self, generation, individuals):
        """
        Collects the results generated by each individual in the generation.
        Results are, for the moment, stored in individual binary files.
        :param generation: generation id
        :param individuals: list of individuals which were executed in this
                            generation
        :return results: a list containing objects produced as results of
                         the execution of each individual
        """
        results = []
        for ind in individuals:
            indfname = "results_%s_%s.bin" % (ind.ind_idx, generation)
            indpath = os.path.join(self.work_paths["results"], indfname)
            with open(indpath, "rb") as handle:
                results.append((ind.ind_idx, pickle.load(handle)))

        return results

    def run(self, trajectory, generation):
        """
        Takes care of running the generation by preparing the JUBE
        configuration files and, waiting for the execution by JUBE and
        gathering the results. This is the main function of the JUBE_runner
        :param trajectory: trajectory object storing individual parameters
                           for each generation
        :param generation: id of the generation
        :return results: a list containing objects produced as results of
                         the execution of each individual
        """
        args = ["run", self.filename]
        self.done = False
        ready_files = []
        path_ready = os.path.join(self.work_paths["ready_files"],
                                  "ready_%d_" % generation)
        self.prepare_run_file(path_ready)

        # Dump all trajectories for each optimizee run in the generation
        for ind in self.trajectory.individuals[generation]:
            trajectory.individual = ind
            trajfname = "trajectory_%s_%s.bin" % (ind.ind_idx, generation)
            trajpath = os.path.join(self.work_paths["trajectories"], trajfname)
            with open(trajpath, "wb") as handle:
                pickle.dump(trajectory, handle, pickle.HIGHEST_PROTOCOL)
            ready_files.append(path_ready + str(ind.ind_idx))

        # Call the main function from JUBE
        logger.info("JUBE running generation: " + str(self.generation))
        main(args)

        # Wait for ready files to be written
        while not self.is_done(ready_files):
            time.sleep(10)

        # Touch done generation
        logger.info("JUBE finished generation: " + str(self.generation))
        fname = "ready_w_%s" % generation
        f = open(os.path.join(self.work_paths["ready_files"], fname), "w")
        f.close()

        self.done = True
        results = self.collect_results_from_run(
            generation, self.trajectory.individuals[generation])
        return results

    @staticmethod
    def is_done(files):
        """
        Identifies if all files marking the end of the execution of
        individuals in a generation are present or not.
        :param files: list of ready files to check
        :return true if all files are present, false otherwise
        """
        done = True
        for f in files:
            if not os.path.isfile(f):  # self.scheduler_config['ready_file']
                done = False
        return done

    def prepare_run_file(self, path_ready):
        """
        Writes a python run file which takes care of loading the optimizee
        from a binary file, the trajectory object of each individual. Then
        executes the 'simulate' function of the optimizee using the trajectory
        and writes the results in a binary file.
        :param path_ready: path to store the ready files
        :return true if all files are present, false otherwise
        """
        trajpath = os.path.join(
            self.work_paths["trajectories"],
            'trajectory_" + str(idx) + "_" + str(iteration) + ".bin')
        respath = os.path.join(
            self.work_paths['results'],
            'results_" + str(idx) + "_" + str(iteration) + ".bin')
        zee_path = os.path.join(
            self.work_paths["run_files"], "run_optimizee.py")
        with open(zee_path, "w") as f:
            zstr = (
                'import pickle\n'
                'import sys\n'
                'idx = sys.argv[1]\n'
                'iteration = sys.argv[2]\n'
                'handle_trajectory = open("{}", "rb")\n'
                'trajectory = pickle.load(handle_trajectory)\n'
                'handle_trajectory.close()\n'
                'handle_optimizee = open("{}", "rb")\n'
                'optimizee = pickle.load(handle_optimizee)\n'
                'handle_optimizee.close()\n\n'
                'res = optimizee.simulate(trajectory)\n\n'
                'handle_res = open("{}", "wb")\n' +
                'pickle.dump(res, handle_res, pickle.HIGHEST_PROTOCOL)\n' +
                'handle_res.close()\n\n' +
                'handle_res = open("{}" + str(idx), "wb")\n' +
                'handle_res.close()')
            f.write(
                zstr.format(trajpath, self.zeepath, respath, path_ready)
            )


def prepare_optimizee(optimizee, path):
    """
    Helper function used to dump the optimizee it a binary file for later
    loading during run.
    :param optimizee: the optimizee to dump into a binary file
    :param path: The path to store the optimizee.
    """
    # Serialize optimizee object so each process can run simulate on it
    # independently on the CNs
    fname = os.path.join(path, "optimizee.bin")
    with open(fname, "wb") as f:
        pickle.dump(optimizee, f)

    logger.info("Serialized optimizee writen to path: " + fname)
