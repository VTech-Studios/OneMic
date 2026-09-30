from onemic.domain.graph import Graph, Node, Port
from onemic.domain.sources import AudioSource, SourceKind, available_sources

OUT = (Port(1, "out"),)


def node(name: str, media_class: str, outputs: tuple[Port, ...] = OUT, description: str = "") -> Node:
    return Node(len(name), name, description or name, media_class, outputs=outputs)


def test_sources_are_grouped_by_kind_and_sorted_by_description() -> None:
    graph = Graph(
        nodes=(
            node("reaper", "Stream/Output/Audio", description="REAPER"),
            node("speakers", "Audio/Sink", description="Speakers"),
            node("mic2", "Audio/Source", description="Scarlett Mic 2"),
            node("cam", "Audio/Source", description="Link 2 mic"),
        )
    )

    assert available_sources(graph) == [
        AudioSource("cam", "Link 2 mic", SourceKind.MICROPHONE),
        AudioSource("mic2", "Scarlett Mic 2", SourceKind.MICROPHONE),
        AudioSource("reaper", "REAPER", SourceKind.APPLICATION),
        AudioSource("speakers", "Speakers", SourceKind.PLAYBACK),
    ]


def test_plumbing_own_nodes_and_silent_nodes_are_not_offered() -> None:
    graph = Graph(
        nodes=(
            node("splitter", "Stream/Input/Audio/Internal"),
            node("onemic.lesson", "Audio/Source/Virtual"),
            node("browser", "Stream/Input/Audio"),
            node("no-ports", "Audio/Source", outputs=()),
            node("camera", "Video/Source"),
        )
    )

    assert available_sources(graph) == []
