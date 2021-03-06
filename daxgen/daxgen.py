import inspect
import networkx as nx
import os
from Pegasus.DAX3 import ADAG, File, Job, Link, PFN
from .cowriter import Cowriter


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
                              if self.graph.node[node_id]['bipartite'] == 1])
            self.tasks = set([node_id for node_id in self.graph
                              if self.graph.node[node_id]['bipartite'] == 0])

        dirname = os.path.dirname(inspect.getfile(Cowriter))
        location = os.path.join(dirname, 'templates')
        self.writer = Cowriter('executor', path=location)

    def read(self, filename):
        """Read a persisted workflow.

        Currently, the following formats are recognized:

        - GraphML,
        - JSON node-link,
        - GEXF.

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
            'graphml': nx.read_graphml
        }
        ext = filename.split('.')[-1]
        try:
            self.graph = methods[ext.lower()](filename)
        except KeyError:
            raise ValueError("Format '{0}' is not supported yet.".format(ext))
        if self.graph:
            self._label()
            self.files = set([v for v in self.graph
                              if self.graph.node[v]['bipartite'] == 1])
            self.tasks = set([v for v in self.graph
                              if self.graph.node[v]['bipartite'] == 0])

    def write(self, filename, name='dax'):
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
        """
        dax = ADAG(name)

        # Add files to DAX-level replica catalog.
        catalog = {}
        for file_id in self.files:
            attrs = self.graph.node[file_id]
            f = File(attrs['lfn'])

            # Add physical file names, if any.
            urls = attrs.get('urls')
            if urls is not None:
                sites = attrs.get('sites')
                if sites is None:
                    sites = ','.join(len(urls) * ['local'])
                for url, site in zip(urls.split(','), sites.split(',')):
                    f.addPFN(PFN(url, site))

            catalog[attrs['lfn']] = f
            dax.addFile(f)

        # Add jobs to the DAX.
        for task_id in self.tasks:
            attrs = self.graph.node[task_id]
            job = Job(name=attrs['name'], id=task_id)

            # Add job command line arguments replacing any file name with
            # respective Pegasus file object.
            args = attrs.get('args')
            if args is not None and args:
                args = args.split()
                lfns = list(set(catalog) & set(args))
                if lfns:
                    indices = [args.index(lfn) for lfn in lfns]
                    for idx, lfn in zip(indices, lfns):
                        args[idx] = catalog[lfn]
                job.addArguments(*args)

            # Specify job's inputs.
            inputs = [file_id for file_id in self.graph.predecessors(task_id)]
            for file_id in inputs:
                attrs = self.graph.node[file_id]
                f = catalog[attrs['lfn']]
                job.uses(f, link=Link.INPUT)

            # Specify job's outputs
            outputs = [file_id for file_id in self.graph.successors(task_id)]
            for file_id in outputs:
                attrs = self.graph.node[file_id]
                f = catalog[attrs['lfn']]
                job.uses(f, link=Link.OUTPUT)

                streams = attrs.get('streams')
                if streams is not None:
                    if streams & 1 != 0:
                        job.setStdout(f)
                    if streams & 2 != 0:
                        job.setStderr(f)

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

    def wrap(self, wrapper='execute', args=None):
        """Use a wrapper (i.e. Executor) to execute tasks.
        """

        # At the moment nodes ids are strings representing consecutive
        # integers.  As we will be adding new nodes soon, we have to find out
        # what is the last value that was used.
        #
        # FIXME: This clearly indicates that a different approach for generating
        # node ids would be beneficial, prehaps based on node attritubtes.
        idx = max(int(s) for s in self.graph)

        src = self._find_root()
        dest = src

        for v in self.tasks:
            attrs = self.graph.node[v]
            name, args = attrs['name'], attrs['args']

            # Generate node id.
            idx += 1
            u = str(idx)

            config = self.writer.write(name, args, src, dest)
            file_attrs = {
                'lfn': config,
                'urls': os.path.abspath(config),
                'sites': 'local'
            }
            self.graph.add_node(u, **file_attrs)
            self.graph.add_edge(u, v)
            self.files.add(u)

            attrs['name'], attrs['args'] = wrapper, config

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
            self.graph.node[v]['bipartite'] = 1 if v in files else 0

    def _find_root(self):
        """Find root of the dataset repository.
        """
        lfns = [self.graph.node[file_id]['lfn'] for file_id in self.files]
        for lfn in lfns:
            if '_mapper' in lfn:
                break
        return os.path.dirname(lfn)


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
