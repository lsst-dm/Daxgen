import unittest
import networkx as nx
import os
import tempfile
from ..daxgen import Daxgen


class TestDaxgen(unittest.TestCase):

    def setUp(self):
        self.empty = Daxgen()

        g = nx.DiGraph(name='valid')
        g.add_node("0", lfn='input')
        g.add_node("1", name='task', args='--opt val arg')
        g.add_node("2", lfn='output')
        g.add_edges_from([("0", "1"), ("1", "2")])
        self.valid = Daxgen(g)

        json_data = """{
    "graph" : {"name" : "valid"},
    "nodes" : [
        {"id" : "0", "lfn" : "input"},
        {"id" : "1", "name" : "task", "args" : "--opt val arg"},
        {"id" : "2", "lfn" : "output"}
    ],
    "links" : [
        {"source" : "0", "target" : "1"},
        {"source" : "1", "target" : "2"}
    ]
}
"""
        self.json_fd, self.json_path = tempfile.mkstemp(suffix='.json')
        os.write(self.json_fd, json_data)
        os.close(self.json_fd)

        graphml_data = """<?xml version='1.0' encoding='utf-8'?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns
http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">
  <key attr.name="name" attr.type="string" for="node" id="d3" />
  <key attr.name="args" attr.type="string" for="node" id="d2" />
  <key attr.name="lfn" attr.type="string" for="node" id="d1" />
  <key attr.name="name" attr.type="string" for="graph" id="d0" />
  <graph edgedefault="directed">
    <data key="d0">valid</data>
    <node id="0">
      <data key="d1">input</data>
    </node>
    <node id="1">
      <data key="d2">--opt val arg</data>
      <data key="d3">task</data>
    </node>
    <node id="2">
      <data key="d1">output</data>
    </node>
    <edge source="0" target="1" />
    <edge source="1" target="2" />
  </graph>
</graphml>
"""
        self.graphml_fd, self.graphml_path = tempfile.mkstemp(suffix='.graphml')
        os.write(self.graphml_fd, graphml_data)
        os.close(self.graphml_fd)

    def tearDown(self):
        os.remove(self.json_path)
        os.remove(self.graphml_path)

    def test_init_empty(self):
        nodes, edges = self.empty.graph.nodes(), self.empty.graph.edges()
        self.assertEqual(len(nodes), 0)
        self.assertEqual(len(edges), 0)

    def test_init_valid(self):
        nodes, edges = self.valid.graph.nodes(), self.valid.graph.edges()
        self.assertEqual(len(nodes), 3)
        self.assertEqual(len(edges), 2)

    def test_label_invalid(self):
        g = self.valid.graph.copy()
        g.add_edge("0", "2")
        with self.assertRaises(ValueError):
            Daxgen(g)

    def test_label_valid(self):
        g = self.valid.graph
        attrs = tuple(g.node[u]['bipartite'] for u in ['0', '1', '2'])
        self.assertEqual(attrs, (1, 0, 1))

    @unittest.skip('requires development version of NetworkX (>1.11)')
    def test_read_json(self):
        gen = Daxgen()
        gen.read(self.json_path)
        g, h = gen.graph, self.valid.graph
        self.assertEqual(sorted(g.nodes()), sorted(h.nodes()))
        self.assertEqual(sorted(g.edges()), sorted(h.edges()))
        self.assertDictContainsSubset(h.graph, g.graph)
        for u, v in zip(sorted(g.nodes()), sorted(h.nodes())):
            self.assertEqual(g.node[u], h.node[v])

    def test_read_graphml(self):
        gen = Daxgen()
        gen.read(self.graphml_path)
        g, h = gen.graph, self.valid.graph
        self.assertEqual(sorted(g.nodes()), sorted(h.nodes()))
        self.assertEqual(sorted(g.edges()), sorted(h.edges()))
        self.assertDictContainsSubset(h.graph, g.graph)
        for u, v in zip(sorted(g.nodes()), sorted(h.nodes())):
            self.assertEqual(g.node[u], h.node[v])

    def test_read_unsupported(self):
        with self.assertRaises(ValueError):
            self.empty.read('workflow.xml')

    def test_write(self):
        pass


if __name__ == '__main__':
    unittest.main()
