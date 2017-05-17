import argparse
import itertools
import networkx as nx
import six
import xmltodict


def create_parser():
    """Create a parser for the command line arguments.

    Returns
    -------
    `argparse.ArgumentParser`
        Namespace populated with attributes representing the arguments.
    """
    p = argparse.ArgumentParser()
    p.add_argument('filename', help='File with DAX workflow')
    p.add_argument('-o', '--output', help='Output filename',
                   default='plan.gml')
    return p


def parse_dax(plan):
    """Convert Pegasus DAX to generic graph representation.

    Parameters
    ----------
    plan : `dict`
        Representation of the workflow.

    Returns
    -------
    `networkx.DiGraph`
        A graph representing the workflow.
    """
    # Initialize node id generator.
    id_ = node_id()

    label = plan['adag'].get('@name')
    dag = nx.DiGraph() if label is None else nx.DiGraph(name=label)

    # Add files to the graph.
    files = plan['adag']['file']
    for entry in files:
        v = id_()
        attrs = {'lfn': entry['@name']}

        pfns = entry.get('pfn')
        if pfns is not None:
            attrs['urls'] = ','.join([pfn['@url'] for pfn in pfns])
            attrs['sites'] = ','.join([pfn.get('@site', 'local')
                                       for pfn in pfns])

        dag.add_node(v, **attrs)

    # Create a map between logical file names and node ids.
    mapping = {dag.node[v]['lfn']: v for v in dag}

    # Add jobs to the graph.
    jobs = plan['adag']['job']
    for entry in jobs:
        v = id_()
        attrs = {'name': entry['@name']}

        argv = entry.get('argument')
        if argv is not None:
            attrs['args'] = stringify(argv)

        dag.add_node(v, **attrs)

        # Add job's data dependencies.
        resources = entry.get('uses')
        if resources is not None:
            inputs = [entry['@name'] for entry in resources
                      if entry['@link'] == 'input']
            outputs = [entry['@name'] for entry in resources
                       if entry['@link'] == 'output']
            dag.add_edges_from([(mapping[lfn], v) for lfn in inputs])
            dag.add_edges_from([(v, mapping[lfn]) for lfn in outputs])

        # Flag files to which standard streams are redirected.
        streams = {'stderr': 2, 'stdout': 1}
        for kind, code in streams.items():
            stream = entry.get(kind)
            if stream is not None:
                u = mapping[stream['@name']]
                attrs = dag.node[u]
                try:
                    attrs['streams'] |= code
                except KeyError:
                    attrs['streams'] = code
                dag.add_edge(v, u)

    return dag


def stringify(arguments):
    """Ensure proper format of job arguments.

    If arguments of a DAX job are represented by a string, only superfluous
    spaces are removed. If DAX jobs contains Pegasus file objects, they are
    replaced by their logical file names.

    Parameters
    ----------
    arguments : `str` or `dict`
        A string or a dictionary with job arguments

    Returns
    -------
    `str`
        A string representing job's space-separated arguments.
    """
    if not isinstance(arguments, six.string_types):
        files = [name for _, name in arguments['file'].items()]

        # Find out job options which require a file as an argument and
        # insert required file after each of them.
        #
        # This approach only works if ordering of files corresponds to
        # ordering of options withing the string representing arguemnt vector.
        text = arguments['#text'].split()
        indices = [text.index(opt) for opt in {'-C'}]
        for idx, pos in enumerate(sorted(indices)):
            text.insert(pos + 1, files[idx])
        return ' '.join(text)
    return ' '.join(arguments.split())


def node_id():
    """Initialize node id generator.

    Node id can be any hashable object (except None).  Current implementation
    uses consecutive integers.

    Returns
    -------
    count
        Node id generator
    """
    c = itertools.count()

    def count():
        return next(c)
    return count


if __name__ == '__main__':
    parser = create_parser()
    args = parser.parse_args()
    with open(args.filename) as f:
        workflow = xmltodict.parse(f.read())
    graph = parse_dax(workflow)
    nx.write_graphml(graph, args.output)
