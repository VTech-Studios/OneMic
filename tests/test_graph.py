from onemic.domain.graph import Graph, Link, Node, Port, pair_channels

MONO = (Port(1, "capture_MONO", "MONO"),)
STEREO_OUT = (Port(2, "out1"), Port(3, "out2"), Port(4, "out3"), Port(5, "out4"))
STEREO_IN = (Port(10, "input_FL", "FL"), Port(11, "input_FR", "FR"))


def test_a_mono_source_feeds_every_input() -> None:
    assert pair_channels(MONO, STEREO_IN) == {Link(1, 10), Link(1, 11)}


def test_channels_pair_in_order_and_extra_outputs_are_left_alone() -> None:
    assert pair_channels(STEREO_OUT, STEREO_IN) == {Link(2, 10), Link(3, 11)}


def test_nothing_is_linked_without_ports() -> None:
    assert pair_channels((), STEREO_IN) == frozenset()
    assert pair_channels(STEREO_OUT, ()) == frozenset()


def test_graph_finds_nodes_by_name() -> None:
    node = Node(7, "REAPER", "REAPER", "Stream/Output/Audio")
    graph = Graph(nodes=(node,))

    assert graph.node("REAPER") is node
    assert graph.node("missing") is None


def test_links_touching_includes_either_end() -> None:
    source = Node(1, "a", "a", "Audio/Source", outputs=MONO)
    sink = Node(2, "b", "b", "Audio/Sink", inputs=STEREO_IN)
    other = Link(98, 99)
    graph = Graph(nodes=(source, sink), links=frozenset({Link(1, 10), Link(1, 11), other}))

    assert graph.links_touching([source]) == {Link(1, 10), Link(1, 11)}
    assert graph.links_touching([sink]) == {Link(1, 10), Link(1, 11)}
