import pickle
import networkx as nx
from Pegasus.DAX3 import ADAG, File, Job, Link, PFN


class Daxgen(object):
    """Generator of Pegasus DAXes.

    Parameters
    ----------
    graph : `networkx.DiGraph`, optional
        Graph representation of the workflow, defaults to an empty graph.
    """

    def __init__(self, graph=None):
        self.graph = graph.copy() if graph is not None else nx.DiGraph()
        if self.graph:
            self._label()
            self.files = set([node_id for node_id in self.graph
                              if self.graph.node[node_id]['node_type'] == 0])
            self.tasks = set([node_id for node_id in self.graph
                              if self.graph.node[node_id]['node_type'] == 1])
        self.catalog = {}

    def read(self, filename):
        """Read a persisted workflow.

        Currently, the following formats are recognized:

        - GraphML,
        - JSON node-link,
        - GEXF,
        - Python pickle.

        Parameters
        ----------
        filename : `str`
            File with the persisted workflow.

        Raises
        ------
        `ValueError`
            If graph representing the workflow is persisted in an unsupported
            format or is not bipartite.
        """
        methods = {
            'json': read_json,
            'gexf': nx.read_gexf,
            'gxf': nx.read_gexf,
            'gml': nx.read_graphml,
            'graphml': nx.read_graphml,
            'pickle': read_pickle
        }
        ext = filename.split('.')[-1]
        try:
            self.graph = methods[ext.lower()](filename)
        except KeyError:
            raise ValueError("Format '{0}' is not supported yet.".format(ext))
        if self.graph:
            self._label()
            self.files = set([v for v in self.graph
                              if self.graph.node[v]['node_type'] == 0])
            self.tasks = set([v for v in self.graph
                              if self.graph.node[v]['node_type'] == 1])

    def write_dax(self, filename='workflow.dax', name='workflow'):
        """Generate Pegasus abstract workflow (DAX).

        Parameters
        ----------
        filename : `str`
            File to write the DAX to.
        name : `str`, optional
            Name of the DAX.

        Returns
        -------
        `Pegasus.ADAG`
            Abstract workflow used by Pegasus' planner.

        Raises
        ------
        `ValueError`
            If either task or file node is missing mandatory attribute.
        """
        dax = ADAG(name)

        # Process file nodes.
        for file_id in self.files:
            attrs = self.graph.node[file_id]
            try:
                name = attrs['lfn']
            except KeyError:
                msg = 'Mandatory attribute "%s" is missing.'
                raise AttributeError(msg.format('lfn'))
            file_ = File(name)

            # Add physical file names, if any.
            urls = attrs.get('pfn')
            if urls is not None:
                urls = urls.split(',')
                sites = attrs.get('sites')
                if sites is None:
                    sites = len(urls) * ['condorpool']
                for url, site in zip(urls, sites):
                    file_.addPFN(PFN(url, site))

            self.catalog[attrs['lfn']] = file_

        # Add jobs to the DAX.
        counter = {}
        for task_id in self.tasks:
            attrs = self.graph.node[task_id]
            try:
                name = attrs['exec_name']
            except KeyError:
                msg = 'Mandatory attribute "%s" is missing.'
                raise AttributeError(msg.format('exec_name'))
            counter.setdefault(name, 0)
            counter[name] += 1
            label = '{name}_{count}'.format(name=name, count=counter[name])
            job = Job(name, id=label)

            # Add job command line arguments replacing any file name with
            # respective Pegasus file object.
            args = attrs.get('exec_args', [])
            if args:
                args = args.split()
                lfns = list(set(self.catalog) & set(args))
                if lfns:
                    indices = [args.index(lfn) for lfn in lfns]
                    for idx, lfn in zip(indices, lfns):
                        args[idx] = self.catalog[lfn]
                job.addArguments(*args)

            # Specify job's inputs.
            inputs = [file_id for file_id in self.graph.predecessors(task_id)]
            for file_id in inputs:
                attrs = self.graph.node[file_id]
                is_ignored = attrs.get('ignore', False)
                if not is_ignored:
                    file_ = self.catalog[attrs['lfn']]
                    job.uses(file_, link=Link.INPUT)

            # Specify job's outputs
            outputs = [file_id for file_id in self.graph.successors(task_id)]
            for file_id in outputs:
                attrs = self.graph.node[file_id]
                is_ignored = attrs.get('ignore', False)
                if not is_ignored:
                    file_ = self.catalog[attrs['lfn']]
                    job.uses(file_, link=Link.OUTPUT)

                    streams = attrs.get('streams')
                    if streams is not None:
                        if streams & 1 != 0:
                            job.setStdout(file_)
                        if streams & 2 != 0:
                            job.setStderr(file_)

            # Provide default files to store stderr and stdout, if not
            # specified explicitly.
            if job.stderr is None:
                file_ = File('{name}.out'.format(name=label))
                job.setStderr(file_)
            if job.stdout is None:
                file_ = File('{name}.err'.format(name=label))
                job.setStdout(file_)

            dax.addJob(job)

        # Add job dependencies to the DAX.
        for task_id in self.tasks:
            parents = set()
            for file_id in self.graph.predecessors(task_id):
                parents.update(self.graph.predecessors(file_id))
            for parent_id in parents:
                dax.depends(parent=dax.getJob(parent_id),
                            child=dax.getJob(task_id))

        # Finally, write down the workflow in DAX format.
        with open(filename, 'w') as f:
            dax.writeXML(f)

    def write_rc(self, name='rc.txt'):
        """Write replica catalog.

        Parameters
        ----------
        name : string, optional
            Name of the replica file.
        """
        files = [file_ for file_ in self.catalog.values() if file_.pfns]
        with open(name, 'w') as f:
            for file_ in files:
                lfn = file_.name
                for pfn in file_.pfns:
                    f.write(' '.join([lfn, pfn.url, pfn.site]) + '\n')

    def _label(self):
        """Differentiate files from tasks.

        The function adds an additional attribute `bipartite` to each node in
        the graph to easily keep track of which set a node belongs to.  By
        convention, 1 will be used to denote files, and 0 to denote tasks.

        Raises
        ------
        `ValueError`
            If the graph is not bipartite.
        """
        # Set of mandatory attributes unique to file nodes. Currently, these
        # are:
        # - lfn: logical file name.
        file_attrs = {'lfn'}

        try:
            nx.bipartite.color(self.graph)
        except nx.NetworkXError:
            raise ValueError("Graph is not bipartite.")

        U, V = nx.bipartite.sets(self.graph)

        # Select an arbitrary vertex from the set U and based on its
        # attributes decide if the set U represents files and respectively,
        # V represents tasks, or the other way round.
        v = next(iter(U))
        node_attrs = set(self.graph.node[v].keys())
        files, tasks = (U, V) if file_attrs.issubset(node_attrs) else (V, U)

        # Add the new attribute which allow to quickly differentiate
        # vertices representing files from those representing tasks.
        for v in self.graph:
            self.graph.node[v]['node_type'] = 0 if v in files else 1


def read_json(filename):
    """Read a workflow specified in JSON node-link format.

    Parameters
    ----------
    filename : `str`
        File with the persisted workflow.

    Returns
    -------
    `networkx.DiGraph`
        Graph representing the workflow.
    """
    import json
    from networkx.readwrite import json_graph

    with open(filename, 'r') as f:
        data = json.load(f)
    return json_graph.node_link_graph(data, directed=True)


def read_pickle(filename):
    """Read a workflow specified as a Python pickle file.

    Parameters
    ----------
    filename : `str`
        File with the persisted workflow.

    Returns
    -------
    `networkx.DiGraph`
        Graph representing the workflow.
    """
    import pickle

    with open(filename, 'rb') as f:
        data = pickle.load(f)
    return data
