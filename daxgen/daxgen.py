import networkx as nx
from Pegasus.DAX3 import ADAG, File, Job, Link


# Set of attributes unique to file nodes. Do not have to be complete,
_FILE_ATTRS = {'lfn', 'pfns'}


class Daxgen(object):
    """Generator of Pegasus DAXes.

    Parameters
    ----------
    graph : `networkx.DiGraph`, optional
        Graph representation of the workflow, defaults to an empty graph.
    """

    def __init__(self, graph=None):
        self.graph = graph if graph is not None else nx.DiGraph()
        self._check_sanity()

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
        self._check_sanity()

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
            lfn, pfns = self.graph.node[v]['lfn'], self.graph.node[v]['pfns']
            f = File(lfn)
            for pfn, site in pfns:
                f.addPFN(pfn, site)
            catalog[lfn] = f
        for f in catalog.values():
            dax.addFile(f)

        # Add jobs to the DAX.
        for v in tasks:
            attrs = self.graph.node[v]
            job = Job(name=attrs['name'], id=v)
            job.addArguments(attrs['args'].split())

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

                stream = attrs.get('stream')
                if stream is not None:
                    stream = stream.lower()
                    if stream == 'stderr':
                        job.setStderr(f)
                    elif stream == 'stdout':
                        job.setStdout(f)
                    else:
                        # For now, ignore errors in stream specification. Log
                        # in the future.
                        pass
            dax.addJob(job)

        # Add job dependencies to the DAX.
        for v in tasks:
            inputs = set([u for u in self.graph.predeccessors(v)])
            parents = set([self.graph.predeccessors(u) for u in inputs])
            for u in parents:
                dax.depends(parent=dax.getJob(u), child=dax.getJob(v))

        # Finally, write down the workflow in DAX format.
        with open(filename, 'w') as f:
            dax.writeXML(f)

    def _color(self):
        """Differentiate files from tasks.

        To easily keep track of which set a node belongs to the function adds
        an additional attribute `bipartite` to each node in the graph. By
        convention, 1 will be used to denote files, and 0 to denote tasks.
        """
        U, V = nx.bipartite.sets(self.graph)

        # Select an arbitrary vertex from the set U and based on its attributes
        # decide if the set U represents files and respectively, V represents
        # tasks, or the other way round.
        v = next(iter(U))
        node_attrs = set(self.graph.node[v].keys())
        files, tasks = (U, V) if node_attrs >= _FILE_ATTRS else (V, U)

        # Add the new attribute which allow to quickly differentiate
        # vertices representing files from those representing tasks.
        for v in self.graph:
            self.graph.node[v]['bipartite'] = 1 if v in files else 0

    def _check_sanity(self):
        """Check if graph is bipartite.

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
