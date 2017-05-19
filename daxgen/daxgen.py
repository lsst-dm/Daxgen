import networkx as nx
from Pegasus.DAX3 import ADAG, File, Job, Link, PFN


# Set of mandatory attributes unique to file nodes. Do not have to be
# exhaustive.
_FILE_ATTRS = {'lfn'}


class Daxgen(object):
    """Generator of Pegasus DAXes.

    Parameters
    ----------
    graph : `networkx.DiGraph`, optional
        Graph representation of the workflow, defaults to an empty graph.
    """

    def __init__(self, graph=None):
        self.graph = graph.copy() if graph is not None else nx.DiGraph()
        self._color()

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
            'graphml': nx.read_graphml
        }
        ext = filename.split('.')[-1]
        try:
            self.graph = methods[ext.lower()](filename)
        except KeyError:
            raise ValueError('Format \'%s\' is not supported yet.' % ext)
        self._color()

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
        self._color()
        files = set([v for v in self.graph
                     if self.graph.node[v]['bipartite'] == 1])
        tasks = set([v for v in self.graph
                     if self.graph.node[v]['bipartite'] == 0])

        dax = ADAG(name)

        # Add files to DAX-level replica catalog.
        catalog = {}
        for v in files:
            attrs = self.graph.node[v]
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
        for v in tasks:
            attrs = self.graph.node[v]
            job = Job(name=attrs['name'], id=v)

            # Add job command line arguments replacing any file name with
            # respective Pegasus file object.
            args = attrs['args'].split()
            lfns = list(set(catalog) & set(args))
            if lfns:
                indices = [args.index(lfn) for lfn in lfns]
                for idx, lfn in zip(indices, lfns):
                    args[idx] = catalog[lfn]
            job.addArguments(*args)

            # Specify job's inputs.
            vertices = [u for u in self.graph.predecessors(v)]
            for u in vertices:
                attrs = self.graph.node[u]
                f = catalog[attrs['lfn']]
                job.uses(f, link=Link.INPUT)

            # Specify job's outputs
            vertices = [u for u in self.graph.successors(v)]
            for u in vertices:
                attrs = self.graph.node[u]
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
        for v in tasks:
            parents = set()
            for u in self.graph.predecessors(v):
                parents.update(self.graph.predecessors(u))
            for u in parents:
                dax.depends(parent=dax.getJob(u), child=dax.getJob(v))

        # Finally, write down the workflow in DAX format.
        with open(filename, 'w') as f:
            dax.writeXML(f)

    def _color(self):
        """Differentiate files from tasks.

        The function adds an additional attribute `bipartite` to each node in
        the graph to easily keep track of which set a node belongs to.  By
        convention, 1 will be used to denote files, and 0 to denote tasks.

        Raises
        ------
        `ValueError`
            If the graph is not bipartite.
        """
        if self.graph:
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
            files, tasks = (U, V) if node_attrs >= _FILE_ATTRS else (V, U)

            # Add the new attribute which allow to quickly differentiate
            # vertices representing files from those representing tasks.
            for v in self.graph:
                self.graph.node[v]['bipartite'] = 1 if v in files else 0


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
